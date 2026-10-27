async page => {
  if(!page.url().startsWith('http://127.0.0.1:'))throw Error('Loopback QA only');
  const errors=[];const onError=e=>errors.push(e.message);page.on('pageerror',onError);
  const geometry=[];
  async function choose(name){
    await page.setViewportSize({width:1280,height:900});
    await page.getByRole('button',{name}).click();
  }
  async function widths(label,selector){
    for(const width of [1280,390,320]){
      await page.setViewportSize({width,height:900});
      if(width<900 && await page.locator('#drawer').getAttribute('aria-hidden')==='false')await page.locator('#drawerClose').click();
      if(width<900)await page.waitForFunction(()=>document.querySelector('#drawer').getBoundingClientRect().right<=1);
      // Scroll in one DOM turn: periodic sync replaces message nodes during
      // Playwright's stability wait. Do not suppress the application's sync.
      await page.locator(selector).first().evaluate(n=>n.scrollIntoView({block:'center'}));
      const g=await page.locator(selector).first().evaluate(n=>{const r=n.getBoundingClientRect();return {viewport:innerWidth,root:document.documentElement.scrollWidth,left:r.left,right:r.right};});
      await page.screenshot({path:`qa-artifacts/v5910/${label}-${width}.png`});
      if(g.root>width||g.left<-.5||g.right>width+.5)throw Error('Overflow '+JSON.stringify(g));
      geometry.push({label,...g});
    }
  }
  try{
    await choose(/^Pesquisa profunda sobre quem fundou a WEG/);
    await widths('source','.jdui-srccard');
    const source=page.locator('.jdui-srccard');
    const sourceLink=source.getByRole('link',{name:'Abrir fonte ↗',exact:true});
    const popupPending=page.waitForEvent('popup');await sourceLink.click();
    const popup=await popupPending;await popup.waitForLoadState('domcontentloaded');
    const opened=popup.url();await popup.close();
    if(!opened.startsWith('https://en.wikipedia.org/wiki/WEG'))throw Error('Unexpected destination');
    const coverage=page.locator('.message.ai table').first();await coverage.waitFor({state:'visible'});
    const tableText=await coverage.innerText();
    await choose(/^Pesquise imagens da Ponte/);
    await widths('gallery','.jdui-media-grid .jdui-pcard');
    const zoom=page.locator('.jdui-media-zoom:visible').first();await zoom.click();
    const dialog=page.locator('.jdui-image-dialog');await dialog.waitFor({state:'visible'});
    await page.waitForFunction(()=>{const img=document.querySelector('.jdui-image-dialog img');return img&&img.complete&&img.naturalWidth>0&&!img.hidden;},null,{timeout:20000});
    const before=await dialog.locator('.jdui-image-caption').innerText();await page.keyboard.press('ArrowRight');
    const after=await dialog.locator('.jdui-image-caption').innerText();if(before===after)throw Error('Gallery keyboard failed');
    await page.screenshot({path:'qa-artifacts/v5910/gallery-modal.png'});
    await page.keyboard.press('Escape');await dialog.waitFor({state:'detached'});
    const focus=await zoom.evaluate(n=>n===document.activeElement);if(!focus)throw Error('Focus not restored');
    await page.setViewportSize({width:1280,height:900});await page.evaluate(()=>document.body.style.zoom='2');
    const scale=await page.evaluate(()=>({viewport:innerWidth,root:document.documentElement.scrollWidth}));
    await page.screenshot({path:'qa-artifacts/v5910/zoom-200.png'});
    await page.evaluate(()=>document.body.style.zoom='');if(scale.root>scale.viewport)throw Error('Zoom overflow');
    await page.emulateMedia({reducedMotion:'reduce'});
    const motion=await zoom.evaluate(n=>getComputedStyle(n).transitionDuration);await page.emulateMedia({reducedMotion:'no-preference'});
    const details=page.locator('.jdui-media-details').first();await details.locator('summary').click();
    const media=await page.locator('.jdui-media-grid .jdui-pcard').count();await page.reload();
    await page.locator('#loginOverlay').waitFor({state:'hidden'});await details.waitFor({state:'visible'});
    if(!await details.evaluate(n=>n.open))throw Error('Metadata state lost');
    if(await page.locator('.jdui-media-grid .jdui-pcard').count()!==media)throw Error('Media lost');
    await page.context().setOffline(true);let rejected=false;
    try{rejected=await page.evaluate(async()=>{try{await fetch('/api/health');return false;}catch{return true;}});}
    finally{await page.context().setOffline(false);}
    const health=await page.evaluate(async()=>(await fetch('/api/health')).status);
    if(!rejected||health!==200)throw Error('Network negative case failed');
    return {scope:'REAL_CHROME_LIVE_PUBLIC_SOURCES_VIEWPORT_EMULATION_NOT_PHYSICAL_PHONE',geometry,opened_source:opened,
      table_text:tableText,gallery_loaded:true,keyboard:true,focus_restored:focus,zoom:scale,reduced_motion:motion,
      metadata_restored:true,media_cards:media,offline_fetch_rejected:rejected,health_after_reconnect:health,page_errors:errors};
  }finally{await page.context().setOffline(false);await page.evaluate(()=>document.body.style.zoom='');page.removeListener('pageerror',onError);}
}
