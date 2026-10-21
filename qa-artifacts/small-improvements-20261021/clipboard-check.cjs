// Real served UI/IndexedDB; clipboard transports stubbed to preserve the OS clipboard.
const {chromium}=require('playwright'),fs=require('fs'),assert=require('assert/strict');
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:390,height:844}}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto('http://127.0.0.1:8770');
  await page.locator('#loginUser').fill('preview');
  await page.locator('#loginPassword').fill('preview-only-2026');
  await page.locator('#loginButton').click();
  await page.locator('#loginOverlay').waitFor({state:'hidden'});
  await page.waitForFunction(()=>pcOnline && !busy);
  const results=await page.evaluate(async()=>{
   const checks={},writes=[];
   const clipboard=value=>Object.defineProperty(navigator,'clipboard',{configurable:true,value});
   clipboard({writeText:async text=>writes.push(text)});
   await storeMessages([{id:'small-copy-001',conversation_id:'small-copy-chat',origin:'mobile',
     role:'assistant',text:'Texto original\n  com espaços',created_at:new Date().toISOString(),status:'synced',owner:currentUid}]);
   let reads=0,scans=0;const oldRead=messageById,oldAll=allMessages;
   messageById=async id=>{reads++;return oldRead(id)};
   allMessages=async()=>{scans++;return oldAll()};
   await copyMessage('small-copy-001');
   messageById=oldRead;allMessages=oldAll;
   checks.directLookup=reads===1 && scans===0 && writes[0]==='Texto original\n  com espaços';
   await storeMessages([{id:'small-copy-other',owner:'other-account',conversation_id:'other-chat',
     origin:'mobile',role:'assistant',text:'Other account',created_at:new Date().toISOString()}]);
   const count=writes.length;await copyMessage('small-copy-other');
   checks.ownerIsolation=writes.length===count && toast.textContent.includes('indisponível');
   clipboard(undefined);
   let selected='';const originalExec=document.execCommand;
   document.execCommand=function(command){if(command!=='copy')throw Error('Unexpected command');selected=document.activeElement.value;return true};
   messageInput.value='rascunho preservado';messageInput.focus();messageInput.setSelectionRange(2,5);
   const before=document.querySelectorAll('textarea').length;
   checks.fallback=await copyText('Código\n  original');
   checks.fallbackText=selected==='Código\n  original';
   checks.focusRestored=document.activeElement===messageInput && messageInput.selectionStart===2 && messageInput.selectionEnd===5;
   checks.noTemporaryField=document.querySelectorAll('textarea').length===before;
   clipboard({writeText:async()=>{throw new DOMException('Denied','NotAllowedError')}});
   checks.deniedFallsBack=await copyText('Alternativa');
   document.execCommand=()=>false;
   checks.failureVisible=!(await copyText('Sem permissão')) && toast.textContent.includes('copie manualmente');
   document.execCommand=originalExec;
   clipboard({writeText:async text=>{window.copiedCode=text}});
   const block=document.createElement('div');block.id='copy-code-regression';
   block.innerHTML='<button class="code-copy">Copiar código</button><pre><code></code></pre>';
   block.querySelector('code').textContent='const x = 1;\n  // preserve spacing';
   conversation.append(block);
   return checks;
  });
  await page.locator('#copy-code-regression .code-copy').click();
  await page.waitForFunction(()=>window.copiedCode==='const x = 1;\n  // preserve spacing');
  results.codeButton=true;
  Object.assign(results,await page.evaluate(async()=>{
   const id='small-copy-001',oldContext=jduiCtx({id,conversation_id:'small-copy-chat'});
   oldContext.saveState('quiz',{answer:1});
   const pending=persistJduiSoon(),loading=preloadJduiStates([id]);
   await clearStorage();await pending;await loading;
   const emptyCount=await reqPromise(db.transaction(UISTATE).objectStore(UISTATE).count());
   const reset=emptyCount===0 && Object.keys(jduiDirty).length===0 && Object.keys(jduiStateCache).length===0 && jduiSyncTimer===null;
   oldContext.saveState('quiz',{answer:2});
   const staleContext=Object.keys(jduiDirty).length===0 && Object.keys(jduiStateCache).length===0 && jduiSyncTimer===null;
   const freshContext=jduiCtx({id,conversation_id:'small-copy-chat'});
   freshContext.saveState('quiz',{answer:3});await persistJduiSoon();
   const row=await reqPromise(db.transaction(UISTATE).objectStore(UISTATE).get(id+'#quiz'));
   const freshWorks=!!row && row.state.answer===3;
   await clearStorage();
   return {cacheClearCancelsPendingWork:reset,staleWidgetCannotRestoreCache:staleContext,freshWidgetStillSaves:freshWorks};
  }));
  assert(Object.values(results).every(Boolean),JSON.stringify(results));assert.deepEqual(errors,[]);
  const report={checks:results,errors,note:'Actual Chrome UI and IndexedDB; clipboard API/legacy return values simulated. OS clipboard unchanged.'};
  fs.writeFileSync('qa-artifacts/small-improvements-20261021/clipboard-check.json',JSON.stringify(report,null,2));
  console.log(JSON.stringify(report));
 }finally{await browser.close()}
})().catch(error=>{console.error(error);process.exitCode=1});
