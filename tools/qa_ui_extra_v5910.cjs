async page => {
  if(!page.url().startsWith('http://127.0.0.1:'))throw Error('Loopback QA only');
  const version=await page.evaluate(()=>JSON.parse(sessionStorage.getItem('research-qa-config')||'{}').version||'v5910');
  if(!['v5910','v5911'].includes(version))throw Error('Unknown QA version');
  await page.setViewportSize({width:1280,height:900});
  await page.getByRole('button',{name:/^Pesquisa profunda sobre quem fundou a WEG/}).click();
  await page.getByRole('button',{name:'Ver pesquisa',exact:true}).first().click();
  const downloads=[];
  for(const [name,format] of [['Baixar MD','md'],['Baixar CSV','csv']]){
    const pending=page.waitForEvent('download');await page.getByRole('link',{name,exact:true}).click();
    const file=await pending;await file.saveAs('qa-artifacts/'+version+'/research-export.'+format);
    const failure=await file.failure();if(failure)throw Error(failure);downloads.push(format);
  }
  const storage=await page.evaluate(async()=>{
    const names=await indexedDB.databases();let messages=[];
    for(const {name} of names){
      const db=await new Promise((res,rej)=>{const r=indexedDB.open(name);r.onsuccess=()=>res(r.result);r.onerror=()=>rej(r.error);});
      if(db.objectStoreNames.contains('messages'))messages.push(...await new Promise((res,rej)=>{const r=db.transaction('messages','readonly').objectStore('messages').getAll();r.onsuccess=()=>res(r.result);r.onerror=()=>rej(r.error);}));
      db.close();
    }
    return {messages:messages.length,unique_ids:new Set(messages.map(m=>m.id)).size,
      structured_assistant:messages.filter(m=>m.role==='assistant'&&m.text?.includes('```jdui')).length,
      result_messages:messages.filter(m=>m.id?.endsWith('-result')).length};
  });
  if(storage.messages!==storage.unique_ids||!storage.structured_assistant||!storage.result_messages)throw Error('IndexedDB regression');
  return {scope:'REAL_QA_JOB_EXPORT_AND_INDEXEDDB',downloads,storage};
}
