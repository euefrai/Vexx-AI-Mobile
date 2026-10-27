import json
import pytest
import research_synthesis as rs

SOURCE={'id':'E1','evidence_id':'ev-test','title':'Luma','url':'https://example.org/luma',
        'excerpt':'Luma foi fundada por Ana Ribeiro. Luma fabrica motores elétricos.'}


def writer(ref='Q1',text='A fundadora da Luma é Ana Ribeiro.'):
 def generate(messages,timeout):
  payload=json.loads(messages[-1]['content'])
  assert 'quotes' in payload['sources'][0] and 'excerpt' not in payload['sources'][0]
  assert all(q['text'] in SOURCE['excerpt'] for q in payload['sources'][0]['quotes'])
  return json.dumps({'points':[{'text':text,'evidence':[{'id':'E1','quote_id':ref}]}]})
 generate.literal_quote_ids=True
 return generate


def review(*args):return json.dumps({'reviews':[{'paragraph':0,'state':'SUPPORTED','reason':'none'}]})


def test_literal_catalog_resolves_only_real_source_text_before_strict_validation():
 result=rs.generate('Quem fundou Luma?',[SOURCE],[],writer(),verify_fn=review)
 assert result['llm'] and result['provenance'][0]['quote']=='Luma foi fundada por Ana Ribeiro.'


def test_unknown_quote_id_is_rejected_not_retried():
 with pytest.raises(ValueError):rs.generate('Quem fundou Luma?',[SOURCE],[],writer('Q999'),verify_fn=review)


def test_catalog_does_not_weaken_numeric_or_unit_validation():
 with pytest.raises(ValueError):rs.generate('Quem fundou Luma?',[SOURCE],[],writer(text='Luma foi fundada em 1991 por Ana Ribeiro.'),verify_fn=review)


def test_catalog_cannot_quote_across_noncontiguous_passages():
 text='Primeira passagem literal com 450 g. Segunda passagem distinta com bateria B12.'
 source={**SOURCE,'excerpt':text,'passage_ranges':[{'start':0,'end':35},{'start':36,'end':len(text)}]}
 options=rs.quote_options(source)
 assert options and all(any(o['text'] in text[r['start']:r['end']] for r in source['passage_ranges']) for o in options)
