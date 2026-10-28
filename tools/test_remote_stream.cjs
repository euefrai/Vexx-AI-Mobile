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
 events:{},addEventListener(k,f){this.events[k]=f;},removeAttribute(){},setPointerCapture(){},blur(){},focus(){},setAttribute(){},
 getBoundingClientRect(){return {left:0,top:0,width:400,height:225};}});return els.get(id);}
global.document={hidden:false,getElementById:el,addEventListener(){}};
global.window=global;global.addEventListener=()=>{};
Object.defineProperty(global,'navigator',{value:{userAgent:'Android',onLine:true},configurable:true});
global.Image=class{async decode(){}};
const state={approved:true,view_allowed:true,control_allowed:true,capture_ready:true,supported:true};
let holdFrame=false, releaseFrame, holdInput=false, releaseInput;
const ctx={authenticated:()=>true,online:()=>true,identity:()=> 'u1',headers:()=>({}),notify(){},
 async api(path,opts){requests.push({path,cmd:opts?.body&&JSON.parse(opts.body)});
 if(path.startsWith('/api/input') && holdInput){holdInput=false;await new Promise(r=>releaseInput=r);}
 if(path.includes('/status'))return {...state};
 if(path.includes('/screen')){if(holdFrame)await new Promise(r=>releaseFrame=r);return {imagem:'fixture',cursor:{x:.25,y:.5},largura:1920,altura:1080,remote_enabled:true};}
 return {ok:true};}};
const flush=async()=>{for(let i=0;i<12;i++)await Promise.resolve();};
async function advance(ms){now+=ms;for(const [id,t] of [...timers])if(t.at<=now){timers.delete(id);t.fn();}await flush();}
function event(type,x,y,id=1){el('remoteFrame').events[type]({clientX:x,clientY:y,pointerId:id,pointerType:'touch',button:0,target:{closest:()=>null},preventDefault(){}});}
const commands=()=>requests.filter(x=>x.cmd).map(x=>x.cmd);
(async()=>{
 require('../public/remote.js');const remote=VexxRemote.mount(ctx);remote.update();await flush();
 el('remoteConnect').events.click();await flush();
 assert(requests.some(x=>x.path.includes('max_w=1280&q=72')));
 assert.equal(el('remotePointer').style.display,'block');
 assert.equal(el('remotePointer').style.left,'25%');
 assert.equal(el('remotePointer').style.top,'50%');
 event('pointerdown',20,20);event('pointermove',180,100);event('pointerup',190,110);await flush();
 assert.equal(commands().at(-1).kind,'drag');assert.equal(commands().at(-1).points.at(-1).x,190/400);
 await advance(300);
 event('pointerdown',100,100);event('pointerup',100,100);await advance(80);
 event('pointerdown',100,100);event('pointerup',100,100);await flush();
 assert.equal(commands().at(-1).kind,'double');assert(!commands().some(c=>c.kind==='click'));
 await advance(300);
 event('pointerdown',100,100,1);event('pointerdown',180,100,2);event('pointermove',100,180,1);await advance(40);
 assert.equal(commands().at(-1).kind,'scroll');event('pointerup',100,180,1);event('pointerup',180,100,2);
 await advance(300);const count=commands().length;
 event('pointerdown',100,100);event('pointermove',150,150);event('pointercancel',150,150);event('pointerup',150,150);await advance(300);
 assert.equal(commands().length,count);
 holdFrame=true;await advance(1000);assert(releaseFrame);
 const before=requests.filter(x=>x.path.includes('/screen')).length;
 el('refreshButton').events.click();await flush();assert.equal(requests.filter(x=>x.path.includes('/screen')).length,before);
 el('remoteDisconnect').events.click();el('screenImg').src='cleared';releaseFrame();await flush();
 assert.equal(el('screenImg').src,'cleared');
 assert.equal(el('remotePointer').style.display,'none');
 // Current agent capabilities: binary frames, input batches, high-resolution wheel.
 holdFrame=false;
 Object.assign(state,{input_batch:true,precise_scroll:true});
 const made=[],revoked=[];
 const make=URL.createObjectURL.bind(URL),revoke=URL.revokeObjectURL.bind(URL);
 URL.createObjectURL=b=>{const u=make(b);made.push(u);return u;};
 URL.revokeObjectURL=u=>{revoked.push(u);revoke(u);};
 ctx.frame=async()=>({blob:new Blob(['jpeg-fixture']),largura:1920,altura:1080,remote_enabled:true,cursor:{x:.5,y:.5}});
 const modern=VexxRemote.mount(ctx);modern.update();await flush();
 el('remoteConnect').events.click();await flush();
 assert(made.length>0 && el('screenImg').src.startsWith('blob:'));
 const keys=el('remoteKeys');keys.value='prefix';holdInput=true;
 const start=requests.length;
 keys.events.input({});await flush();assert(releaseInput);
 keys.events.compositionstart();keys.value='ação🚀';keys.events.input({isComposing:true});
 assert.equal(keys.value,'ação🚀');keys.events.compositionend();keys.events.input({});
 keys.value='🙂'.repeat(201)+'z';keys.events.input({});
 keys.events.keydown({key:'Enter',preventDefault(){}});
 releaseInput();await flush();await advance(100);
 const modernRequests=requests.slice(start).filter(x=>x.cmd);
 assert(modernRequests.some(x=>x.path==='/api/input/batch'));
 const flat=modernRequests.flatMap(x=>x.cmd.commands || [x.cmd]);
 assert.equal(flat.filter(x=>x.kind==='text').map(x=>x.text).join(''),'prefixação🚀'+'🙂'.repeat(201)+'z');
 assert.equal(flat.at(-1).key,'enter');assert(flat.filter(x=>x.kind==='text').every(x=>Array.from(x.text).length<=200));
 await advance(100);
 keys.events.beforeinput({inputType:'deleteContentBackward',preventDefault(){}});await flush();
 assert.equal(commands().at(-1).key,'backspace');
 await advance(100);
 event('pointerdown',100,100,1);event('pointerdown',180,100,2);
 event('pointermove',100,102,1);event('pointermove',100,104,1);
 event('pointerup',100,104,1);event('pointerup',180,100,2);await flush();
 assert.deepEqual(commands().at(-1),{kind:'wheel',delta_x:0,delta_y:5});
 const current=el('screenImg').src;el('remoteDisconnect').events.click();
 assert(revoked.includes(current));assert.equal(keys.value,'');assert(keys.hidden);
 console.log('PASS legacy/modern frames, blob cleanup, batches, composition, Unicode paste, mobile delete, small final two-finger scroll');
 console.log('PASS drag, double tap, two-finger scroll, cancel, single-flight, stale frame');
})().catch(e=>{console.error(e);process.exitCode=1;});
