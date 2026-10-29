// Full real application, public network and configured model. Never fixtures.
// Login through the ordinary UI to the disposable local QA account first.
async (page) => {
  if (!/^http:\/\/127\.0\.0\.1:\d+\//.test(page.url())) throw Error('Local QA application required');
  const cases=[],errors=[];
  page.on('pageerror',e=>errors.push(String(e)));
  page.on('console',e=>{if(e.type()==='error')errors.push(e.text());});
  const send=async(name,prompt,timeout=120000)=>{
    const before=await page.locator('.message.ai').count(),start=Date.now();
    await page.getByRole('textbox',{name:'Mensagem',exact:true}).fill(prompt);
    await page.getByRole('button',{name:'Enviar',exact:true}).click();
    const reply=page.locator('.message.ai').nth(before);
    await reply.waitFor({state:'visible',timeout:15000});
    await page.waitForFunction(i=>{
      const el=document.querySelectorAll('.message.ai')[i];
      return el && !!el.querySelector('p,pre,table,h1,h2,.jdui-slot');
    },before,{timeout});
    await page.getByRole('button',{name:'Interromper',exact:true}).waitFor({state:'hidden',timeout});
    const row={name,prompt,elapsed_ms:Date.now()-start,reply:await reply.innerText(),
      links:await reply.locator('a[href]').evaluateAll(els=>els.map(a=>({text:a.innerText,url:a.href})))};
    cases.push(row);return {row,reply};
  };
  await page.getByRole('heading',{name:'Bem-vindo ao Vexx AI.',exact:true}).waitFor({state:'hidden',timeout:15000});
  await page.getByRole('button',{name:'Nova conversa',exact:true}).first().click();
  await page.waitForFunction(()=>document.querySelectorAll('.message.ai').length===0);
  const simple=await send('real-model','Oi Lucas, explique em duas frases o que é uma lista em Python.');
  simple.row.hasAnswer=/lista/i.test(simple.row.reply) && !/indisponível|não consegui/i.test(simple.row.reply);
  const product=await send('shopping','Pesquise uma placa de vídeo RTX 3050 de 6 GB à venda no Brasil. Quero preço e link direto do produto.');
  product.row.cardCount=await product.reply.locator('.jdui-pcard').count();
  product.row.directProductLinks=product.row.links.filter(a=>/kabum\.com\.br\/produto\/\d+\//.test(a.url));
  if(product.row.directProductLinks.length){
    const open=product.reply.getByRole('link',{name:'Abrir oferta ↗',exact:true}).first();
    const quotedPrice=await product.reply.locator('.jdui-ppreco').first().innerText();
    const next=page.context().waitForEvent('page',{timeout:15000});await open.click();
    const detail=await next;
    try{
      await detail.waitForLoadState('domcontentloaded');
      const heading=await detail.locator('h1').first().innerText({timeout:20000});
      const priceConfirmed=await detail.waitForFunction(price=>document.body.innerText.replace(/\s/g,'').includes(price.replace(/\s/g,'')),quotedPrice,{timeout:20000}).then(()=>true,()=>false);
      product.row.openedProduct={url:detail.url(),heading,quotedPrice,priceConfirmed,correctVariant:/3050/.test(heading)&&/6\s*gb/i.test(heading)};
      await detail.screenshot({path:'output/real-ui/product-opened.png'});
    }catch(e){product.row.openedProduct={url:detail.url(),verified:false,error:String(e).slice(0,180)};}
    await detail.close();
    const comparison=await send('product-comparison','Compare as duas primeiras opções, com os preços e as diferenças que você conseguiu confirmar.');
    comparison.row.comparisonCards=await comparison.reply.locator('.jdui-comparison-card').count();
  }
  const deep=await send('deep-research','Faça uma pesquisa profunda comparando asyncio.TaskGroup e asyncio.gather em Python. Verifique cancelamento e tratamento de exceções, com documentação oficial.');
  try{
    const result=page.locator('.message.ai[data-mid$="-result"]').last();
    await result.waitFor({state:'visible',timeout:210000});
    deep.row.result=await result.innerText();
    deep.row.sourceCards=await result.locator('.jdui-research-sources .jdui-srccard').count();
    deep.row.resultLinks=await result.locator('a[href]').evaluateAll(els=>els.map(a=>({text:a.innerText,url:a.href})));
  }catch(e){deep.row.resultError=String(e).slice(0,200);}
  const news=await send('local-news','Quais são as notícias desta semana de Ubatã e região? Traga links das matérias.');
  news.row.sourceCards=await news.reply.locator('.jdui-research-sources .jdui-srccard').count();
  news.row.rawIsoDates=await news.reply.locator('.jdui-ploja').evaluateAll(els=>els.map(e=>e.innerText).filter(t=>/\d{4}-\d{2}-\d{2}T/.test(t)));
  const images=await send('real-images','Pesquise e mostre imagens reais da Ponte Estaiada de São Paulo.');
  images.row.mediaCards=await images.reply.locator('.jdui-media-grid .jdui-pcard').count();
  if(images.row.mediaCards){
    await images.reply.evaluate(el=>el.scrollIntoView({block:'start'}));
    await images.reply.locator('.jdui-pimg').first().waitFor({state:'visible'});
    images.row.imageStates=await images.reply.locator('img').evaluateAll(els=>els.map(i=>({url:i.src,loaded:i.complete&&i.naturalWidth>0})));
    for(let i=0;i<await images.reply.locator('img').count();i++)
      await images.reply.locator('img').nth(i).evaluate(el=>el.scrollIntoView({block:'nearest'}));
    await page.waitForFunction(()=>Array.from(document.querySelectorAll('.message.ai:last-child img')).every(i=>i.complete),null,{timeout:25000}).catch(()=>{});
    images.row.imageStates=await images.reply.locator('img').evaluateAll(els=>els.map(i=>({url:i.src,loaded:i.complete&&i.naturalWidth>0})));
  }
  const geometry=[];
  for(const width of [390,320,1280]){
    await page.setViewportSize({width,height:900});
    const menu=page.getByRole('button',{name:'Abrir menu',exact:true});
    if(width<900 && await menu.getAttribute('aria-expanded')==='true')await page.getByRole('button',{name:'Fechar menu',exact:true}).click();
    await page.waitForFunction(()=>{const r=document.querySelector('.drawer').getBoundingClientRect();return innerWidth>=900 ? Math.abs(r.left)<1 : r.right<=0;});
    await product.reply.locator('.jdui-title').first().evaluate(el=>el.scrollIntoView({block:'start'}));
    const measure=await page.evaluate(()=>({width:innerWidth,documentWidth:document.documentElement.scrollWidth}));
    geometry.push(measure);
    await page.screenshot({path:'output/real-ui/chat-'+width+'.png'});
  }
  const beforeReload={messages:await page.locator('.message').count(),cards:await page.locator('.jdui-pcard,.jdui-srccard').count()};
  await page.reload();
  await page.getByRole('heading',{name:'Bem-vindo ao Vexx AI.',exact:true}).waitFor({state:'hidden',timeout:20000});
  await page.waitForFunction(n=>document.querySelectorAll('.message').length>=n,beforeReload.messages,{timeout:20000});
  const afterReload={messages:await page.locator('.message').count(),cards:await page.locator('.jdui-pcard,.jdui-srccard').count()};
  await page.screenshot({path:'output/real-ui/chat-reloaded.png'});
  return {scope:'FULL_LOCAL_APPLICATION_REAL_PUBLIC_SEARCH_AND_CONFIGURED_FREE_MODEL_NO_FIXTURES',
    cases,errors,geometry,beforeReload,afterReload};
}
