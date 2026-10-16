/* Run against the disposable tests/preview_workspace.py server, never production. */
const {chromium} = require('playwright');
const fs = require('fs'), path = require('path'), assert = require('assert/strict');
const output = process.env.VEXX_QA_OUTPUT || path.resolve('qa-artifacts/3d');
fs.mkdirSync(output,{recursive:true});
const url = 'http://127.0.0.1:8770';
const fixture = '<!doctype html><html lang="pt-BR"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="/styles.css"><link rel="stylesheet" href="/interface.css"><body><main id="fixture"></main><script src="/model3d-schema.js"></script><script src="/jdui.js"></script></body></html>';
const base = kind => ({id:'demo',version:1,title:'Demonstração 3D',description:'Objeto geométrico de teste.',objects:[{id:kind,kind,label:kind,description:'Geometria original de teste.'}]});
let browser, debugPage;
(async () => {
  browser = await chromium.launch({channel:'chrome',headless:true});
  const context = await browser.newContext({viewport:{width:1100,height:850}});
  await context.addInitScript(() => {
    window.__gpu = {draws:0,created:0,deleted:0};
    const proto = window.WebGL2RenderingContext?.prototype;
    if (proto) for (const [method,key] of [['drawElements','draws'],['drawArrays','draws'],['createBuffer','created'],['deleteBuffer','deleted']]) {
      const original = proto[method]; proto[method] = function (...args) {window.__gpu[key]++; return original.apply(this,args);};
    }
  });
  const page = await context.newPage(), errors = [], requests = [];
  page.on('pageerror',e => errors.push(e.message)); page.on('console',m => {if(m.type()==='error') errors.push(m.text());});
  page.on('request',r => requests.push(r.url()));
  await page.route('**/qa-3d',r => r.fulfill({status:200,contentType:'text/html',body:fixture,
    headers:{'Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'"}}));
  await page.goto(url+'/qa-3d'); await page.waitForFunction(() => window.JDUI);
  assert(!requests.some(r => r.includes('three-engine') || r.includes('model3d-viewer')));
  async function mount(props, append=false) {
    await page.evaluate(({props,append}) => {
      const target = document.querySelector('#fixture'); if (!append) target.replaceChildren();
      window.__state = {};
      const message = JDUI.validateMessage({version:JDUI.version,blocks:[{type:'ui',component:'model3d',props}]});
      if (!message.ok) throw Error(JSON.stringify(message.erros));
      JDUI.mount(target,[message.msg],{loadState:() => window.__state,saveState:(k,s) => {window.__state=s;}});
    },{props,append});
  }
  await mount(base('cube'));
  assert(!requests.some(r => r.includes('three-engine')),'Engine must stay lazy before activation');
  await page.getByRole('button',{name:'Explorar em 3D',exact:true}).click();
  await page.waitForFunction(() => document.querySelector('.m3-status')?.textContent.startsWith('Arraste'));
  const gpu = await page.evaluate(() => {const gl=document.querySelector('canvas').getContext('webgl2'); const ext=gl.getExtension('WEBGL_debug_renderer_info');return {version:gl.getParameter(gl.VERSION),renderer:ext?gl.getParameter(ext.UNMASKED_RENDERER_WEBGL):'unavailable'};});
  const canvas = page.locator('canvas'); await canvas.focus();
  const initial = await canvas.screenshot(); await canvas.press('ArrowRight'); await page.waitForTimeout(80);
  assert(!initial.equals(await canvas.screenshot()),'Rotation must change actual pixels');
  const bounds = await canvas.boundingBox();
  await page.mouse.move(bounds.x+bounds.width/2,bounds.y+bounds.height/2); await page.mouse.down();
  await page.mouse.move(bounds.x+bounds.width/2+40,bounds.y+bounds.height/2+20,{steps:5}); await page.mouse.up();
  assert((await page.evaluate(() => window.__state.rotation[1])) > .5);
  await page.getByRole('button',{name:'Ampliar',exact:true}).click();
  assert(Math.abs(await page.evaluate(() => window.__state.distance)-4.8)<1e-9);
  await page.getByRole('button',{name:'Restaurar',exact:true}).click();
  assert.equal(await page.evaluate(() => window.__state.distance),6);
  await canvas.click(); await page.waitForSelector('.m3-part');
  assert.equal(await page.locator('.m3-part').getAttribute('aria-pressed'),'true');
  await page.getByRole('button',{name:'Animar',exact:true}).click(); await page.waitForTimeout(180);
  await page.getByRole('button',{name:'Pausar',exact:true}).click(); await page.waitForTimeout(80);
  const paused = await page.evaluate(() => window.__gpu.draws); await page.waitForTimeout(180);
  assert.equal(await page.evaluate(() => window.__gpu.draws),paused,'Paused viewer must stop drawing');
  await page.getByRole('button',{name:'Tela ampliada',exact:true}).click();
  assert(await page.locator('.m3-expanded').count());
  await page.getByRole('button',{name:'Recolher',exact:true}).click();
  await page.screenshot({path:path.join(output,'desktop.png'),fullPage:true});
  const cdp = await context.newCDPSession(page); await cdp.send('Performance.enable');
  const before = await cdp.send('Performance.getMetrics');
  await mount(base('sphere'),true); await page.getByRole('button',{name:'Explorar em 3D',exact:true}).last().click();
  await page.waitForFunction(() => document.querySelectorAll('canvas').length === 1 && document.querySelectorAll('.m3-status')[1].textContent.startsWith('Arraste'));
  assert.equal(await page.locator('canvas').count(),1);
  for (const kind of ['cylinder','pyramid']) {await mount(base(kind)); await page.getByRole('button',{name:'Explorar em 3D',exact:true}).click(); await page.waitForSelector('.m3-preview[hidden]',{state:'attached'});}
  await mount({...base('cube'),model:'demo-cube',objects:[]});
  await page.getByRole('button',{name:'Explorar em 3D',exact:true}).click(); await page.waitForSelector('.m3-preview[hidden]',{state:'attached'});
  await page.screenshot({path:path.join(output,'glb.png'),fullPage:true});
  await page.setViewportSize({width:390,height:844});
  await mount({id:'demo',version:1,title:'Sólidos geométricos',objects:['cube','sphere','cylinder','pyramid'].map((kind,i)=>({id:kind,kind,position:[(i-1.5)*1.7,0,0],label:kind}))});
  await page.getByRole('button',{name:'Explorar em 3D',exact:true}).click(); await page.waitForSelector('.m3-preview[hidden]',{state:'attached'});
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  await page.screenshot({path:path.join(output,'mobile.png'),fullPage:true});
  // Touch events dispatched through Chrome's input domain, not a mocked renderer.
  const touch = await page.locator('canvas').boundingBox();
  await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x:touch.x+100,y:touch.y+100}]});
  await cdp.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x:touch.x+150,y:touch.y+130}]});
  await cdp.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
  await page.waitForTimeout(60); assert((await page.evaluate(() => window.__state.rotation?.[1])) > .5);
  await page.getByRole('button',{name:'Animar',exact:true}).click();
  await page.evaluate(() => {const host=document.querySelector('#fixture'); host.style.height='400px'; host.style.overflow='auto'; const spacer=document.createElement('div'); spacer.style.height='2000px'; host.append(spacer); host.scrollTop=2000;});
  assert(await page.evaluate(() => document.querySelector('canvas').getBoundingClientRect().bottom < 0));
  await page.waitForTimeout(150); const offscreen = await page.evaluate(() => window.__gpu.draws);
  await page.waitForTimeout(150); assert.equal(await page.evaluate(() => window.__gpu.draws),offscreen);
  await page.evaluate(() => document.querySelector('#fixture').replaceChildren()); await page.waitForTimeout(60);
  const cleanup = await page.evaluate(() => ({...window.__gpu,canvases:document.querySelectorAll('canvas').length}));
  assert.equal(cleanup.canvases,0); assert.equal(cleanup.created,cleanup.deleted,'All GL buffers must be deleted');
  const after = await cdp.send('Performance.getMetrics');
  await cdp.send('HeapProfiler.collectGarbage');
  const afterGC = await cdp.send('Performance.getMetrics');
  assert.deepEqual(errors,[]);
  // Reduced motion and constrained CPU are browser settings, not a claim about a physical phone.
  await page.emulateMedia({reducedMotion:'reduce'});
  await cdp.send('Emulation.setCPUThrottlingRate',{rate:4});
  await page.evaluate(() => {const h=document.querySelector('#fixture'); h.style.height=''; h.style.overflow='';});
  await mount({...base('sphere'),autoRotate:true});
  await page.getByRole('button',{name:'Explorar em 3D',exact:true}).click(); await page.waitForSelector('.m3-preview[hidden]',{state:'attached'});
  assert(await page.getByRole('button',{name:'Animar',exact:true}).isVisible());
  await page.waitForTimeout(100); const quiet = await page.evaluate(() => window.__gpu.draws);
  await page.waitForTimeout(150); assert.equal(await page.evaluate(() => window.__gpu.draws),quiet);
  await page.getByRole('button',{name:'Animar',exact:true}).click(); const frameStart = await page.evaluate(() => window.__gpu.draws);
  const tick = Date.now(); await page.waitForTimeout(1000); const sampleMs=Date.now()-tick;
  const sampleDraws = await page.evaluate(() => window.__gpu.draws) - frameStart;
  assert(sampleDraws > 0 && sampleDraws/sampleMs*1000 < 45);
  await page.getByRole('button',{name:'Pausar',exact:true}).click();
  await cdp.send('Emulation.setCPUThrottlingRate',{rate:1});
  // Context loss must restore 2D; explicit retry creates a fresh working renderer.
  await page.evaluate(() => document.querySelector('canvas').getContext('webgl2').getExtension('WEBGL_lose_context').loseContext());
  await page.getByText('A renderização 3D foi interrompida. Preview 2D disponível; tente abrir novamente.').waitFor();
  assert.equal(await page.locator('canvas').count(),0);
  await page.getByRole('button',{name:'Explorar em 3D',exact:true}).click(); await page.waitForSelector('.m3-preview[hidden]',{state:'attached'});
  // Bounded local loader refuses even a valid URL if the response exceeds its byte budget.
  await page.route('**/models/demo-cube.glb',r=>r.fulfill({body:Buffer.alloc(65537),contentType:'model/gltf-binary'}));
  await mount({...base('cube'),objects:[],model:'demo-cube'}); await page.getByRole('button',{name:'Explorar em 3D',exact:true}).click();
  await page.getByText('3D indisponível. Use o preview 2D e a descrição; você pode tentar novamente.').waitFor();
  assert(await page.locator('.m3-preview').isVisible());
  await page.unroute('**/models/demo-cube.glb');
  // No-WebGL browser context: a real browser with GPU contexts explicitly disabled.
  const noGL = await browser.newContext();
  await noGL.addInitScript(() => {const orig=HTMLCanvasElement.prototype.getContext; HTMLCanvasElement.prototype.getContext=function(type,...args){return type.startsWith('webgl')?null:orig.call(this,type,...args);};});
  const fallback = await noGL.newPage(); await fallback.route('**/qa-3d',r=>r.fulfill({contentType:'text/html',body:fixture}));
  await fallback.goto(url+'/qa-3d'); await fallback.waitForFunction(() => window.JDUI);
  await fallback.evaluate(p => JDUI.mount(document.querySelector('#fixture'),[{version:JDUI.version,blocks:[{type:'ui',component:'model3d',props:p}]}]),base('cube'));
  await fallback.getByRole('button',{name:'Explorar em 3D',exact:true}).click();
  await fallback.getByText('3D indisponível. Use o preview 2D e a descrição; você pode tentar novamente.').waitFor();
  assert(await fallback.locator('.m3-preview').isVisible()); assert.equal(await fallback.locator('canvas').count(),0);
  await fallback.screenshot({path:path.join(output,'fallback.png'),fullPage:true});
  await noGL.close();
  // Actual login -> composer -> relay -> PC Agent -> SSE -> IDB -> JDUI.
  const chat = await context.newPage(); const chatErrors=[]; chat.on('pageerror',e=>chatErrors.push(e.message));
  debugPage = chat;
  await chat.goto(url); await chat.locator('#loginUser').fill('preview'); await chat.locator('#loginPassword').fill('preview-only-2026'); await chat.locator('#loginButton').click();
  await chat.locator('#loginOverlay').waitFor({state:'hidden'});
  await chat.locator('#newChatTop').click(); await chat.locator('#messageInput').fill('Lucas, mostre um cubo em 3D.');
  await chat.getByRole('button',{name:'Enviar',exact:true}).click();
  await chat.getByRole('button',{name:'Explorar em 3D',exact:true}).waitFor({timeout:30000});
  await chat.getByRole('button',{name:'Explorar em 3D',exact:true}).click(); await chat.waitForSelector('.m3-preview[hidden]',{state:'attached'});
  await chat.locator('#messageInput').fill('Amplie.'); await chat.getByRole('button',{name:'Enviar',exact:true}).click();
  await chat.getByText('Visualização ampliada.',{exact:false}).waitFor();
  await chat.locator('.model3d').last().locator('.m3-preview[hidden]').waitFor({state:'attached'});
  await chat.reload(); await chat.getByText('Visualização ampliada.',{exact:false}).waitFor();
  assert((await chat.locator('.model3d').count())>=2);
  await chat.getByRole('button',{name:'Explorar em 3D',exact:true}).last().click(); await chat.waitForSelector('.m3-preview[hidden]',{state:'attached'});
  await chat.screenshot({path:path.join(output,'chat.png'),fullPage:true}); assert.deepEqual(chatErrors,[]);
  await chat.setViewportSize({width:390,height:844});
  if (await chat.locator('#drawer').getAttribute('aria-hidden') === 'false') await chat.locator('#drawerClose').click();
  await chat.waitForFunction(() => document.querySelector('#drawer').getBoundingClientRect().right <= 1);
  await chat.locator('.model3d').last().getByRole('button',{name:'Reduzir',exact:true}).click();
  await chat.locator('.model3d').last().evaluate(node => node.scrollIntoView({block:'end'}));
  await chat.screenshot({path:path.join(output,'chat-mobile.png'),fullPage:true});
  assert(await chat.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  await context.setOffline(true);
  assert.equal(await chat.evaluate(async()=> (await fetch('/vendor/three-engine.js')).status),200);
  await chat.getByRole('button',{name:'Explorar em 3D',exact:true}).last().click(); await chat.waitForSelector('.m3-preview[hidden]',{state:'attached'});
  // Existing auth policy blocks a cold offline reload; do not bypass login for 3D.
  await chat.reload(); await chat.locator('#loginOverlay').waitFor({state:'visible'});
  await context.setOffline(false);
  fs.writeFileSync(path.join(output,'metrics.json'),JSON.stringify({gpu,cleanup,before:before.metrics,after:after.metrics,afterGC:afterGC.metrics,throttledCPU:{rate:4,sampleMs,sampleDraws},consoleErrors:errors,chatErrors,checks:'lazy, pixels, mouse, keyboard, zoom, reset, selection, pause, expand, four primitives, GLB, mobile, touch, offscreen, cleanup, reduced motion, CPU4x, context loss, model size, no-WebGL fallback, chat SSE persistence, offline cached engine'},null,2));
  console.log(JSON.stringify({ok:true,gpu,cleanup,output}));
})().catch(async error=>{console.error(error); if(debugPage){await debugPage.screenshot({path:path.join(output,'failure.png'),fullPage:true}).catch(()=>{}); console.error(await debugPage.locator('.m3-status').allTextContents());} process.exitCode=1;}).finally(async()=>{await browser?.close();});
