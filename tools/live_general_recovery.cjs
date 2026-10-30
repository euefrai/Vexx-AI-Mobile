// Ordinary UI, disposable local account, actual providers and configured model.
async (page) => {
  if (!/^http:\/\/127\.0\.0\.1:\d+\//.test(page.url())) throw Error('Local QA application required');
  const errors=[];
  page.on('pageerror',e=>errors.push(String(e)));
  await page.setViewportSize({width:1280,height:900});
  await page.waitForFunction(()=>Math.abs(document.querySelector('.drawer').getBoundingClientRect().left)<1);
  await page.getByRole('button',{name:'Nova conversa',exact:true}).first().click();
  const prompt='Pesquise o que é estoicismo e explique a distinção entre o que depende de nós e o que não depende.';
  const before=await page.locator('.message.ai').count(),start=Date.now();
  await page.getByRole('textbox',{name:'Mensagem',exact:true}).fill(prompt);
  await page.getByRole('button',{name:'Enviar',exact:true}).click();
  const reply=page.locator('.message.ai').nth(before);
  await reply.waitFor({state:'visible',timeout:15000});
  await page.waitForFunction(i=>!!document.querySelectorAll('.message.ai')[i]?.querySelector('p,.jdui-slot'),before,{timeout:120000});
  await page.getByRole('button',{name:'Interromper',exact:true}).waitFor({state:'hidden',timeout:120000});
  const answer=await reply.innerText();
  const links=await reply.locator('a[href]').evaluateAll(es=>es.map(a=>({text:a.innerText,url:a.href})));
  const sourceCards=await reply.locator('.jdui-research-sources .jdui-srccard').count();
  const beforeReload={messages:await page.locator('.message').count(),sourceCards};
  const geometry=[];
  for(const width of [1280,390]){
    await page.setViewportSize({width,height:900});
    await page.waitForFunction(()=>{const r=document.querySelector('.drawer').getBoundingClientRect();return innerWidth>=900?Math.abs(r.left)<1:r.right<=0;});
    await reply.evaluate(el=>el.scrollIntoView({block:'start'}));
    geometry.push(await page.evaluate(()=>({width:innerWidth,documentWidth:document.documentElement.scrollWidth})));
    await page.screenshot({path:'output/general-recovery/research-'+width+'.png',animations:'disabled'});
  }
  await page.reload();
  await page.waitForFunction(n=>document.querySelectorAll('.message').length>=n,beforeReload.messages,{timeout:20000});
  const afterReload={messages:await page.locator('.message').count(),sourceCards:await page.locator('.message.ai').last().locator('.jdui-research-sources .jdui-srccard').count()};
  return {scope:'REAL_LOCAL_APP_PUBLIC_NETWORK_NO_FIXTURES',prompt,elapsedMs:Date.now()-start,answer,links,sourceCards,
    checks:{hasSources:sourceCards>0,hasTopic:/estoicismo/i.test(answer),hasControlExplanation:/control|depende|virtude/i.test(answer),
      cardsPersisted:sourceCards>0&&afterReload.sourceCards===beforeReload.sourceCards},beforeReload,afterReload,geometry,errors};
}
