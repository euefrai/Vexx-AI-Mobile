// Deterministic DOM/API harness. No browser or physical desktop claim.
const assert = require('node:assert/strict');
let now=100000, tid=0;
const timers=new Map(), els=new Map(), requests=[];
global.setTimeout=(fn,delay)=>{timers.set(++tid,{fn,at:now+delay});return tid;};
global.clearTimeout=id=>timers.delete(id);
global.setInterval=()=>0;
Date.now=()=>now;
global.performance={now:()=>now};
function el(id){if(!els.has(id))els.set(id,{hidden:false,disabled:false,value:'',style:{},naturalWidth:1920,naturalHeight:1080,
 events:{},addEventListener(k,f){this.events[k]=f;},removeAttribute(){},setPointerCapture(){},
 getBoundingClientRect(){return {left:0,top:0,width:400,height:225};}});return els.get(id);}
global.document={hidden:false,getElementById:el,addEventListener(){}};
global.window=global;global.addEventListener=()=>{};
Object.defineProperty(global,'navigator',{value:{userAgent:'Android',onLine:true},configurable:true});
global.Image=class{async decode(){}};
const state={approved:true,view_allowed:true,control_allowed:true,capture_ready:true,supported:true};
let holdFrame=false, releaseFrame;
const ctx={authenticated:()=>true,online:()=>true,identity:()=> 'u1',headers:()=>({}),notify(){},
 async api(path,opts){requests.push({path,cmd:opts?.body&&JSON.parse(opts.body)});
 if(path.includes('/status'))return {...state};
 if(path.includes('/screen')){if(holdFrame)await new Promise(r=>releaseFrame=r);return {imagem:'fixture',largura:1920,altura:1080,remote_enabled:true};}
 return {ok:true};}};
const flush=async()=>{for(let i=0;i<12;i++)await Promise.resolve();};
async function advance(ms){now+=ms;for(const [id,t] of [...timers])if(t.at<=now){timers.delete(id);t.fn();}await flush();}
function event(type,x,y,id=1){el('remoteFrame').events[type]({clientX:x,clientY:y,pointerId:id,pointerType:'touch',button:0,target:{closest:()=>null},preventDefault(){}});}
const commands=()=>requests.filter(x=>x.cmd).map(x=>x.cmd);
(async()=>{
 require('../public/remote.js');const remote=VexxRemote.mount(ctx);remote.update();await flush();
 el('remoteConnect').events.click();await flush();
 assert(requests.some(x=>x.path.includes('max_w=1920&q=78')));
 event('pointerdown',20,20);event('pointermove',180,100);event('pointerup',190,110);await flush();
 assert.equal(commands().at(-1).kind,'drag');assert.equal(commands().at(-1).points.at(-1).x,190/400);
 await advance(300);
 event('pointerdown',100,100);event('pointerup',100,100);await advance(80);
 event('pointerdown',100,100);event('pointerup',100,100);await flush();
 assert.equal(commands().at(-1).kind,'double');assert(!commands().some(c=>c.kind==='click'));
 await advance(300);
 event('pointerdown',100,100,1);event('pointerdown',180,100,2);event('pointermove',100,180,1);await flush();
 assert.equal(commands().at(-1).kind,'scroll');event('pointerup',100,180,1);event('pointerup',180,100,2);
 await advance(300);const count=commands().length;
 event('pointerdown',100,100);event('pointermove',150,150);event('pointercancel',150,150);event('pointerup',150,150);await advance(300);
 assert.equal(commands().length,count);
 holdFrame=true;await advance(1000);assert(releaseFrame);
 const before=requests.filter(x=>x.path.includes('/screen')).length;
 el('refreshButton').events.click();await flush();assert.equal(requests.filter(x=>x.path.includes('/screen')).length,before);
 el('remoteDisconnect').events.click();el('screenImg').src='cleared';releaseFrame();await flush();
 assert.equal(el('screenImg').src,'cleared');
 console.log('PASS drag, double tap, two-finger scroll, cancel, single-flight, stale frame');
})().catch(e=>{console.error(e);process.exitCode=1;});
