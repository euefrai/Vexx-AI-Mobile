async page => {
  const errors=[];const onError=e=>errors.push(e.message);page.on('pageerror',onError);
  const pattern='https://upload.wikimedia.org/**';const reject=route=>route.abort('failed');
  try{
    await page.setViewportSize({width:1280,height:900});
    if(!(await page.locator('#newChatCta').isVisible()))await page.locator('#drawerOpen').click();
    await page.getByRole('button',{name:/^Pesquise imagens da Ponte/}).click();
    const zoom=page.locator('.jdui-media-zoom').first();
    await page.route(pattern,reject);
    await zoom.click();
    await page.getByText('Imagem indisponível. Consulte a fonte original.',{exact:true}).waitFor({state:'visible',timeout:15000});
    await page.screenshot({path:'qa-artifacts/v5991/research-image-error.png'});
    await page.keyboard.press('Escape');await page.unroute(pattern,reject);
    await zoom.click();
    await page.waitForFunction(()=>{const img=document.querySelector('.jdui-image-dialog img');return img&&img.complete&&img.naturalWidth>0&&!img.hidden;},null,{timeout:20000});
    await page.keyboard.press('Escape');
    const storage=await page.evaluate(async()=>{
      const databases=await indexedDB.databases();let messages=[];
      for(const database of databases){
        const handle=await new Promise((resolve,reject)=>{const request=indexedDB.open(database.name);request.onsuccess=()=>resolve(request.result);request.onerror=()=>reject(request.error);});
        if(handle.objectStoreNames.contains('messages')){
          const rows=await new Promise((resolve,reject)=>{const request=handle.transaction('messages','readonly').objectStore('messages').getAll();request.onsuccess=()=>resolve(request.result);request.onerror=()=>reject(request.error);});
          messages.push(...rows);
        }
        handle.close();
      }
      return {database_count:databases.length,messages:messages.length,
        structured_assistant_messages:messages.filter(m=>m.role==='assistant'&&m.text?.includes('```jdui')).length,
        result_messages:messages.filter(m=>m.id?.endsWith('-result')).length};
    });
    if(!storage.structured_assistant_messages||!storage.result_messages)throw Error('Structured research absent from IndexedDB');
    if(!(await page.locator('#newChatCta').isVisible()))await page.locator('#drawerOpen').click();
    await page.getByRole('button',{name:/^Pesquisa profunda sobre asyncio/}).click();
    await page.getByRole('button',{name:'Ver pesquisa',exact:true}).first().click();
    const downloads=[];
    for(const [name,extension] of [['Baixar MD','md'],['Baixar CSV','csv']]){
      const pending=page.waitForEvent('download');await page.getByRole('link',{name,exact:true}).click();
      const download=await pending;await download.saveAs('qa-artifacts/v5991/research-export.'+extension);
      downloads.push({format:extension,failure:await download.failure()});
    }
    const resultCards=await page.locator('.message.ai .jdui-srccard').count();
    return {scope:'AUTHENTICATED_QA; image failure is explicitly injected',image_error_visible:true,
      image_recovered:true,indexeddb:storage,downloads,result_cards:resultCards,page_errors:errors};
  }finally{await page.unroute(pattern,reject);page.removeListener('pageerror',onError);}
}
