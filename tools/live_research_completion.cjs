// Real local application, public discovery/reading and the configured model.
async(page)=>{
  if(!/^http:\/\/127\.0\.0\.1:\d+\//.test(page.url()))throw Error('Local QA required');
  const errors=[];page.on('pageerror',e=>errors.push(String(e)));
  page.on('console',e=>{if(e.type()==='error')errors.push(e.text());});
  await page.setViewportSize({width:1280,height:900});
  await page.waitForFunction(()=>Math.abs(document.querySelector('.drawer').getBoundingClientRect().left)<1);
  await page.getByRole('button',{name:'Nova conversa',exact:true}).first().click();
  const prompt='Faça uma pesquisa profunda comparando asyncio.TaskGroup e asyncio.gather em Python. Verifique cancelamento e tratamento de exceções, com documentação oficial.';
  const start=Date.now();
  await page.getByRole('textbox',{name:'Mensagem',exact:true}).fill(prompt);
  await page.getByRole('button',{name:'Enviar',exact:true}).click();
  const result=page.locator('.message.ai[data-mid$="-result"]').last();
  await result.waitFor({state:'visible',timeout:210000});
  await page.getByRole('button',{name:'Interromper',exact:true}).waitFor({state:'hidden',timeout:10000});
  const answer=await result.innerText();
  const sources=await result.locator('.jdui-research-sources .jdui-srccard').count();
  const links=await result.locator('a[href]').evaluateAll(els=>els.map(a=>({text:a.innerText,url:a.href})));
  const before={messages:await page.locator('.message').count(),sources};
  for(const width of [1280,390]){
    await page.setViewportSize({width,height:900});
    await page.waitForFunction(()=>{const r=document.querySelector('.drawer').getBoundingClientRect();return innerWidth>=900?Math.abs(r.left)<1:r.right<=0;});
    await result.evaluate(el=>el.scrollIntoView({block:'start'}));
    await page.screenshot({path:'output/synthesis-completion/research-'+width+'.png',animations:'disabled'});
  }
  await page.reload();
  await page.locator('.message.ai[data-mid$="-result"]').last().waitFor({state:'visible',timeout:20000});
  const after={messages:await page.locator('.message').count(),sources:await page.locator('.message.ai[data-mid$="-result"]').last().locator('.jdui-srccard').count()};
  return {scope:'REAL_LOCAL_RESEARCH_NO_FIXTURES',prompt,elapsedMs:Date.now()-start,answer,sources,links,
    assisted:/Redação assistida por IA/.test(answer),beforeReload:before,afterReload:after,errors};
}
