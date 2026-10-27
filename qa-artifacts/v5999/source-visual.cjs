async page => {
 if(!page.url().startsWith('http://127.0.0.1:57422/'))throw Error('Disposable QA only');
 await page.setViewportSize({width:1280,height:900});
 await page.getByRole('button',{name:/^Pesquisa profunda sobre qual é o peso da Nik/}).click();
 const card=page.locator('.jdui-srccard').filter({hasText:'Nikon Z f Digital Camera'});
 await card.waitFor({state:'visible'});
 const result={scope:'REAL_CHROME_LATE_SOURCE_CARD',viewports:[],text:await card.innerText()};
 for(const width of [1280,390,320]){
  await page.setViewportSize({width,height:900});await card.scrollIntoViewIfNeeded();
  const g=await card.evaluate(n=>{const r=n.getBoundingClientRect();return {viewport:innerWidth,root:document.documentElement.scrollWidth,left:r.left,right:r.right};});
  if(g.root>width||g.left<0||g.right>width)throw Error('Source overflow');
  await card.screenshot({path:`qa-artifacts/v5999/source-card-${width}.png`});result.viewports.push(g);
 }
 await page.reload();await page.locator('#loginOverlay').waitFor({state:'hidden'});
 await card.waitFor({state:'visible'});result.reload_preserved=await card.innerText()===result.text;
 if(!result.reload_preserved)throw Error('Source context not persisted');
 return result;
}
