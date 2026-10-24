"""Offline analysis of public retrieval artifacts; no model, fetch or credentials."""
import argparse
from collections import Counter
import json
from pathlib import Path
from statistics import median


REASONS={'TEMPORAL_MISMATCH':'DATE_MISMATCH','ENTITY_MISMATCH':'HARD_CONSTRAINT_MISMATCH',
         'SOURCE_MISMATCH':'HARD_CONSTRAINT_MISMATCH','TOPIC_MISMATCH':'LOW_RELEVANCE',
         'RELEVANCE_MISMATCH':'LOW_RELEVANCE','INCOMPLETE_EVIDENCE':'EVIDENCE_INSUFFICIENT'}


def analyze_case(row):
    reservoir=row.get('reservoir') or {}
    fetched={entry['url']:entry for entry in row.get('fetches',[]) if entry.get('url')}
    sources={source['url']:source for source in row.get('sources',[]) if source.get('url')}
    candidates=[]
    for item in reservoir.get('items',[]):
        fetch=fetched.get(item['url']) or {};source=sources.get(item['url']) or {}
        selected=item.get('selected',bool(fetch))
        errors=item.get('fetch_error') or fetch.get('error') or ''
        losses=list(item.get('losses') or [])
        if not losses:
            if errors:losses.append('FETCH_BLOCKED' if errors in ('bloqueado','rate_limited') else 'FETCH_FAILED')
            losses.extend(REASONS.get(reason,reason) for reason in item.get('reasons') or [])
            if selected and not item.get('read') and not errors:losses.append('EVIDENCE_INSUFFICIENT')
            if not selected:losses.append('DISCOVERY_ONLY' if item.get('origin')=='google-news' else 'READ_BUDGET_NOT_SELECTED')
        candidates.append({**item,'selected':selected,'returned':item.get('returned',bool(source)),
                           'final_url':item.get('final_url') or fetch.get('final'),
                           'losses':list(dict.fromkeys(losses)),
                           'extracted_chars':item.get('extracted_chars')})
    losses=Counter(code for item in candidates for code in item['losses'])
    if reservoir.get('unique_candidates')==0:
        losses['DISCOVERY_EMPTY']+=1
    elif not reservoir:
        losses['PROBE_FAILED' if row.get('error') else 'TRACE_UNAVAILABLE']+=1
    return {'id':row.get('id'),'question':row.get('query'),'intent_category':row.get('category'),
            'request':row.get('request'),'queries':row.get('calls') or [],
            'network_fetches':row.get('fetches') or [],'candidates':candidates,
            'unique_candidates':reservoir.get('unique_candidates'),'omitted_diagnostic_rows':reservoir.get('omitted'),
            'losses':dict(losses),'state':row.get('state'),'opened_returned':row.get('opened'),
            'eligible_read_returned':row.get('eligible_read'),'seconds':row.get('seconds'),
            'read_in_candidate_pool':sum(bool(item.get('read')) for item in candidates),
            'extraction_trace_available':any('extracted_chars' in item for item in reservoir.get('items',[])),
            'synthesis':'NOT_EXECUTED_RETRIEVAL_PROBE','jdui':'NOT_EXECUTED_RETRIEVAL_PROBE',
            'factual_precision':None,'absolute_recall':None,'judged_incorrect_rejections':None}


def summarize(folder):
    cases=[analyze_case(json.loads(path.read_text(encoding='utf-8')))
           for path in sorted(folder.glob('eva-*.json'))]
    latencies=[case['seconds'] for case in cases if isinstance(case['seconds'],(int,float))]
    return {'scope':'OFFLINE_ANALYSIS_OF_LIVE_EXTERNAL','input_folder':str(folder),
            'cases':cases,'summary':{'cases':len(cases),
                'states':dict(Counter(case['state'] or 'not_reported' for case in cases)),
                'opened_returned':sum(case['opened_returned'] or 0 for case in cases),
                'eligible_read_returned':sum(case['eligible_read_returned'] or 0 for case in cases),
                'read_in_candidate_pool':sum(case['read_in_candidate_pool'] for case in cases),
                'provider_calls':sum(len(case['queries']) for case in cases),
                'network_fetches':sum(len(case['network_fetches']) for case in cases),
                'median_seconds':round(median(latencies),3) if latencies else None,
                'losses':dict(sum((Counter(case['losses']) for case in cases),Counter()))},
            'limits':['Read counters distinguish returned sources from the bounded candidate pool.',
                      'Missing historical traces remain unknown; provider blocks are not product defects.',
                      'No independent relevance denominator, factual or citation judgments.']}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder',type=Path);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();result=summarize(args.folder)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result['summary'],ensure_ascii=False))
