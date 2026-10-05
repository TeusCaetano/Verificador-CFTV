'use strict';
const assert=require('assert'),fs=require('fs'),path=require('path'),vm=require('vm');
const root=path.resolve(__dirname,'..'),html=fs.readFileSync(path.join(root,'frontend/index.html'),'utf8');
function boot(source){
 const elements=new Map();
 function element(id){
  if(!elements.has(id)){
   const e={id,value:'',checked:false,hidden:!['map-page'].includes(id),open:false,textContent:'',innerHTML:'',muted:true,style:{},dataset:{},classList:{add(){},remove(){},toggle(){}},addEventListener(){},setAttribute(){},removeAttribute(){},showModal(){this.open=true},close(){this.open=false},pause(){},load(){},click(){},querySelectorAll(){return []},closest(){return this},appendChild(){},get options(){return [...this.innerHTML.matchAll(/<option value="([^"]*)"/g)].map(m=>({value:m[1]}))}};
   e.elements=new Proxy({},{get:(o,k)=>o[k]||(o[k]={value:'',checked:false,addEventListener(){}})});elements.set(id,e);
  }
  return elements.get(id);
 }
 for(const m of html.matchAll(/id="([^"]+)"/g))element(m[1]);
 const storage={getItem(){return null},setItem(){},removeItem(){}};
 const layer={addTo(){return this},clearLayers(){},on(){return this},bindTooltip(){return this}};
 const map={setView(){return this},getZoom(){return 15},getCenter(){return {lat:-13,lng:-58}},getBounds(){return {}},on(){return this},invalidateSize(){},addLayer(){},removeLayer(){},hasLayer(){return false},project(point){return {x:point[0],y:point[1]}},unproject(point){return {lat:point.x,lng:point.y}},fitBounds(){},panTo(){}};
 const context={ResizeObserver:class {observe(){}},console,crypto:{randomUUID:()=> 'test-key'},document:{createElement:element,getElementById:element,addEventListener(){},querySelectorAll(){return []},hidden:false},sessionStorage:storage,localStorage:storage,setTimeout(){return 1},clearTimeout(){},setInterval(){return 1},location:{reload(){}},L:{map:()=>map,tileLayer:()=>layer,control:{zoom:()=>layer},layerGroup:()=>layer,marker:()=>layer,polyline:()=>layer,divIcon:()=>({}),point:(x,y)=>({x,y}),latLngBounds:()=>({})},URLSearchParams,AbortController,fetch:async()=>{throw Error('Unexpected fetch')}};
 context.window=context;vm.createContext(context);vm.runInContext(fs.readFileSync(path.join(root,'frontend/map-groups.js'),'utf8'),context);
 vm.runInContext(source,context);
 vm.runInContext(fs.readFileSync(path.join(root,'frontend/google-map.js'),'utf8'),context);
 return {context,element};
}
(async()=>{
 const source=fs.readFileSync(path.join(root,'frontend/app.js'),'utf8');
 // Preserve the faulty order as a regression fixture: map exists on first render.
 const faulty=source.replace('let lastMapSignature=null;\n','').replace('function renderMapGroups(visible){','let lastMapSignature=null;\nfunction renderMapGroups(visible){');
 assert.throws(()=>boot(faulty),/lastMapSignature.*initialization/);
 const {context,element}=boot(source);assert.equal(element('login-dialog').open,true);
 const cameras=Array.from({length:240},(_,i)=>({id:i+1,name:'Camera '+(i+1),manufacturer:'Intelbras',model:'NVD',ip:'10.0.0.1',port:554,channel:i+1,unit_id:1,unit_name:'Três Lagoas',sector_id:0,sector_name:'',recorder_name:'NVD',device_type:'nvr',status:'online',is_free:false,lat:-13,lng:-58}));
 const snapshot={units:[{id:1,name:'Três Lagoas',lat:-13,lng:-58}],sectors:[],cameras,maintenance:[],alerts:{summary:{open:0,acknowledged:0,maintenance:0,recurring_devices:0},rows:[]},overview:{live_views:0,registered_users:1,online_users:1,status_changes_24h:0,offline_changes_24h:0,device_types:{nvr:240,camera:0,unknown:0},offline_recent:0,offline_old:0,offline_unknown:0},monitor:{running:true,configured:240,in_progress:0,workers:16,stale:0},events:[]};
 context.fetch=async url=>{assert.match(url,/^\/api\/snapshot/);return {ok:true,json:async()=>snapshot}};
 await vm.runInContext('authToken="test";load()',context);
 assert.equal(element('registered-count').textContent,240);assert.match(element('device-table').innerHTML,/Camera 1/);assert.match(element('camera-tree').innerHTML,/Camera 240/);assert.equal(element('toast').textContent,'');
 cameras[0].status='unknown';
 vm.runInContext('selected=1;liveReceivingId=1;lastVideoProgress=Date.now();renderCameraDetails(cameras[0])',context);
 assert.match(element('viewer-status').innerHTML,/dot unknown/);
 element('live-video').paused=false;element('live-video').readyState=3;
 context.fetch=async (url,options)=>{
  if(url==='/api/live-confirm'){
   assert.equal(options.method,'POST');assert.equal(JSON.parse(options.body).ticket,'test-live-ticket');
   cameras[0].status='online';return {ok:true,json:async()=>({confirmed:true,camera_id:1,status:'online',checked_at:123,diagnostic:'Confirmed playback'})};
  }
  assert.match(url,/^\/api\/snapshot/);return {ok:true,json:async()=>snapshot};
 };
 await vm.runInContext('activeLiveTicket="test-live-ticket";lastLiveConfirmation=0;confirmLivePlayback()',context);
 assert.match(element('viewer-status').innerHTML,/dot online/);
 assert.equal(vm.runInContext('cameras[0].status',context),'online');
 console.log('PASS: startup, 240-camera load and playback status synchronization.');
})().catch(e=>{console.error(e);process.exitCode=1});
