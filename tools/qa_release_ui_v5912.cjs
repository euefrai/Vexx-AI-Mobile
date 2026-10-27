async page => {
  if(!page.url().startsWith('http://127.0.0.1:'))throw Error('Loopback QA only');
  await page.setViewportSize({width:1280,height:900});
  await page.getByRole('button',{name:/^Pesquisa profunda sobre quem fundou a Gerdau/}).click();
  const geometry=[];
  for(const width of [1280,390,320]){
    await page.setViewportSize({width,height:900});
    if(width<900&&await page.locator('#drawer').getAttribute('aria-hidden')==='false')await page.locator('#drawerClose').click();
    if(width<900)await page.waitForFunction(()=>document.querySelector('#drawer').getBoundingClientRect().right<=1);
    const card=page.locator('.jdui-srccard').first();await card.evaluate(n=>n.scrollIntoView({block:'center'}));
    const g=await card.evaluate(n=>{const r=n.getBoundingClientRect();return {viewport:innerWidth,root:document.documentElement.scrollWidth,left:r.left,right:r.right};});
    if(g.root>width||g.left<-.5||g.right>width+.5)throw Error('Overflow');geometry.push(g);
    await page.screenshot({path:`qa-artifacts/v5912/release-source-${width}.png`});
  }
  const link=page.locator('.jdui-srccard').first().getByRole('link',{name:'Abrir fonte ↗',exact:true});
  const before=await link.getAttribute('href');const pending=page.waitForEvent('popup');await link.click();
  const popup=await pending;await popup.waitForLoadState('domcontentloaded');const opened=popup.url();await popup.close();
  if(!opened.startsWith('https://'))throw Error('Source did not open over HTTPS');
  return {scope:'REAL_CHROME_VIEWPORT_EMULATION_NOT_PHYSICAL_PHONE',geometry,source_href:before,opened};
}
