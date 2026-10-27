async page => {
  if (!page.url().startsWith('http://127.0.0.1:57422/')) throw Error('Disposable QA only');
  await page.setViewportSize({width:1280,height:900});
  const grid=page.locator('.jdui-media-grid');
  if (!await grid.isVisible()) await page.getByText(/^Pesquise imagens da Ponte/).first().click();
  await grid.waitFor({state:'visible'});
  const first=grid.locator('.jdui-media-zoom').first();
  await first.scrollIntoViewIfNeeded();
  const images=await grid.locator('img').evaluateAll(ns=>ns.map(n=>({url:n.src,complete:n.complete,width:n.naturalWidth,loading:n.loading})));
  await first.click();
  const dialog=page.locator('.jdui-image-dialog');await dialog.waitFor({state:'visible'});
  const before=await dialog.locator('.jdui-image-caption').innerText();
  await page.keyboard.press('ArrowRight');
  const after=await dialog.locator('.jdui-image-caption').innerText();
  let fullImageLoaded=false;
  try {await dialog.locator('img').waitFor({state:'visible',timeout:30000});fullImageLoaded=await dialog.locator('img').evaluate(n=>n.complete&&n.naturalWidth>0);} catch {}
  await page.screenshot({path:'qa-artifacts/v5999/gallery-dialog.png'});
  await page.keyboard.press('Escape');
  await dialog.waitFor({state:'detached'});
  const focusRestored=await first.evaluate(n=>n===document.activeElement);
  return {scope:'REAL_CHROME_GALLERY',images,keyboard_navigation:before!==after,escape_closes:true,focus_restored:focusRestored,full_image_loaded:fullImageLoaded};
}
