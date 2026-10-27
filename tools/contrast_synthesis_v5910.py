"""B agent then A direct adapter with identical source and verdict arguments."""
import copy,json,os
from pathlib import Path
import sys,tempfile,threading
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
os.environ['JULIA_ENV_FILE']=str(Path(tempfile.gettempdir())/'v5910-none.env')
import synthesis_capture_v5910 as capture
import pc_agent,research_agents as ra,research_synthesis as rs


def main():
    directory=ROOT/'qa-artifacts/v5910/raw/contrast'
    directory.mkdir(parents=True,exist_ok=True)
    if (directory/'result.json').exists():raise SystemExit('Refusing repeat of real model contrast')
    cfg=pc_agent.ai_config();cfg['fallbacks']=[]
    if not cfg['model'].endswith(':free'):raise SystemExit('Explicitly free model required')
    case,record=capture.seed_research()
    original=rs.generate;inputs=[]
    def measured(objective,sources,verdicts,*args,**kw):
        inputs.append(copy.deepcopy([objective,sources,verdicts]))
        return original(objective,sources,verdicts,*args,**kw)
    rs.generate=measured
    restore=capture.install(directory/'B')
    out={'model':cfg['model'],'scope':'KNOWN_PUBLIC_SOURCE_TRANSPORT_NOT_DISCOVERY'}
    with tempfile.TemporaryDirectory(prefix='v5910-contrast-') as temp:
        db=pc_agent.open_db(Path(temp)/'qa.sqlite')
        try:
            job=ra.criar_job(db,'qa',case['query'],conv='contrast',manual='profunda')
            ra.executar(db,job['id'],'qa',ra.provedores_reais(),ra.recuperar_real(),
                        sintetizar_fn=pc_agent._research_writer(cfg,threading.Event()))
            stored=ra.carregar_job(db,'qa',job['id']);b=ra._resumo(db,stored).get('sintese') or {}
            out['B']={k:b.get(k) for k in ('llm','fallback_detail','fallback_provider_code','semantic_review')}
        finally:db.close();restore();rs.generate=original
    if inputs:
        (directory/'evidence-input.json').write_text(json.dumps(inputs[0],ensure_ascii=False),encoding='utf-8')
        restore=capture.install(directory/'A')
        try:
            a=original(*inputs[0],pc_agent._research_writer(cfg,threading.Event()))
            out['A']={k:a.get(k) for k in ('llm','semantic_review','provenance')}
        except Exception as exc:
            out['A']={'llm':False,'failure':rs.failure_detail(exc),'provider':rs.safe_provider_code(exc)}
        finally:restore()
    else:out['A']={'blocked':'No agent synthesis inputs'}
    (directory/'result.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(out,ensure_ascii=False))

if __name__=='__main__':main()
