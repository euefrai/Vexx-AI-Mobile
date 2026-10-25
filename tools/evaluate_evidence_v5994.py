"""Evaluate requirement-level support, separate from parsing and live retrieval."""
import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
import sys
import time
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import evidence_graph as eg


def evaluate(rows):
    decisions=[]
    start=time.perf_counter()
    for row in rows:
        read=row['read_state']=='READ'
        src=dict(id=row['id'],url=row['source'],titulo=row['entity'],trecho=row['passage'],
                 texto_lido=read,content_scope='metadata_only' if row['read_state']=='METADATA_ONLY' else 'page_text')
        # Calibrate the relation layer against explicit annotated requirements;
        # parser success is a separate measurement, not a prerequisite for recall.
        req=dict(id='R-corpus',entity=row['entity'],attribute=row['attribute'],description=row['requirement'],
                 constraints={'mandatory_conditions':row['mandatory_conditions']})
        import inspect
        kwargs={'requirements':[req]} if 'requirements' in inspect.signature(eg.requirement_coverage).parameters else {}
        if kwargs:
            cov=eg.requirement_coverage(row['question'],[src],**kwargs)
        else:
            # Baseline uses the exact existing matcher with explicit requirement
            # injection only at its parser boundary; no classification changes.
            import query_intelligence as qi
            original=qi.answer_requirements
            qi.answer_requirements=lambda _: [dict(req)]
            try:cov=eg.requirement_coverage(row['question'],[src])
            finally:qi.answer_requirements=original
        matched=[p for p in cov['passages'] if p['requirement_id']=='R-corpus']
        pred=('DIRECT_SUPPORT' if any(p.get('support_label','DIRECT_SUPPORT')=='DIRECT_SUPPORT' for p in matched)
              else 'PARTIAL_SUPPORT' if matched else 'REJECTED')
        decisions.append(dict(id=row['id'],domain=row['domain'],gold=row['label'],prediction=pred,
                              retained=bool(matched),complete=cov['complete']))
    def metrics(items):
        tp=sum(d['retained'] and d['gold'] in ('DIRECT_SUPPORT','PARTIAL_SUPPORT') for d in items)
        fp=sum(d['retained'] and d['gold'] not in ('DIRECT_SUPPORT','PARTIAL_SUPPORT') for d in items)
        fn=sum(not d['retained'] and d['gold'] in ('DIRECT_SUPPORT','PARTIAL_SUPPORT') for d in items)
        tn=len(items)-tp-fp-fn
        ratio=lambda n,d: round(n/d,4) if d else None
        precision=ratio(tp,tp+fp);recall=ratio(tp,tp+fn)
        return dict(n=len(items),tp=tp,fp=fp,fn=fn,tn=tn,precision=precision,recall=recall,
            f1=ratio(2*tp,2*tp+fp+fn),false_positive_rate=ratio(fp,fp+tn),false_negative_rate=ratio(fn,tp+fn),
            partial_support_recall=ratio(sum(d['retained'] and d['gold']=='PARTIAL_SUPPORT' for d in items),sum(d['gold']=='PARTIAL_SUPPORT' for d in items)),
            direct_support_precision=ratio(sum(d['prediction']=='DIRECT_SUPPORT' and d['gold']=='DIRECT_SUPPORT' for d in items),sum(d['prediction']=='DIRECT_SUPPORT' for d in items)),
            incorrectly_promoted_partials=sum(d['gold']=='PARTIAL_SUPPORT' and d['complete'] for d in items),
            requirement_coverage=ratio(sum(d['complete'] and d['gold']=='DIRECT_SUPPORT' for d in items),sum(d['gold']=='DIRECT_SUPPORT' for d in items)),
            confusion=dict(Counter(d['gold']+' -> '+d['prediction'] for d in items)))
    return dict(scope='ANNOTATED_CORPUS_SYNTHETIC_AGENT_ANNOTATED_NOT_GLOBAL_PRECISION',
                milliseconds=round((time.perf_counter()-start)*1000,2),aggregate=metrics(decisions),
                categories={k:metrics([d for d in decisions if d['domain']==k]) for k in sorted({d['domain'] for d in decisions})},decisions=decisions)


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    p.add_argument('--split',choices=['TRAIN_OR_DEV','VALIDATION','BLIND_HOLDOUT','all'],default='all')
    p.add_argument('--corpus',type=Path,default=ROOT/'benchmarks/evidence_corpus_v5994.json')
    p.add_argument('--baseline-revision',help='Import immutable baseline modules into a temporary directory')
    a=p.parse_args();data=json.loads(a.corpus.read_text(encoding='utf-8'))
    if 'sealed' in a.corpus.name and not (ROOT/'qa-artifacts/v5994/code-freeze.json').exists():
        raise SystemExit('Freeze candidate before opening sealed evaluation')
    rows=[r for r in data['examples'] if a.split=='all' or r['split']==a.split]
    if a.baseline_revision:
        with tempfile.TemporaryDirectory(prefix='v5994-baseline-') as tmp:
            for name in ('evidence_graph.py','query_intelligence.py','web_extract.py'):
                raw=subprocess.check_output(['git','show',a.baseline_revision+':'+name],cwd=ROOT)
                (Path(tmp)/name).write_bytes(raw)
            sys.path.insert(0,tmp)
            for name in ('evidence_graph','query_intelligence','web_extract'):sys.modules.pop(name,None)
            global eg
            import evidence_graph as eg
            result=evaluate(rows)
    else:result=evaluate(rows)
    result.update(corpus_sha256=hashlib.sha256(a.corpus.read_bytes()).hexdigest(),split=a.split,
                  revision=a.baseline_revision or subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip())
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('split','aggregate','milliseconds')},ensure_ascii=False))


if __name__=='__main__':main()
