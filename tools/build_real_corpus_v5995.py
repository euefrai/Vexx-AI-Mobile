"""Short literal public extraction samples, not synthetic external quotations."""
import hashlib
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]


def main():
    target=ROOT/'benchmarks/real_evidence_v5995.json'
    if target.exists():raise SystemExit('Refusing to overwrite frozen corpus')
    # Snapshot, real source URL fragment, literal anchor, entity, attribute,
    # annotation and explanation. No decision comes from the matcher being tested.
    recipes=[
        ('qa-artifacts/v5993/accepted-holdout/aa-02.json','www.tramontina.com/','Tramontina is a vertically','Tramontina','foundation_date','DIRECT_SUPPORT','Founded year explicitly attached to the company.','companies','DEVELOPMENT'),
        ('qa-artifacts/v5993/accepted-holdout/aa-02.json','www.tramontina.com/','Tramontina is a vertically','Tramontina','founders','WRONG_ATTRIBUTE','Year/manufacturing text does not identify founders.','companies','DEVELOPMENT'),
        ('qa-artifacts/v5993/accepted-holdout/aa-08.json','en-US/docs/Web/JavaScript/Reference/Global_Objects/Array','Array.prototype.toSorted() Returns','Array.prototype.toSorted','behavior','DIRECT_SUPPORT','The named operation returns a new array without modifying the original.','documentation','DEVELOPMENT'),
        ('qa-artifacts/v5993/accepted-holdout/aa-08.json','en-US/docs/Web/JavaScript/Reference/Global_Objects/Array','Array.prototype.toSorted() Returns','Array.prototype.toSorted','limitations','WRONG_ATTRIBUTE','This definition does not document limits or exceptions.','documentation','DEVELOPMENT'),
        ('qa-artifacts/v5994/direction-baseline-sealed/dir-04.json','/resumos/guerra_cisplatina','Principais consequências','Guerra da Cisplatina','consequences','DIRECT_SUPPORT','Heading binds the following explained consequence to the war.','history','DEVELOPMENT'),
        ('qa-artifacts/v5994/direction-baseline-sealed/dir-06.json','/exercicios/revolta-beckman','Assinale a alternativa','Revolta de Beckman','causes','INSUFFICIENT_CONTEXT','Multiple options without the correct answer in this span cannot become facts.','education','DEVELOPMENT'),
        ('qa-artifacts/v5994/direction-after/dir-06.json','suapesquisa','Sobre os desdobramentos','Revolta de Beckman','consequences','INSUFFICIENT_CONTEXT','Question and options are not an identified correct answer.','education','DEVELOPMENT'),
        ('qa-artifacts/v5994/after-live/ei-04.json','brasilescola','campanha de vacinação obrigatória que levou','Revolta da Vacina','causes','DIRECT_SUPPORT','Campaign is an antecedent explicitly leading to the revolt.','history','DEVELOPMENT'),
        ('qa-artifacts/v5994/after-live/ei-04.json','brasilescola','campanha de vacinação obrigatória que levou','Revolta da Vacina','consequences','WRONG_RELATION','Antecedent of the revolt is not its consequence.','history','DEVELOPMENT'),
        ('qa-artifacts/v5994/historical/eva-04.json','ebiografia.com','Clarice Lispector nasceu','Clarice Lispector','birth_date','DIRECT_SUPPORT','Explicit birth date; exposes an attribute outside the old matcher vocabulary.','culture','VALIDATION'),
        ('qa-artifacts/v5994/historical/eva-04.json','ebiografia.com','Clarice Lispector nasceu','Clarice Lispector','products','WRONG_ATTRIBUTE','Biography birth date does not identify published works.','culture','VALIDATION'),
        ('qa-artifacts/v5994/historical/eva-06.json','cascaneia.com.br','Excursão em parque aquático','Parque Nacional de Brasília','opening_hours','WRONG_ENTITY','Water park travel advice does not describe the requested national park.','services','VALIDATION'),
        ('qa-artifacts/v5994/historical/eva-11.json','dicasdeviagem','Fortaleza é a capital','Fortaleza','event_date','TOPIC_ONLY','Travel description is not a dated cultural event.','events','VALIDATION'),
        ('qa-artifacts/v5994/historical/eva-01.json','g1.globo','Segundo o Tribunal','Manaus','news_date','INSUFFICIENT_CONTEXT','Article/feed fragment has no date establishing the requested seven-day interval.','news','VALIDATION'),
        ('qa-artifacts/v5994/historical/eva-01.json','en.wikipedia','Manaus','Manaus','location','PARTIAL_SUPPORT','Small opening extract establishes a place context, not all geography details.','places','VALIDATION'),
        ('qa-artifacts/v5994/after-live/ei-03.json','wikipedia','Ano','Fundação Oswaldo Cruz','foundation_date','WRONG_ENTITY','Calendar year article does not identify the foundation.','public_organizations','SEALED_HOLDOUT'),
        ('qa-artifacts/v5994/after-live/ei-06.json','tuasaude','peso','Canon EOS R8','weight','WRONG_ENTITY','Human body weight page does not measure the camera.','products','SEALED_HOLDOUT'),
        ('qa-artifacts/v5994/historical/eva-05.json','en.wikipedia','Embraer','Embraer','products','PARTIAL_SUPPORT','Opening company context may identify industry; not a complete product range.','technology','SEALED_HOLDOUT'),
    ]
    examples=[];skipped=[]
    for i,(file,fragment,anchor,entity,attribute,label,reason,domain,split) in enumerate(recipes):
        snapshot=ROOT/file
        data=json.loads(snapshot.read_text(encoding='utf-8'))
        entry=next((x for x in data.get('extractions',[]) if fragment in x.get('url','') and (x.get('result') or {}).get('texto')),None)
        if not entry:skipped.append({'recipe':i+1,'reason':'source_not_in_snapshot'});continue
        text=entry['result']['texto'];match=re.search(re.escape(anchor),text,re.I)
        if not match:skipped.append({'recipe':i+1,'reason':'anchor_not_in_read_text'});continue
        start=match.start();end=min(len(text),start+420)
        if end<len(text):end=text.rfind(' ',start,end)
        passage=text[start:end]
        # No large protected article/HTML duplication. Hashes reference the actual
        # returned extraction and the already recorded source capture.
        url=entry['url'];group=re.sub(r'/[a-z]{2}(?:-[A-Z]{2})?/docs/','/docs/',url).rstrip('/')
        examples.append(dict(id=f'real-{i+1:02}',split=split,question=f'{entity}: {attribute}',
            requirement=attribute,entity=entity,attribute=attribute,relation=attribute,domain=domain,
            passage=passage,necessary_context='',source=entry['result'].get('titulo') or url,url=url,
            source_type='PUBLIC_CAPTURED_PAGE',document_type='exercise' if domain=='education' else 'page',
            read_state='READ',label=label,justification=reason,review_status='MODEL_PROPOSED',
            review_note='Agent authored/reviewed; NOT independent human ground truth.',
            reference=dict(snapshot=file,url=url,returned_text_sha256=hashlib.sha256(text.encode()).hexdigest(),
                passage_sha256=hashlib.sha256(passage.encode()).hexdigest(),start=start,end=end),
            document_group=group,mandatory_conditions=[]))
    audit=json.loads((ROOT/'qa-artifacts/v5995/provider-audit.json').read_text(encoding='utf-8'))
    for i,provider in enumerate(['worldbank','openlibrary','commons']):
        row=next(r for r in audit['rows'] if r['provider']==provider)
        if not row.get('results'):continue
        item=row['results'][0]
        examples.append(dict(id=f'metadata-{i+1}',split='DEVELOPMENT',question=row['query'],requirement='page_reading',
            entity=row['query'],attribute='behavior',relation='page_reading',domain='economy' if provider=='worldbank' else 'culture',
            passage=item.get('snippet') or item['title'],necessary_context='',source=item['title'],url=item['url'],
            source_type='PUBLIC_PROVIDER_METADATA',document_type='metadata',read_state='UNREAD',label='UNREAD',
            justification='Actual discovery metadata; no document body read in this record.',review_status='MODEL_PROPOSED',
            review_note='Agent authored/reviewed; no independent human ground truth.',
            reference={'snapshot':'qa-artifacts/v5995/provider-audit.json','provider':provider,'rank':1},
            document_group=item['url'],mandatory_conditions=[]))
    # Protect exact-URL groups from accidental leakage.
    groups={}
    for r in examples:groups.setdefault(r['document_group'],set()).add(r['split'])
    if any(len(v)>1 for v in groups.values()):raise SystemExit('Document crosses splits')
    target.write_text(json.dumps(dict(scope='REAL_PUBLIC_TEXT_SHORT_SAMPLES_MODEL_ANNOTATED_NOT_HUMAN_GOLD',
        annotation_guideline='Per requirement; explicit support only; unkeyed alternatives never factual evidence.',
        examples=examples,collection_failures=skipped),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Public records',len(examples),'collection gaps',len(skipped))


if __name__=='__main__':main()
