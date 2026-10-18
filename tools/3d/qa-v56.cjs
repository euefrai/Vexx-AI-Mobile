/* V5.6 real Chrome + WebGL QA: catálogo, grupos/conexões, cena de pesquisa e chat durável.
   Rodar da raiz do repositório com tests/preview_workspace.py ativo na 8770. */
const {chromium}=require('playwright');
const fs=require('fs'),path=require('path'),assert=require('assert/strict'),{execFileSync}=require('child_process');
const PY=path.resolve('../.venv/Scripts/python.exe');
function py(code){return JSON.parse(execFileSync(PY,['-c',code],{encoding:'utf8'}));}
const scenes=py("import json;from model3d_catalog import cena;print(json.dumps({k:cena(k) for k in ('xbox','gabinete')}))");
// Cena de pesquisa gerada com busca falsa: determinística e sem rede.
scenes.aproximado=py([
  "import json",
  "import model3d_research as mr",
  "mr.limpar_cache()",
  "def fake(consulta,limite):",
  "    return [{'titulo':'Aspirador robô 32,5 x 32,5 x 9,7 cm','url':'https://exemplo.com/ficha','trecho':'Dimensões: 32,5 x 32,5 x 9,7 cm.'}]",
  "print(json.dumps(mr.gerar('aspirador de robo',buscar=fake)))"].join('\n'));
const externos=scenes.xbox.objects.filter(o=>o.group==='external').map(o=>o.id);
const internos=scenes.xbox.objects.filter(o=>o.group==='internal').map(o=>o.id);
const out=path.resolve('qa-artifacts/3d-v56');fs.mkdirSync(out,{recursive:true});
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
 await page.route('**/qa-v56',r=>r.fulfill({contentType:'text/html; charset=utf-8',body:'<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="/styles.css"><link rel="stylesheet" href="/interface.css"><style>html,body{height:auto;overflow:auto}#fixture{max-width:760px;margin:auto}</style><main id="fixture"></main><script src="/model3d-schema.js"></script><script src="/jdui.js"></script>'}));
 await page.goto(url+'/qa-v56');await page.waitForFunction(()=>window.JDUI);
 async function mount(p){await page.evaluate(({p})=>{
   const host=document.querySelector('#fixture');host.replaceChildren();window.__state={};
   const validated=JDUI.validateMessage({version:JDUI.version,blocks:[{type:'ui',component:'model3d',props:p}]});
   if(!validated.ok)throw Error(JSON.stringify(validated.erros));
   window.__mountCount=(window.__mountCount||0)+1;
   JDUI.mount(host,[validated.msg],{ownerId:'qa',conversationId:'qa',messageId:'qa-message-'+__mountCount,loadState:()=>__state,saveState:(k,s)=>{window.__state=s;}});
 },{p});}
 const state=()=>page.evaluate(()=>getModel3DContext('qa','qa').interaction);
 const status=()=>page.locator('.m3-status').last().textContent();
 const button=name=>page.locator('.m3-live').getByRole('button',{name,exact:true}).last();

 // 1) Cena de catálogo: selo, grupos, conexões e pixels reais.
 await mount(scenes.xbox);
 await page.locator('.m3-chip').filter({hasText:'Modelo aproximado'}).first().waitFor();
 await page.getByText('Cena educativa',{exact:true}).first().waitFor();
 await page.getByRole('button',{name:'Explorar em 3D',exact:true}).click();
 await page.waitForSelector('canvas');
 await page.waitForFunction(()=>window.getModel3DContext?.('qa','qa'));
 await page.getByText('Mais opções',{exact:true}).click();
 await button('Ver só internas').click();
 assert.deepEqual([...(await state()).hidden].sort(),[...externos].sort(),'Ver só internas esconde externas');
 assert.equal(await status(),'Exibindo apenas as peças internas.');
 await page.waitForTimeout(300);
 const soInternas=await page.locator('canvas').screenshot();
 await button('Ver só externas').click();
 assert.deepEqual([...(await state()).hidden].sort(),[...internos].sort(),'Ver só externas esconde internas');
 await page.waitForTimeout(300);
 assert(!soInternas.equals(await page.locator('canvas').screenshot()),'Grupos mudam os pixels renderizados');
 await button('Revelar tudo').click();
 await page.locator('.m3-part').filter({hasText:'Corpo'}).first().click();
 await button('Ver conexões').click();
 assert.match(await status(),/^Corpo se conecta a: Grade superior, Porta USB, Botão de energia\.$/);
 const antesExplodir=await page.locator('canvas').screenshot();
 await button('Separar peças').click();assert((await state()).exploded);
 await page.waitForTimeout(400);
 assert(!antesExplodir.equals(await page.locator('canvas').screenshot()),'Explodir muda os pixels');
 await page.locator('.model3d').screenshot({path:path.join(out,'xbox-desktop.png')});
 const draws=await page.evaluate(()=>__gpu.draws);assert(draws>0,'WebGL desenhou de verdade');

 // 2) Cena aproximada por pesquisa: rótulo, fonte visível e interação.
 await mount(scenes.aproximado);
 await page.getByRole('button',{name:'Explorar em 3D',exact:true}).click();
 await page.waitForFunction(id=>window.getModel3DContext?.('qa','qa')?.scene===id,scenes.aproximado.id);
 await page.locator('.m3-chip').filter({hasText:'Modelo aproximado'}).first().waitFor();
 await page.getByText(/Aproximado por referências públicas/).first().waitFor();
 await page.getByText(/não é CAD|Não é CAD/).first().waitFor();
 await page.getByText('Mais opções',{exact:true}).click();
 await page.locator('.m3-part').filter({hasText:'Corpo'}).first().click();
 await button('Focar').click();
 await page.waitForTimeout(300);
 await page.locator('.model3d').screenshot({path:path.join(out,'aproximado-desktop.png')});
 await page.evaluate(()=>document.querySelector('#fixture').replaceChildren());
 await page.waitForTimeout(150);
 const cleanup=await page.evaluate(()=>__gpu);assert.equal(cleanup.created,cleanup.deleted,'Buffers WebGL liberados na limpeza');
 assert.deepEqual(errors,[]);

 // 3) Chat real: pedido de dispositivo, continuação por grupo e estado durável.
 await page.goto(url);await page.locator('#loginUser').fill('preview');await page.locator('#loginPassword').fill('preview-only-2026');await page.locator('#loginButton').click();
 await page.locator('#loginOverlay').waitFor({state:'hidden'});await page.locator('#newChatTop').click();
 async function send(text){await page.locator('#messageInput').fill(text);await page.getByRole('button',{name:'Enviar',exact:true}).click();}
 await send('me mostre um Xbox Series S em 3D');
 await page.getByRole('button',{name:'Explorar em 3D',exact:true}).last().waitFor({timeout:30000});
 await page.getByRole('button',{name:'Explorar em 3D',exact:true}).last().click();
 await page.waitForSelector('canvas');
 await page.getByText('Mais opções',{exact:true}).last().click();
 await page.locator('.m3-part').filter({hasText:'Corpo'}).first().click();
 await page.locator('.m3-live').getByRole('button',{name:'Ver conexões',exact:true}).last().click();
 assert.match(await page.locator('.m3-status').last().textContent(),/se conecta a:/);
 await page.evaluate(()=>window.__chatCanvas=document.querySelector('canvas'));
 await send('mostre apenas as peças internas');
 await page.locator('.model3d').nth(1).locator('canvas').waitFor();
 await page.waitForTimeout(1000);
 assert(await page.evaluate(()=>document.querySelector('canvas')===__chatCanvas),'Chat reusa canvas/buffers');
 const saved=await page.evaluate(()=>getModel3DContext(currentUid,activeConversation));
 assert.deepEqual([...saved.interaction.hidden].sort(),[...externos].sort(),'Continuação por grupo persistida');
 await page.reload();
 await page.getByRole('button',{name:'Explorar em 3D',exact:true}).last().click();await page.waitForSelector('canvas');
 await page.waitForFunction(()=>window.getModel3DContext?.(currentUid,activeConversation));
 const restored=await page.evaluate(()=>getModel3DContext(currentUid,activeConversation));
 assert.deepEqual(restored.interaction,saved.interaction,'Estado restaurado após reload');
 await page.setViewportSize({width:390,height:844});
 if(await page.locator('#drawer').getAttribute('aria-hidden')==='false')await page.locator('#drawerClose').click();
 await page.waitForFunction(()=>document.querySelector('#drawer').getBoundingClientRect().right<=1);
 await page.locator('.model3d').last().evaluate(n=>n.scrollIntoView({block:'end'}));
 await page.screenshot({path:path.join(out,'chat-device-mobile.png'),fullPage:true});
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 assert.deepEqual(errors,[]);
 fs.writeFileSync(path.join(out,'metrics.json'),JSON.stringify({cleanup,draws,errors,expectedAuth,restored,checks:'catalogo local, selo de fidelidade, ver-so-internas/externas com pixels reais, ver conexoes, explodir com pixels, cena aproximada por pesquisa com fonte visivel, limpeza de buffers, chat de dispositivo, continuacao por grupo, canvas reutilizado, estado restaurado no reload, mobile sem overflow'},null,2));
 console.log(JSON.stringify({ok:true,cleanup,draws,out}));
})().catch(async e=>{console.error(e);await page?.screenshot({path:path.join(out,'failure.png'),fullPage:true}).catch(()=>{});process.exitCode=1;}).finally(async()=>{await browser?.close();});
