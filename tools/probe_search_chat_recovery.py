"""Explicit live smoke in disposable SQLite; never accesses a production account."""
import json, os, sys, tempfile, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
os.environ['JULIA_ENV_FILE']=str(Path(tempfile.gettempdir())/'vexx-search-no-env')
import pc_agent, research, shopping, jdui


def main():
    report={'scope':'LIVE_PUBLIC_RETRIEVAL_ISOLATED_SQLITE_NOT_AUTHENTICATED_PRODUCTION','queries':[]}
    original=pc_agent.gerar_texto
    def bounded(cfg,messages,**kw):
        kw['timeout']=20;kw['max_tokens']=1000
        return original({**cfg,'fallbacks':[]},messages,**kw)
    pc_agent.gerar_texto=bounded
    with tempfile.TemporaryDirectory(prefix='vexx-search-repair-') as temp:
        db=pc_agent.open_db(Path(temp)/'qa.sqlite')
        cfg={**pc_agent.ai_config(),'fallbacks':[],'memoria_global':False,'max_tokens':1000}
        for index,query in enumerate(['pesquisa por Minecraft','pesquisa por jogos em promoção na steam']):
            payload={'message_id':f'qa-live-search-{index}','conversation_id':f'qa-chat-{index}',
                     'owner':'u-qa-search','text':query}
            start=time.monotonic()
            try:
                result=pc_agent.ai_completa(db,payload,cfg)
                text=result.get('response_text','')
                _,uis,errors=jdui.normalizar(text)
                blocks=[b for msg in uis for b in msg['blocks']]
                replay=pc_agent.ai_completa(db,payload,cfg)
                row={'query':query,'seconds':round(time.monotonic()-start,2),'error':result.get('error'),
                     'response':text,'components':[b.get('component') for b in blocks],
                     'jdui_errors':errors,'replay_equal':replay.get('replay') is True and replay.get('response_text')==text}
                report['queries'].append(row)
            except Exception as exc:
                report['queries'].append({'query':query,'error':type(exc).__name__,'seconds':round(time.monotonic()-start,2)})
            print(json.dumps({k:v for k,v in report['queries'][-1].items() if k!='response'},ensure_ascii=True),flush=True)
        db.close()
    out=ROOT/'qa-artifacts/search-chat-live.json'
    out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__':main()
