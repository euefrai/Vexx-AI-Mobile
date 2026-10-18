const {chromium}=require('playwright');
const {execFileSync}=require('child_process');
const path=require('path');
const PY=path.resolve('../.venv/Scripts/python.exe');
const scenes=JSON.parse(execFileSync(PY,['-c',"import json;from model3d_catalog import cena;print(json.dumps({k:cena(k) for k in ('xbox','motor_v8','gabinete')}))"],{encoding:'utf8'}));
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 const page=await browser.newPage({viewport:{width:900,height:900}});
 await page.route('**/qa-perf',r=>r.fulfill({contentType:'text/html; charset=utf-8',body:'<!doctype html><meta charset="utf-8"><link rel="stylesheet" href="/interface.css"><main id="fixture"></main><script src="/model3d-schema.js"></script><script src="/jdui.js"></script>'}));
 await page.goto('http://127.0.0.1:8770/qa-perf');await page.waitForFunction(()=>window.JDUI);
 for(const key of Object.keys(scenes)){
  const ms=await page.evaluate(async({p,key})=>{
    const t0=performance.now();
    const host=document.querySelector('#fixture');host.replaceChildren();window.__state={};
    const v=JDUI.validateMessage({version:JDUI.version,blocks:[{type:'ui',component:'model3d',props:p}]});
    if(!v.ok)throw Error(JSON.stringify(v.erros));
    JDUI.mount(host,[v.msg],{ownerId:'perf',conversationId:'perf',messageId:'m-'+key,loadState:()=>window.__state,saveState:(k,s)=>{window.__state=s;}});
    document.querySelector('.m3-start button,#fixture button').click();
    await new Promise(r=>{const id=setInterval(()=>{if(document.querySelector('canvas')&&window.getModel3DContext?.('perf','perf')){clearInterval(id);r();}},16);});
    return performance.now()-t0;
  },{p:scenes[key],key});
  const size=JSON.stringify(scenes[key]).length;
  console.log(key,'mount+start ms=',Math.round(ms),'json bytes=',size);
 }
 await browser.close();
})().catch(e=>{console.error(e);process.exit(1);});
