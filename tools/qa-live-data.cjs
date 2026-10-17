/* Live APIs + Chrome + disposable preview only. No provider responses mocked. */
const {chromium}=require('playwright');
const fs=require('fs'),path=require('path'),assert=require('assert/strict');
const out=path.resolve('qa-artifacts/live-data');fs.mkdirSync(out,{recursive:true});
let browser,page;
(async()=>{
 browser=await chromium.launch({channel:'chrome',headless:true});
 const context=await browser.newContext({viewport:{width:1100,height:900},timezoneId:'America/Bahia'});
 page=await context.newPage();const errors=[],results=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('http://127.0.0.1:8770');
 await page.locator('#loginUser').fill('preview');await page.locator('#loginPassword').fill('preview-only-2026');
 await page.locator('#loginButton').click();await page.locator('#loginOverlay').waitFor({state:'hidden'});
 await page.locator('#newChatTop').click();
 async function send(text,expected){
   const count=await page.locator('.message.ai').count(),start=Date.now();
   await page.locator('#messageInput').fill(text);await page.getByRole('button',{name:'Enviar',exact:true}).click();
   await page.waitForFunction(({count,expected})=>{
     const rows=[...document.querySelectorAll('.message.ai')];
     return rows.length===count+1 && rows.at(-1).textContent.includes(expected) && !rows.at(-1).classList.contains('failed');
   },{count,expected},{timeout:45000});
   results.push({question:text,elapsedMs:Date.now()-start,answer:await page.locator('.message.ai').last().innerText()});
 }
 await send('Qual o clima agora?','em qual cidade');
 await send('Salvador, Bahia','Open-Meteo');
 assert.match(results.at(-1).answer,/\d+(?:[.,]\d+)? °C/);
 await send('Vai chover amanhã em Salvador, Bahia?','Chance de chuva');
 assert(await page.locator('.message.ai').last().locator('table').count());
 await send('Que horas são em Tóquio, Japão?','Asia/Tokyo');
 await send('Qual a data de hoje?','America/Bahia');
 await send('Quais as notícias de hoje?','Manchetes e datas publicadas');
 assert((await page.locator('.message.ai').last().locator('a[href^="http"]').count())>0);
 await page.screenshot({path:path.join(out,'news-desktop.png'),fullPage:true});
 await page.reload();await page.waitForFunction(()=>document.querySelectorAll('.message.ai').length===6);
 await page.setViewportSize({width:390,height:844});
 if(await page.locator('#drawer').getAttribute('aria-hidden')==='false')await page.locator('#drawerClose').click();
 await page.waitForFunction(()=>document.querySelector('#drawer').getBoundingClientRect().right<=1);
 await page.locator('.message.ai').nth(1).evaluate(n=>n.scrollIntoView({block:'start'}));
 await page.screenshot({path:path.join(out,'weather-mobile.png'),fullPage:true});
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 assert.deepEqual(errors,[]);
 fs.writeFileSync(path.join(out,'results.json'),JSON.stringify({testedAt:new Date().toISOString(),results,errors,reloadMessages:6},null,2));
 console.log(JSON.stringify({ok:true,results:results.map(({question,elapsedMs})=>({question,elapsedMs})),out}));
})().catch(async e=>{console.error(e);await page?.screenshot({path:path.join(out,'failure.png'),fullPage:true}).catch(()=>{});process.exitCode=1;}).finally(async()=>{await browser?.close();});
