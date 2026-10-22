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
ART = ROOT / 'qa-artifacts/v594'
ART.mkdir(parents=True, exist_ok=True)
harness.ART = ART


def run():
    result = {'kind':'BROWSER_E2E_LOCAL_FIXTURE', 'model_inference':False, 'ok':False}
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
            VEXX_RESEARCH_FIXTURE='1', VEXX_LIVE_TRACE=str(ART/'live-trace.jsonl'), VEXX_FIXTURE_IMAGE_URL=base+'/icon-192.png')
        try:
            processes.append(harness.Processo([sys.executable,'-m','uvicorn','server:app','--host','127.0.0.1','--port',str(port)],tmp/'relay.log',env))
            harness.esperar_http(base+'/api/diag',lambda r:True,30,'relay')
            processes.append(harness.Processo([sys.executable,'tests/live_fixture_agent_v594.py'],tmp/'agent.log',env))
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
            assert cdp.js("document.getElementById('researchBar').hidden"), 'no research bar before starting'
            trace=ART/'live-trace.jsonl'
            if trace.exists():trace.unlink()
            transcript=[]
            def chat(text,expected,timeout=45):
                start=time.monotonic()
                count=cdp.js("document.querySelectorAll('.message.ai').length")
                cdp.js("document.getElementById('messageInput').focus(); true")
                cdp.cmd('Input.insertText',{'text':text})
                cdp.js("document.getElementById('composer').requestSubmit(); true")
                cdp.esperar_js(f"document.querySelectorAll('.message.ai').length>{count} && !aiAbort",bool,timeout,'chat completed: '+text)
                reply=cdp.js("Array.from(document.querySelectorAll('.message.ai')).at(-1).innerText")
                assert any(token in reply for token in expected),reply
                assert 'TODO.md' not in reply and 'Controle remoto' not in reply,reply
                transcript.append(dict(user=text,reply=reply,latency_ms=round((time.monotonic()-start)*1000)))
                (ART/'chat-transcript.json').write_text(json.dumps(transcript,ensure_ascii=False,indent=2),encoding='utf-8')
                return reply
            cdp.js("navigate('chat'); document.getElementById('newChatTop').click(); true")
            cdp.esperar_js("document.querySelectorAll('.message.ai').length===0 && !aiAbort",bool,10,"new chat ready")
            weather=chat('qual a temperatura em ubata bahia agora?',('Clima em Ubatã','indisponível','limitou','Não consegui confirmar'))
            if 'Clima em Ubatã' in weather:
                assert '°C' in weather and 'modelos meteorológicos' in weather and 'Open-Meteo' in weather
                assert cdp.js("document.querySelectorAll('.message.ai .jdui-card').length>0 || document.querySelectorAll('.message.ai .jdui-slot').length>0")
            assert 'Salvador' not in weather and 'Ubá,' not in weather,weather
            cdp.screenshot('weather-desktop.png')
            cdp.cmd('Emulation.setDeviceMetricsOverride',{'width':390,'height':844,'deviceScaleFactor':1,'mobile':True})
            tomorrow=chat('e amanhã?',('Previsão','indisponível','limitou','Não consegui confirmar'))
            assert 'Ubatã' in tomorrow or 'indisponível' in tomorrow or 'limitou' in tomorrow
            assert cdp.js('document.documentElement.scrollWidth<=innerWidth+1')
            cdp.screenshot('weather-mobile.png')
            assert cdp.js("getComputedStyle(document.querySelector('.message.ai table td:first-child')).whiteSpace==='nowrap'")
            cdp.cmd('Emulation.setDeviceMetricsOverride',{'width':320,'height':844,'deviceScaleFactor':1,'mobile':True})
            assert cdp.js('document.documentElement.scrollWidth<=innerWidth+1')
            cdp.screenshot('weather-mobile-320.png')
            cdp.cmd('Emulation.setDeviceMetricsOverride',{'width':390,'height':844,'deviceScaleFactor':1,'mobile':True})

            before_geo=trace.read_text(encoding='utf-8').count('"kind": "geocode"') if trace.exists() else 0
            chat('oi',('Oi!',))
            after_geo=trace.read_text(encoding='utf-8').count('"kind": "geocode"') if trace.exists() else 0
            assert before_geo==after_geo,'greeting invoked geocoder'
            time_reply=chat('que horas são agora?',('America/Bahia','São Paulo','America/Sao_Paulo','UTC'))
            assert 'relógio do sistema' in time_reply.lower()
            cdp.screenshot('time-mobile.png')
            cdp.js("document.getElementById('newChatTop').click(); true")
            cdp.esperar_js("document.querySelectorAll('.message.ai').length===0 && !aiAbort",bool,10,"new chat ready")
            chat('qual a temperatura?',('em qual cidade',))
            chat('oi, tudo bem?',('Oi!',))
            result['live_chat']=dict(weather_live='Clima em Ubatã' in weather,greeting_geocode_calls=after_geo-before_geo,isolated_new_chat=True,turns=len(transcript))
            cdp.cmd('Emulation.setDeviceMetricsOverride',{'width':1280,'height':900,'deviceScaleFactor':1,'mobile':False})

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
            cdp.esperar_js("researchJob === null && document.getElementById('researchBar').hidden",bool,25,'terminal bar cleared')
            result['terminal_bar_cleared']=True
            cdp.js(f"navigate('research'); researchWorkspaceAbrir({json.dumps(job)})")
            cdp.esperar_js("document.querySelectorAll('#researchWorkspaceView .jdui-srccard').length",lambda n:n>0,15,'source cards')
            cdp.esperar_js("Array.from(document.querySelectorAll('#researchWorkspaceView img')).some(i=>i.complete&&i.naturalWidth>0)",bool,15,'real local image bytes')
            cdp.js("document.querySelector('#researchWorkspaceView .jdui-media-zoom').click(); true")
            assert cdp.js("!!document.querySelector('dialog[open]')")
            cdp.cmd('Input.dispatchKeyEvent',{'type':'keyDown','key':'Escape','code':'Escape','windowsVirtualKeyCode':27,'nativeVirtualKeyCode':27})
            cdp.cmd('Input.dispatchKeyEvent',{'type':'keyUp','key':'Escape','code':'Escape','windowsVirtualKeyCode':27,'nativeVirtualKeyCode':27})
            cdp.esperar_js("!document.querySelector('dialog[open]')",bool,5,'Escape closes image')
            cdp.js("document.getElementById('researchWorkspaceView').scrollIntoView({block:'start'}); true")
            cdp.screenshot('research-desktop.png')
            cdp.js("document.querySelector('#researchWorkspaceView .jdui-source-title').closest('.jdui-srccard').scrollIntoView({block:'start'}); true")
            cdp.screenshot('sources-desktop.png')
            for width in (390,320):
                cdp.cmd('Emulation.setDeviceMetricsOverride',{'width':width,'height':844,'deviceScaleFactor':1,'mobile':True})
                time.sleep(.3)
                assert cdp.js('document.documentElement.scrollWidth <= innerWidth + 1'),f'overflow at {width}'
                cdp.screenshot(f'research-mobile-{width}.png')
            # Explicit synthetic UI fixtures; these are not live news/events/offers.
            import research_view, jdui
            sources=[
                {'titulo':'Notícia fictícia de QA','url':base+'/icon-192.png','publicado_em':'2026-10-22','publicador':'Veículo de teste','status':'encontrada','content_scope':'feed_metadata','trecho':'Fixture de renderização, sem acontecimento real.','imagens':[{'url':base+'/icon-192.png'}],'vertical':{'kind':'news','data':{}}},
                {'titulo':'Evento fictício de QA','url':base+'/icon-192.png','texto_lido':True,'vertical':{'kind':'events','data':{'event_date':'2026-10-29T19:00:00-03:00','location':'Local fictício','organizer':'Organizador de teste'}}},
                {'titulo':'Rota fictícia de QA','url':base+'/icon-192.png','texto_lido':True,'vertical':{'kind':'bus_travel','data':{'departureBusStop':'Origem de teste','arrivalBusStop':'Destino de teste','departureTime':'2026-10-29T09:00:00-03:00'}}},
                {'titulo':'Publicação fictícia de QA','url':base+'/icon-192.png','doi':'10.5555/fixture-qa','authors':['Autor de teste'],'year':2024,'trecho':'Abstract fictício','content_scope':'abstract_only'}]
            message={'version':jdui.VERSION,'blocks':[{'type':'ui','component':'sources','props':{'title':'Fixtures explícitas de apresentação','items':[research_view.source_card(row) for row in sources]}}]}
            ok,message,errors=jdui.validar_mensagem(message);assert ok,errors
            cdp.js("(() => {const root=document.getElementById('researchWorkspaceView');root.replaceChildren();JDUI.mount(root,["+json.dumps(message)+"]);return true;})()")
            cdp.esperar_js("document.querySelector('.jdui-source-image').complete && document.querySelector('.jdui-source-image').naturalWidth>0",bool,10,'source image bytes')
            assert cdp.js("document.getElementById('researchWorkspaceView').textContent.includes('disponibilidade atual') && document.getElementById('researchWorkspaceView').textContent.includes('10.5555/fixture-qa')")
            for width in (1280,390,320):
                cdp.cmd('Emulation.setDeviceMetricsOverride',{'width':width,'height':900 if width==1280 else 844,'deviceScaleFactor':1,'mobile':width!=1280})
                cdp.js("document.getElementById('researchWorkspaceView').scrollIntoView({block:'start'});true")
                time.sleep(.3)
                assert cdp.js("document.documentElement.scrollWidth <= innerWidth+1 && [...document.querySelectorAll('#researchWorkspaceView .jdui-srccard')].every(e=>e.scrollWidth<=e.clientWidth+1)")
                cdp.screenshot(f'contextual-{width}.png')
            result['contextual_cards_fixture']=True
            # Export must return real bytes, not a decorative control.
            export=cdp.js(f"fetch('/api/research/export?job_id={job}&formato=md').then(async r=>({{status:r.status,bytes:(await r.arrayBuffer()).byteLength}}))")
            assert export['status']==200 and export['bytes']>100,export
            cdp.cmd('Emulation.setDeviceMetricsOverride',{'width':1280,'height':900,'deviceScaleFactor':1,'mobile':False})
            cdp.js("navigate('chat'); document.getElementById('newChatTop').click(); true")
            cdp.esperar_js("document.querySelectorAll('.message.ai').length===0 && !aiAbort",bool,10,"new chat ready")
            for text in ('Quanto vale 100 dólares em reais agora? Mostre a fonte e o horário da cotação.',
                         'Como mudou o dólar em relação ao real nos últimos 30 dias?'):
                count=cdp.js("document.querySelectorAll('.message.ai').length")
                cdp.js("document.getElementById('messageInput').focus(); true")
                cdp.cmd('Input.insertText',{'text':text})
                cdp.js("document.getElementById('composer').requestSubmit(); true")
                cdp.esperar_js(f"Array.from(document.querySelectorAll('.message.ai')).length > {count} && Array.from(document.querySelectorAll('.message.ai')).at(-1).textContent.includes('Frankfurter')",bool,35,'external currency answer')
            assert cdp.js("document.querySelectorAll('.message.ai .jdui-slot').length >= 2")
            cdp.screenshot('exchange-desktop.png')
            cdp.cmd('Page.reload',{'ignoreCache':True})
            cdp.esperar_js("Array.from(document.querySelectorAll('.message.ai')).some(e=>e.textContent.includes('Frankfurter'))",bool,20,'exchange persists after reload')
            cdp.cmd('Emulation.setDeviceMetricsOverride',{'width':390,'height':844,'deviceScaleFactor':1,'mobile':True})
            cdp.esperar_js("document.getElementById('drawer').getBoundingClientRect().right <= 1",bool,5,'mobile drawer settled')
            assert cdp.js('document.documentElement.scrollWidth <= innerWidth + 1')
            cdp.screenshot('exchange-mobile.png')
            chart=cdp.js(r"(() => { const svg=document.querySelector('.message.ai .jdui-chart svg'); const labels=[...svg.querySelectorAll('text')].filter(n=>Number(n.getAttribute('y'))===212); const boxes=labels.map(n=>n.getBoundingClientRect()).sort((a,b)=>a.x-b.x); return {points:svg.querySelectorAll('circle').length, ticks:labels.length, overlap:boxes.some((b,i)=>i&&b.left<boxes[i-1].right-1), dated:[...svg.querySelectorAll('circle')].every(n=>/\d{4}-\d{2}-\d{2}/.test(n.getAttribute('aria-label')||''))}; })()" )
            assert chart['points']>=2 and chart['ticks']<=4 and not chart['overlap'] and chart['dated'],chart
            result['chart']=chart
            result['exchange_chat_external']=True
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
                result['ui_state']=cdp.js("({job:researchJob&&{id:researchJob.id,seq:researchJob.seq},hidden:document.getElementById('researchBar').hidden,label:document.getElementById('researchLabel').textContent,last:[...document.querySelectorAll('#researchSteps .timeline-item')].slice(-3).map(n=>n.dataset.tipo)})")
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
