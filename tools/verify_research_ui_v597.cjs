/* Controlled async contracts against actual app functions; not browser E2E. */
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync('public/app.js', 'utf8');
const between = (start, end) => source.slice(source.indexOf(start), source.indexOf(end, source.indexOf(start)));
const functions = between('async function preloadJduiStates(', 'async function persistJduiSoon(')
  + between('async function researchJduiContext(', 'function researchStop()');
const deferred = () => { let resolve; const promise = new Promise(r => resolve = r); return {promise, resolve}; };
const element = () => ({dataset: {}, hidden: false, textContent: '', children: [],
  replaceChildren() {this.children=[];}, appendChild(item) {this.children.push(item);},
  hasChildNodes() {return this.children.length > 0;}});
function fixture() {
  const nodes = Object.fromEntries(['researchJobList', 'researchWorkspace', 'researchWorkspaceView', 'researchWorkspaceTitle', 'researchView'].map(id => [id, element()]));
  const mounts = [];
  const ctx = {currentUid:'owner-a', storageGeneration:1, active:'job-a', jduiStateCache:{chat: {keep:true}}, jduiDirty:{},
    UISTATE:'state', db:null, reqPromise:async r => r, $: id => nodes[id],
    researchJobIdAtual:() => ctx.active, researchWorkspaceExporta:()=>{},
    renderMarkdown:t=>t, downloadFile:()=>{}, queueLearn:()=>{}, sendMessage:()=>{}, persistJduiSoon:()=>{},
    authenticated:false, pcOnline:false, navigator:{onLine:true},
    document:{createElement:element}, JDUI:{mount:(node, slots, state)=>{node.children=slots; mounts.push({slots,state});}}};
  vm.createContext(ctx); vm.runInContext(functions, ctx);
  return {ctx,nodes,mounts};
}
(async () => {
  let f=fixture(); let waiting=deferred();
  f.ctx.api=async url => url.includes('status?job_id=job-a') ? waiting.promise : url.includes('/status') ? {resumo:{objetivo:'B'}} : {message:{id:'B'}};
  const stale=f.ctx.researchWorkspaceAbrir('job-a');
  await f.ctx.researchWorkspaceAbrir('job-b'); waiting.resolve({resumo:{objetivo:'A'}}); await stale;
  assert.equal(f.nodes.researchWorkspaceTitle.textContent,'B'); assert.equal(f.mounts.length,1);
  f=fixture(); waiting=deferred(); f.ctx.api=()=>waiting.promise;
  const view=f.ctx.researchCarregaView(true); f.ctx.active='job-b'; waiting.resolve({message:{id:'A'}}); await view;
  assert.equal(f.mounts.length,0);
  f=fixture(); waiting=deferred(); f.ctx.api=()=>waiting.promise;
  const owner=f.ctx.researchWorkspaceAbrir('job-a'); f.ctx.currentUid='owner-b'; f.ctx.storageGeneration++;
  waiting.resolve({resumo:{objetivo:'private A'}}); await owner;
  assert.equal(f.mounts.length,0); assert.notEqual(f.nodes.researchWorkspaceTitle.textContent,'private A');
  f=fixture(); const state=await f.ctx.researchJduiContext('job-a'); state.saveState('0:1:sources',{open:true});
  assert.equal(state.loadState('0:1:sources').open,true);
  assert.equal(f.ctx.jduiStateCache.chat.keep,true);
  const other=await f.ctx.researchJduiContext('job-b'); assert.equal(other.loadState('0:1:sources'),undefined);
  f.ctx.currentUid='owner-b'; f.ctx.storageGeneration++;
  state.saveState('stale',{bad:true}); assert.equal(Object.keys(f.ctx.jduiDirty).length,1);
  console.log(JSON.stringify({scope:'controlled VM; real app functions; no authenticated browser',passed:4,total:4}));
})().catch(error=>{console.error(error);process.exitCode=1;});
