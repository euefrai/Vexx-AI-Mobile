"""Allowlisted public summaries from disposable QA; read-only SQLite."""
import argparse,json,sqlite3,tempfile
from pathlib import Path
parser=argparse.ArgumentParser();parser.add_argument('--artifact-version',choices=['v5910','v5911','v5912'],default='v5910')
parser.add_argument('--log-prefix',choices=['live','release'],default='live');args=parser.parse_args()
R=Path(__file__).resolve().parents[1];P=R/'qa-artifacts'/args.artifact_version
private=json.loads((P/'qa-runtime-private.json').read_text())
database=Path(private['database']).resolve()
assert database.name=='qa.sqlite' and database.parent.name.startswith('v5981-admin-qa-')
assert database.is_relative_to(Path(tempfile.gettempdir()).resolve())
db=sqlite3.connect(database.as_uri()+'?mode=ro',uri=True)
cases=[]
for path in sorted(P.glob(args.log_prefix+'-?.log')):
    lines=path.read_text(encoding='utf-8-sig').splitlines()
    if not lines or lines[0]!='### Result':continue
    d=json.loads(lines[1]);row={k:d.get(k) for k in ('name','query','seconds','http_status','content_type','job','job_state',
     'outcome','synthesis_llm','chat_result_id','assistant_messages','reload_preserved','media_cards','page_errors')}
    row['source_card_count']=len(d.get('source_cards',[]));row['source_links']=d.get('links',[])
    row['requirements']=[{'entity':r['entity'],'attribute':r['attribute'],'state':r['state']}
                        for r in (d.get('answer_coverage') or {}).get('requirements',[])]
    if d.get('job'):
        checkpoint=db.execute('SELECT state_json FROM research_context_checkpoints WHERE job_id=? ORDER BY sequence DESC LIMIT 1',(d['job'],)).fetchone()
        if checkpoint:
            synthesis=(json.loads(checkpoint[0])['state'].get('results') or {}).get('synthesis',{})
            row['synthesis']={k:synthesis.get(k) for k in ('llm','fallback_detail','fallback_provider_code','semantic_review','format_normalization','answer_coverage')}
    cases.append(row)
out={'scope':'REAL_CHROME_AUTHENTICATED_FASTAPI_DEVELOPMENT_AGENT_TEMPORARY_SQLITE_NO_URL_SEEDS',
 'cases':cases,'messages':dict(db.execute('select role,count(*) from messages group by role')),
 'message_count':db.execute('select count(*) from messages').fetchone()[0],
 'distinct_message_ids':db.execute('select count(distinct id) from messages').fetchone()[0],
 'models':[r[0] for r in db.execute('select distinct model from ai_requests')],
 'quick_check':db.execute('pragma quick_check').fetchone()[0],
 'limits':['completed_flow in legacy harness means transport/job observed, not acceptance.',
           *(['SQLite includes one failed stale QA session attempt, not counted as successful chat.'] if args.artifact_version=='v5910' else []),
           'LLM validation alone does not establish complete research; inspect outcome and requirement coverage.']}
db.close()
(P/'authenticated-summary.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print([(r['name'],r.get('synthesis')) for r in cases])
