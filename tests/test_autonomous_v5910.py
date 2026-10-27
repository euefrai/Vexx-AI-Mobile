"""Development regressions: natural requirements, constrained queries and real table evidence."""
import copy
import pytest
import query_intelligence as qi
import evidence_graph as eg

@pytest.mark.parametrize('question,entity,facets',[
 ('Quem criou a linguagem Lua e quando?','linguagem Lua',{'founders','creation_date'}),
 ('Por que aconteceu a Revolta Aurora e o que mudou depois?','Revolta Aurora',{'causes','consequences'}),
 ('Como funciona Object.values e qual seu retorno?','Object.values',{'behavior','return_value'})])
def test_natural_required_facets(question,entity,facets):
 rs=qi.answer_requirements(question)
 assert facets<={r['attribute'] for r in rs}
 assert {r['entity'] for r in rs}=={entity}


def test_product_query_can_be_natural_without_losing_model_or_weight_condition():
 q='Qual o peso da Camera ZX700 com bateria e cartão e qual bateria utiliza?'
 rs=qi.answer_requirements(q)
 queries=qi.context_subqueries(q,[q],4)
 assert len(queries)==2
 assert all('Camera ZX700' in s for s in queries)
 assert any('com bateria e cartão' in s for s in queries)
 assert all(not s.startswith('Qual o') for s in queries)
 with qi.discovery_scope(qi.analyze(q)):
  assert not qi.constrain_provider_query(queries[0]).startswith('Qual o')


def test_non_model_numbers_negative_or_place_scope_are_not_removed():
 for q in ['Compare dois notebooks Lenovo com 16 GB de RAM, excluindo usados',
           'Qual o peso da Camera ZX700 em Salvador, excluindo acessórios?',
           'Qual o preço da Camera ZX700 até R$ 2500?']:
  for s in qi.context_subqueries(q,[q],4):
   assert q in s


def table_source():
 text='Luma Razão social Luma Ltda Tipo Empresa Fundação 12 de março de 1902 Fundador(es) Ana Ribeiro Produtos Motores elétricos'
 return {'titulo':'Luma (empresa)','texto':text,'texto_lido':True,'url':'https://example.org/luma',
         'tabelas':[[['Luma'],['Fundação','12 de março de 1902'],['Fundador(es)','Ana Ribeiro'],['Produtos','Motores elétricos']]]}


def test_literal_company_table_is_useful_partial_not_title_only_fact():
 rec=table_source();q='Quem fundou a Luma, em que ano e quais produtos fabrica?'
 cov=eg.requirement_coverage(q,[rec])
 assert {r['state'] for r in cov['requirements']}=={'PARTIALLY_SUPPORTED'}
 ps=eg.select_answer_passages(cov)
 assert len(ps)==3
 assert all(rec['texto'][p['text_span']['start']:p['text_span']['end']]==p['text'] for p in ps)
 stored={'texto_lido':True,'trecho':ps[0]['text'],'answer_passages':ps}
 assert {r['state'] for r in eg.requirement_coverage(q,[stored])['requirements']}=={'PARTIALLY_SUPPORTED'}


def test_wrong_table_entity_or_unread_metadata_cannot_supply_evidence():
 q='Quem fundou a Luma, em que ano e quais produtos fabrica?'
 for change in [{'texto_lido':False},{'tabelas':[[['Outra empresa'],['Fundação','1902'],['Fundador(es)','Ana Ribeiro']]]}]:
  assert not eg.requirement_coverage(q,[{**table_source(),**change}])['passages']


def test_table_value_must_exist_literally_in_returned_text():
 rec=table_source();rec['texto']='Luma table unavailable.'
 assert not eg.requirement_coverage('Quem fundou a Luma, em que ano e quais produtos fabrica?',[rec])['passages']

def test_creation_date_is_not_the_release_year_or_another_entity():
 q='Quem criou Python e quando?'
 for text in ['Python foi criado por Ana e lançado em 1991.','Python inspirou Ruby criado em 1995.']:
  cov=eg.requirement_coverage(q,[{'texto':text,'texto_lido':True}])
  assert next(r for r in cov['requirements'] if r['attribute']=='creation_date')['state']!='SUPPORTED'


def test_gap_search_does_not_repeat_already_supported_company_facets():
 import research_gaps
 q='Quem fundou a Luma, em que ano e quais produtos fabrica?'
 ev={'id':'ev-a','url':'https://example.org/luma','texto_lido':True,
     'trecho':'Luma foi fundada em 1902 por Ana Ribeiro.'}
 job={'id':'qa','objetivo':q,'plano':[],'usados':{'buscas':0},'orcamento':{'buscas':4}}
 gaps=research_gaps.identify(job,[ev])
 assert next(g for g in gaps if g['dimension']=='products')['query']
 assert all(not g['query'] for g in gaps if g['dimension'] in ('founders','foundation_date'))
