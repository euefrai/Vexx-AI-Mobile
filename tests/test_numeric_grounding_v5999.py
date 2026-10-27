"""Controlled numeric contracts. Semantic review still owns entity/attribute support."""
import pytest
import research_synthesis as rs

@pytest.mark.parametrize('claim,quote',[
 ('1,5 kg','1.5 kg'),('1.25 %','1,25 %'),('R$ 1.234,56','R$ 1,234.56'),
 ('-2,5 °C','-2.5 °C'),('10 horas','10 horas'),('2026-10-27','2026-10-27'),
 ('1,5–2,5 V','1.5–2.5 V'),('V5.9.9.9','V5.9.9.9')])
def test_unambiguous_numeric_format_preserves_units(claim,quote):
 assert rs.numeric_values(claim)<=rs.numeric_values(quote)
 assert rs.quantities(claim)<=rs.quantities(quote)

@pytest.mark.parametrize('claim,quote',[
 ('710 kg','710 g'),('710 g','710 kg'),('USD 10','BRL 10'),('USD 10','10'),
 ('-5 °C','5 °C'),('1,234 g','1234 g'),('1,234 g','1.234 g'),
 ('2026-10-27','2026-10-26'),('1.5 %','1.5 kg'),('R$ 10','US$ 10')])
def test_wrong_or_ambiguous_quantity_is_not_normalized_into_support(claim,quote):
 assert not (rs.numeric_values(claim)<=rs.numeric_values(quote) and rs.quantities(claim)<=rs.quantities(quote))


def test_technical_model_suffix_is_not_just_a_number():
 assert rs.technical_identifiers('EN-EL15c')==rs.technical_identifiers('EN‑EL15c')
 assert not rs.technical_identifiers('EN-EL15b')<=rs.technical_identifiers('EN‑EL15c')


def test_attribute_swap_is_not_claimed_as_locally_verified():
 # Equal numeric sets are insufficient: this intentionally still needs review.
 assert rs.quantities('Camera weight 710 g; package 900 g.')==rs.quantities('Camera weight 900 g; package 710 g.')

@pytest.mark.parametrize('text,quote,accepted',[
 ('A amostra tem massa de 1,5 kg no ensaio.','A amostra tem massa de 1.5 kg no ensaio.',True),
 ('A amostra tem massa de 100 kg no ensaio.','A amostra tem massa de 100,00 kg no ensaio.',True),
 ('A amostra tem massa de 710 kg no ensaio.','A amostra tem massa de 710 g no ensaio.',False),
 ('A bateria utilizada é EN-EL15b neste modelo.','A bateria utilizada é EN-EL15c neste modelo.',False)])
def test_numeric_gate_still_runs_before_independent_review(text,quote,accepted):
 import json
 source={'id':'E1','evidence_id':'ev-1','url':'https://example.org/manual','excerpt':quote}
 output=json.dumps({'points':[{'text':text,'evidence':[{'id':'E1','quote':quote}]}]})
 calls=[]
 def review(messages,timeout):
  calls.append(True)
  return json.dumps({'reviews':[{'paragraph':0,'state':'SUPPORTED','reason':'none'}]})
 if accepted:
  result=rs.generate('Qual a especificação?', [source], [], lambda *a:output,verify_fn=review)
  assert result['llm'] is True and calls
 else:
  with pytest.raises(ValueError):rs.generate('Qual a especificação?',[source],[],lambda *a:output,verify_fn=review)
  assert not calls
