import pytest
import json
import pc_agent
import evidence_graph as eg
import query_intelligence as qi
import research_agents as ra
import search_orchestrator as orch
import web_extract as we


QUERY='Quem fundou a Atlas, em que ano foi fundada e quais produtos fabrica?'


def source(text):
    return {'id':'ev-atlas','texto':text,'texto_lido':True,'url':'https://example.org/atlas'}


def test_generated_facet_queries_do_not_turn_labels_into_proper_names():
    for r in qi.answer_requirements(QUERY):
        query=qi.requirement_query(r,QUERY)
        assert not orch._context_mismatch({'titulo':'Atlas','url':'https://example.org/atlas','trecho':'Atlas fabrica motores e foi fundada em 1981.'},query)


@pytest.mark.parametrize('query',[
    'Quais foram as causas da Revolta do Sal e quais foram suas consequências?',
    'Quais foram as causas e as consequências da Revolta do Sal?'])
def test_history_keeps_event_as_subject(query):
    assert {r['entity'] for r in qi.answer_requirements(query)}=={'Revolta do Sal'}


def test_short_unambiguous_pronoun_chain_keeps_manufacturer_relation():
    text='Atlas was founded in 1981 by Rita Silva. The company has operations in ten countries. It is one of the largest manufacturers of electric motors in the world.'
    cov=eg.requirement_coverage(QUERY,[source(text)])
    assert cov['complete']
    assert all(p['text'] in text for p in cov['passages'])


@pytest.mark.parametrize('middle',[
    'Orion has operations in ten countries.',
    'The company says Orion is its partner.',
    'The company does not manufacture electric motors.'])
def test_pronoun_cannot_cross_changed_subject_or_negated_relation(middle):
    text='Atlas was founded in 1981 by Rita Silva. '+middle+' It is one of the largest manufacturers of electric motors in the world.'
    cov=eg.requirement_coverage(QUERY,[source(text)])
    assert next(r for r in cov['requirements'] if r['attribute']=='products')['state']!='SUPPORTED'


def test_acquisition_does_not_resolve_ambiguous_pronoun():
    rec=source('Atlas acquired Orion. It is a manufacturer of electric motors.')
    cov=eg.requirement_coverage(QUERY,[rec])
    assert next(r for r in cov['requirements'] if r['attribute']=='products')['state']!='SUPPORTED'


def article(table_name='Atlas Corporation'):
    html='<html><head><title>Atlas</title></head><body><main><h1>Atlas</h1><table><tr><th>'+table_name+'</th></tr><tr><th>Founded</th><td>1981</td></tr><tr><th>Founder</th><td>Rita Silva</td></tr><tr><th>Products</th><td>Electric motors and generators</td></tr></table>'
    html+='<p>'+('Unrelated background without answer facts. '*400)+'</p></main></body></html>'
    return {**we.extrair_pagina(html,'https://example.org/atlas',consulta=QUERY),'texto_lido':True,'url':'https://example.org/atlas'}


def test_same_dom_named_table_keeps_attribution_and_all_facets():
    rec=article();cov=eg.requirement_coverage(QUERY,[rec])
    assert cov['complete']
    assert len(rec['texto'])<=8000
    assert all(p['text']==rec['texto'][p['text_span']['start']:p['text_span']['end']] for p in cov['passages'])
    assert all(p.get('table_header')=='Atlas Corporation' for p in cov['passages'])


def test_other_table_cannot_inherit_page_heading():
    cov=eg.requirement_coverage(QUERY,[article('Orion Corporation')])
    assert not any(r['state']=='SUPPORTED' for r in cov['requirements'])


def test_provider_fallback_does_not_stop_at_hard_entity_mismatch():
    class Provider:
        def __init__(self,name,title):self.nome=name;self.title=title
        def buscar(self,*args):return [{'titulo':self.title,'url':'https://example.org/'+self.nome,'trecho':self.title}]
    rows,info=ra.buscar_com_fallback([Provider('wrong','Orion was founded in 1970'),Provider('right','Atlas Motors was founded in 1981')],
                                   'Quem fundou a Atlas Motors?')
    assert info['provedor']=='right'
    assert len(rows)==1


def test_structural_attribution_reaches_bounded_writer(tmp_path):
    rec=article();passages=eg.select_answer_passages(eg.requirement_coverage(QUERY,[rec]))
    db=pc_agent.open_db(tmp_path/'qa.sqlite')
    try:
        job=ra.criar_job(db,'qa',QUERY,conv='qa')
        ev={'id':'ev-atlas','titulo':'Atlas','dominio':'example.org','url':rec['url'],'texto_lido':True,
            'trecho':rec['texto'],'answer_passages':passages,'score':1}
        captured=[]
        def writer(messages,timeout):
            payload=json.loads(messages[-1]['content']);captured.append(payload)
            return '{}'
        writer.literal_quote_ids=True
        ra.agente_sintetizador(db,job,[ev],[],sintetizar_fn=writer)
        assert len(captured)==1
        assert all(r['state']=='SUPPORTED' for r in captured[0]['requirements'])
        assert any(q.get('table_header')=='Atlas Corporation' for q in captured[0]['sources'][0]['quotes'])
    finally:db.close()


def test_answer_coverage_uses_accepted_plain_paragraphs_not_rendered_links(tmp_path):
    db=pc_agent.open_db(tmp_path/'qa.sqlite')
    first='Atlas foi fundada em 1981 por Rita Silva.'
    second='A empresa fabrica motores elétricos e geradores.'
    try:
        job=ra.criar_job(db,'qa',QUERY,conv='qa')
        ev={'id':'ev-atlas','titulo':'Atlas','dominio':'example.org','url':'https://example.org/atlas',
            'trecho':first+' '+second,'texto_lido':True,'score':1}
        def writer(messages,timeout):
            return json.dumps({'points':[{'text':text,'evidence':[{'id':'E1','quote':text}]} for text in [first,second]]})
        def reviewer(messages,timeout):
            return json.dumps({'reviews':[{'paragraph':i,'state':'SUPPORTED','reason':'none'} for i in range(2)]})
        result=ra.agente_sintetizador(db,job,[ev],[],sintetizar_fn=writer,verificar_fn=reviewer)
        assert result['llm'] and result['answer_coverage']['complete']
    finally:db.close()
