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


def test_short_fields_remain_citable_without_lowering_quote_minimum():
    import research_synthesis as rs
    rec=article();passages=eg.select_answer_passages(eg.requirement_coverage(QUERY,[rec]))
    quotes=[q for p in passages for q in rs.quote_options({'excerpt':p['text']})]
    assert any('Founded 1981' in q['text'] for q in quotes)
    assert all(len(q['text'])>=24 and q['text'] in rec['texto'] for q in quotes)


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
        job['sintese']=result
        job['achados']=[{'afirmacao':QUERY,'estado':'UNVERIFIED'}]
        assert ra._completion_outcome(job,[ev],[],assisted=True)['state']=='complete'
        job['achados'][0]['estado']='CONTRADICTED'
        assert ra._completion_outcome(job,[ev],[],assisted=True)['state']=='partial'
        job['achados'][0]['estado']='UNVERIFIED'
        result.pop('semantic_review')
        assert ra._completion_outcome(job,[ev],[],assisted=True)['state']=='partial'
    finally:db.close()


def test_wikipedia_prefix_search_uses_entity_not_answer_facets(monkeypatch):
    import research
    from urllib.parse import parse_qs,urlsplit
    calls=[]
    def get(url,**kwargs):
        calls.append(parse_qs(urlsplit(url).query)['search'][0]);return ['',[],[],[]]
    monkeypatch.setattr(research,'_baixar_json',get)
    query='Quais são a nascente e a foz do rio Azul?'
    with qi.discovery_scope(qi.analyze(query),job_id='qa',step_id='qa'):
        research.buscar_wikipedia('rio Azul nascente')
    assert calls==['rio Azul']


def test_doi_suffix_is_not_a_product_model():
    row={'titulo':'Experimental methods for solid-state cells','url':'https://example.org/paper',
         'doi':'10.1234/result-1','trecho':'Methods and experimental conditions.'}
    assert not orch._context_mismatch(row,'papers "10.1234/result-1" methods sample experimental')


def test_single_extra_closing_delimiter_does_not_discard_valid_cited_data():
    import research_synthesis as rs
    text='Atlas fabrica motores elétricos e geradores.'
    src={'id':'E1','evidence_id':'ev-atlas','url':'https://example.org/atlas','excerpt':text}
    raw=json.dumps({'points':[{'text':text,'evidence':[{'id':'E1','quote':text}]}]})+']'
    review=lambda *args:json.dumps({'reviews':[{'paragraph':0,'state':'SUPPORTED','reason':'none'}]})
    result=rs.generate('Quais produtos a Atlas fabrica?',[src],[],lambda *args:raw,verify_fn=review)
    assert result['llm'] and result['format_normalization']==['single_trailing_delimiter']


@pytest.mark.parametrize('suffix',[' prose',' {}',' ] ]','; run()'])
def test_json_repair_never_accepts_extra_payload_or_instructions(suffix):
    import research_synthesis as rs
    text='Atlas fabrica motores elétricos e geradores.'
    src={'id':'E1','evidence_id':'ev-atlas','url':'https://example.org/atlas','excerpt':text}
    raw=json.dumps({'points':[{'text':text,'evidence':[{'id':'E1','quote':text}]}]})+suffix
    with pytest.raises(ValueError):rs.generate('Quais produtos a Atlas fabrica?',[src],[],lambda *args:raw)
