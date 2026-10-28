"""Execute the real composer functions with controlled asynchronous upload timing."""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HARNESS = r"""
const fs = require('node:fs');
const assert = require('node:assert/strict');
const src = fs.readFileSync('public/app.js', 'utf8');
const start = src.indexOf('function renderAttachmentTray()');
const end = src.indexOf("\ncomposer.addEventListener('submit'", start);
assert.ok(start > 0 && end > start);
let currentUid='alice', authEpoch=1, storageGeneration=0, authenticated=true;
let PREVIEW_MODE=false, db={}, pcOnline=true, activeConversation='chat-a';
let pendingAttachments=[], sendingMessages=new Set(), attachmentUploadCache=new Map();
const attachmentSends=new Map();
let csrf='csrf-alice', sequence=0, saved=[], calls=[], toasts=[], ai=[], scrolls=0;
const nodes=new Map();
function element(){return {hidden:true,disabled:false,textContent:'',value:'',children:[],
  append(...items){this.children.push(...items);},replaceChildren(){this.children=[];},
  appendChild(item){this.children.push(item);},
  setAttribute(){},focus(){},dataset:{},classList:{add(){},remove(){}}};}
const $=id=>{if(!nodes.has(id))nodes.set(id,element());return nodes.get(id);};
const document={createElement:element};
const navigator={onLine:true,storage:null};
const location={assign(){}};
const messageInput=$('messageInput');
const newId=()=>String(++sequence);
const formatarTamanhoAnexo=n=>String(n);
const textoComAnexos=(s,items)=>s+' '+items.map(a=>a.name).join(' ');
const showToast=s=>toasts.push(s);
const storeMessages=async rows=>saved.push(...rows.map(row=>({...row,owner:row.owner||currentUid})));
const touchSession=async()=>{};
const requestAI=async row=>ai.push(row);
const titleFrom=s=>s;
const renderSessions=async()=>{};
const renderMessages=async()=>{};
const renderDocs=()=>{};
const scrollChat=()=>scrolls++;
const autoresize=()=>{};
const syncAndRefresh=async()=>{};
const updateConnection=()=>{};
class FormData { constructor(){this.values={};} append(k,v){this.values[k]=v;} }
function response(id,status=200){return {ok:status===200,status,json:async()=>status===200?{doc_id:id}:{detail:'failed'}};}
function deferred(){let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return {promise,resolve,reject};}
let fetchImpl;
const fetch=async(url,options)=>{calls.push({url,options});return fetchImpl(url,options);};
function attachment(id='a'){return {id,name:id+'.txt',size:10,file:{lastModified:1},doc:null,docConversation:activeConversation};}
eval(src.slice(start,end));
const tick=()=>new Promise(resolve=>setImmediate(resolve));
async function main(){
  const kind=process.argv[1];
  pendingAttachments=[attachment()];messageInput.value='Read this';
  if(kind==='late-logout'||kind==='late-account'){
    const gate=deferred();fetchImpl=()=>gate.promise;
    const send=sendMessage('Read this',{fromComposer:true});await tick();
    authEpoch++;
    if(kind==='late-logout')authenticated=false;else currentUid='bob';
    gate.resolve(response('doc-a'));await send;
    assert.equal(saved.length,0,'stale upload must not save a message');
    assert.equal(ai.length,0,'stale upload must not start inference');
    assert.equal(attachmentUploadCache.size,0,'stale upload must not repopulate cache');
  }else if(kind==='cancel-retry'){
    fetchImpl=(_,options)=>new Promise((resolve,reject)=>options.signal.addEventListener('abort',()=>reject(new DOMException('Aborted','AbortError')),{once:true}));
    const send=sendMessage('Read this',{fromComposer:true});await tick();
    cancelAttachmentSend();await send;
    assert.equal(saved.length,0);assert.equal(ai.length,0);
    assert.equal(pendingAttachments.length,1,'cancel preserves the draft attachment');
    assert.equal($('uploadStatus').hidden,true);
    fetchImpl=async()=>response('doc-a');
    await Promise.all([sendMessage('Read this',{fromComposer:true}),sendMessage('Read this',{fromComposer:true})]);
    assert.equal(saved.length,1);assert.equal(ai.length,1);assert.equal(saved[0].owner,'alice');
    assert.equal(pendingAttachments.length,0);assert.equal(calls.length,2);
  }else if(kind==='partial-retry'){
    pendingAttachments.push(attachment('b'));
    fetchImpl=async(_,options)=>options.body.values.file===pendingAttachments[0].file?response('doc-a'):response('',503);
    await sendMessage('Read this',{fromComposer:true});
    assert.equal(saved.length,0);assert.equal(pendingAttachments.length,2);
    fetchImpl=async()=>response('doc-b');
    await sendMessage('Read this',{fromComposer:true});
    assert.equal(calls.length,3,'a successful first document must not upload twice on retry');
    assert.equal(saved.length,1);assert.equal(attachmentUploadCache.size,0);
  }else if(kind==='background-state'){
    const a=deferred(),b=deferred();fetchImpl=(_,o)=>o.body.values.conversation_id==='chat-a'?a.promise:b.promise;
    const first=sendMessage('Read this',{fromComposer:true});await tick();
    activeConversation='chat-b';pendingAttachments=[attachment('b')];
    const second=sendMessage('Read that',{fromComposer:true});await tick();
    a.resolve(response('doc-a'));await first;
    assert.equal($('uploadStatus').hidden,false,'first chat must not hide another chat upload');
    assert.equal($('attachButton').disabled,true);
    assert.equal(scrolls,0,'a background send must not scroll the active chat');
    b.resolve(response('doc-b'));await second;
    assert.equal(saved.length,2);assert.equal($('uploadStatus').hidden,true);
  }else if(kind==='reset-and-late-response'){
    const gate=deferred();fetchImpl=()=>gate.promise;
    const send=sendMessage('Read this',{fromComposer:true});await tick();
    resetAttachmentSends();authEpoch++;
    gate.resolve(response('doc-a'));await send;
    assert.equal(calls[0].options.signal.aborted,true);
    assert.equal(pendingAttachments.length,0);assert.equal(attachmentUploadCache.size,0);
    assert.equal(saved.length,0);assert.equal(ai.length,0);
  }else if(kind==='unauthorized'){
    fetchImpl=async()=>response('',401);
    await sendMessage('Read this',{fromComposer:true});
    assert.equal(authenticated,false);assert.equal($('loginOverlay').hidden,false);
    assert.equal(saved.length,0);assert.equal(ai.length,0);
    assert.equal(pendingAttachments.length,0);assert.equal(attachmentUploadCache.size,0);
  }else throw Error('Unknown case');
  console.log('ok '+kind);
}
main().catch(err=>{console.error(err);process.exitCode=1;});
"""


@pytest.mark.parametrize('case', [
    'late-logout', 'late-account', 'cancel-retry', 'partial-retry',
    'background-state', 'reset-and-late-response', 'unauthorized',
])
def test_attachment_send_lifecycle(case):
    node = shutil.which('node')
    if not node:
        pytest.skip('Node unavailable')
    result = subprocess.run([node, '-e', HARNESS, case], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
