"""Frozen returned-read reclassification only; no network, discovery or model."""
from datetime import datetime
import json
from pathlib import Path
import sys
import subprocess

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import query_intelligence as qi
import research


def main():
    result={'scope':'FROZEN_REPLAY_UNIQUE_RETURNED_READS_ONLY_NOT_FULL_RETRIEVAL',
            'source_revision':subprocess.check_output(['git','rev-parse','HEAD'],text=True,cwd=ROOT).strip(),
            'limits':['No search/query-navigation benefit is measured.',
                      'Same captured body and request clock; unmatched or ambiguous extractions excluded.',
                      'Engine flags do not establish independent relevance or factual correctness.'], 'runs':{}}
    analyze=qi.analyze
    for folder in ['accepted-historical','accepted-holdout']:
        rows=[]
        for file in sorted((ROOT/'qa-artifacts/v5992'/folder).glob('*.json')):
            old=json.loads(file.read_text(encoding='utf-8'))
            if not isinstance(old,dict) or not old.get('id'):continue
            anchor=(old.get('request') or {}).get('resolved_at')
            clock=datetime.fromisoformat(anchor) if anchor else None
            qi.analyze=lambda text,now=None,timezone_name='America/Bahia':analyze(text,now or clock,timezone_name)
            sources=[]
            for source in old.get('sources',[]):
                extracts=[e['result'] for e in old.get('extractions',[]) if e['url']==source['url']]
                if source.get('status')!='aberta' or len(extracts)!=1 or not extracts[0]:continue
                new=research._fonte_de(extracts[0],source,old['query'])
                sources.append({'url':source['url'],'before_eligible':bool(source.get('relevante')),
                                'after_eligible':bool(new['relevante']),'answerability':new.get('answerability')})
            rows.append({'id':old['id'],'sources':sources})
        qi.analyze=analyze
        result['runs'][folder]={'cases':rows,'summary':{'cases':len(rows),
            'unique_returned_reads_replayed':sum(len(r['sources']) for r in rows),
            'before_engine_flags':sum(s['before_eligible'] for r in rows for s in r['sources']),
            'after_engine_flags':sum(s['after_eligible'] for r in rows for s in r['sources'])}}
    (ROOT/'qa-artifacts/v5993/frozen-replay.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print({name:run['summary'] for name,run in result['runs'].items()})


if __name__=='__main__':main()
