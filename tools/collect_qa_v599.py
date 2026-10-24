"""Allowlisted evidence from a disposable QA database; never production users."""
import argparse
import json
from pathlib import Path
import sqlite3
import tempfile

ROOT=Path(__file__).resolve().parents[1]
QA=ROOT/'qa-artifacts/v599'


def collect(prefix,output):
    runtime=json.loads((QA/'qa-runtime-private.json').read_text(encoding='utf-8'))
    database=Path(runtime['database']).resolve()
    assert database.is_relative_to(Path(tempfile.gettempdir()).resolve())
    assert database.parent.name.startswith('v5981-admin-qa-') and database.name=='qa.sqlite'
    db=sqlite3.connect(database.as_uri()+'?mode=ro',uri=True)
    cases=[]
    for path in sorted(QA.glob(prefix+'*.log')):
        text=path.read_text(encoding='utf-8-sig')
        if text.startswith('### Result\n'):cases.append(json.loads(text.splitlines()[1]))
    caches=[]
    for query,response in db.execute('select consulta,resposta from research_cache'):
        data=json.loads(response)
        caches.append({'query':query,'state':data.get('estado'),'read':data.get('fontes_lidas'),
              'useful':data.get('fontes_uteis'),'media':len(data.get('midia') or []),
              'reservoir':data.get('candidate_reservoir'),
              'sources':[{k:s.get(k) for k in ('url','titulo','publicado_em','status','content_scope','relevante','vertical')} for s in data.get('fontes') or []]})
    result={'scope':'AUTHENTICATED_E2E; isolated QA accounts and SQLite only','cases':cases,'cache':caches,
            'messages':dict(db.execute('select role,count(*) from messages group by role').fetchall()),
            'unique_message_ids':db.execute('select count(distinct id) from messages').fetchone()[0],
            'models':[r[0] for r in db.execute('select distinct model from ai_requests')],
            'requests':dict(db.execute('select state,count(*) from ai_requests group by state').fetchall()),
            'research_jobs':dict(db.execute('select status,count(*) from research_jobs group by status').fetchall())}
    db.close()
    (QA/output).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'cases':len(cases),'messages':result['messages'],'requests':result['requests']}))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--prefix',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args();assert Path(args.output).name==args.output
    collect(args.prefix,args.output)
