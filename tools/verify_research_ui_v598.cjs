/* Actual app helper, controlled status API; not authenticated browser E2E. */
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const code=fs.readFileSync('public/app.js','utf8');
const helper=code.slice(code.indexOf('const researchMessageChecks ='),code.indexOf('function researchAttach(jobId)'));
function setup(){
  const attached=[];let calls=0;
  const c={authenticated:true,pcOnline:true,currentUid:'owner-a',authEpoch:1,activeConversation:'chat-a',
    api:async()=>{calls++;return {resumo:{status:'concluida'}};},researchAttach:id=>attached.push(id)};
  vm.createContext(c);vm.runInContext(helper,c);return {c,attached,calls:()=>calls};
}
(async()=>{
  let f=setup();await f.c.researchAttachFromMessage('rj-old','msg-old','chat-a');
  await f.c.researchAttachFromMessage('rj-old','msg-old','chat-a');
  assert.equal(f.calls(),1);assert.equal(f.attached.length,0);
  f.c.api=async()=>({resumo:{status:'em_andamento'}});
  await f.c.researchAttachFromMessage('rj-old','msg-resume','chat-a');
  assert.equal(f.attached.length,1);
  f=setup();let resolve;f.c.api=()=>new Promise(r=>resolve=r);
  const wait=f.c.researchAttachFromMessage('rj-a','msg-a','chat-a');
  f.c.currentUid='owner-b';f.c.authEpoch++;resolve({resumo:{status:'em_andamento'}});await wait;
  assert.equal(f.attached.length,0);
  f=setup();f.c.api=()=>new Promise(r=>resolve=r);
  const other=f.c.researchAttachFromMessage('rj-a','msg-a','chat-a');
  f.c.activeConversation='chat-b';resolve({resumo:{status:'em_andamento'}});await other;
  assert.equal(f.attached.length,0);
  console.log(JSON.stringify({passed:4,total:4,scope:'VM status races; actual helper; no production calls'}));
})().catch(e=>{console.error(e);process.exitCode=1;});
