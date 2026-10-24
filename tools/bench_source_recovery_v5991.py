"""Bounded opt-in live probes, reusing the V599 benchmark and retrieval engine."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live',action='store_true',required=True)
    parser.add_argument('--split',choices=('evaluation','holdout'),default='evaluation')
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--case')
    args=parser.parse_args()
    dataset=ROOT/'benchmarks'/('source_recovery_v5991_holdout.json' if args.split=='holdout' else 'universal_search_v599.json')
    data=json.loads(dataset.read_text(encoding='utf-8'))
    cases=data['queries' if args.split=='holdout' else 'evaluation']
    if args.case:
        from tools.bench_universal_v599 import probe
        row=probe(next(case for case in cases if case['id']==args.case))
        row['source_revision']=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
        row['dataset_sha256']=hashlib.sha256(dataset.read_bytes()).hexdigest()
        print(json.dumps(row,ensure_ascii=False));return
    args.output.mkdir(parents=True,exist_ok=True)
    summary=[]
    for case in cases:
        try:
            command=[sys.executable,__file__,'--live','--split',args.split,'--output',str(args.output),'--case',case['id']]
            child=subprocess.run(command,capture_output=True,timeout=65,encoding='utf-8',cwd=ROOT,
                env={**os.environ,'PYTHONIOENCODING':'utf-8'})
            row=json.loads(child.stdout) if child.returncode==0 else {'id':case['id'],'error':'process_failed','detail':child.stderr[-1200:]}
        except subprocess.TimeoutExpired:row={'id':case['id'],'error':'process_ceiling_65s'}
        (args.output/(case['id']+'.json')).write_text(json.dumps(row,ensure_ascii=False,indent=2),encoding='utf-8')
        brief={key:row.get(key) for key in ('id','state','eligible_read','seconds','error')}
        summary.append(brief);print(json.dumps(brief),flush=True)
        (args.output/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')


if __name__=='__main__':main()
