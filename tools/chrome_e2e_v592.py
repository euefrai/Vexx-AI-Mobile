"""Real Chrome/relay/PC E2E, disposable SQLite, fixture research sources, no model."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request

import chrome_e2e_v58 as harness

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / 'qa-artifacts/v592'
ART.mkdir(parents=True, exist_ok=True)
harness.ART = ART


def run():
    result = {'kind':'CHROME_E2E_LOCAL_FIXTURE', 'model_inference':False, 'ok':False}
    processes = []
    cdp = None
    with tempfile.TemporaryDirectory(prefix='vexx-v592-chrome-') as directory:
        tmp = Path(directory)
        port, debug = harness.porta_livre(), harness.porta_livre()
        base = f'http://127.0.0.1:{port}'
        (tmp/'empty.env').write_text('', encoding='utf-8')
        env = dict(os.environ, JULIA_USERNAME='preview',
            JULIA_PASSWORD_HASH=harness.PasswordHasher().hash('preview-only-2026'),
            JULIA_SESSION_SECRET='a'*64, JULIA_AGENT_TOKEN='b'*64,
            JULIA_RELAY_URL=base, JULIA_SQLITE_PATH=str(tmp/'fixture.sqlite3'),
            JULIA_ENV_FILE=str(tmp/'empty.env'), JULIA_REMOTE='0',
            HERMES_PROXY_URL='http://127.0.0.1:9/v1',
            VEXX_RESEARCH_FIXTURE='1', VEXX_FIXTURE_IMAGE_URL=base+'/icon-192.png')
        try:
            processes.append(harness.Processo([sys.executable,'-m','uvicorn','server:app','--host','127.0.0.1','--port',str(port)],tmp/'relay.log',env))
            harness.esperar_http(base+'/api/diag',lambda r:True,30,'relay')
            processes.append(harness.Processo([sys.executable,'tests/research_fixture_agent_v592.py'],tmp/'agent.log',env))
            harness.esperar_http(base+'/api/diag',lambda r:r.get('pc_online') is True,45,'PC')
            chrome = harness.Processo([str(harness.CHROME),'--headless=new',f'--remote-debugging-port={debug}',
                f'--user-data-dir={tmp / "chrome-profile"}','--no-first-run','--disable-extensions',
                '--disable-background-networking','--window-size=1280,900','about:blank'],tmp/'chrome.log',env)
            processes.append(chrome)
            harness.esperar_http(f'http://127.0.0.1:{debug}/json/version',lambda r:bool(r.get('webSocketDebuggerUrl')),30,'Chrome')
            req=urllib.request.Request(f'http://127.0.0.1:{debug}/json/new?'+urllib.parse.quote(base+'/',safe=':/'),method='PUT')
            with urllib.request.urlopen(req,timeout=10) as response:
                tab=json.load(response)
            cdp=harness.CDP(tab['webSocketDebuggerUrl'])
            for domain in ('Page','Runtime','Log','Network'):
                cdp.cmd(domain+'.enable')
            cdp.cmd('Page.navigate',{'url':base+'/'})
            cdp.esperar_js("document.readyState === 'complete' && typeof api === 'function' && !!document.getElementById('loginUser')",bool,20,'login handlers ready')
            cdp.js("document.getElementById('loginUser').value='preview'; document.getElementById('loginPassword').value='preview-only-2026'; document.getElementById('loginForm').requestSubmit(); true")
            cdp.esperar_js("authenticated && pcOnline && document.getElementById('loginOverlay').hidden",bool,25,'authenticated PC')
            created=cdp.js("api('/api/research/start',{method:'POST',body:JSON.stringify({objetivo:'Bateria ZX capacidade nominal — teste local',modo:'profunda'})})")
            job=created['job_id']
            cdp.js(f'researchAttach({json.dumps(job)}); true')
            cdp.esperar_js("document.querySelectorAll('#researchSteps .timeline-item').length",lambda n:n>0,10,'live events')
            before=cdp.js(f"api('/api/research/status?job_id={job}')")
            assert before['resumo']['status']=='em_andamento',before
            # Force a real stream disconnect, then reload before fixture reading ends.
            cdp.js('researchJob.controller.abort(); true')
            cdp.cmd('Page.reload',{'ignoreCache':True})
            cdp.esperar_js(f"typeof researchJobIdAtual==='function' && researchJobIdAtual()==={json.dumps(job)}",bool,20,'automatic owner-scoped resume')
            cdp.esperar_js("document.querySelectorAll('#researchSteps .timeline-item').length",lambda n:n>0,15,'event replay')
            cdp.esperar_js(f"api('/api/research/status?job_id={job}').then(r=>r.resumo.status)",lambda s:s=='concluida',30,'worker completion')
            cdp.js(f"navigate('research'); researchWorkspaceAbrir({json.dumps(job)})")
            cdp.esperar_js("document.querySelectorAll('#researchWorkspaceView .jdui-srccard').length",lambda n:n>0,15,'source cards')
            cdp.esperar_js("Array.from(document.querySelectorAll('#researchWorkspaceView img')).some(i=>i.complete&&i.naturalWidth>0)",bool,15,'real local image bytes')
            cdp.js("document.querySelector('#researchWorkspaceView .jdui-media-zoom').click(); true")
            assert cdp.js("!!document.querySelector('dialog[open]')")
            cdp.cmd('Input.dispatchKeyEvent',{'type':'keyDown','key':'Escape','code':'Escape','windowsVirtualKeyCode':27,'nativeVirtualKeyCode':27})
            cdp.cmd('Input.dispatchKeyEvent',{'type':'keyUp','key':'Escape','code':'Escape','windowsVirtualKeyCode':27,'nativeVirtualKeyCode':27})
            cdp.esperar_js("!document.querySelector('dialog[open]')",bool,5,'Escape closes image')
            cdp.screenshot('research-desktop.png')
            for width in (390,320):
                cdp.cmd('Emulation.setDeviceMetricsOverride',{'width':width,'height':844,'deviceScaleFactor':1,'mobile':True})
                time.sleep(.3)
                assert cdp.js('document.documentElement.scrollWidth <= innerWidth + 1'),f'overflow at {width}'
                cdp.screenshot(f'research-mobile-{width}.png')
            # Export must return real bytes, not a decorative control.
            export=cdp.js(f"fetch('/api/research/export?job_id={job}&formato=md').then(async r=>({{status:r.status,bytes:(await r.arrayBuffer()).byteLength}}))")
            assert export['status']==200 and export['bytes']>100,export
            state=cdp.js(f"api('/api/research/status?job_id={job}&apos_seq=0')")
            events=state['eventos']
            seqs=[e['seq'] for e in events]
            assert seqs==sorted(set(seqs)) and any(e['tipo']=='adaptive_round_evaluated' for e in events)
            assert not cdp.erros,cdp.erros
            result.update(ok=True, job_id=job, reloaded_while_running=True, forced_disconnect=True,
                source_cards=True, image_bytes=True, image_zoom_escape=True, viewport_widths=[1280,390,320],
                export=export,events=len(events),errors=cdp.erros)
        except Exception as exc:
            result['error']=f'{type(exc).__name__}: {exc}'
            if cdp:
                cdp.screenshot('chrome-failure.png')
            for name in ('agent','relay'):
                if (tmp/(name+'.log')).exists():
                    (ART/(name+'-failure.log')).write_bytes((tmp/(name+'.log')).read_bytes()[-12000:])
            raise
        finally:
            if cdp:
                cdp.ws.close()
            for process in reversed(processes):
                process.parar()
            (ART/'chrome-continuity.json').write_bytes(json.dumps(result,ensure_ascii=False,indent=2).encode('utf-8'))
            print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':
    run()
