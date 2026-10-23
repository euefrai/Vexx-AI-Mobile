"""Local Chrome QA of actual components/captures; not authenticated app E2E.

Serves only copied public assets and public evaluation captures in a temporary
directory. SSE is explicitly a replay, not new research. No real database/key.
"""
import json
from pathlib import Path
import shutil
import tempfile
import os
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
import time
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import research_view


def main():
    qa=ROOT/'qa-artifacts/v596'
    captures={}
    for name,folder in [('images','live-recovery-final'),('documentation','live-recovery-final'),
                        ('news_local','live-recovery-final'),('comparison','live-model-acceptance')]:
        captures[name]=json.loads((qa/folder/(name+'.json')).read_text(encoding='utf-8'))
    messages={}
    for name,data in captures.items():
        view=research_view.build_view(data['summary'],data.get('evidence',[]))
        # Exports/job actions are tested against the real authenticated API in
        # pytest; this component harness must not expose dead production buttons.
        view['blocks']=[b for b in view['blocks'] if b.get('component') not in ('filecard','researchplan','accordion')]
        messages[name]=view
    (qa/'jdui-browser-input.json').write_text(json.dumps(messages,ensure_ascii=False,indent=2),encoding='utf-8')
    with tempfile.TemporaryDirectory(prefix='v596-jdui-') as temporary:
        folder=Path(temporary)
        for name in ('jdui.js','styles.css'):shutil.copyfile(ROOT/'public'/name,folder/name)
        (folder/'messages.json').write_text(json.dumps(messages,ensure_ascii=False),encoding='utf-8')
        (folder/'index.html').write_text('''<!doctype html><html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>V596 — QA de pesquisa</title><link rel="icon" href="data:,"><link rel="stylesheet" href="styles.css"><style>html,body{height:auto;overflow:auto}body{display:block;padding:16px}main{max-width:1050px;margin:auto}h1{font-size:22px}header{margin-bottom:20px}select,button{min-height:44px;max-width:100%}.tools{display:flex;gap:8px;flex-wrap:wrap;margin:12px 0}#status{font-size:12px;color:var(--muted);overflow-wrap:anywhere}#result{min-width:0}</style><main><header><h1>Explorar a pesquisa</h1><p>QA local · capturas externas reais · eventos em replay · sem sessão do aplicativo</p><label for="scenario">Pesquisa</label><select id="scenario"><option value="images">Imagens · Ponte Estaiada</option><option value="documentation">Documentação · TaskGroup</option><option value="comparison">Estudos · sódio e lítio</option><option value="news_local">Notícias · Ubatã</option></select><div class="tools"><button id="replay">Reproduzir eventos capturados</button><button id="cancel" disabled>Parar reprodução</button></div><div id="status" role="status" aria-live="polite">Carregando</div></header><div id="result"></div></main><script src="jdui.js"></script><script>
let messages,stream;const result=document.getElementById('result'),status=document.getElementById('status'),select=document.getElementById('scenario'),cancel=document.getElementById('cancel');
function show(){result.replaceChildren();const v=JDUI.validateMessage(messages[select.value]);if(!v.ok)throw Error(v.erros.join(';'));JDUI.mount(result,[v.msg],{download:(name,mime,text)=>{const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([text],{type:mime}));a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);},loadState:key=>JSON.parse(localStorage.getItem(select.value+key)||'{}'),saveState:(key,state)=>localStorage.setItem(select.value+key,JSON.stringify(state))});status.textContent='Captura externa · '+select.value;window.fixtureReady=true;}
select.onchange=()=>{localStorage.setItem('v596-scenario',select.value);show();};
fetch('messages.json').then(r=>r.json()).then(data=>{messages=data;select.value=localStorage.getItem('v596-scenario')||'images';show();});
document.getElementById('replay').onclick=()=>{if(stream)stream.close();status.textContent='Replay dos eventos externos';cancel.disabled=false;stream=new EventSource('/events');stream.onmessage=e=>{let data=JSON.parse(e.data);status.textContent='Replay: '+data.description;if(data.done){stream.close();cancel.disabled=true;}};};
cancel.onclick=()=>{if(stream)stream.close();cancel.disabled=true;status.textContent='Reprodução cancelada; não altera o job capturado.';};
</script></html>''',encoding='utf-8')
        events=captures['comparison'].get('search_events',[])[:4]
        class Handler(SimpleHTTPRequestHandler):
            def __init__(self,*args,**kwargs):super().__init__(*args,directory=str(folder),**kwargs)
            def do_GET(self):
                if self.path!='/events':return super().do_GET()
                self.send_response(200);self.send_header('Content-Type','text/event-stream');self.send_header('Cache-Control','no-cache');self.end_headers()
                try:
                    for event in events:
                        self.wfile.write(('data: '+json.dumps({'description':event.get('descricao','')},ensure_ascii=False)+'\n\n').encode());self.wfile.flush();time.sleep(1)
                    self.wfile.write(b'data: {"description":"fim dos eventos capturados","done":true}\n\n');self.wfile.flush()
                except (BrokenPipeError,ConnectionResetError):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        (qa/'ui-runtime.json').write_text(json.dumps({'pid':os.getpid(),'url':f'http://127.0.0.1:{server.server_port}/index.html','folder':str(folder)}),encoding='utf-8')
        server.serve_forever()


if __name__=='__main__':main()
