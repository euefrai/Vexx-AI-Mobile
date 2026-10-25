"""Exploratory support metrics on public samples; not independently human gold."""
import argparse
import importlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools import evaluate_evidence_v5994 as engine


def main():
    p=argparse.ArgumentParser();p.add_argument('--split',choices=['DEVELOPMENT','VALIDATION','SEALED_HOLDOUT'],required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--revision')
    a=p.parse_args()
    if a.split=='SEALED_HOLDOUT' and not (ROOT/'qa-artifacts/v5995/code-freeze.json').exists():
        raise SystemExit('Freeze code before opening held-out examples')
    if a.output.exists():raise SystemExit('Do not overwrite an evaluation')
    data=json.loads((ROOT/'benchmarks/real_evidence_v5995.json').read_text(encoding='utf-8'))
    rows=[{**r,'source':r['url']} for r in data['examples'] if r['split']==a.split]
    def run():
        result=engine.evaluate(rows)
        result.update(scope='REAL_PUBLIC_SHORT_SAMPLES_MODEL_ANNOTATED_EXPLORATORY_NOT_HUMAN_GOLD',
          split=a.split,annotation_states=sorted({r['review_status'] for r in rows}),
          limitations=['Same agent annotation/review; no independent human gold.',
                       'Requirement supplied explicitly: parsing/discovery are separate.',
                       'Binary retention metrics do not certify all rejection labels or population accuracy.'])
        return result
    if a.revision:
        with tempfile.TemporaryDirectory(prefix='v5995-baseline-') as folder:
            for name in ('evidence_graph.py','query_intelligence.py','web_extract.py'):
                (Path(folder)/name).write_bytes(subprocess.check_output(['git','show',a.revision+':'+name],cwd=ROOT))
            sys.path.insert(0,folder)
            for name in ('evidence_graph','query_intelligence','web_extract'):sys.modules.pop(name,None)
            engine.eg=importlib.import_module('evidence_graph');result=run()
    else:result=run()
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(split=a.split,metrics=result['aggregate']),ensure_ascii=False))


if __name__=='__main__':main()
