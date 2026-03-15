// =============================
// MAP LOCATION
// Flood prone jungle area near Ranthambore
// =============================

var base = [26.0173, 76.5026];

var map = L.map('map').setView(base, 13);

L.tileLayer(
'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
{ maxZoom:19 }
).addTo(map);


// =============================
// LARGE CLEAR ICONS
// =============================

var droneIcon = L.divIcon({
html:"🛩️",
className:"",
iconSize:[70,70]
});

var humanIcon = L.divIcon({
html:"🧍‍♂️",
className:"",
iconSize:[80,80]
});

var houseIcon = L.divIcon({
html:"🏚️",
className:"",
iconSize:[70,70]
});

var treeIcon = L.divIcon({
html:"🌲",
className:"",
iconSize:[70,70]
});


// =============================
// SURVIVOR LOCATIONS
// =============================

var humans = [
[26.018,76.498],
[26.020,76.507],
[26.014,76.503]
];

var houses = [
[26.019,76.505],
[26.013,76.500]
];

var trees = [
[26.021,76.502],
[26.017,76.509]
];


// =============================
// CREATE MARKERS
// =============================

humans.forEach(p=>{
let m=L.marker(p,{icon:humanIcon}).addTo(map);

m.on("click",()=>{
showPopup(
"Survivor Detected",
"Person stranded in flooded jungle area.",
p,
true
);
});
});

houses.forEach(p=>{
let m=L.marker(p,{icon:houseIcon}).addTo(map);

m.on("click",()=>{
showPopup(
"Damaged Shelter",
"Flood impacted structure detected.",
p,
true
);
});
});

trees.forEach(p=>{
let m=L.marker(p,{icon:treeIcon}).addTo(map);

m.on("click",()=>{
showPopup(
"Forest Area",
"Dense vegetation zone.",
p,
false
);
});
});


// =============================
// DRONE SYSTEM
// =============================

var drone;
var pathLine;
var dronePath=[];

var battery=100;
var altitude=45;

function deployDrone(){

document.getElementById("droneId").innerText="Drone-01";

drone=L.marker(base,{icon:droneIcon}).addTo(map);

dronePath=[base];

pathLine=L.polyline(dronePath,{color:"orange"}).addTo(map);


// Pentagon scan

let route=[
base,
[26.022,76.498],
[26.023,76.506],
[26.017,76.510],
[26.012,76.503],
base
];

moveDroneSmooth(route);

}


// =============================
// VERY SMOOTH DRONE MOVEMENT
// =============================

function moveDroneSmooth(route){

let i=0;

function move(){

if(i>=route.length-1) return;

let start=route[i];
let end=route[i+1];

let steps=150;

let latStep=(end[0]-start[0])/steps;
let lngStep=(end[1]-start[1])/steps;

let step=0;

let interval=setInterval(()=>{

let lat=start[0]+latStep*step;
let lng=start[1]+lngStep*step;

let pos=[lat,lng];

drone.setLatLng(pos);

dronePath.push(pos);

pathLine.setLatLngs(dronePath);

updateTelemetry(pos);

step++;

if(step>steps){

clearInterval(interval);

i++;

move();

}

},200);

}

move();

}


// =============================
// TELEMETRY
// =============================

function updateTelemetry(pos){

battery=Math.max(0,battery-0.02);

document.getElementById("battery").innerText=Math.floor(battery);

document.getElementById("altitude").innerText=altitude;

document.getElementById("speed").innerText=5;

document.getElementById("lat").innerText=pos[0].toFixed(5);

document.getElementById("lon").innerText=pos[1].toFixed(5);

document.getElementById("altitudeBar").style.width=(altitude/100*100)+"%";

}


// =============================
// POPUP SYSTEM
// =============================

var target=null;

function showPopup(title,desc,pos,allow){

document.getElementById("popupTitle").innerText=title;
document.getElementById("popupDescription").innerText=desc;

target=pos;

document.getElementById("supplyBtn").style.display=allow?"block":"none";

document.getElementById("infoPopup").classList.remove("hidden");

}

function closePopup(){

document.getElementById("infoPopup").classList.add("hidden");

}


// =============================
// SUPPLY DRONE
// =============================

function dispatchSupply(){

if(!target) return;

let supply=L.marker(base,{icon:droneIcon}).addTo(map);

let route=[base,target,base];

moveDroneSmoothSupply(supply,route);

closePopup();

}

function moveDroneSmoothSupply(drone,route){

let i=0;

function move(){

if(i>=route.length-1){

map.removeLayer(drone);

return;

}

let start=route[i];
let end=route[i+1];

let steps=120;

let latStep=(end[0]-start[0])/steps;
let lngStep=(end[1]-start[1])/steps;

let step=0;

let interval=setInterval(()=>{

let lat=start[0]+latStep*step;
let lng=start[1]+lngStep*step;

drone.setLatLng([lat,lng]);

step++;

if(step>steps){

clearInterval(interval);

i++;

move();

}

},200);

}

move();

}


// =============================
// ANNOUNCEMENT
// =============================

function sendText(){

let msg=document.getElementById("announcement").value;

if(msg==="") return;

alert("Emergency Broadcast: "+msg);

}


// =============================
// VOICE RECORDING
// =============================

let recorder;

function startRecording(){

navigator.mediaDevices.getUserMedia({audio:true})
.then(stream=>{

recorder=new MediaRecorder(stream);

recorder.start();

alert("Voice announcement recording started");

});

}