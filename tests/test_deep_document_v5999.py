"""Controlled long-document regressions; fixtures are not autonomous search."""
import hashlib
import pytest
import web_extract as we
import evidence_graph as eg
import query_intelligence as qi

URL='https://example.org/manual'
FILLER='<p>Unrelated maintenance and safety instructions for this document. '+('Ordinary text without requested attributes. '*35)+'</p>'

def extract(body,query):
    return we.extrair_pagina('<title>Technical reference</title><main>'+body+'</main>',URL,query,usar_trafilatura=False)


def assert_spans(rec):
    assert len(rec['texto'])<=8000
    assert len(rec['answer_passages'])<=8
    for p in rec['answer_passages']:
        s=p['text_span'];assert rec['texto'][s['start']:s['end']]==p['text']
        assert s['scope']=='returned_extracted_text'
        assert p['source_span']['scope']=='normalized_available_extraction'
        assert len(p['text'])<=1100


@pytest.mark.parametrize('position',[0,6,15])
def test_requested_fact_at_start_middle_or_end(position):
    blocks=[FILLER]*16
    blocks.insert(position,'<h2>Weight</h2><p>Camera ZX weight is 710 g with battery and memory card.</p>')
    rec=extract(''.join(blocks),'Qual o peso da Camera ZX com bateria e cartão?')
    assert '710 g with battery and memory card' in rec['texto']
    assert_spans(rec)
    rec['texto_lido']=True
    assert eg.requirement_coverage('Qual o peso da Camera ZX com bateria e cartão?',[rec])['requirements'][0]['state']=='SUPPORTED'


def test_multiple_late_sections_short_paragraph_and_code():
    query='Como usar Object.assign, qual a sintaxe, comportamento e valor retornado?'
    rec=extract(FILLER*12+'<h2>Syntax</h2><pre>Object.assign(target, source)</pre>'+FILLER*3+
        '<h2>Return value</h2><p>The target object.</p>'+FILLER*3+
        '<h2>Description</h2><p>Object.assign copies enumerable own properties from source objects.</p>',query)
    assert all(t in rec['texto'] for t in ['Object.assign(target, source)','The target object.','copies enumerable'])
    assert rec['document_scan']['late_passages']>=3
    assert_spans(rec)


def test_table_keeps_value_qualifier_and_scoped_partial_only():
    query='Qual o peso da Camera ZX com bateria e cartão e qual bateria utiliza?'
    rec=extract('<h2>Camera ZX</h2><table>'+''.join('<tr><td>Maintenance</td><td>'+('Unrelated text. '*100)+'</td></tr>' for _ in range(12))+
        '<tr><th>Battery</th><td>One AB-123 rechargeable battery.</td></tr>'+
        '<tr><th>Weight</th><td>Approx. 710 g with battery and memory card; 630 g body only.</td></tr></table>',query)
    assert '710 g with battery and memory card; 630 g body only' in rec['texto']
    assert 'AB-123' in rec['texto'];assert_spans(rec)
    rec['texto_lido']=True
    c=eg.requirement_coverage(query,[rec])
    assert {r['state'] for r in c['requirements']}=={'PARTIALLY_SUPPORTED'}
    for p in rec['answer_passages']:p['section']='Camera ZX II'
    # An explicit different variant cannot be inherited from a shorter name.
    assert not eg.requirement_coverage(query,[rec])['passages']


def test_wrong_entity_or_heading_without_value_cannot_support():
    query='Qual o peso da Camera ZX?'
    rec=extract(FILLER*12+'<h2>Camera ZX weight</h2><p>Camera QY weight is 710 g with battery and memory card.</p>',query)
    rec['texto_lido']=True
    assert not eg.requirement_coverage(query,[rec])['passages']


def test_source_offsets_are_real_normalized_extraction():
    body=FILLER*12+'<h2>Battery</h2><p>Camera ZX battery is AB-123.</p>'
    html='<title>Manual</title><main>'+body+'</main>'
    rec=we.extrair_pagina(html,URL,'Qual a bateria da Camera ZX?',usar_trafilatura=False)
    full=we.extrair_pagina(html,URL,'',teto=100000,usar_trafilatura=False)['texto']
    normalized=we._normalizar(full)
    for p in rec['answer_passages']:
        s=p['source_span'];assert normalized[s['start']:s['end']]==p['text']
        assert s['sha256']==hashlib.sha256(normalized.encode()).hexdigest()
    again=we.extrair_pagina(html,URL,'Qual a bateria da Camera ZX?',usar_trafilatura=False)
    assert rec['answer_passages']==again['answer_passages']


def test_does_not_join_noncontiguous_text_into_one_claim():
    rec=extract('<h2>Weight</h2><p>Camera ZX weight is unknown.</p>'+FILLER*12+
                '<h2>Weight</h2><p>Camera QY weight is 710 g.</p>','Qual o peso da Camera ZX?')
    assert_spans(rec)
    assert not any('unknown' in p['text'] and '710 g' in p['text'] for p in rec['answer_passages'])
    rec['texto_lido']=True
    assert not eg.requirement_coverage('Qual o peso da Camera ZX?',[rec])['complete']


@pytest.mark.parametrize('query',['Qual o peso da Camera ZX?','Qual é o peso da Camera ZX?','Qual a bateria da Camera ZX?'])
def test_interrogative_entity_does_not_become_qual_o(query):
    assert qi.answer_requirements(query)[0]['entity']=='Camera ZX'


def test_trace_only_bounded_counts():
    import retrieval_trace as rt
    with rt.observe() as rows:
        rt.record('job','step',{},'CONTENT_EXTRACTED',rec={'document_scan':{'available_chars':12000,'secret':'do not log','selected_passages':8,'late_passages':-1}})
    assert rows[0]['document_scan']=={'available_chars':12000,'selected_passages':8}
    assert 'do not log' not in str(rows)

def test_unwrapped_late_text_is_scanned_without_inventing_structure():
    rec=extract(FILLER*12+'<div>Camera ZX weight is 710 g with battery and memory card.</div>',
                'Qual o peso da Camera ZX com bateria e cartão?')
    assert '710 g' in rec['texto']
    assert_spans(rec)


def test_section_context_reaches_validated_source_card():
    import research_view,jdui
    item={'titulo':'Manual','url':URL,'texto_lido':True,'trecho':'Weight Approx. 710 g with battery and memory card.',
          'answer_passages':[{'section':'Dimensions/weight','text':'Weight Approx. 710 g.'}]}
    card=research_view.source_card(item)
    assert 'Contexto da seção: Dimensions/weight' in card['detalhes']
    ok,_,_=jdui.validar_mensagem({'version':jdui.VERSION,'blocks':[{'type':'ui','component':'sources','props':{'items':[card]}}]})
    assert ok

def test_table_scope_survives_persistence_without_full_document():
    query='Qual o peso da Camera ZX?'
    rec=extract('<h2>Camera ZX</h2><table>'+''.join('<tr><td>Maintenance</td><td>'+('Unrelated text. '*100)+'</td></tr>' for _ in range(12))+
                '<tr><th>Weight</th><td>Approx. 710 g with battery and memory card.</td></tr></table>',query)
    rec['texto_lido']=True
    first=eg.requirement_coverage(query,[rec]);selected=eg.select_answer_passages(first)
    stored={'texto_lido':True,'trecho':selected[0]['text'],'answer_passages':selected}
    assert eg.requirement_coverage(query,[stored])['requirements'][0]['state']=='PARTIALLY_SUPPORTED'

@pytest.mark.parametrize('query,answer,terms',[
 ('Quem fundou a Acme, em que ano e quais produtos fabrica?',
  '<h2>História</h2><p>Acme foi fundada em 1987 por Maria Silva. Acme fabrica motores e bombas industriais.</p>',
  ['1987','Maria Silva','motores']),
 ('Quais foram as causas e consequências da Revolta Aurora?',
  '<h2>Causas</h2><p>Revolta Aurora foi causada pela crise econômica e pelas mudanças tributárias.</p>'+
  '<h2>Consequências</h2><p>Revolta Aurora resultou em novas eleições e mudanças políticas.</p>',
  ['crise econômica','novas eleições'])])
def test_other_domains_recover_late_literal_sections(query,answer,terms):
 rec=extract(FILLER*16+answer,query)
 assert_spans(rec)
 assert all(term in rec['texto'] for term in terms)
 assert any(p['source_span']['start']>=8000 for p in rec['answer_passages'])


def test_unrelated_long_source_is_not_promoted_by_selection():
 rec=extract(FILLER*16,'Quem fundou a Acme, em que ano e quais produtos fabrica?')
 rec['texto_lido']=True
 assert not eg.requirement_coverage('Quem fundou a Acme, em que ano e quais produtos fabrica?',[rec])['passages']
