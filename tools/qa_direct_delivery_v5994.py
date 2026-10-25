"""Controlled discovery fixture + real public read + real local persistence.

Never presented as autonomous search or complete model E2E. Only the disposable
QA SQLite created by serve_admin_qa_v5981 may be opened for writes.
"""
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=ROOT/'qa-artifacts/v5994/direct-delivery.json')
    args=parser.parse_args()
    if args.output.exists():raise SystemExit('Refusing to overwrite previous delivery evidence')
    import pc_agent,research_agents as ra
    qa=ROOT/'qa-artifacts/v5994'
    private=json.loads((qa/'qa-runtime-private.json').read_text(encoding='utf-8'))
    database=Path(private['database']).resolve()
    if (database.name!='qa.sqlite' or not database.parent.name.startswith('v5981-admin-qa-')
            or database.parent.parent!=Path(tempfile.gettempdir()).resolve()):
        raise SystemExit('Disposable QA path required')
    if not os.environ.get('JULIA_ENV_FILE'):raise SystemExit('Isolated environment required')
    db=pc_agent.open_db(database)
    owner,conv=db.execute('SELECT owner_id,conv FROM research_jobs ORDER BY criado_em DESC LIMIT 1').fetchone()
    url='https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Array/toSorted'
    class DirectURLFixture:
        nome='fixture-explicit-public-url'
        def buscar(self,query,limite=6):return [dict(titulo='Array.prototype.toSorted',url=url,trecho='')]
    question='Como funciona Array.prototype.toSorted, qual sua sintaxe e limitações?'
    job=ra.criar_job(db,owner,question,conv=conv,modo='profunda')
    result=ra.executar(db,job['id'],owner,[DirectURLFixture()],ra.recuperar_real())
    stored=ra.carregar_job(db,owner,job['id'])
    reply=pc_agent._persistir_resultado_pesquisa(db,stored,owner)
    evidence=ra.listar_evidencias(db,owner,job['id'])
    row=dict(scope='FIXTURE_DISCOVERY_REAL_PUBLIC_READ_SQLITE_DELIVERY_NO_MODEL',
             job_id=job['id'],reply_id=reply,question=question,state=stored['status'],
             coverage=stored.get('usados',{}).get('answer_coverage'),
             evidence=[{k:e.get(k) for k in ('id','url','answer_passages','answerability')} for e in evidence],
             limitations=['Discovery URL explicitly seeded as a test fixture; not discovered autonomously.',
                          'Extractive fallback, no model inference in this test.'])
    args.output.write_text(json.dumps(row,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(state=row['state'],reply=bool(reply),evidence=len(evidence))))
    db.close()


if __name__=='__main__':main()
