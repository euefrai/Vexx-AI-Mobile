/* Real weather API, installed Chrome, disposable preview on port 8770. */
const {chromium}=require('playwright');
const fs=require('fs'),path=require('path'),assert=require('assert/strict');
const out=path.resolve('qa-artifacts/followups');fs.mkdirSync(out,{recursive:true});
let browser,page;
(async()=>{
 browser=await chromium.launch({channel:'chrome',headless:true});
 page=await browser.newPage({viewport:{width:390,height:844},timezoneId:'America/Bahia'});
 const errors=[],results=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('http://127.0.0.1:8770');
 await page.locator('#loginUser').fill('preview');await page.locator('#loginPassword').fill('preview-only-2026');
 await page.locator('#loginButton').click();await page.locator('#loginOverlay').waitFor({state:'hidden'});
 await page.locator('#drawerOpen').click();
 await page.locator('#newChatCta').click();
 await page.waitForFunction(()=>document.querySelector('#drawer').getBoundingClientRect().right<=1);
 async function send(text){
   const count=await page.locator('.message.ai').count(),start=Date.now();
   await page.locator('#messageInput').fill(text);await page.getByRole('button',{name:'Enviar',exact:true}).click();
   await page.waitForFunction(count=>{
     const rows=[...document.querySelectorAll('.message.ai')];
     return rows.length===count+1 && rows.at(-1).textContent.includes('Open-Meteo');
   },count,{timeout:45000});
   const answer=await page.locator('.message.ai').last().innerText();
   assert.match(answer,/Salvador/);
   results.push({question:text,elapsedMs:Date.now()-start,answer});
 }
 await send('Qual o clima agora em Salvador, Bahia?');
 await send('E amanhã?');
 assert(await page.locator('.message.ai').last().locator('table').count());
 await send('E no fim de semana?');
 assert(await page.locator('.message.ai').last().locator('table').count());
 await page.reload();await page.waitForFunction(()=>document.querySelectorAll('.message.ai').length===3);
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 await page.screenshot({path:path.join(out,'weather-mobile.png'),fullPage:true});
 assert.deepEqual(errors,[]);
 fs.writeFileSync(path.join(out,'results.json'),JSON.stringify({testedAt:new Date().toISOString(),results,errors,reloadMessages:3},null,2));
 console.log(JSON.stringify({ok:true,results:results.map(({question,elapsedMs})=>({question,elapsedMs})),out}));
})().catch(async e=>{console.error(e);await page?.screenshot({path:path.join(out,'failure.png'),fullPage:true}).catch(()=>{});process.exitCode=1;}).finally(async()=>{await browser?.close();});
