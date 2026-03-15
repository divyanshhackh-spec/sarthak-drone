import asyncio
import time
import math
import json
import socket
import threading
from queue import Queue
from gpiozero import Servo, LED
from picamera2 import Picamera2
import cv2
import numpy as np
import serial

class DroneState:
    def __init__(self):
        self.latitude = 0.0
        self.longitude = 0.0
        self.altitude = 0.0
        self.battery = 100.0
        self.mode = "IDLE"
        self.velocity = 0.0
        self.heading = 0.0
        self.target = None
        self.supply_loaded = True
        self.scan_active = False
        self.last_detection = None
        self.last_update = time.time()

class GPSReader:
    def __init__(self, port="/dev/ttyAMA0", baudrate=9600):
        self.serial = serial.Serial(port, baudrate, timeout=1)
        self.latitude = 0.0
        self.longitude = 0.0

    def parse(self, line):
        parts = line.split(',')
        if parts[0] == "$GPGGA":
            lat = parts[2]
            lat_dir = parts[3]
            lon = parts[4]
            lon_dir = parts[5]
            if lat and lon:
                lat_val = float(lat[:2]) + float(lat[2:]) / 60
                lon_val = float(lon[:3]) + float(lon[3:]) / 60
                if lat_dir == "S":
                    lat_val *= -1
                if lon_dir == "W":
                    lon_val *= -1
                self.latitude = lat_val
                self.longitude = lon_val

    def update(self):
        line = self.serial.readline().decode(errors="ignore").strip()
        if line.startswith("$GPGGA"):
            self.parse(line)

class MotorController:
    def __init__(self):
        self.speed = 0.0

    def set_speed(self, value):
        self.speed = max(0.0, min(1.0, value))

    def stop(self):
        self.speed = 0.0

class Navigation:
    def __init__(self, state):
        self.state = state

    def distance(self, lat1, lon1, lat2, lon2):
        r = 6371000
        p1 = math.radians(lat1)
        p2 = math.radians(lat2)
        dp = math.radians(lat2 - lat1)
        dl = math.radians(lon2 - lon1)
        a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        return r * c

    def bearing(self, lat1, lon1, lat2, lon2):
        p1 = math.radians(lat1)
        p2 = math.radians(lat2)
        dl = math.radians(lon2 - lon1)
        x = math.sin(dl) * math.cos(p2)
        y = math.cos(p1)*math.sin(p2) - math.sin(p1)*math.cos(p2)*math.cos(dl)
        br = math.degrees(math.atan2(x, y))
        return (br + 360) % 360

    def update_heading(self, target):
        if target:
            lat, lon = target
            self.state.heading = self.bearing(self.state.latitude, self.state.longitude, lat, lon)

class SupplySystem:
    def __init__(self, pin=17):
        self.servo = Servo(pin)
        self.locked = True

    def drop(self):
        self.servo.value = 1
        time.sleep(1)
        self.servo.value = -1
        self.locked = False

class TelemetryServer:
    def __init__(self, state, port=9000):
        self.state = state
        self.port = port
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.clients = []

    def start(self):
        self.socket.bind(("", self.port))
        self.socket.listen(5)
        threading.Thread(target=self.accept_loop, daemon=True).start()

    def accept_loop(self):
        while True:
            conn, addr = self.socket.accept()
            self.clients.append(conn)

    def broadcast(self):
        data = json.dumps(self.state.__dict__).encode()
        for c in self.clients[:]:
            try:
                c.sendall(data + b"\n")
            except:
                self.clients.remove(c)

class CameraScanner:
    def __init__(self, state):
        self.state = state
        self.camera = Picamera2()
        config = self.camera.create_preview_configuration(main={"size": (640,480)})
        self.camera.configure(config)
        self.camera.start()
        self.hog = cv2.HOGDescriptor()
        self.hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())

    def scan_frame(self):
        frame = self.camera.capture_array()
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        boxes, weights = self.hog.detectMultiScale(gray, winStride=(8,8))
        if len(boxes) > 0:
            x,y,w,h = boxes[0]
            self.state.last_detection = {
                "x": int(x),
                "y": int(y),
                "width": int(w),
                "height": int(h),
                "time": time.time()
            }
        return frame

class BatteryManager:
    def __init__(self, state):
        self.state = state

    def update(self):
        usage = 0.01 if self.state.mode == "SCAN" else 0.005
        self.state.battery -= usage
        if self.state.battery < 0:
            self.state.battery = 0

class DroneController:
    def __init__(self):
        self.state = DroneState()
        self.gps = GPSReader()
        self.motor = MotorController()
        self.nav = Navigation(self.state)
        self.supply = SupplySystem()
        self.telemetry = TelemetryServer(self.state)
        self.camera = CameraScanner(self.state)
        self.battery = BatteryManager(self.state)
        self.command_queue = Queue()
        self.running = True

    def start(self):
        self.telemetry.start()
        threading.Thread(target=self.command_processor, daemon=True).start()
        asyncio.run(self.main_loop())

    def command_processor(self):
        while self.running:
            cmd = self.command_queue.get()
            if cmd["type"] == "scan":
                self.state.mode = "SCAN"
                self.state.scan_active = True
            if cmd["type"] == "goto":
                self.state.target = (cmd["lat"], cmd["lon"])
                self.state.mode = "NAVIGATE"
            if cmd["type"] == "drop":
                if self.state.supply_loaded:
                    self.supply.drop()
                    self.state.supply_loaded = False
            if cmd["type"] == "return":
                self.state.mode = "RETURN"

    async def navigation_step(self):
        if self.state.target:
            lat, lon = self.state.target
            dist = self.nav.distance(self.state.latitude, self.state.longitude, lat, lon)
            self.nav.update_heading(self.state.target)
            if dist < 3:
                self.state.mode = "HOVER"
                self.motor.stop()
            else:
                self.motor.set_speed(0.2)

    async def scanning_step(self):
        if self.state.scan_active:
            self.camera.scan_frame()

    async def telemetry_step(self):
        self.telemetry.broadcast()

    async def battery_step(self):
        self.battery.update()

    async def gps_step(self):
        self.gps.update()
        self.state.latitude = self.gps.latitude
        self.state.longitude = self.gps.longitude

    async def main_loop(self):
        while self.running:
            await self.gps_step()
            if self.state.mode == "NAVIGATE":
                await self.navigation_step()
            if self.state.mode == "SCAN":
                await self.scanning_step()
            await self.telemetry_step()
            await self.battery_step()
            await asyncio.sleep(0.1)

class GroundCommandListener:
    def __init__(self, controller, port=9100):
        self.controller = controller
        self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    def start(self):
        self.sock.bind(("", self.port))
        self.sock.listen(1)
        threading.Thread(target=self.listen_loop, daemon=True).start()

    def listen_loop(self):
        while True:
            conn, addr = self.sock.accept()
            threading.Thread(target=self.client_thread, args=(conn,), daemon=True).start()

    def client_thread(self, conn):
        buffer = ""
        while True:
            data = conn.recv(1024)
            if not data:
                break
            buffer += data.decode()
            if "\n" in buffer:
                line, buffer = buffer.split("\n",1)
                try:
                    cmd = json.loads(line)
                    self.controller.command_queue.put(cmd)
                except:
                    pass

class PathScanner:
    def __init__(self, controller):
        self.controller = controller
        self.points = []
        self.index = 0

    def generate_grid(self, center_lat, center_lon, size=0.001, steps=5):
        for i in range(steps):
            for j in range(steps):
                lat = center_lat + (i - steps/2) * size/steps
                lon = center_lon + (j - steps/2) * size/steps
                self.points.append((lat,lon))

    async def run(self):
        while True:
            if self.controller.state.scan_active and self.points:
                target = self.points[self.index]
                self.controller.command_queue.put({
                    "type":"goto",
                    "lat":target[0],
                    "lon":target[1]
                })
                self.index = (self.index + 1) % len(self.points)
            await asyncio.sleep(5)

class SystemMonitor:
    def __init__(self, controller):
        self.controller = controller

    async def monitor(self):
        while True:
            st = self.controller.state
            if st.battery < 20 and st.mode != "RETURN":
                self.controller.command_queue.put({"type":"return"})
            await asyncio.sleep(2)

def start_system():
    controller = DroneController()
    listener = GroundCommandListener(controller)
    scanner = PathScanner(controller)
    monitor = SystemMonitor(controller)

    listener.start()

    async def async_tasks():
        asyncio.create_task(scanner.run())
        asyncio.create_task(monitor.monitor())
        await controller.main_loop()

    asyncio.run(async_tasks())

if __name__ == "__main__":
    start_system()