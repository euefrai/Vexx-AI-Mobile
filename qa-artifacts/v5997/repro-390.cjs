async page => {
 if(!page.url().startsWith('http://127.0.0.1:'))throw Error('QA only');
 await page.emulateMedia({reducedMotion:'no-preference'});
 const card=page.locator('.message.ai').last().locator('.jdui-readonly');
 await page.setViewportSize({width:1280,height:900});
 await page.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));
 await page.setViewportSize({width:390,height:900});
 const measure=()=>page.evaluate(()=>{
  const card=document.querySelector('.message.ai:last-child .jdui-readonly')||[...document.querySelectorAll('.message.ai .jdui-readonly')].at(-1);
  const drawer=document.querySelector('.drawer');
  const rect=el=>{const r=el?.getBoundingClientRect();return r?{x:r.x,right:r.right,width:r.width}:null};
  return {viewport:innerWidth,root:document.documentElement.scrollWidth,card:rect(card),drawer:rect(drawer),
    animations:document.getAnimations().map(a=>({target:a.effect?.target?.className,playState:a.playState,iterations:a.effect?.getTiming().iterations}))};
 });
 const immediate=await measure();
 await page.evaluate(async()=>{await document.fonts.ready;await Promise.all(document.getAnimations().filter(a=>Number.isFinite(a.effect?.getTiming().iterations)).map(a=>a.finished.catch(()=>{})));});
 await card.scrollIntoViewIfNeeded();
 const stable=await measure();
 await page.screenshot({path:'qa-artifacts/v5997/full-stable-390.png',fullPage:true});
 await card.screenshot({path:'qa-artifacts/v5997/card-stable-390.png'});
 return {scope:'REAL_CHROME_RESPONSIVE_TRANSITION_DIAGNOSTIC',immediate,stable};
}