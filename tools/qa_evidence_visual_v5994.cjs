async page => {
  if (!page.url().startsWith('http://127.0.0.1:')) throw Error('Disposable localhost QA only');
  const errors=[];
  const onError=e=>errors.push(e.message);page.on('pageerror',onError);
  const out={scope:'REAL_CHROME_LOCAL_PARTIAL_RESULT_VISUAL_NOT_COMPLETE_RESEARCH',viewports:[]};
  try {
    const message=page.locator('.message.ai').last();
    await message.locator('table').waitFor({state:'visible'});
    const card=message.locator('.jdui-readonly');
    for (const width of [1280,390,320]) {
      await page.setViewportSize({width,height:900});
      await card.scrollIntoViewIfNeeded();
      const geometry=await page.evaluate(()=>({viewport:innerWidth,root:document.documentElement.scrollWidth}));
      const box=await message.boundingBox();
      await card.screenshot({path:`qa-artifacts/v5994/coverage-card-${width}.png`});
      out.viewports.push({...geometry,message_width:box.width});
      if (geometry.root>width)throw Error('Root overflow at '+width);
    }
    const table=message.locator('table');
    const before=await table.innerText();
    const header=table.locator('th').first();
    await header.focus();await page.keyboard.press('Enter');
    out.keyboard_sort=(await header.innerText()).includes('▲');
    const download=page.waitForEvent('download');
    await message.getByRole('button',{name:'Baixar CSV',exact:true}).click();
    const file=await download;await file.saveAs('qa-artifacts/v5994/coverage-export.csv');
    out.csv=await file.failure()===null;
    out.edit_buttons=await message.getByRole('button',{name:/editar|adicionar linha|restaurar/i}).count();
    await page.emulateMedia({reducedMotion:'reduce'});
    out.reduced_motion=await page.evaluate(()=>matchMedia('(prefers-reduced-motion: reduce)').matches);
    await page.evaluate(()=>document.body.style.zoom='2');
    await card.scrollIntoViewIfNeeded();
    const wrapper=table.locator('..');
    out.zoom=await wrapper.evaluate(el=>({width:el.clientWidth,scroll:el.scrollWidth,root:document.documentElement.scrollWidth,viewport:innerWidth}));
    await card.screenshot({path:'qa-artifacts/v5994/coverage-zoom-card-left.png'});
    await wrapper.evaluate(el=>el.scrollLeft=el.scrollWidth);
    out.zoom.scroll_left=await wrapper.evaluate(el=>el.scrollLeft);
    await card.screenshot({path:'qa-artifacts/v5994/coverage-zoom-card-right.png'});
    await page.evaluate(()=>document.body.style.zoom='');
    await page.setViewportSize({width:1280,height:900});
    const id=await message.getAttribute('data-mid');
    await page.reload();await page.locator('#loginOverlay').waitFor({state:'hidden'});
    const restored=page.locator(`[data-mid="${id}"]`);
    await restored.locator('table').waitFor({state:'visible'});
    out.reload_table=await restored.locator('table').innerText()===before;
    out.indexeddb=await page.evaluate(async()=>{
      const descriptions=await indexedDB.databases(),out=[];
      for (const entry of descriptions) {
        const db=await new Promise((resolve,reject)=>{const r=indexedDB.open(entry.name);r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error);});
        const stores=[];
        for (const name of db.objectStoreNames) {
          const count=await new Promise((resolve,reject)=>{const r=db.transaction(name).objectStore(name).count();r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error);});
          stores.push({name,count});
        }
        db.close();out.push({name:entry.name,stores});
      }
      return out;
    });
    if (!out.csv||out.edit_buttons||!out.reload_table||!out.keyboard_sort)throw Error('Partial coverage interaction failed');
    return {...out,page_errors:errors};
  } finally {page.removeListener('pageerror',onError);}
}
