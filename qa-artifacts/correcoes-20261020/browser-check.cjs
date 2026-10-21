const {chromium}=require('playwright'),fs=require('fs'),path=require('path'),assert=require('assert');
const out=path.resolve('qa-artifacts/correcoes-20261020');
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 const result={layouts:[],errors:[]};
 try{
  const page=await browser.newPage({viewport:{width:390,height:844}});
  page.on('pageerror',e=>result.errors.push(e.message));
  await page.goto('http://127.0.0.1:8770');
  await page.locator('#loginUser').fill('preview');
  await page.locator('#loginPassword').fill('preview-only-2026');
  await page.locator('#loginButton').click();
  await page.locator('#loginOverlay').waitFor({state:'hidden'});
  await page.waitForFunction(()=>typeof pcOnline!=='undefined' && pcOnline);
  for(const width of [320,390,1280]){
   await page.setViewportSize({width,height:844});
   for(const tab of ['documents','estudos','settings']){
    const open=page.locator('#drawerOpen');
    if(await open.isVisible() && await page.locator('#drawer').getAttribute('aria-hidden')!=='false')await open.click();
    await page.locator('.drawer-nav [data-tab="'+tab+'"]').click();
    await page.locator('#page-'+tab).waitFor({state:'visible'});
    if(width<1000)await page.waitForFunction(()=>document.querySelector('#drawer').getBoundingClientRect().right<=1);
    const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);
    result.layouts.push({width,tab,overflow});assert(!overflow);
    if(width===390 && tab==='settings')await page.screenshot({path:path.join(out,'settings-mobile.png')});
   }
  }
  // Exercise the actual composer and inspect its real network request.
  await page.locator('#newChatCta').click();
  await page.locator('#messageInput').fill('Que horas são agora?');
  const streamResponse=page.waitForResponse(r=>r.url().includes('/api/ai/stream'));
  await page.locator('#messageInput').press('Enter');
  const uiResponse=await streamResponse;
  result.composer={method:uiResponse.request().method(),url:uiResponse.url(),
    status:uiResponse.status()};
  assert.equal(result.composer.method,'POST');assert.equal(result.composer.status,200);
  assert(!result.composer.url.includes('?'));
  await page.waitForFunction(()=>!aiAbort && document.querySelector('#conversation').textContent.includes('São'));
  result.composer.rendered=await page.locator('#conversation').innerText();
  await page.setViewportSize({width:390,height:844});
  await page.waitForFunction(()=>document.querySelector('#drawer').getBoundingClientRect().right<=1);
  await page.screenshot({path:path.join(out,'chat-mobile.png')});
  // Actual renderer from the served application under its actual CSP.
  await page.route('https://audit.invalid/**',route=>{result.unexpectedExternal=true;return route.abort()});
  result.svg=await page.evaluate(async()=>{
   const node=document.createElement('div');document.body.append(node);
   node.innerHTML=renderMarkdown('```svg\n<svg xmlns="http://www.w3.org/2000/svg" width="40" height="40"><rect width="40" height="40" fill="red"/></svg>\n```');
   const img=node.querySelector('img');await img.decode();
   const validImage=img.naturalWidth===40;
   node.innerHTML=renderMarkdown('```svg\n<svg xmlns="http://www.w3.org/2000/svg"></svg><meta http-equiv="refresh" content="0;url=https://audit.invalid/redirect"><script>window.SVG_INJECTED=true</script>\n```');
   const isolated=!node.querySelector('meta,script,svg') && !!node.querySelector('img');
   await new Promise(resolve=>setTimeout(resolve,300));node.remove();
   return {validImage,isolated,scriptExecuted:!!window.SVG_INJECTED};
  });
  assert(result.svg.validImage && result.svg.isolated && !result.svg.scriptExecuted);
  assert(page.url().startsWith('http://127.0.0.1:8770'));
  // Actual POST SSE -> relay -> PC -> SQLite with a deterministic clock request.
  result.stream=await page.evaluate(async()=>{
   const session=await (await fetch('/api/session')).json();
   const id='browser-audit-'+crypto.randomUUID(),conversation_id='browser-clock-'+crypto.randomUUID();
   const body={message_id:id,conversation_id,text:'Que horas são agora?',created_at:new Date().toISOString(),
     timezone:'America/Bahia',local_time:new Date().toISOString(),memory:0};
   const url='/api/ai/stream';
   const response=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':session.csrf},body:JSON.stringify(body)});
   const events=await response.text();
   const history=await (await fetch('/api/messages?conversation_id='+conversation_id)).json();
   return {status:response.status,url:response.url,done:events.includes('event: done'),
     events:events.slice(0,1500),persisted:history.messages.map(m=>({role:m.role,text:m.text}))};
  });
  assert.equal(result.stream.status,200);assert(result.stream.done);
  assert.equal(result.stream.persisted.length,2);assert(!result.stream.url.includes('?'));
  // Clear only this disposable browser's IndexedDB and inspect every affected store.
  result.cache=await page.evaluate(async()=>{
   await clearStorage();workspace.reset();
   const counts={};for(const name of [STORE,SESSIONS,SAVED,UISTATE,META])counts[name]=await reqPromise(db.transaction(name).objectStore(name).count());
   return counts;
  });
  assert(Object.values(result.cache).every(n=>n===0));
  const oldCookie=(await page.context().cookies()).find(c=>c.name==='JULIA_session');
  result.logout=await page.evaluate(async()=>{
   const session=await (await fetch('/api/session')).json();
   const response=await fetch('/api/logout',{method:'POST',headers:{'X-CSRF-Token':session.csrf}});
   return response.status;
  });
  assert.equal(result.logout,200);
  await page.context().addCookies([oldCookie]);
  result.revokedReplay=await page.evaluate(async()=> (await fetch('/api/messages')).status);
  assert.equal(result.revokedReplay,401);assert.deepEqual(result.errors,[]);assert(!result.unexpectedExternal);
  fs.writeFileSync(path.join(out,'browser-check.json'),JSON.stringify(result,null,2));
  console.log(JSON.stringify(result));
 }catch(error){fs.writeFileSync(path.join(out,'browser-check-failure.json'),JSON.stringify({...result,failure:String(error)},null,2));throw error}
 finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
