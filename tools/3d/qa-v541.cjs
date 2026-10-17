/* V5.4.1: roteamento e execução 3D — pedidos exatos do usuário no Chrome real.
   Rode tests/preview_workspace.py primeiro (LLM indisponível de propósito: HERMES morte).
   Uso: node tools/3d/qa-v541.cjs  (a partir da raiz do repositório) */
const {chromium}=require('playwright');
const fs=require('fs'),path=require('path'),assert=require('assert/strict');
const out=path.resolve('qa-artifacts/3d-v541');fs.mkdirSync(out,{recursive:true});
const url='http://127.0.0.1:8770';let browser,page;
const ASCII=/[┌┐└┘├┤┬┴┼─│╔╗╚╝║═╠╣╦╩╬█▀▄▌▐░▒▓]/;
(async()=>{
 browser=await chromium.launch({channel:'chrome',headless:true});
 const context=await browser.newContext({viewport:{width:1100,height:1000}}),errors=[],expectedAuth=[];
 await context.addInitScript(()=>{
   window.__gpu={draws:0};
   const p=WebGL2RenderingContext.prototype,original=p.drawElements;
   p.drawElements=function(...args){__gpu.draws++;return original.apply(this,args);};
 });
 page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
 page.on('console',m=>{if(m.type()==='error'){
   if(m.location().url===url+'/api/session' && m.text().includes('401'))expectedAuth.push(m.text());
   else errors.push(m.text()+' '+m.location().url);
 }});
 await page.goto(url);await page.locator('#loginUser').fill('preview');
 await page.locator('#loginPassword').fill('preview-only-2026');await page.locator('#loginButton').click();
 await page.locator('#loginOverlay').waitFor({state:'hidden'});await page.locator('#newChatTop').click();
 async function send(text){await page.locator('#messageInput').fill(text);await page.getByRole('button',{name:'Enviar',exact:true}).click();}
 async function aguardarCards(n){await page.waitForFunction(x=>document.querySelectorAll('.model3d').length>x,n,{timeout:30000});}
 async function abrir(card){
   const btn=card.getByRole('button',{name:'Explorar em 3D',exact:true});
   if(await btn.isVisible().catch(()=>false))await btn.click();
   await page.waitForSelector('canvas');
   await page.waitForFunction(()=>window.getModel3DContext?.(currentUid,activeConversation));
 }
 const estado=()=>page.evaluate(()=>getModel3DContext(currentUid,activeConversation));
 const semAscii=async(rotulo)=>{
   const texto=await page.locator('#conversation').innerText();
   assert(!ASCII.test(texto),`Arte ASCII no chat (${rotulo})`);
   assert.equal(await page.locator('#conversation pre').count(),0,`Bloco de código inesperado (${rotulo})`);
 };

 /* 1) "Lucas, mostre um computador em 3D." — cena determinística, sem ASCII. */
 await send('Lucas, mostre um computador em 3D.');
 await aguardarCards(0);
 const card1=page.locator('.model3d').last();
 await card1.getByRole('button',{name:'Explorar em 3D',exact:true}).waitFor({timeout:30000});
 assert.match(await page.locator('#conversation').innerText(),/Cena educativa preparada/);
 await semAscii('pedido exato');
 await abrir(card1);

 /* Canvas WebGL2 real + draw calls. */
 assert(await page.evaluate(()=>!!document.querySelector('canvas').getContext('webgl2')),'Canvas sem WebGL2');
 await page.waitForTimeout(300);
 const draws0=await page.evaluate(()=>__gpu.draws);assert(draws0>0,'Nenhum draw call WebGL');
 const ctx1=await estado();assert.equal(ctx1.scene,'edu-computer');

 /* Rotação real por arrasto; zoom real por scroll. */
 const box=await page.locator('canvas').first().boundingBox();
 const rot0=ctx1.rotation[1];
 await page.mouse.move(box.x+box.width/2,box.y+box.height/2);
 await page.mouse.down();await page.mouse.move(box.x+box.width/2+90,box.y+box.height/2+30,{steps:6});await page.mouse.up();
 await page.waitForTimeout(250);
 const rot1=(await estado()).rotation[1];
 assert(Math.abs(rot1-rot0)>0.05,'Arrasto deve girar a cena');
 const dist0=(await estado()).distance;
 await page.mouse.wheel(0,120);await page.waitForTimeout(150);
 const dist1=(await estado()).distance;
 assert(dist1>dist0+0.1,'Scroll deve ampliar (zoom)');

 /* Seleção de parte real. */
 await page.locator('.m3-part').filter({hasText:'Processador'}).click();
 assert.equal((await estado()).interaction.selected,'cpu','Seleção de parte via toque/clique');
 await page.locator('.model3d').first().evaluate(n=>n.scrollIntoView({block:'center'}));
 await page.waitForTimeout(400);
 await page.screenshot({path:path.join(out,'chat-canvas.png'),fullPage:false});

 /* 2) "Isso não está em 3D, reconstrua em 3D, por favor." — rebuild determinístico. */
 await send('Isso não está em 3D, reconstrua em 3D, por favor.');
 await aguardarCards(1);
 assert.match(await page.locator('#conversation').innerText(),/Cena reconstruída em 3D/);
 await semAscii('continuação exata');
 await abrir(page.locator('.model3d').last());
 assert.equal((await estado()).scene,'edu-computer');

 /* 2b) Variação da correção do usuário: "faça em 3D de verdade". */
 await send('Isso não é 3D, faça em 3D de verdade.');
 await aguardarCards(2);
 await semAscii('variação de correção');
 assert.equal((await estado()).scene,'edu-computer');

 /* 3) Reload: cena persiste e reabre. */
 await page.reload();
 await page.locator('#loginOverlay').waitFor({state:'hidden'}).catch(()=>{});
 await page.waitForFunction(()=>document.querySelectorAll('.model3d').length>=3,{timeout:30000});
 await abrir(page.locator('.model3d').last());
 const restaurado=await estado();
 assert.equal(restaurado.scene,'edu-computer');

 /* 4) Mobile: sem overflow horizontal. */
 await page.setViewportSize({width:390,height:844});
 if(await page.locator('#drawer').getAttribute('aria-hidden')==='false')await page.locator('#drawerClose').click();
 await page.waitForFunction(()=>document.querySelector('#drawer').getBoundingClientRect().right<=1);
 await page.locator('.model3d').last().evaluate(n=>n.scrollIntoView({block:'end'}));
 await page.screenshot({path:path.join(out,'chat-mobile.png'),fullPage:true});
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 assert.deepEqual(errors,[]);
 fs.writeFileSync(path.join(out,'metrics.json'),JSON.stringify({cards:3,draws:draws0,rotationDelta:rot1-rot0,
   distance:{antes:dist0,depois:dist1},restaurado:{scene:restaurado.scene,interaction:restaurado.interaction},
   errors,expectedAuth,checks:'pedido exato -> cena edu-computer, continuação exata -> rebuild, variação correção, sem ASCII/bloco de código, WebGL2 real com draws, arrasto gira, scroll amplia, seleção de parte, reload restaura, mobile sem overflow, LLM indisponível (preview)'},null,2));
 console.log(JSON.stringify({ok:true,cards:3,draws:draws0,out}));
})().catch(async e=>{console.error(e);await page?.screenshot({path:path.join(out,'failure.png'),fullPage:true}).catch(()=>{});process.exitCode=1;}).finally(async()=>{await browser?.close();});
