"""Single free synthesis diagnostic from an actually fetched public document.

This bypasses discovery to isolate inference. Never label it full search E2E.
No provider fallback or indefinite retry; normal writing + mandatory review only.
"""
import json
import os
from pathlib import Path
import sys
import threading
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=ROOT/'qa-artifacts/v5994/isolated-real-model.json')
    args=parser.parse_args()
    if args.output.exists():raise SystemExit('Refusing to overwrite prior inference evidence')
    if not os.environ.get('JULIA_ENV_FILE'):
        raise SystemExit('Explicit isolated environment required')
    import pc_agent,research,web_extract,evidence_graph,research_synthesis
    cfg=pc_agent.ai_config()
    if not cfg['model'].endswith(':free'):
        raise SystemExit('Explicit free model required')
    cfg['fallbacks']=[]
    url='https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Array/toSorted'
    question='Como funciona Array.prototype.toSorted, qual sua sintaxe e quais as limitações?'
    record={'scope':'REAL_MODEL_ISOLATED_SYNTHESIS_NOT_AUTHENTICATED_SEARCH_E2E',
            'model':cfg['model'],'source_url':url,'objective':question,'calls':[],
            'status':'SOURCE_INSUFFICIENT','phase_seconds':{},'source_read':False}
    target=args.output
    writer=pc_agent._research_writer(cfg,threading.Event())
    def call(messages,timeout):
        started=time.monotonic();entry={'context_chars':sum(len(m['content']) for m in messages),'timeout_seconds':timeout}
        record['calls'].append(entry)
        try:
            value=writer(messages,timeout);entry['response_chars']=len(value);return value
        except Exception as exc:
            entry['error_code']=research_synthesis.safe_provider_code(exc)
            raise
        finally:entry['seconds']=round(time.monotonic()-started,3)
    try:
        start=time.monotonic();final,body=research.baixar(url,timeout=8)
        record['phase_seconds']['retrieval']=round(time.monotonic()-start,3)
        start=time.monotonic();doc=web_extract.extrair_pagina(body,final,question)
        record['phase_seconds']['extraction']=round(time.monotonic()-start,3)
        coverage=evidence_graph.requirement_coverage(question,[{**doc,'url':final,'lida':bool(doc.get('texto'))}])
        passages=evidence_graph.select_answer_passages(coverage)
        record['source_read']=bool(doc.get('texto'));record['coverage']=evidence_graph.compact_coverage(coverage)
        if not passages:return
        # Whole literal spans, bounded as in the existing writer. No paraphrase
        # silently replaces evidence; quotation ranges enforce passage boundaries.
        excerpt='';ranges=[]
        for p in passages:
            if len(excerpt)+len(p['text'])+2>1800:continue
            prefix='\n\n' if excerpt else '';start=len(excerpt)+len(prefix)
            excerpt+=prefix+p['text'];ranges.append({'id':p['id'],'start':start,'end':len(excerpt)})
        source={'id':'S1','evidence_id':'direct-read-s1','title':doc.get('titulo',''),
                'url':final,'excerpt':excerpt,'scope':'retrieved_page_excerpt','passage_ranges':ranges}
        record['evidence_passage_ids']=[p['id'] for p in passages]
        start=time.monotonic()
        result=research_synthesis.generate(question,[source],[],call,timeout=25)
        record['phase_seconds']['synthesis_and_validation']=round(time.monotonic()-start,3)
        record['status']='PARTIAL_VERIFIED' if result else 'SYNTHESIS_REJECTED'
        record['result']=result
    except Exception as exc:
        code=research_synthesis.safe_provider_code(exc)
        record['error_code']=code
        record['failure_detail']=research_synthesis.failure_detail(exc)
        record['status']=('MODEL_RATE_LIMITED' if code in ('rate_limit','rate_limited') else
                          'MODEL_TIMEOUT' if code=='timeout' else 'SYNTHESIS_REJECTED' if record['calls'] else 'SOURCE_INSUFFICIENT')
    finally:
        record['limits']=['No discovery/plan/chat delivery/reload in this diagnostic.',
                          'No SUCCESS_VERIFIED declaration; parsed facet coverage is not complete factual verification.',
                          'First token timing unavailable in the nonstreaming research writer.',
                          'Synthesis and validation time reported together where nested calls cannot be separated.']
        target.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({k:record[k] for k in ('status','model','source_read','calls')},ensure_ascii=False))


if __name__=='__main__':main()
