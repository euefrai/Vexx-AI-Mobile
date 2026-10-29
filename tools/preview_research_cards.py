"""Isolated JDUI browser QA with controlled records; no account, model or relay.

Uses production validation, rendering and IndexedDB state functions. Follow-up
sends are captured locally, never sent to an AI provider.
"""
import json
import shutil
import sys
import tempfile
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import jdui
import research_view


def main():
    sources = [
        {'titulo': 'Garantia e condições de uso — documento de teste', 'url': 'https://example.org/warranty',
         'dominio': 'example.org', 'status': 'aberta', 'texto_lido': True, 'tipo': 'Documento',
         'trecho': 'Introdução sem a resposta.', 'authors': ['Autor de teste'],
         'answer_passages': [{'text': 'A garantia do modelo A cobre três anos.', 'section': 'Garantia'}]},
        {'titulo': 'Modelo B: garantia, limitações e peças de reposição', 'url': 'https://example.net/model-b',
         'dominio': 'example.net', 'status': 'aberta', 'texto_lido': True, 'content_scope': 'abstract_only',
         'trecho': 'O resumo menciona dois anos de garantia; outras condições não foram recuperadas.'},
        {'titulo': 'Resultado ainda não lido', 'url': 'https://example.com/pending',
         'dominio': 'example.com', 'status': 'encontrada', 'trecho': 'Esta prévia não comprova os dados da página.'},
        {'titulo': 'Fonte indisponível', 'url': 'https://example.com/blocked',
         'dominio': 'example.com', 'status': 'encontrada', 'access_state': 'blocked',
         'trecho': 'Página bloqueada na leitura.'},
    ]
    items = [dict(nome=name, preco=price, preco_valor=value, moeda=currency,
                  loja='Loja de teste', url=f'https://example.org/product/{i}',
                  specs={'Garantia': warranty, 'Conectividade': 'USB-C'})
             for i, (name, price, value, currency, warranty) in enumerate([
                 ('Modelo A — descrição completa sem truncamento', 'R$ 240', 240, 'BRL', '3 anos'),
                 ('Modelo B', 'R$ 180', 180, 'BRL', '2 anos')])]
    message = {'version': jdui.VERSION, 'blocks': [
        {'type': 'ui', 'component': 'sources', 'props': {'title': 'Fontes da pesquisa',
            'items': [research_view.source_card(s) for s in sources]}},
        {'type': 'ui', 'component': 'productcompare', 'props': {'title': 'Comparação de opções', 'items': items}}]}
    ok, message, errors = jdui.validar_mensagem(message)
    assert ok, errors
    app = (ROOT / 'public/app.js').read_text(encoding='utf-8')
    state_functions = app[app.index('async function preloadJduiStates('):app.index('async function syncJduiStates(')]
    with tempfile.TemporaryDirectory(prefix='vexx-research-cards-') as temporary:
        folder = Path(temporary)
        for name in ('jdui.js', 'styles.css', 'interface.css'):
            shutil.copyfile(ROOT / 'public' / name, folder / name)
        (folder / 'state.js').write_text(state_functions, encoding='utf-8')
        (folder / 'message.json').write_text(json.dumps(message, ensure_ascii=False), encoding='utf-8')
        (folder / 'index.html').write_text('''<!doctype html><html lang="pt-BR"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Pesquisa · QA isolado</title>
<link rel="icon" href="data:,"><link rel="stylesheet" href="styles.css"><link rel="stylesheet" href="interface.css">
<style>html,body{height:auto;overflow:auto}body{display:block;padding:20px}main{max-width:860px;margin:auto;min-width:0}header{padding:12px 0 24px}h1{font-size:24px;letter-spacing:-.03em}header p,header label{font-size:13px;color:var(--text-2);line-height:1.7}#view>.jdui-slot{margin-bottom:36px}select{min-height:44px;background:var(--surface-2);color:var(--text);border:1px solid var(--line);border-radius:8px;padding:8px}#captured{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}</style>
<main><header><h1>Pesquisa e comparação</h1><p>QA local · dados controlados. Nenhuma pesquisa real ou envio ao modelo neste cenário.</p>
<label>Conta de teste <select id="owner"><option value="qa-a">A</option><option value="qa-b">B</option></select></label></header>
<div id="view"></div><pre id="captured" aria-live="polite"></pre></main><script src="jdui.js"></script><script>
let currentUid=localStorage.getItem('qa-owner')||'qa-a',storageGeneration=1,db;
let jduiStateCache={},jduiDirty={},jduiSyncTimer,authenticated=true,pcOnline=true;
const UISTATE='state',reqPromise=r=>new Promise((resolve,reject)=>{r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error)});
const txDone=t=>new Promise((resolve,reject)=>{t.oncomplete=resolve;t.onerror=()=>reject(t.error);t.onabort=()=>reject(t.error)});
const api=()=>{throw Error('No API in isolated QA')},queueLearn=()=>{},downloadFile=()=>{},renderMarkdown=()=>'',syncJduiStates=()=>{};
window.qa={prompts:[],fail:false,online:true,pending:false};
async function sendMessage(text){if(qa.fail)throw Error('controlled failure');qa.prompts.push(text);document.getElementById('captured').textContent=text;if(qa.pending)await new Promise(resolve=>qa.release=resolve);}
</script><script src="state.js"></script><script>
let message;
async function show(){const owner=document.getElementById('owner').value;if(owner!==currentUid){currentUid=owner;storageGeneration++;jduiStateCache={};}localStorage.setItem('qa-owner',currentUid);const id='qa-message:'+currentUid;await preloadJduiStates([id]);const ctx=jduiCtx({id,conversation_id:'qa-conversation'});ctx.online=()=>qa.online;const root=document.getElementById('view');root.replaceChildren();JDUI.mount(root,[message],ctx);window.qa.ready=true;}
document.getElementById('owner').value=currentUid;document.getElementById('owner').addEventListener('change',show);
const open=indexedDB.open('vexx-research-cards-isolated-qa',1);open.onupgradeneeded=()=>open.result.createObjectStore(UISTATE,{keyPath:'k'});
open.onsuccess=async()=>{db=open.result;message=await(await fetch('message.json')).json();await show();};
</script></html>''', encoding='utf-8')

        class Handler(SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=str(folder), **kwargs)

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        print(f'http://127.0.0.1:{server.server_port}/index.html', flush=True)
        server.serve_forever()


if __name__ == '__main__':
    main()
