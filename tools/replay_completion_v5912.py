"""Re-extract identical captured development HTML; no network/model calls."""
import argparse,hashlib,json,os,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
os.environ['JULIA_ENV_FILE']=str(Path(tempfile.gettempdir())/'v5912-none.env')
import query_intelligence as qi,web_extract as we,evidence_graph as eg


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--baseline',action='store_true');args=parser.parse_args()
    if args.baseline:
        for mod in (qi,we,eg):
            code=subprocess.check_output(['git','show','40f9531:'+mod.__name__+'.py'],cwd=ROOT).decode('utf-8')
            exec(compile(code,'<baseline:'+mod.__name__+'>','exec'),mod.__dict__)
    p=ROOT/'qa-artifacts/v5912';rows=[]
    for path in sorted(p.glob('before-dev-*.json')):
        before=json.loads(path.read_text(encoding='utf-8'));case=before['case'];docs=[];hashes=[];literal=True
        folder=p/'raw'/hashlib.sha256(('B|'+case['id']).encode()).hexdigest()[:20]
        for capture in sorted(folder.glob('*.json')):
            item=json.loads(capture.read_text(encoding='utf-8'))
            if not isinstance(item,dict) or not isinstance(item.get('record'),dict) or not isinstance(item.get('body'),str):continue
            hashes.append(hashlib.sha256(capture.read_bytes()).hexdigest())
            rec=we.extrair_pagina(item['body'],item['url'],consulta=case['query'])
            rec.update(url=item['url'],texto_lido=bool(rec.get('texto')) and not rec.get('ilegivel'))
            docs.append(rec)
        coverage=eg.requirement_coverage(case['query'],docs)
        for passage in coverage['passages']:
            doc=next(d for d in docs if d['url']==passage['source_id'])
            start,end=passage['text_span']['start'],passage['text_span']['end']
            literal=literal and doc['texto'][start:end]==passage['text']
        rows.append({'case':case,'snapshot_sha256':hashlib.sha256(''.join(hashes).encode()).hexdigest(),
                     'documents':len(docs),'coverage':eg.compact_coverage(coverage),
                     'all_spans_literal':literal,'output_chars_max':max((len(d['texto']) for d in docs),default=0)})
    out=p/('reading-before-summary.json' if args.baseline else 'reading-after-summary.json')
    out.write_text(json.dumps({'scope':'CONTROLLED_SAME_HTML_REEXTRACTION_NO_DISCOVERY_NO_MODEL_NOT_HUMAN_GOLD',
                   'baseline':args.baseline,'baseline_ref':'40f9531','cases':rows},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print([(r['case']['id'],r['coverage']['complete'],len(r['coverage']['passages']),r['all_spans_literal']) for r in rows])


if __name__=='__main__':main()
