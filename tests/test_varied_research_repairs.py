import pytest
import query_intelligence as qi
import pc_agent
import search_orchestrator as orch


@pytest.mark.parametrize('query', ['Faça uma pesquisa profunda: quem criou a linguagem Rust?',
    'Investigue a fundo as diferenças entre list.append e list.extend no Python.',
    'Pesquisa profunda sobre o teorema de Pitágoras', 'pesquise a fundo uma empresa'])
def test_explicit_deep_command_accepts_punctuation_and_verbs(query):
    assert pc_agent._JOB_START_RE.search(query)


@pytest.mark.parametrize('query,entity', [
    ('Pesquise quem fundou a Embraer e em que ano ela foi criada. Mostre as fontes.','Embraer'),
    ('Pesquise a história da Empresa Atlas: fundação e fundadores.','Empresa Atlas'),
    ('a linguagem Rust: criador e finalidade, usando fontes oficiais','Rust'),
    ('Faça uma pesquisa profunda: quem criou a linguagem Rust e qual é sua finalidade? Consulte fontes oficiais.','linguagem Rust'),
    ('o teorema de Pitágoras: enunciado e um exemplo numérico, com fontes','teorema de Pitágoras')])
def test_aspect_clauses_do_not_become_part_of_entity(query,entity):
    requirements=qi.answer_requirements(query)
    assert requirements and {r['entity'] for r in requirements}=={entity}
    assert qi.topic_profile(query)['original_request']==query


def test_colon_constraints_are_not_erased_from_discovery():
    text='Camera ZX: peso sem bateria e preço até R$ 3000'
    assert qi.topic_profile(text)['focused_query']==text


def test_language_request_does_not_accept_same_name_game():
    request='a linguagem Rust: criador e finalidade, usando fontes oficiais'
    item={'url':'https://example.org/game','titulo':'Rust survival game','trecho':'Rust was created by game developers.'}
    assert 'CONTEXT_MISMATCH' in orch._context_mismatch(item,request)


def test_verified_price_query_uses_facts_but_analysis_still_needs_model(monkeypatch):
    result={'produtos':[{'preco_confirmado':True,'link_veredito':'verificado'}]}
    monkeypatch.setattr(pc_agent.shopping,'resumo_texto',lambda r:'Observed price')
    monkeypatch.setattr(pc_agent,'_shopping_aplicar',lambda text,r:text+' cards')
    assert pc_agent._shopping_resposta_factual(result,'Encontre preço e link de um SSD')=='Observed price cards'
    assert not pc_agent._shopping_resposta_factual(result,'Compare o preço e desempenho dos SSDs')
    assert not pc_agent._shopping_resposta_factual({'produtos':[{'preco_confirmado':False}]},'Preço e link do SSD')


def test_storage_tb_and_gb_do_not_confuse_small_ram():
    import shopping
    assert shopping._armazenamento_aparente('SSD 1 TB, cache 16 GB') == 1024
    assert shopping._armazenamento_aparente('SSD 2TB') == 2048
    assert shopping._armazenamento_aparente('SSD 512 GB') == 512
    assert shopping._armazenamento_aparente('RAM 16 GB') is None


def test_same_query_history_survives_matching_short_random_prefixes(tmp_path,monkeypatch):
    import secrets,shopping
    counter=iter(range(2))
    monkeypatch.setattr(secrets,'token_hex',lambda n:(b'\xab\xcd'+next(counter).to_bytes(14,'big'))[:n].hex())
    db=pc_agent.open_db(tmp_path/'shopping-history.sqlite')
    try:
        first=shopping.salvar_consulta(db,'owner','chat','SSD',{}, {'produtos':[]})
        second=shopping.salvar_consulta(db,'owner','chat','SSD',{}, {'produtos':[]})
        assert first!=second
        assert db.execute('SELECT count(*) FROM shopping_consultas').fetchone()[0]==2
    finally:db.close()


def test_only_same_site_identity_links_follow_foundation_question():
    import web_extract
    links=[{'url':'https://example.org/about','texto':'About'},
           {'url':'https://external.org/about','texto':'About'},
           {'url':'https://example.org/legal','texto':'Privacy policy'}]
    query='Pesquise quem fundou a Empresa Atlas e em que ano foi criada'
    assert [r['url'] for r in web_extract.navigation_candidates(links,query,'https://example.org/')] == ['https://example.org/about']
    assert not web_extract.navigation_candidates(links,'Qual o peso da Camera ZX?','https://example.org/')
    links.insert(0,{'url':'https://example.org/atlas-products','texto':'Empresa Atlas produtos'})
    assert web_extract.navigation_candidates(links,query,'https://example.org/',limit=1)[0]['url']=='https://example.org/about'


def test_requested_creation_year_does_not_become_a_location_filter():
    query='Pesquise quem fundou a Embraer e em que ano ela foi criada. Mostre as fontes.'
    assert orch._termos_correspondencia(query)==['embraer']
    local='Quem fundou a Empresa Atlas em São Paulo?'
    assert not orch._util_para_pedido({'titulo':'Empresa Atlas','trecho':'Empresa Atlas foi fundada por Maria Silva.'},orch._termos_correspondencia(local),local)


def test_wiki_editorial_links_do_not_spend_document_navigation_slots():
    import web_extract
    parent='https://pt.wikipedia.org/wiki/Atlas'
    links=[{'url':parent+'?action=history','texto':'História Atlas'},
           {'url':'https://pt.wikipedia.org/wiki/Discuss%C3%A3o:Atlas','texto':'Atlas discussão'},
           {'url':'https://de.wikipedia.org/wiki/Atlas','texto':'Atlas'},
           {'url':'https://example.org/atlas/history','texto':'Atlas history'}]
    assert [r['url'] for r in web_extract.navigation_candidates(links,'Quem fundou Atlas?',parent)]==['https://example.org/atlas/history']
    extracted=web_extract.extrair_links('<a href="/w/index.php?title=Atlas&amp;action=history">Atlas história</a>',parent)
    assert extracted[0]['url'].endswith('title=Atlas&action=history')
    assert not web_extract.navigation_candidates(extracted,'Quem fundou Atlas?',parent)


def test_python_inventory_subquery_keeps_original_language_scope(monkeypatch):
    import time
    import python_docs_discovery as docs
    monkeypatch.setattr(docs,'_CACHE',(time.monotonic()+60,[
        'list.append py:method 1 library/stdtypes.html#$ -']))
    assert not docs.search('list.append retorno')
    request=qi.analyze('Investigue a fundo list.append no Python, qual o retorno?')
    with qi.discovery_scope(request):
        assert docs.search('list.append retorno')[0]['meta']['api_names']==['list.append']


def test_focused_creator_question_preserves_language_and_facets():
    query='Quem criou a linguagem Rust e qual é sua finalidade?'
    profile=qi.topic_profile(query)
    assert profile['primary_topic']=='linguagem Rust'
    assert 'linguagem' in profile['focused_query']
    assert set(r['attribute'] for r in profile['answer_requirements'])=={'founders','definition'}


def test_comparison_instruction_is_not_a_third_api():
    query='as diferenças entre list.append e list.extend no Python. Explique o retorno e se alteram a lista original usando a documentação oficial'
    assert {r['entity'] for r in qi.answer_requirements(query)}=={'list.append','list.extend'}
    assert 'linguagem' in qi.constrain_discovery('Rust fundadores',qi.analyze('Quem criou a linguagem Rust?'))


def test_document_scan_does_not_start_at_long_bibliography():
    import web_extract,evidence_graph
    query='Quem criou a linguagem NovaLang e qual é sua finalidade?'
    html=('<main><h1>NovaLang</h1><p>NovaLang foi criada por Maria Silva.</p>'
          '<p>NovaLang é uma linguagem de programação para criar aplicações seguras.</p>'
          '<section><h2>Referências</h2><ol>'+''.join('<li>Referência bibliográfica '+str(i)+' — '+'documento '*25+'</li>' for i in range(120))+'</ol></section></main>')
    doc=web_extract.extrair_pagina(html,'https://example.org/novalang',query,teto=1500,usar_trafilatura=False)
    coverage=evidence_graph.requirement_coverage(query,[{**doc,'lida':True}])
    assert len(doc['texto'])<=1500
    assert coverage['complete']
    assert 'Maria Silva' in doc['texto']


def test_empty_sphinx_anchor_alias_keeps_own_operation_scope():
    import copy,web_extract,evidence_graph
    query='Como usar list.append no Python? Explique seu comportamento e retorno.'
    html=('<main><h1>Built-in types</h1><p>'+'Introduction. '*700+'</p>'
          '<dl><span id="list.append"></span><dt>sequence.append(value, /)</dt>'
          '<dd><p>Append value to the end of the sequence.</p></dd></dl>'
          '<dl><dt>sequence.reverse()</dt><dd><p>Returns None after reversing the sequence.</p></dd></dl></main>')
    doc=web_extract.extrair_pagina(html,'https://docs.python.org/3/builtins/stdtypes.html',query,teto=1200,usar_trafilatura=False)
    coverage=evidence_graph.requirement_coverage(query,[{**doc,'lida':True}])
    assert next(r for r in coverage['requirements'] if r['attribute']=='behavior')['state']=='PARTIALLY_SUPPORTED'
    assert next(r for r in coverage['requirements'] if r['attribute']=='return_value')['state']!='SUPPORTED'
    assert 'reversing' not in doc['texto']
    passage=next(p for p in doc['answer_passages'] if web_extract.scoped_api_aliases(p))
    assert web_extract.scoped_api_aliases(passage)==['list.append']
    invalid=copy.deepcopy(passage);invalid['section_path'][-1]['dom_api_aliases']=['list.extend']
    assert not web_extract.scoped_api_aliases(invalid)
    invalid=copy.deepcopy(passage);invalid['source_span']['sha256']='stale'
    assert not web_extract.scoped_api_aliases(invalid)


def test_historical_source_cards_never_cross_chats(tmp_path):
    import research_agents
    db=pc_agent.open_db(tmp_path/'scoped-sources.sqlite')
    try:
        job=research_agents.criar_job(db,'owner','Rust language',conv='old-chat')
        source={'id':'S1','url':'https://example.org/rust','titulo':'Rust','dominio':'example.org'}
        research_agents.registrar_evidencia(db,job,source,'Rust is a programming language.')
        assert pc_agent.fence_de_fontes(db,'owner',conv='old-chat')
        assert not pc_agent.fence_de_fontes(db,'owner',conv='new-chat')
        assert not pc_agent.fence_de_evidencias(db,'owner','new-chat')
        assert not pc_agent.fence_de_fontes(db,'another-owner',conv='old-chat')
    finally:db.close()
