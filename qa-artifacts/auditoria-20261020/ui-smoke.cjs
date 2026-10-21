const {chromium}=require('playwright'),fs=require('fs'),path=require('path');
const out=path.resolve('qa-artifacts/auditoria-20261020');
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:390,height:844}});
  const errors=[],checks=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('http://127.0.0.1:8770');
  await page.locator('#loginUser').fill('preview');
  await page.locator('#loginPassword').fill('preview-only-2026');
  await page.locator('#loginButton').click();
  await page.locator('#loginOverlay').waitFor({state:'hidden'});
  for(const width of [390,320,1280]){
   await page.setViewportSize({width,height:844});
   for(const tab of ['documents','estudos','settings']){
    const open=page.locator('#drawerOpen');
    if(await open.isVisible() && await page.locator('#drawer').getAttribute('aria-hidden')!=='false')await open.click();
    await page.locator('.drawer-nav [data-tab="'+tab+'"]').click();
    await page.locator('#page-'+tab).waitFor({state:'visible'});
    if(width<1000)await page.waitForFunction(()=>document.querySelector('#drawer').getBoundingClientRect().right<=1);
    checks.push({width,tab,overflow:await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)});
    if(width===390 && tab==='settings')await page.screenshot({path:path.join(out,'settings-mobile.png')});
   }
  }
  fs.writeFileSync(path.join(out,'ui-smoke.json'),JSON.stringify({checks,errors},null,2));
  console.log(JSON.stringify({checks,errors}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
