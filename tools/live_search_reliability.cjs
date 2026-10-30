// Run through playwright-cli after ordinary UI login to a disposable local lab.
// Public network and the configured model only; no provider or result fixtures.
async (page) => {
  if (!/^http:\/\/127\.0\.0\.1:\d+\//.test(page.url())) throw Error('Disposable local QA app required');
  const errors=[],cases=[];
  page.on('pageerror',e=>errors.push(String(e)));
  await page.setViewportSize({width:1280,height:900});
  await page.waitForFunction(()=>Math.abs(document.querySelector('.drawer').getBoundingClientRect().left)<1);
  await page.getByRole('button',{name:'Nova conversa',exact:true}).first().click();
  await page.waitForFunction(()=>document.querySelectorAll('.message.ai').length===0);
  const prompts=[
    'Pesquise uma placa de vídeo RTX 3050 de 6 GB à venda no Brasil. Quero preço e link direto do produto.',
    'Pesquise placas de vídeo com 6 GB de VRAM para comprar no Brasil, com links diretos dos produtos e preços atuais.'
  ];
  for (const prompt of prompts) {
    const before=await page.locator('.message.ai').count(),start=Date.now();
    await page.getByRole('textbox',{name:'Mensagem',exact:true}).fill(prompt);
    await page.getByRole('button',{name:'Enviar',exact:true}).click();
    const reply=page.locator('.message.ai').nth(before);
    await reply.waitFor({state:'visible',timeout:15000});
    await page.waitForFunction(i=>!!document.querySelectorAll('.message.ai')[i]?.querySelector('p,.jdui-slot'),before,{timeout:120000});
    await page.getByRole('button',{name:'Interromper',exact:true}).waitFor({state:'hidden',timeout:120000});
    const cards=await reply.locator('.jdui-pcard').allInnerTexts();
    const links=await reply.getByRole('link',{name:'Abrir oferta ↗',exact:true}).evaluateAll(els=>els.map(a=>a.href));
    cases.push({prompt,elapsed_ms:Date.now()-start,cards,links,answer:await reply.innerText(),
      correctCategory:cards.length>0&&cards.every(t=>/placa.{0,5}v[ií]deo|\bgpu\b|geforce|radeon/i.test(t)&&!/tablet|smartphone|mem[oó]ria ram/i.test(t)),
      sixGB:cards.length>0&&cards.every(t=>/6\s*gb/i.test(t)),directProductLinks:links.length>0&&links.every(u=>/\/produto\/\d+\//.test(u))});
  }
  const open=page.locator('.message.ai').last().getByRole('link',{name:'Abrir oferta ↗',exact:true}).first();
  if (await open.count()) {
    const price=await page.locator('.message.ai').last().locator('.jdui-ppreco').first().innerText();
    const next=page.context().waitForEvent('page',{timeout:15000});await open.click();
    const detail=await next;
    try {
      await detail.waitForLoadState('domcontentloaded');
      const heading=await detail.locator('h1').first().innerText({timeout:20000});
      const priceVisible=await detail.waitForFunction(p=>document.body.innerText.replace(/\s/g,'').includes(p.replace(/\s/g,'')),price,{timeout:20000}).then(()=>true,()=>false);
      cases[cases.length-1].opened={url:detail.url(),heading,price,priceVisible,correctVariant:/6\s*gb/i.test(heading)&&/3050|placa.{0,5}v[ií]deo/i.test(heading)};
      await detail.screenshot({path:'output/search-reliability/product-opened.png',animations:'disabled'});
    } catch(e) {cases[cases.length-1].opened={url:detail.url(),error:String(e).slice(0,250)};}
    await detail.close();
  }
  const geometry=[];
  for (const width of [390,320,1280]) {
    await page.setViewportSize({width,height:900});
    const menu=page.getByRole('button',{name:'Abrir menu',exact:true});
    if(width<900&&await menu.getAttribute('aria-expanded')==='true')await page.keyboard.press('Escape');
    await page.waitForFunction(()=>{const r=document.querySelector('.drawer').getBoundingClientRect();return innerWidth>=900?Math.abs(r.left)<1:r.right<=0;});
    await page.locator('.message.ai').last().evaluate(el=>el.scrollIntoView({block:'start'}));
    geometry.push(await page.evaluate(()=>({width:innerWidth,documentWidth:document.documentElement.scrollWidth})));
    await page.screenshot({path:'output/search-reliability/chat-'+width+'.png',animations:'disabled'});
  }
  const beforeReload={messages:await page.locator('.message').count(),cards:await page.locator('.jdui-pcard').count()};
  await page.reload();
  await page.waitForFunction(n=>document.querySelectorAll('.message').length>=n,beforeReload.messages,{timeout:20000});
  const afterReload={messages:await page.locator('.message').count(),cards:await page.locator('.jdui-pcard').count()};
  return {scope:'REAL_LOCAL_FULL_STACK_PUBLIC_NETWORK_NO_FIXTURES',cases,errors,geometry,beforeReload,afterReload};
}
