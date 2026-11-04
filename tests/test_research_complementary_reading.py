"""Document selection and context propagation; these tests use controlled HTML."""
import copy
import pytest
import evidence_graph as eg
import pc_agent
import query_intelligence as qi
import research
import research_agents as agents
import web_extract as web


QUERY='Investigue as diferenças entre list.append e list.extend no Python. Explique o retorno e comportamento.'
POLICY=('Some collection classes are mutable. The methods that add, subtract, or rearrange '
        'their members in place, and do not return a specific item, never return the '
        'collection instance itself but None.')
URL='https://reference.example/types'


def api_document():
    html=('<main><h1>Built-in types</h1><p>'+POLICY+'</p><p>'+'Introduction. '*800+'</p>'
          '<dl><span id="list.append"></span><dt>sequence.append(value)</dt>'
          '<dd><p>Append value to the end of the sequence.</p></dd></dl>'
          '<dl><span id="list.extend"></span><dt>sequence.extend(iterable)</dt>'
          '<dd><p>Extend sequence with the contents of iterable.</p></dd></dl>'
          '<dl><dt>sequence.reverse()</dt><dd><p>Returns None after reversing.</p></dd></dl></main>')
    return web.extrair_pagina(html,URL,QUERY,teto=1200,usar_trafilatura=False)


def test_shared_policy_stays_literal_context_without_certifying_a_return():
    doc=api_document()
    contexts=web.select_context_passages(doc,QUERY)
    assert len(doc['texto'])<=1200 and len(contexts)==1
    assert POLICY in contexts[0]['text'] and contexts[0]['context_only'] is True
    coverage=eg.requirement_coverage(QUERY,[{**doc,'lida':True,'url':URL}])
    assert all(r['state']!='SUPPORTED' for r in coverage['requirements'] if r['attribute']=='return_value')
    assert not web.select_context_passages(doc,'Como funciona list.append?')


@pytest.mark.parametrize('corruption',['text','hash','method_scope'])
def test_stale_or_other_operation_context_is_rejected(corruption):
    doc=api_document();policy=next(p for p in doc['answer_passages'] if POLICY in p['text'])
    if corruption=='text':policy['text']='A forged return rule.'
    elif corruption=='hash':policy['source_span']['sha256']='a'*64
    else:policy['section_path']=[{'level':7,'text':'unrelated.reverse()'}]
    assert not web.select_context_passages(doc,QUERY)


def test_policy_survives_common_read_and_deep_persistence_to_synthesis(tmp_path):
    doc=api_document();candidate={'url':URL,'titulo':'list.append and list.extend reference'}
    source=research._fonte_de({**doc,'lida':True,'final':URL},candidate,QUERY)
    assert any(p.get('context_only') for p in source['answer_passages'])
    db=pc_agent.open_db(tmp_path/'research.sqlite')
    try:
        job=agents.criar_job(db,'owner',QUERY)
        step={'id':'p2','alvo':QUERY,'tipo':'ler'}
        agents.agente_analista(db,job,step,[candidate],lambda url:{**doc,'final':url})
        evs=agents.listar_evidencias(db,'owner',job['id'])
        assert len(evs)==1 and any(p.get('context_only') for p in evs[0]['answer_passages'])
        _,sources=agents._synthesis_context(QUERY,evs,{evs[0]['id']:'E1'})
        assert POLICY in sources[0]['excerpt'] and len(sources[0]['excerpt'])<=1800
    finally:db.close()


def test_named_table_fields_outrank_incidental_history_prose():
    query='Quem fundou a Empresa Atlas e em que ano ela foi criada?'
    table=('<table><tr><th colspan="2">Empresa Atlas</th></tr>'
           '<tr><th>Fundação</th><td>19 de agosto de 1969</td></tr>'
           '<tr><th>Fundador(es)</th><td>Maria Silva</td></tr></table>')
    noise=''.join('<p>A Empresa Atlas tem uma história com fundadores e fundação em debate. '
                  +'Informações da trajetória. '*12+'</p>' for _ in range(30))
    doc=web.extrair_pagina('<main><h1>Empresa Atlas</h1>'+table+noise+'</main>',URL,query,teto=1500,usar_trafilatura=False)
    coverage=eg.requirement_coverage(query,[{**doc,'lida':True,'url':URL}])
    assert coverage['complete'] and len(doc['texto'])<=1500
    wrong=web.extrair_pagina('<main>'+table.replace('Empresa Atlas','Oficina Boreal')+noise+'</main>',URL,query,teto=1500,usar_trafilatura=False)
    assert not eg.requirement_coverage(query,[{**wrong,'lida':True,'url':URL}])['complete']


def test_common_answer_filter_keeps_verified_table_identity_with_generic_title():
    query='Quem fundou a Empresa Atlas e em que ano ela foi criada?'
    html=('<main><h1>Empresa Atlas</h1><table><tr><th colspan="2">Empresa Atlas</th></tr>'
          '<tr><th>Fundação</th><td>19 de agosto de 1969</td></tr>'
          '<tr><th>Fundador(es)</th><td>Maria Silva</td></tr></table><p>'+'History. '*1500+'</p></main>')
    doc=web.extrair_pagina(html,URL,query,usar_trafilatura=False)
    source=research._fonte_de({**doc,'lida':True,'final':URL,'titulo':'Aircraft manufacturer'},
                            {'url':URL,'titulo':'Aircraft manufacturer'},query)
    assert source['relevante'] and 'Empresa Atlas' not in source['texto_lido']
    assert research.fontes_relevantes(query,[source])==[source]
    for field,value in [('table_header','Oficina Boreal'),('table_header_span',{'sha256':'wrong'})]:
        wrong=copy.deepcopy(source)
        for passage in wrong['answer_passages']:passage[field]=value
        assert not research.fontes_relevantes(query,[wrong])
    wrong=copy.deepcopy(source);wrong['texto_lido']='Unrelated read text.'
    assert not research.fontes_relevantes(query,[wrong])


def test_official_preference_survives_planning_and_provider_selection(tmp_path,monkeypatch):
    query='Pesquisa profunda sobre a linguagem Rust: criador e finalidade, usando fontes oficiais.'
    context=qi.retrieval_context(query)
    assert context['source_preference']=='fontes oficiais'
    assert all('oficiais' in q for q in qi.context_subqueries(query,[],3))
    assert qi.constrain_discovery('Rust fundadores fontes oficiais',qi.analyze(query)).count('fontes oficiais')==1
    assert qi.retrieval_context('Quem fundou Atlas? Use fontes primárias.')['source_preference']=='fontes primárias'
    seen=[]
    def search(providers,q,*args,**kw):
        seen.append((providers,q))
        return [],{'provedor':'','erros':[]}
    monkeypatch.setattr(agents,'buscar_com_fallback',search)
    db=pc_agent.open_db(tmp_path/'providers.sqlite')
    try:
        job=agents.criar_job(db,'owner',query);specialized=agents.ProvedorOrquestrado()
        agents.agente_busca(db,job,{'id':'p1','alvo':'Rust fundadores'},[agents.ProvedorWikipedia(),specialized],set())
        assert seen and all(isinstance(providers[0],agents.ProvedorWikipedia) for providers,q in seen)
        seen.clear();job['usados']['consultas_etapas']={}
        agents.agente_busca(db,job,{'id':'p3','alvo':'Rust fontes oficiais','replan_reason':'source_authority'},
                            [agents.ProvedorWikipedia(),specialized],set())
        assert seen and all(providers[0] is specialized and 'oficiais' in q for providers,q in seen)
    finally:db.close()


def test_document_title_keeps_subject_when_metadata_is_only_a_description():
    query='Quem fundou Empresa Atlas?'
    html=('<title>Empresa Atlas – Enciclopédia</title><meta property="og:title" content="Aircraft manufacturer">'
          '<main><p>Empresa Atlas foi fundada por Maria Silva.</p></main>')
    assert web.extrair_pagina(html,URL,query,usar_trafilatura=False)['titulo']=='Empresa Atlas – Enciclopédia'


def test_exact_short_api_names_are_discovered_without_loosening_generic_terms(monkeypatch):
    import time,python_docs_discovery as docs
    monkeypatch.setattr(docs,'_CACHE',(time.monotonic()+60,[
        'list.pop py:method 1 library/stdtypes.html#$ -',
        'dict.pop py:method 1 library/stdtypes.html#$ -']))
    assert docs.search('Python list.pop retorno')[0]['meta']['api_names']==['list.pop']
    assert not docs.search('Python pop retorno')
    with qi.discovery_scope(qi.analyze('O que retorna list.pop no Python?')):
        assert docs.search('list pop valor retornado')[0]['meta']['api_names']==['list.pop']
        assert not docs.search('dict pop valor retornado')
    import search_orchestrator
    query=qi.constrain_discovery('list.pop valor retornado documentação oficial',qi.analyze('O que retorna list.pop no Python?'))
    assert search_orchestrator.classificar(query)['python_docs']


def test_passive_return_description_is_not_lost_or_assigned_to_another_method():
    query='O que retorna list.pop no Python?'
    text='Retrieve an item and remove it. The last item is removed and returned.'
    html=('<main><h1>Built-in types</h1><p>'+'Introduction. '*800+'</p>'
          '<dl><span id="list.pop"></span><dt>sequence.pop(index=-1)</dt><dd><p>'+text+'</p></dd></dl>'
          '<dl><dt>sequence.reverse()</dt><dd><p>The result is returned as None.</p></dd></dl></main>')
    doc=web.extrair_pagina(html,URL,query,teto=1200,usar_trafilatura=False)
    assert text in doc['texto'] and 'as None' not in doc['texto']
    coverage=eg.requirement_coverage(query,[{**doc,'lida':True,'url':URL}])
    assert coverage['requirements'][0]['state']=='PARTIALLY_SUPPORTED'
    assert not eg.requirement_coverage(query,[{'titulo':'list.pop','texto':text,'lida':True,'url':URL}])['passages']
