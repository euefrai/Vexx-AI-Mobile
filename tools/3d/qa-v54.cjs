/* Real Chrome + disposable relay/SQLite: run tests/preview_workspace.py first. */
const {chromium}=require('playwright');
const fs=require('fs'),path=require('path'),assert=require('assert/strict'),{execFileSync}=require('child_process');
const scenes=JSON.parse(execFileSync(path.resolve('../.venv/Scripts/python.exe'),['-c',"import json;from model3d_education import scene;print(json.dumps({k:scene(k) for k in ('computer','geometry','solar')}))"],{encoding:'utf8'}));
scenes.computer.annotations=[{objectId:'cpu',text:'Anotação vinculada ao processador.'}];
const out=path.resolve('qa-artifacts/3d-v54');fs.mkdirSync(out,{recursive:true});
const url='http://127.0.0.1:8770';let browser,page;
(async()=>{
 browser=await chromium.launch({channel:'chrome',headless:true});
 const context=await browser.newContext({viewport:{width:1100,height:1000}}),errors=[],expectedAuth=[];
 await context.addInitScript(()=>{
   window.__gpu={draws:0,created:0,deleted:0};
   for(const [method,key] of [['drawElements','draws'],['createBuffer','created'],['deleteBuffer','deleted']]){
     const p=WebGL2RenderingContext.prototype,original=p[method];p[method]=function(...args){__gpu[key]++;return original.apply(this,args);};
   }
 });
 page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
 page.on('console',m=>{if(m.type()==='error'){
   if(m.location().url===url+'/api/session' && m.text().includes('401'))expectedAuth.push(m.text());
   else errors.push(m.text()+' '+m.location().url);
 }});
 await page.route('**/qa-v54',r=>r.fulfill({contentType:'text/html',body:'<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="/styles.css"><link rel="stylesheet" href="/interface.css"><style>html,body{height:auto;overflow:auto}#fixture{max-width:760px;margin:auto}</style><main id="fixture"></main><script src="/model3d-schema.js"></script><script src="/jdui.js"></script>'}));
 await page.goto(url+'/qa-v54');await page.waitForFunction(()=>window.JDUI);
 async function mount(p,append=false){await page.evaluate(({p,append})=>{
   const host=document.querySelector('#fixture');if(!append){host.replaceChildren();window.__state={};}
   const validated=JDUI.validateMessage({version:JDUI.version,blocks:[{type:'ui',component:'model3d',props:p}]});
   if(!validated.ok)throw Error(JSON.stringify(validated.erros));
   window.__mountCount=(window.__mountCount||0)+1;
   JDUI.mount(host,[validated.msg],{ownerId:'qa',conversationId:'qa',messageId:'qa-message-'+__mountCount,loadState:()=>__state,saveState:(k,s)=>{window.__state=s;}});
 },{p,append});}
 const state=()=>page.evaluate(()=>getModel3DContext('qa','qa').interaction);
 const button=name=>page.locator('.m3-live').getByRole('button',{name,exact:true});
 await mount(scenes.computer);await page.getByRole('button',{name:'Explorar em 3D',exact:true}).click();await page.waitForSelector('canvas');
 await page.waitForFunction(()=>window.getModel3DContext?.('qa','qa'));
 await page.locator('.m3-part').filter({hasText:'Processador'}).click();
 await page.getByText('Anotação vinculada ao processador.',{exact:true}).waitFor();
 await page.locator('.m3-part').filter({hasText:'Memória RAM'}).focus();await page.keyboard.press('Enter');
 assert.equal((await state()).selected,'ram');assert.equal(await page.evaluate(()=>document.activeElement.dataset.part),'ram');
 await page.getByText('Mais opções',{exact:true}).click();await button('Isolar').click();await button('Focar').click();
 await page.waitForTimeout(350);const isolated=await page.locator('canvas').screenshot();
 // Reset selection through a new snapshot while retaining focus/isolation, then real raycast at center.
 const focused={...scenes.computer,interaction:{...(await state()),selected:''}};
 await page.evaluate(()=>{window.__canvas=document.querySelector('canvas');window.__buffers=__gpu.created;});
 await mount(focused,true);await page.waitForTimeout(350);
 assert(await page.evaluate(()=>document.querySelector('canvas')===__canvas && __gpu.created===__buffers),'Simple commands must reuse GPU buffers/canvas');
 await page.locator('canvas').click();assert.equal((await state()).selected,'ram','Real raycast selects focused RAM');
 await button('Transparência').click();assert.deepEqual((await state()).transparent,['ram']);
 await button('Ocultar').click();assert.deepEqual((await state()).hidden,['ram']);
 await page.waitForTimeout(350);assert(!isolated.equals(await page.locator('canvas').screenshot()));
 await button('Revelar tudo').click();await button('Separar peças').click();assert((await state()).exploded);
 await page.locator('.m3-secondary select').selectOption('back');assert.equal((await state()).view,'back');
 await button('Remontar peças').click();await button('Próxima etapa').click();assert.equal((await state()).step,1);
 await button('Etapa anterior').click();await page.locator('.m3-lesson select').last().selectOption('2');
 await button('Reproduzir etapas').click();await page.waitForTimeout(2200);assert((await state()).step>=1);
 await button('Pausar etapas').click();await page.waitForTimeout(400);
 const draws=await page.evaluate(()=>__gpu.draws);await page.waitForTimeout(180);assert.equal(await page.evaluate(()=>__gpu.draws),draws);
 await button('Restaurar').click();assert.equal((await state()).selected,'');assert.equal((await state()).speed,1);
 await page.getByText('Mais opções',{exact:true}).last().click();
 await page.locator('.model3d').last().screenshot({path:path.join(out,'computer-desktop.png')});
 await page.setViewportSize({width:390,height:1000});
 await mount(scenes.geometry);await page.getByRole('button',{name:'Explorar em 3D',exact:true}).click();await page.waitForFunction(()=>document.querySelectorAll('.m3-part').length===26);
 const cdp=await context.newCDPSession(page),box=await page.locator('canvas').boundingBox();
 await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x:box.x+100,y:box.y+100}]});
 await cdp.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x:box.x+150,y:box.y+125}]});
 await cdp.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
 assert((await page.evaluate(()=>getModel3DContext('qa','qa').rotation[1]))>.6);
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 await page.screenshot({path:path.join(out,'geometry-mobile.png'),fullPage:true});
 await mount(scenes.solar);await page.getByRole('button',{name:'Explorar em 3D',exact:true}).click();
 await page.waitForFunction(()=>window.getModel3DContext?.('qa','qa')?.scene==='edu-solar');
 const orbitStart=await page.locator('canvas').screenshot();await button('Reproduzir etapas').click();
 await page.waitForTimeout(500);await button('Pausar etapas').click();await page.waitForTimeout(350);
 const orbitPaused=await page.locator('canvas').screenshot();assert(!orbitStart.equals(orbitPaused),'Orbital motion changes actual pixels');
 await page.waitForTimeout(200);assert(orbitPaused.equals(await page.locator('canvas').screenshot()),'Pause freezes orbital positions');
 await page.screenshot({path:path.join(out,'solar-mobile.png'),fullPage:true});
 await page.emulateMedia({reducedMotion:'reduce'});await mount({...scenes.solar,interaction:{lessonPlaying:true}});
 await page.getByRole('button',{name:'Explorar em 3D',exact:true}).click();await page.waitForFunction(()=>window.getModel3DContext?.('qa','qa')?.scene==='edu-solar');
 assert.equal((await state()).lessonPlaying,false);
 await button('Reproduzir etapas').click();await page.waitForTimeout(100);
 // Visibility pauses the actual WebGL draw loop.
 await page.evaluate(()=>{const h=document.querySelector('#fixture');h.style.height='300px';h.style.overflow='auto';const s=document.createElement('div');s.style.height='3000px';h.append(s);h.scrollTop=3000;});
 await page.waitForTimeout(180);const off=await page.evaluate(()=>__gpu.draws);await page.waitForTimeout(180);assert.equal(await page.evaluate(()=>__gpu.draws),off);
 await page.evaluate(()=>document.querySelector('#fixture').replaceChildren());await page.waitForTimeout(100);
 const cleanup=await page.evaluate(()=>__gpu);assert.equal(cleanup.created,cleanup.deleted);
 assert.deepEqual(errors,[]);
 // Real authenticated chat -> deterministic agent -> SSE -> IndexedDB -> reload.
 await page.emulateMedia({reducedMotion:'no-preference'});await page.setViewportSize({width:1100,height:1000});
 await page.goto(url);await page.locator('#loginUser').fill('preview');await page.locator('#loginPassword').fill('preview-only-2026');await page.locator('#loginButton').click();
 await page.locator('#loginOverlay').waitFor({state:'hidden'});await page.locator('#newChatTop').click();
 async function send(text){await page.locator('#messageInput').fill(text);await page.getByRole('button',{name:'Enviar',exact:true}).click();}
 await send('Mostre um computador em 3D');await page.getByRole('button',{name:'Explorar em 3D',exact:true}).waitFor({timeout:30000});
 await page.getByRole('button',{name:'Explorar em 3D',exact:true}).click();await page.locator('.m3-part').filter({hasText:'Memória RAM'}).click();
 await page.getByText('Mais opções',{exact:true}).click();await button('Ocultar').click();
 await page.evaluate(()=>window.__chatCanvas=document.querySelector('canvas'));
 await send('Separe as peças');await page.locator('.model3d').nth(1).locator('canvas').waitFor();
 await page.waitForTimeout(1000);
 assert(await page.evaluate(()=>document.querySelector('canvas')===__chatCanvas));
 const saved=await page.evaluate(()=>getModel3DContext(currentUid,activeConversation));
 assert.deepEqual(saved.interaction.hidden,['ram']);assert(saved.interaction.exploded);
 await page.reload();await page.getByRole('button',{name:'Explorar em 3D',exact:true}).last().click();await page.waitForSelector('canvas');
 await page.waitForFunction(()=>window.getModel3DContext?.(currentUid,activeConversation));
 const restored=await page.evaluate(()=>getModel3DContext(currentUid,activeConversation));
 assert.deepEqual(restored.interaction,saved.interaction);
 await page.setViewportSize({width:390,height:844});
 if(await page.locator('#drawer').getAttribute('aria-hidden')==='false')await page.locator('#drawerClose').click();
 await page.waitForFunction(()=>document.querySelector('#drawer').getBoundingClientRect().right<=1);
 await page.locator('.model3d').last().evaluate(n=>n.scrollIntoView({block:'end'}));
 await page.screenshot({path:path.join(out,'chat-mobile.png'),fullPage:true});
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));assert.deepEqual(errors,[]);
 fs.writeFileSync(path.join(out,'metrics.json'),JSON.stringify({cleanup,errors,expectedAuth,restored,checks:'raycast, keyboard focus, real pixels, opacity, hide/reveal, isolate, focus, explode, views, steps, speed, pause, reset, canvas/buffer reuse, touch, reduced motion, offscreen, disposal, authenticated SSE, immediate state, IndexedDB reload'},null,2));
 console.log(JSON.stringify({ok:true,cleanup,out}));
})().catch(async e=>{console.error(e);await page?.screenshot({path:path.join(out,'failure.png'),fullPage:true}).catch(()=>{});process.exitCode=1;}).finally(async()=>{await browser?.close();});
