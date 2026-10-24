async page => {
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.setViewportSize({width:1280,height:900});
  if(!(await page.locator('#newChatCta').isVisible()))await page.locator('#drawerOpen').click();
  await page.getByRole('button',{name:/^Pesquise imagens da Ponte/}).click();
  const cards=page.locator('.message.ai .jdui-media-grid .jdui-pcard');
  await cards.first().waitFor({state:'visible'});
  const geometry=[];
  for(const width of [1280,390,320]){
    await page.setViewportSize({width,height:900});
    if(width<900 && await page.locator('#drawer').getAttribute('aria-hidden')==='false')await page.locator('#drawerClose').click();
    await cards.first().scrollIntoViewIfNeeded();
    const dimensions=await page.evaluate(()=>({viewport:innerWidth,root:document.documentElement.scrollWidth,
      cards:[...document.querySelectorAll('.message.ai .jdui-media-grid .jdui-pcard')].map(c=>Math.round(c.getBoundingClientRect().width))}));
    await page.screenshot({path:`qa-artifacts/v599/research-${width}.png`});
    if(dimensions.root>width)throw Error('Overflow '+JSON.stringify(dimensions));
    geometry.push(dimensions);
  }
  const zoom=page.locator('.jdui-media-zoom:visible').first();await zoom.click();
  await page.getByRole('dialog').waitFor({state:'visible'});
  const before=await page.locator('.jdui-image-caption').innerText();
  await page.getByRole('button',{name:'Próxima imagem',exact:true}).click();
  const after=await page.locator('.jdui-image-caption').innerText();
  if(before===after)throw Error('Next image did not change selection');
  await page.keyboard.press('ArrowLeft');
  if(await page.locator('.jdui-image-caption').innerText()!==before)throw Error('Arrow navigation failed');
  await page.screenshot({path:'qa-artifacts/v599/research-modal.png'});
  await page.keyboard.press('Escape');await page.getByRole('dialog').waitFor({state:'detached'});
  if(!(await zoom.evaluate(b=>b===document.activeElement)))throw Error('Focus was not restored');
  await page.evaluate(()=>document.body.style.zoom='2');
  const scale=await page.evaluate(()=>({viewport:innerWidth,root:document.documentElement.scrollWidth}));
  await page.screenshot({path:'qa-artifacts/v599/research-zoom-200.png'});
  if(scale.root>scale.viewport)throw Error('Overflow at CSS 200%');
  await page.evaluate(()=>document.body.style.zoom='');
  await page.emulateMedia({reducedMotion:'reduce'});
  const transition=await zoom.evaluate(b=>getComputedStyle(b).transitionDuration);
  await page.emulateMedia({reducedMotion:'no-preference'});
  const mediaBefore=await cards.count();await page.reload();
  await page.locator('#loginOverlay').waitFor({state:'hidden'});await cards.first().waitFor({state:'visible'});
  if(await cards.count()!==mediaBefore)throw Error('Gallery changed after reload');
  return {scope:'Real authenticated local chat, live retrieved Commons media; no fixture gallery',geometry,scale,
    next:true,arrows:true,escape:true,focus_restored:true,reload:true,reduced_motion_transition:transition,
    loaded_images:await page.locator('.message.ai').last().evaluate(el=>[...el.querySelectorAll('img')].filter(i=>i.complete&&i.naturalWidth>0).length),
    errors};
}
