// Synthetic local browser probe. All HTTP requests fulfilled in memory.
const {chromium}=require('playwright');
const fs=require('fs');
(async()=>{
 const app=fs.readFileSync('public/app.js','utf8');
 const fn=app.slice(app.indexOf('function sanitizeSvg('),app.indexOf('\nlet pendingJdui'));
 const server=fs.readFileSync('server.py','utf8');
 const csp=server.match(/response.headers\["Content-Security-Policy"\] = "([^"]+)"/)[1];
 const browser=await chromium.launch({channel:'chrome',headless:true});
 try {
  const page=await browser.newPage(); const seen=[];
  await page.route('**/*',async route=>{
   seen.push(route.request().url());
   await route.fulfill({status:200,contentType:'text/html',headers:{'Content-Security-Policy':csp},body:'<!doctype html><div id="bubble"></div>'});
  });
  await page.goto('https://audit.invalid/app');
  await page.evaluate('window.sanitizeSvg = '+fn);
  const output=await page.evaluate(()=>{
   const payload='<svg xmlns="http://www.w3.org/2000/svg"></svg><meta http-equiv="refresh" content="0;url=https://audit.invalid/redirect">';
   const clean=sanitizeSvg(payload);
   document.querySelector('#bubble').innerHTML='<div class="svg-art">'+clean+'</div>';
   return clean;
  });
  await page.waitForURL('https://audit.invalid/redirect',{timeout:3000});
  console.log(JSON.stringify({sanitizerPreservedMeta:output.includes('<meta'),navigated:page.url(),requestsIntercepted:seen},null,2));
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
