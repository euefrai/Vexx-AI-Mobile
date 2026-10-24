"""Local component QA: real captures and actual JDUI/IndexedDB functions.

No production session, relay, model or simulated successful research. The
isolated IndexedDB database contains public QA captures only.
"""
import json
import os
from pathlib import Path
import shutil
import tempfile
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

ROOT = Path(__file__).resolve().parents[1]


def main():
    qa = ROOT / 'qa-artifacts/v598/development/browser'
    qa.mkdir(parents=True, exist_ok=True)
    import sys
    sys.path.insert(0, str(ROOT))
    import research_view
    captures = {
        'official': json.loads((ROOT/'qa-artifacts/v598/development/live/official.json').read_text(encoding='utf-8')),
        'images': json.loads((ROOT/'qa-artifacts/v597/live-final/images.json').read_text(encoding='utf-8')),
        'comparison': json.loads((ROOT/'qa-artifacts/v596/live-model-acceptance/comparison.json').read_text(encoding='utf-8')),
    }
    messages = {}
    for name, data in captures.items():
        msg = research_view.build_view(data['summary'], data.get('evidence', []))
        msg['blocks'] = [b for b in msg['blocks'] if b.get('component') not in ('filecard','researchplan')]
        messages[name] = msg
    controlled=json.loads((ROOT/'qa-artifacts/v598/development/after.json').read_text(encoding='utf-8'))
    messages['gaps']=research_view.build_view({'id':'rj-fixture-gaps','objetivo':controlled['question'],
        'status':'interrompida','usados':{'research_gaps':controlled['initial_gaps']}},[])
    messages['gaps']['blocks'] = [b for b in messages['gaps']['blocks'] if b.get('component') == 'accordion' and any('falta confirmar' in i.get('title','') for i in b.get('props',{}).get('items',[]))]
    app = (ROOT/'public/app.js').read_text(encoding='utf-8')
    def section(start, end):
        return app[app.index(start):app.index(end, app.index(start))]
    functions = section('async function preloadJduiStates(', 'async function syncJduiStates(')
    functions += section('async function researchJduiContext(', 'async function researchWorkspaceAbrir(')
    functions += '\n'.join(line for line in app.splitlines() if line.startswith(('function esc(', 'function validUrl('))) + '\n'
    functions += section('const ESC_DIV =', 'function nearBottom(')
    functions += app[app.index('function downloadFile('):app.index('\n}',app.index('function downloadBlob('))+2]

    with tempfile.TemporaryDirectory(prefix='v598-components-') as temporary:
        folder = Path(temporary)
        for name in ('jdui.js', 'styles.css'):
            shutil.copyfile(ROOT/'public'/name, folder/name)
        (folder/'functions.js').write_text(functions, encoding='utf-8')
        (folder/'messages.json').write_text(json.dumps(messages, ensure_ascii=False), encoding='utf-8')
        (folder/'index.html').write_text('''<!doctype html><html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>V598 Research Explorer QA</title><link rel="icon" href="data:,"><link rel="stylesheet" href="styles.css"><style>html,body{height:auto;overflow:auto}body{display:block;padding:12px}main{max-width:1000px;margin:auto;min-width:0}select,button{min-height:44px;max-width:100%}nav{display:flex;gap:8px;flex-wrap:wrap}#researchWorkspaceView{min-width:0}h1{font-size:20px}</style><main><h1>Pesquisa — QA de componentes</h1><p>Fontes públicas em replay e lacunas de fixture identificadas. Sem sessão ou pesquisa de produção.</p><nav><label>Usuário <select id="owner"><option>owner-a</option><option>owner-b</option></select></label><label>Pesquisa <select id="job"><option>comparison</option><option>official</option><option>gaps</option><option>images</option></select></label></nav><p id="status" role="status"></p><div id="researchWorkspaceView"></div></main><script src="jdui.js"></script><script>
let currentUid='owner-a',storageGeneration=1,db,jduiStateCache={},jduiDirty={},jduiSyncTimer, messages;
const UISTATE='state',authenticated=false,pcOnline=false;
const reqPromise=req=>new Promise((resolve,reject)=>{req.onsuccess=()=>resolve(req.result);req.onerror=()=>reject(req.error);});
const txDone=tx=>new Promise((resolve,reject)=>{tx.oncomplete=resolve;tx.onerror=()=>reject(tx.error);tx.onabort=()=>reject(tx.error);});
const syncJduiStates=()=>{},api=()=>{},queueLearn=()=>{},sendMessage=()=>{};
</script><script src="functions.js"></script><script>
async function show(){const job=document.getElementById('job').value,owner=document.getElementById('owner').value;if(currentUid!==owner){currentUid=owner;storageGeneration++;jduiStateCache={};}localStorage.setItem('v598-selected',job);localStorage.setItem('v598-owner',owner);const ctx=await researchJduiContext(job);const root=document.getElementById('researchWorkspaceView');root.replaceChildren();const v=JDUI.validateMessage(messages[job]);if(!v.ok)throw Error(v.erros.join(';'));JDUI.mount(root,[v.msg],ctx);document.getElementById('status').textContent=owner+' / '+job;window.fixtureReady=true;}
const open=indexedDB.open('v598-public-component-qa',1);open.onupgradeneeded=()=>open.result.createObjectStore(UISTATE,{keyPath:'k'});open.onsuccess=async()=>{db=open.result;messages=await(await fetch('messages.json')).json();document.getElementById('job').value=localStorage.getItem('v598-selected')||'comparison';document.getElementById('owner').value=localStorage.getItem('v598-owner')||'owner-a';await show();};document.getElementById('job').onchange=show;document.getElementById('owner').onchange=show;
</script></html>''', encoding='utf-8')
        class Handler(SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=str(folder), **kwargs)
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        (qa/'ui-runtime.json').write_text(json.dumps({'pid': os.getpid(), 'url':f'http://127.0.0.1:{server.server_port}/index.html'}), encoding='utf-8')
        server.serve_forever()


if __name__ == '__main__':
    main()
