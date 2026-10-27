import copy
import pytest
import query_intelligence as qi
import evidence_graph as eg
import search_orchestrator as orch


def source(text,**extra):
 return {'texto':text,'texto_lido':True,'url':'https://example.org/source','document_id':'D-test',**extra}


def test_undecomposed_objective_is_never_resolved_by_topic_text():
 q='Qual é o festival mais procurado da região?'
 cov=eg.requirement_coverage(q,[source('O festival reúne visitantes de diferentes regiões.')])
 assert cov['requirements'] and any(r['type']=='original_objective' for r in cov['requirements'])
 assert not cov['complete'] and not cov['passages']
 assert cov['fully_decomposed'] is False


def test_ignored_question_part_prevents_false_complete():
 q='Quem fundou a Luma e qual é seu código de registro?'
 cov=eg.requirement_coverage(q,[source('Luma foi fundada por Ana Ribeiro.')])
 assert any(r['attribute']=='founders' and r['state']=='SUPPORTED' for r in cov['requirements'])
 assert any(r['type']=='original_objective' and r['state']!='SUPPORTED' for r in cov['requirements'])
 assert not cov['complete']


@pytest.mark.parametrize('q',[
 'Compare Camera ZX7 e Camera ZX9 quanto ao peso e bateria.',
 'Entre Camera ZX7 e Camera ZX9, qual é mais leve e qual bateria utiliza?'])
def test_comparison_has_per_entity_facets_without_instruction_pollution(q):
 rs=qi.answer_requirements(q)
 assert {(r['entity'],r['attribute']) for r in rs}=={(e,a) for e in ['Camera ZX7','Camera ZX9'] for a in ['weight','battery']}
 assert len({r['id'] for r in rs})==4


def test_history_entity_excludes_source_comparison_instruction():
 rs=qi.answer_requirements('Pesquise as causas e consequências da Revolta do Porto e compare as fontes históricas.')
 assert {r['entity'] for r in rs}=={'Revolta do Porto'}


def test_geography_explicit_relation_and_multi_requirement_binding():
 q='Quais são a nascente e a foz do rio Azul e por quais regiões passa?'
 rec=source('O rio Azul nasce na Serra Clara e deságua na Baía Norte. O rio Azul atravessa o Vale Verde.')
 cov=eg.requirement_coverage(q,[rec]);ps=eg.select_answer_passages(cov)
 assert {r['attribute'] for r in cov['requirements']}=={'river_source','river_mouth','course'}
 assert cov['complete'] and any(len(p['requirement_ids'])>1 for p in ps)
 assert all(p.get('document_id')=='D-test' for p in ps)
 assert all(rec['texto'][p['text_span']['start']:p['text_span']['end']]==p['text'] for p in ps)
 stored={**rec,'answer_passages':copy.deepcopy(ps)}
 assert eg.requirement_coverage(q,[stored])['complete']
 assert all(p.get('document_id')=='D-test' for p in eg.compact_coverage(cov)['passages'])


def test_wrong_entity_relation_or_direction_is_not_support():
 q='Qual é a nascente e a foz do rio Azul?'
 for text in ['O rio Azul tem estudos da nascente e da foz.','O rio Azul recebe o rio Branco, que nasce na Serra Clara.','O rio Branco nasce na Serra Clara e deságua no rio Azul.']:
  assert not eg.requirement_coverage(q,[source(text)])['passages']


def test_literal_river_table_keeps_only_partial_support():
 q='Qual é a nascente e a foz do rio Azul?'
 text='Rio Azul Nascente Serra Clara Foz Baía Norte'
 rec=source(text,tabelas=[[['Rio Azul'],['Nascente','Serra Clara'],['Foz','Baía Norte']]])
 cov=eg.requirement_coverage(q,[rec])
 assert {r['state'] for r in cov['requirements']}=={'PARTIALLY_SUPPORTED'}
 assert not cov['complete']


def test_persisted_passage_labels_do_not_transfer_to_wrong_requirement():
 rec=source('Luma foi fundada por Ana Ribeiro.')
 ps=eg.select_answer_passages(eg.requirement_coverage('Quem fundou a Luma?',[rec]))
 fake={**rec,'answer_passages':[{**p,'requirement_ids':['forged'],'requirement_support':{'forged':'DIRECT_SUPPORT'}} for p in ps]}
 assert not eg.requirement_coverage('Quem fundou a Beta?',[fake])['passages']


def test_model_spacing_alias_does_not_merge_variant_suffixes():
 q='Qual o peso da Camera ZX 7 com bateria e cartão?'
 assert 'ENTITY_MISMATCH' not in orch._context_mismatch({'titulo':'Camera ZX7 peso e especificações','url':'https://example.org/zx7'},q)
 assert 'ENTITY_MISMATCH' in orch._context_mismatch({'titulo':'Camera ZX7 II peso e especificações','url':'https://example.org/zx7-ii'},q)


def test_definition_linking_requires_entity_as_subject_not_topic_overlap():
 q='Quais as diferenças entre bacharelado, licenciatura e tecnólogo?'
 cov=eg.requirement_coverage(q,[source('Bacharelado é um curso de formação ampla. Licenciatura é uma graduação destinada à docência. Tecnólogo é uma graduação de formação tecnológica.')])
 assert len(cov['requirements'])==3 and cov['complete']
 assert not eg.requirement_coverage(q,[source('Bacharelado, licenciatura e tecnólogo são assuntos deste artigo.')])['passages']


def test_stale_cached_passage_cannot_override_changed_full_document():
 rec=source('Luma foi fundada por Ana Ribeiro.')
 ps=eg.select_answer_passages(eg.requirement_coverage('Quem fundou a Luma?',[rec]))
 changed={**rec,'texto':'Luma apresenta notícias gerais sem indicar fundadores.','answer_passages':ps}
 assert not eg.requirement_coverage('Quem fundou a Luma?',[changed])['passages']


def test_official_source_constraint_is_not_resolved_by_private_definition():
 cov=eg.requirement_coverage('Quais diferenças entre bacharelado e licenciatura segundo fontes oficiais?',[source('Bacharelado é um curso de formação ampla. Licenciatura é uma graduação para a docência.')])
 assert any(r['type']=='mandatory_constraint' and r['state']!='SUPPORTED' for r in cov['requirements'])
 assert not cov['complete']


def test_structured_type_is_not_a_source_title():
 import web_extract
 html='<title>Luma história</title><script type="application/ld+json">{"@type":"Organization","name":"company"}</script><p>Luma é uma empresa.</p>'
 assert web_extract.extrair_metadados(html)['titulo']=='Luma história'
