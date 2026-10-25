async page => {
  if (!page.url().startsWith('http://127.0.0.1:')) throw Error('Disposable localhost QA only');
  const errors=[],timings=[];
  const onError=e=>errors.push(e.message);
  const onConsole=e=>{if(e.text().startsWith('[chat-timing]'))timings.push(e.text());};
  page.on('pageerror',onError);page.on('console',onConsole);
  try {
    await page.setViewportSize({width:1280,height:900});
    if (!(await page.locator('#newChatCta').isVisible())) await page.locator('#drawerOpen').click();
    await page.locator('#newChatCta').click();
    await page.getByRole('textbox',{name:'Mensagem',exact:true}).fill('Olá, em uma frase curta, explique para que serve uma tabela.');
    const response=page.waitForResponse(r=>r.url().includes('/api/ai/stream')&&r.request().method()==='POST');
    const start=Date.now();await page.getByRole('button',{name:'Enviar',exact:true}).click();
    const stream=await response;
    await page.locator('.message.ai').last().waitFor({state:'visible',timeout:15000});
    await page.locator('#stopGen').waitFor({state:'hidden',timeout:70000});
    const text=await page.locator('.message.ai').last().innerText();
    const stored=await page.locator('.message').evaluateAll(ns=>ns.map(n=>({id:n.dataset.mid,text:JSON.parse(n._renderSignature)[0]})));
    await page.reload();await page.locator('#loginOverlay').waitFor({state:'hidden'});
    await page.locator(`[data-mid="${stored.at(-1).id}"]`).waitFor({state:'visible'});
    const restored=await page.locator('.message').evaluateAll(ns=>ns.map(n=>({id:n.dataset.mid,text:JSON.parse(n._renderSignature)[0]})));
    if(JSON.stringify(stored)!==JSON.stringify(restored))throw Error('Chat persistence changed after reload');
    return {scope:'REAL_FREE_MODEL_COMMON_CHAT_LOCAL_CHROME',http_status:stream.status(),content_type:stream.headers()['content-type'],
      seconds:(Date.now()-start)/1000,message_count:stored.length,unique_ids:new Set(stored.map(m=>m.id)).size,
      reload_preserved:true,text,timings,page_errors:errors};
  } finally {page.removeListener('pageerror',onError);page.removeListener('console',onConsole);}
}
