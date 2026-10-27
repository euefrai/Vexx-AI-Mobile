"""Inspect already-open public V5910 captures without network/model calls."""
import hashlib,json,pathlib,sys
R=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(R))
import query_intelligence as qi,evidence_graph as eg
P=R/'qa-artifacts/v5911';P.mkdir(parents=True,exist_ok=True)
out=[]
for cid,terms in [('ar-07',['nasce','nascente','foz','desagua']),('ar-08',['bacharelado','licenciatura','tecnólogo']),('ar-09',['2026','2025','2024','próximo'])]:
    data=json.loads((R/f'qa-artifacts/v5910/holdout-{cid}.json').read_text(encoding='utf-8'))
    records={}
    folder=R/'qa-artifacts/v5910/raw'/hashlib.sha256(('B|'+cid).encode()).hexdigest()[:20]
    for path in folder.glob('*.json'):
        rec=json.loads(path.read_text(encoding='utf-8'))
        if isinstance(rec,dict) and isinstance(rec.get('record'),dict):records[rec['url']]=rec['record']
    sources=[]
    for source in data['evidence']:
        if not source['read'] or source['url'] not in records:continue
        rec=records[source['url']];text=rec.get('texto','');snippets=[]
        for term in terms:
            pos=qi.normalized(text).find(qi.normalized(term))
            if pos>=0:snippets.append(text[max(0,pos-80):pos+300])
        sources.append({'url':source['url'],'text_chars':len(text),'snippets':snippets[:3]})
    out.append({'case':cid,'question':data['case']['query'],'requirements':qi.answer_requirements(data['case']['query']),
        'first_loss':'REQUIREMENT_NOT_RECOGNIZED','retained_read':sources,'old_linked_passages':len(data['coverage']['passages'])})
(P/'previous-loss-summary.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(out,ensure_ascii=False,indent=2))
