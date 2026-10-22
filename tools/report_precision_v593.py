"""Reproduce final metrics and explicitly labelled replays from stored probes."""
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import query_intelligence as qi
import research
import research_view
import search_verticals
from bench_universal_v592 import CASES

ART=ROOT/'qa-artifacts/v593'


def read(name):
    return json.loads((ART/name).read_text(encoding='utf-8-sig'))


def main():
    snapshots=read('live-after.json')
    replacements={'air':'air-repair.json','bus-feira':'bus-repair.json','transformer':'transformer-repair.json'}
    rows=[]
    for snapshot in snapshots:
        origin=replacements.get(snapshot['case'],'live-after.json')
        row=read(origin) if origin!='live-after.json' else snapshot
        request=row.get('request') or qi.analyze(row['query'])
        # Source review is a deterministic replay; original live state is retained.
        reviewed=[]
        for s in row.get('sources') or []:
            assessed=search_verticals.assess(request,{**s,'trecho':s.get('texto_lido') or s.get('trecho','')})
            reviewed.append({'url':s.get('url'),'eligible':bool(s.get('relevante')) and assessed['eligible'],'reasons':assessed['reasons'],'scope':s.get('content_scope')})
        rows.append({'kind':'LIVE_RETRIEVAL','id':row['case'],'source_artifact':origin,
            'query':row['query'],'constraints':request.get('parameters'), 'executed_at':row.get('executed_at'),
            'queries':row.get('queries'), 'discovered':row.get('discovered'), 'sources':row.get('sources'),
            'data':row.get('currency_data') or row.get('products') or row.get('source_contracts'),
            'live_state_at_capture':row.get('state'),'reply':row.get('final'),
            'cards':row.get('contextual_jdui') or row.get('jdui'),'seconds':row.get('seconds'),
            'provider_decisions':row.get('provider_decisions'), 'page_diagnostics':row.get('page_diagnostics'),
            'filter_review':{'kind':'DETERMINISTIC_REPLAY','sources':reviewed}})
    replays=[]
    for row in snapshots:
        if row['case'] not in ('municipal','capital','regional'):continue
        sources=[s for s in row.get('sources',[]) if s.get('content_scope')=='feed_metadata']
        if not sources:continue
        sources=[{**s,'meta':{'publicado_em':s.get('publicado_em','')},'tipo':'noticia'} for s in sources]
        byurl={s['url']:s for s in sources}
        def unread(url):
            s=byurl[url]
            return {'titulo':s['titulo'],'texto':'','lida':False,'content_scope':'feed_metadata','trecho_usado':s.get('trecho',''),'metadados':{'publicado_em':s.get('publicado_em',''),'site':s.get('publicador','')}}
        db=sqlite3.connect(':memory:');research.criar_tabelas(db)
        result=research.pesquisa_rapida(db,'replay',row['query'],buscar_fn=lambda q:sources,recuperar_fn=unread)
        assert result['fontes_uteis']==0 and result['estado']=='parcial'
        replays.append({'kind':'DETERMINISTIC_REPLAY','source_artifact':'live-after.json','id':row['case'],
            'network_calls':0,'result':result,'cards':research_view.contextual_fence(result['fontes'])})
        db.close()
    contracts=[]
    for group,query,_ in CASES:
        request=qi.analyze(query,now=datetime(2026,10,22,12,tzinfo=timezone.utc))
        contracts.append({'kind':'DETERMINISTIC','group_from_v592':group,'query':query,'request':request,
                          'reply':'Contract only; no retrieval or factual answer scored.','cards':None,'sources':[], 'coverage':'not_measured'})
    report={'schema':'universal-benchmark/3.0','scope':'Not universal accuracy. All live captures and deterministic replays are separately labelled.',
            'live':rows,'news_replay':replays,'request_contracts':contracts,
            'browser':read('chrome-continuity.json'),'real_model':read('model-availability.json')}
    (ART/'universal-v3.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    metrics={}
    for name in ('before','after'):
        report=read('precision-'+name+'.json')
        queries=[q for c in report['documents']['5']['cases'] for q in c['queries']]
        returned=sum(q['metrics']['retrieved_count_at_k'] for q in queries)
        hits=sum(round(q['metrics']['precision_at_k']*5) for q in queries)
        metrics[name]={'document_macro':{k:r['retrieval_metrics'] for k,r in report['documents'].items()},
            'returned_document_precision_micro':hits/returned if returned else 0,
            'returned_documents':returned,'relevant_hits':hits,'queries':len(queries),
            'holdout_macro':{key:sum(c[key] for c in report['holdout'])/len(report['holdout']) for key in ('eligible_precision','eligible_recall')},
            'holdout_p5':sum(c['at5']['precision_at_k'] for c in report['holdout'])/len(report['holdout']),
            'holdout_ndcg10':sum(c['at10']['ndcg_at_k'] for c in report['holdout'])/len(report['holdout']),
            'holdout_sha256':report['holdout_sha256']}
    assert metrics['before']['holdout_sha256']==metrics['after']['holdout_sha256']
    (ART/'metrics-comparison.json').write_text(json.dumps(metrics,indent=2),encoding='utf-8')
    print('Universal 3.0:',len(rows),'live captures,',len(replays),'news replays;',len(contracts),'request contracts')


if __name__=='__main__':main()
