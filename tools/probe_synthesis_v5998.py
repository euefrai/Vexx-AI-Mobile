"""Track C: actual free writer/reviewer with verified public-source snapshot.

No autonomous-discovery claim. Optional delivery targets only the disposable QA
database. Transport timing stores no payload, credentials or private endpoint.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
os.environ['JULIA_ENV_FILE']=str(Path(tempfile.gettempdir())/'v5998-isolated.env')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--qa',type=Path)
    p.add_argument('--artifact-version',choices=['v5998','v5999'],default='v5998')
    args=p.parse_args()
    raw=ROOT/'qa-artifacts'/args.artifact_version/'raw'
    raw.mkdir(parents=True,exist_ok=True)
    if args.output.exists():raise SystemExit('Refusing to overwrite model evidence')
    import pc_agent,research,research_agents as ra,research_synthesis as rs,evidence_graph as eg
    case=next(x for x in json.loads((ROOT/'benchmarks/source_quality_v5998_dev.json').read_text(encoding='utf-8'))['queries'] if x['id']=='hypot')
    ref=hashlib.sha256(b'A|hypot').hexdigest()[:20]
    frozen=ROOT/'qa-artifacts/v5998/raw'/ref/'known-source.json'
    snap=json.loads(frozen.read_text(encoding='utf-8'))
    rec=research.extrair_artigo(snap['body'],snap['url'],consulta=case['query'])
    rec.update(url=snap['url'],final=snap['url'],texto_lido=True)
    coverage=eg.requirement_coverage(case['query'],[rec])
    if not coverage['complete']:raise SystemExit('Track C requires all parsed facets in actual read evidence')
    cfg=pc_agent.ai_config();cfg['fallbacks']=[]
    if not cfg['model'].endswith(':free'):raise SystemExit('Explicit free model required')
    out={'track':'C','scope':'VERIFIED_PUBLIC_SOURCE_INPUT_REAL_FREE_MODEL_NOT_DISCOVERY',
         'model':cfg['model'],'source_url':snap['url'],'source_sha256':hashlib.sha256(frozen.read_bytes()).hexdigest(),
         'input_coverage':eg.compact_coverage(coverage),'calls':[],'transport':[],'first_token_s':None}
    writer=pc_agent._research_writer(cfg,threading.Event())
    def measured(messages,timeout):
        row={'phase':'writing' if not out['calls'] else 'review','input_chars':sum(len(m['content']) for m in messages),
             'timeout_s':timeout};out['calls'].append(row);start=time.monotonic()
        try:
            result=writer(messages,timeout)
            (raw/(args.output.stem+'-'+row['phase']+'.json')).write_text(
                json.dumps({'messages':messages,'response':result},ensure_ascii=False),encoding='utf-8')
            row.update(output_chars=len(result),metadata=writer.last_metadata)
            return result
        except Exception as exc:row['error_code']=rs.safe_provider_code(exc);raise
        finally:row['elapsed_s']=round(time.monotonic()-start,3)
    original=urllib.request.urlopen
    def observed(req,*a,**kw):
        row={'phase':out['calls'][-1]['phase'] if out['calls'] else 'other','timeout_s':kw.get('timeout')}
        out['transport'].append(row);start=time.monotonic()
        try:
            response=original(req,*a,**kw)
            row['http_status']=getattr(response,'status',None)
            return response
        except Exception as exc:
            row['exception_type']=type(exc).__name__
            raise
        finally:row['time_to_headers_or_error_s']=round(time.monotonic()-start,3)
    class SeededSource:
        nome='verified-public-source-fixture'
        def buscar(self,q,limite=6):return [{'titulo':rec['titulo'],'url':snap['url']}]
    def reader(url):
        if url!=snap['url']:raise research.ResearchErro('Snapshot missing','frozen_missing')
        return copy.deepcopy(rec)
    with tempfile.TemporaryDirectory(prefix='v5998-synthesis-') as folder:
        if args.qa:
            private=json.loads((args.qa/'qa-runtime-private.json').read_text(encoding='utf-8'))
            database=Path(private['database']).resolve()
            if database.name!='qa.sqlite' or not database.parent.name.startswith('v5981-admin-qa-') or database.parent.parent!=Path(tempfile.gettempdir()).resolve():
                raise SystemExit('Disposable QA database required')
        else:database=Path(folder)/'qa.sqlite'
        db=pc_agent.open_db(database)
        try:
            owner,conv=(db.execute('SELECT owner_id,conv FROM research_jobs ORDER BY criado_em DESC LIMIT 1').fetchone() if args.qa else ('qa-c','qa-c'))
            job=ra.criar_job(db,owner,case['query'],conv=conv,manual='profunda')
            urllib.request.urlopen=observed;started=time.monotonic()
            try:ra.executar(db,job['id'],owner,[SeededSource()],reader,sintetizar_fn=measured)
            finally:urllib.request.urlopen=original
            stored=ra.carregar_job(db,owner,job['id']);synthesis=ra._resumo(db,stored).get('sintese') or {}
            out.update(job=job['id'],job_state=stored['status'],outcome=stored.get('usados',{}).get('research_outcome'),
                       synthesis_llm=bool(synthesis.get('llm')),fallback_detail=synthesis.get('fallback_detail'),
                       provider_code=synthesis.get('fallback_provider_code'),synthesis_budget=stored.get('usados',{}).get('synthesis_budget'),
                       semantic_review=synthesis.get('semantic_review'),elapsed_s=round(time.monotonic()-started,3))
            if args.qa:out['chat_result_id']=pc_agent._persistir_resultado_pesquisa(db,stored,owner)
            (raw/('C-'+args.output.stem+'.json')).write_text(json.dumps(synthesis,ensure_ascii=False),encoding='utf-8')
        finally:db.close()
    out['limits']=['Source input explicitly seeded; never autonomous discovery.','Nonstreaming writer has no first-token measurement.',
                   'HTTP headers timing does not identify internal provider queue or cold-start cause.','Model support review is not independent human gold.']
    args.output.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:out.get(k) for k in ('synthesis_llm','provider_code','fallback_detail','calls','transport')}))


if __name__=='__main__':main()
