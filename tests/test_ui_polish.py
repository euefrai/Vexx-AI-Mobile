"""Behavioral regressions: real frontend request code and real SQLite agent state."""
import shutil
import subprocess
from pathlib import Path

import pytest
import pc_agent

ROOT = Path(__file__).resolve().parents[1]


def test_duplicate_claim_and_startup_recovery_preserve_partial_text(tmp_path):
    db = pc_agent.open_db(tmp_path / 'interrupted.sqlite3')
    payload = dict(message_id='polish-user-002', conversation_id='conv-polish', text='Olá')
    prep = pc_agent.ai_preparar(db, payload, {'model':'test'})
    assert pc_agent.ai_preparar(db, payload, {'model':'test'}) == {'busy':True}
    pc_agent.ai_marcar(db, payload['message_id'], payload['conversation_id'], 'test', 'processing',
                      reply_id=prep['reply_id'], response_text='Trecho salvo')
    pc_agent.recover_interrupted_ai(db)
    state = pc_agent.ai_estado(db, payload['message_id'])
    assert state['state'] == 'failed' and state['response_text'] == 'Trecho salvo'
    assert 'user_text' in pc_agent.ai_preparar(db, payload, {'model':'test'})
    db.close()


def test_worker_exception_releases_message_for_retry(tmp_path, monkeypatch):
    path = tmp_path / 'exception.sqlite3'
    payload = dict(message_id='polish-user-003', conversation_id='conv-polish', text='Olá')
    def fail(*args):
        raise RuntimeError('controlled test failure')
    monkeypatch.setattr(pc_agent, 'interpretar_comando_memoria', fail)
    events = []
    monkeypatch.setattr(pc_agent, 'enviar_ws', lambda ws, obj: events.append(obj))
    pc_agent.ai_stream_worker(path, {'model':'test'}, payload, 's1', object(), pc_agent.SessaoStream(), {})
    db = pc_agent.open_db(path)
    assert pc_agent.ai_estado(db, payload['message_id'])['state'] == 'failed'
    assert events[-1]['type'] == 'ai_error'
    assert 'user_text' in pc_agent.ai_preparar(db, payload, {'model':'test'})
    db.close()


def test_stream_replay_is_done_and_identity_is_bound_to_conversation(tmp_path, monkeypatch):
    path = tmp_path / 'replay.sqlite3'
    db = pc_agent.open_db(path)
    payload = dict(message_id='polish-user-001', conversation_id='conv-polish', text='Olá')
    cfg = dict(model='test-model')
    prep = pc_agent.ai_preparar(db, payload, cfg)
    pc_agent.ai_guardar_resposta(db, payload['message_id'], payload['conversation_id'],
                                cfg['model'], prep['reply_id'], 'Resposta salva')
    assert pc_agent.ai_preparar(db, dict(payload, conversation_id='other-conv'), cfg)['codigo'] == 'invalido'
    # Returning an existing result must not spend or require new generation quota.
    monkeypatch.setattr(pc_agent.JULIA_auth, 'uso_ia_hora', lambda *a: 999999)
    assert pc_agent.ai_preparar(db, payload, cfg)['replay']
    db.close()
    events = []
    monkeypatch.setattr(pc_agent, 'enviar_ws', lambda ws, obj: events.append(obj))
    pc_agent.ai_stream_worker(path, cfg, payload, 'stream-test', object(), pc_agent.SessaoStream(), {})
    assert len(events) == 1
    assert events[0]['type'] == 'ai_done'
    assert events[0]['response_text'] == 'Resposta salva'
    assert events[0]['reply_id'] == 'polish-user-001-r1'


def test_frontend_stream_lifecycle(tmp_path):
    node = shutil.which('node')
    if not node:
        pytest.skip('Node indisponível')
    harness = tmp_path / 'stream.cjs'
    harness.write_text(r'''
const fs = require('fs'), vm = require('vm'), assert = require('assert/strict');
const src = fs.readFileSync(process.argv[2], 'utf8');
const code = src.slice(src.indexOf('function requestAI(userRow'), src.indexOf('\nfunction stopAI()'));
const event = (name, data, nl='\n') => `event: ${name}${nl}data: ${JSON.stringify(data)}${nl}${nl}`;
async function run(wire, apiResult, previous='') {
  const rows = new Map(), saves=[], calls=[], notices=[];
  const id='polish-user-001-r1';
  if(previous) rows.set(id,{id,text:previous,status:'failed',created_at:'2026-01-01T00:00:00Z'});
  const bytes = new TextEncoder().encode(wire);
  const ctx = { authenticated:true, pcOnline:true, navigator:{onLine:true}, db:{}, currentUid:'alice',
    activeConversation:'conv-polish', aiRequests:new Set(), aiQueue:[], aiQueueRunning:false,
    aiAbort:null, aiStartT:0, aiFirstTokenT:0, genTimer:null, rafPending:null, csrf:'test',
    performance, Date, TextDecoder, URLSearchParams, AbortController,
    console:{info(){},warn(){}}, setInterval:()=>1, clearInterval(){}, cancelAnimationFrame(){},
    messageById:async id=>rows.get(id), allMessages:async()=>[...rows.values()],
    storeMessages:async ms=>ms.forEach(m=>{rows.set(m.id,m); saves.push({...m});}),
    modeloAtivo:()=> 'test-model', memoryOn:()=>false, aiLocalContext:()=>({}),
    setGenBar(){},tickGen(){},schedulePaint(){},showToast:m=>notices.push(m),
    renderMessages:async()=>{},renderSessions:async()=>{},$:()=>({value:''}),
    fetch:async()=>({ok:true,body:new ReadableStream({start(c){
      // One-byte chunks exercise UTF-8 and CRLF boundaries across network reads.
      for(const b of bytes)c.enqueue(new Uint8Array([b])); c.close();
    }})}),
    api:async(path)=>{calls.push(path);if(path==='/api/sync')return {confirmed_ids:['polish-user-001']};
      return apiResult || {response_text:'Fallback',reply_id:id};}
  };
  vm.createContext(ctx);vm.runInContext(code,ctx);
  await ctx.requestAI({id:'polish-user-001',conversation_id:'conv-polish',text:'Oi'}, {immediate:true});
  return {row:rows.get(id),saves,calls,notices,ctx};
}
(async()=>{
  let r=await run(event('done',{response_text:'Olá',reply_id:'polish-user-001-r1'},'\r\n'));
  assert.equal(r.row.text,'Olá');assert.equal(r.row.status,'synced');assert.equal(r.calls.length,0);
  r=await run(event('done',{response_text:''}));assert.equal(r.row.status,'failed');
  r=await run(event('delta',{seq:1,trecho:'Parte'}));
  assert.equal(r.row.status,'failed');assert.equal(r.row.text,'Parte');assert.equal(r.calls.length,0);
  assert(r.saves.some(m=>m.status==='generating' && m.text==='Parte'));
  r=await run(event('delta',{seq:1,trecho:'A'})+event('delta',{seq:1,trecho:'A'})+
    event('delta',{seq:2,trecho:'B'})+event('done',{}));
  assert.equal(r.row.text,'AB');assert.equal(r.row.status,'synced');
  r=await run(event('delta',{seq:1,trecho:'A'})+event('delta',{seq:3,trecho:'C'}));
  assert.equal(r.row.status,'failed');assert.equal(r.row.text,'A');
  r=await run(event('cancelled',{partial:'Parcial'}));
  assert.equal(r.row.text,'Parcial');assert.equal(r.row.status,'failed');assert.equal(r.calls.length,0);
  r=await run(event('done',{response_text:'Errada',reply_id:'other-id'}));
  assert.equal(r.row.status,'failed');assert.notEqual(r.row.text,'Errada');
  r=await run(event('error',{codigo:'sem_mensagem'}));
  assert.deepEqual(r.calls,['/api/sync','/api/ai']);assert.equal(r.row.status,'synced');
  r=await run(event('error',{codigo:'offline',error:'Sem rede'}),null,'Texto preservado');
  assert.equal(r.row.text,'Texto preservado');assert.equal(r.row.owner,'alice');
  assert.equal(r.ctx.aiRequests.size,0);
  console.log('9 streaming lifecycle scenarios passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
''', encoding='utf-8')
    result = subprocess.run([node, str(harness), str(ROOT / 'public/app.js')],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
