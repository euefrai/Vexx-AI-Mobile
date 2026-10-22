"""Frozen document metrics plus an independent candidate-ranking holdout, no network."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from datetime import datetime, timezone
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import research_quality_lab as lab
import search_orchestrator as orch
import query_intelligence


def evaluate(output):
    path = ROOT / 'benchmarks/precision_holdout_v593.json'
    cases = json.loads(path.read_text(encoding='utf-8'))
    result = {'kind': 'DETERMINISTIC', 'holdout_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
              'scope': 'Document-level synthetic local retrieval and frozen candidate reranking; not universal web accuracy.',
              'documents': {}, 'holdout': []}
    for k in (5, 10):
        with tempfile.TemporaryDirectory(prefix='vexx-precision-') as tmp:
            r = lab.run_document_retrieval_benchmark(ROOT/'benchmarks/research_quality_v2.json', tmp, k=k)
        result['documents'][str(k)] = r
    original=query_intelligence.analyze
    frozen=datetime(2026,10,22,12,tzinfo=timezone.utc)
    result['holdout_clock_utc']=frozen.isoformat()
    with patch.object(query_intelligence,'analyze',lambda text,now=None,timezone_name='America/Bahia':original(text,now=now or frozen,timezone_name=timezone_name)):
        for case in cases:
            info = orch.classificar(case['query'])
            candidates = deepcopy(case['candidates'])
            ranked = orch.ranquear(candidates, case['query'], info['classes'], info)
            ids = [r['id'] for r in ranked]
            eligible = [r for r in ranked if orch._util_para_pedido(r, orch._termos_correspondencia(case['query']), case['query'])]
            result['holdout'].append({'id': case['id'], 'query': case['query'],
                'ranked': ids, 'eligible': [r['id'] for r in eligible],
                'at5': lab.retrieval_metrics(ids, case['relevance'], 5),
                'at10': lab.retrieval_metrics(ids, case['relevance'], 10),
                'eligible_precision': len({r['id'] for r in eligible}&set(case['relevance']))/max(1,len(eligible)),
                'eligible_recall': len({r['id'] for r in eligible}&set(case['relevance']))/len(case['relevance'])})
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:r['retrieval_metrics'] for k,r in result['documents'].items()}))


if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    evaluate(p.parse_args().output)
