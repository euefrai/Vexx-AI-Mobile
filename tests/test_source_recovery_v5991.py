"""Pipeline regressions, not evidence of live recall or semantic quality."""
from datetime import datetime
from zoneinfo import ZoneInfo
import sqlite3

import pytest
import research


def test_promising_original_after_six_generic_results_receives_a_read_slot():
    db=sqlite3.connect(':memory:');research.criar_tabelas(db)
    found=[{'titulo':'Guia turístico de Recife','url':f'https://travel{i}.example/recife',
            'trecho':'Turismo em Recife','tipo':'pagina'} for i in range(6)]
    original={'titulo':'Intervenções no trânsito','url':'https://publisher.example/intervencoes',
              'source_recovery':{'method':'publisher_link'},'tipo':'noticia'}
    found.append(original)
    calls=[]
    today=datetime.now(ZoneInfo('America/Bahia')).date().isoformat()
    def read(url):
        calls.append(url)
        return {'titulo':'Recife registra acidente de trânsito' if url==original['url'] else 'Guia turístico de Recife',
                'texto':('Um acidente ocorreu hoje em Recife. '*25 if url==original['url'] else 'Passeios e turismo em Recife. '*25),
                'lida':True,'final':url,'metadados':{'publicado_em':today}}
    result=research.pesquisa_rapida(db,'qa','Notícias sobre acidente em Recife hoje',lambda _:found,read)
    assert original not in found[:6]  # Reproduces the previous positional cut.
    assert original['url'] in calls and len(calls)==6
    assert result['fontes_uteis']==1
    source=next(s for s in result['fontes'] if s['url']==original['url'])
    assert source['status']=='aberta' and source['relevante']
    trace=next(s for s in result['candidate_reservoir']['items'] if s['url']==original['url'])
    assert trace['selected'] and trace['returned'] and trace['extracted_chars']>0
    assert trace['evidence_ref']==source['id'] and trace['content_state']=='READ_PARTIAL'
    db.close()


def test_diversity_uses_same_priority_without_promoting_index_or_expanding_reads():
    candidates=[{'titulo':'Solar news','url':f'https://one.example/article{i}'} for i in range(8)]
    other={'titulo':'Solar news','url':'https://two.example/article'}
    index={'titulo':'Solar news','url':'https://index.example/search?q=solar'}
    result=research.selecionar_candidatos_leitura(candidates+[index,other],'Solar news')
    assert len(result)==6 and other in result and index not in result
    assert result[:2]==[candidates[0],other]


def test_feed_media_and_malformed_targets_do_not_consume_article_read_slots():
    rows=[{'url':'https://news.google.com/rss/articles/x','content_scope':'feed_metadata'},
          {'url':'https://upload.wikimedia.org/p.jpg','origem':'commons','tipo':'imagem'},
          {'url':'https://[invalid','titulo':'Invalid'}]
    assert research.selecionar_candidatos_leitura(rows,'notícias')==[]


@pytest.mark.parametrize('error,loss',[
    ('bloqueado','FETCH_BLOCKED'),('rate_limited','FETCH_BLOCKED'),('rede','FETCH_FAILED')])
def test_read_failure_is_not_mislabelled_as_topic_rejection(error,loss):
    row={'url':'https://publisher.example/report','titulo':'Report'}
    trace=research.candidate_report([row],[],'Report',read_outcomes={row['url']:{'error':error}},
        selected_urls={row['url']},returned_urls=set())['items'][0]
    assert trace['losses']==[loss] and not trace['read']


def test_empty_extraction_budget_omission_and_constraint_rejection_are_distinct():
    rows=[{'url':f'https://publisher.example/{i}','titulo':str(i)} for i in range(3)]
    source={**rows[2],'status':'aberta','relevante':False,
            'vertical':{'reasons':['TEMPORAL_MISMATCH','ENTITY_MISMATCH']}}
    trace=research.candidate_report(rows,[source],'notícias',
        read_outcomes={rows[0]['url']:{'chars':0},rows[2]['url']:{'chars':200}},
        selected_urls={rows[0]['url'],rows[2]['url']},returned_urls=set())['items']
    assert trace[0]['losses']==['EXTRACTION_EMPTY']
    assert trace[1]['losses']==['READ_BUDGET_NOT_SELECTED']
    assert trace[2]['losses']==['DATE_MISMATCH','HARD_CONSTRAINT_MISMATCH']
    assert trace[2]['state']=='REJECTED' and trace[2]['read']


def test_old_retrieval_cache_is_not_reused_after_selection_change():
    db=sqlite3.connect(':memory:');research.criar_tabelas(db)
    research.cache_put(db,'qa','web','solar',{'retrieval_version':'5.9.9','fontes':[]},600)
    calls=[]
    result=research.pesquisa_rapida(db,'qa','solar',lambda q:calls.append(q) or [],lambda _:None)
    assert calls and not result['de_cache'] and result['retrieval_version']=='5.9.9.1'
    db.close()


def test_offline_loss_analysis_does_not_invent_missing_trace_or_model_failure():
    from tools.analyze_source_recovery_v5991 import analyze_case
    row=analyze_case({'id':'shopping','sources':[],'calls':[],'opened':0})
    assert row['losses']=={'TRACE_UNAVAILABLE':1}
    assert row['synthesis']=='NOT_EXECUTED_RETRIEVAL_PROBE'
    assert row['factual_precision'] is None and row['absolute_recall'] is None


def test_offline_loss_analysis_preserves_read_rejection_and_external_block():
    from tools.analyze_source_recovery_v5991 import analyze_case
    row=analyze_case({'reservoir':{'unique_candidates':2,'items':[
        {'url':'https://one.example/a','read':True,'reasons':['TEMPORAL_MISMATCH']},
        {'url':'https://two.example/a','read':False,'reasons':[]}]},
        'fetches':[{'url':'https://one.example/a','final':'https://one.example/a'},
                   {'url':'https://two.example/a','error':'bloqueado'}]})
    assert row['losses']=={'DATE_MISMATCH':1,'FETCH_BLOCKED':1}
    assert row['read_in_candidate_pool']==1
    assert row['extraction_trace_available'] is False


@pytest.mark.parametrize('query,entity',[
    ('História da empresa Embraer fontes oficiais','Embraer'),
    ('História da fundação de Ouro Preto','Ouro Preto'),
    ('História da empresa Horizonte Verde exceto publicidade','Horizonte Verde'),
])
def test_named_entity_retry_or_original_preserves_request_constraints(query,entity):
    import search_orchestrator as orch
    retry=orch.consulta_conteudo(query) or query
    assert entity in retry
    assert retry.replace('"','')==query


def test_named_entity_retry_does_not_replace_original_or_change_product_query():
    import search_orchestrator as orch
    query='História da empresa Horizonte Verde fontes oficiais'
    assert orch.variantes(query)[0]==query
    assert not orch.consulta_conteudo('notebook 16 GB até R$ 3000')


def test_publisher_name_does_not_dilute_headline_match_or_create_duplicate_originals():
    import search_providers as sp
    lead={'publisher_url':'https://publisher.example','titulo':'Biblioteca municipal inaugurada - Agência Estadual de Comunicação',
          'publicador':'Agência Estadual de Comunicação','url':'https://news.google.com/rss/articles/x'}
    calls=[]
    def fetch(url,kind):
        calls.append(url)
        return url,('<a href="/">Biblioteca municipal inaugurada</a>'
                    '<a href="/report">Biblioteca municipal inaugurada</a>'
                    '<a href="/report">Biblioteca municipal inaugurada</a>'
                    '<a href="https://publisher.example.evil.test/report">Biblioteca municipal inaugurada</a>')
    result=sp.recuperar_feed_publicador(lead,fetch)
    assert calls==[lead['publisher_url']]
    assert len(result)==1 and result[0]['url']=='https://publisher.example/report'
    assert result[0]['content_scope']=='article_candidate'
    assert not result[0].get('publicado_em')


def test_article_extraction_resolves_declared_metadata_against_fetched_destination(monkeypatch):
    final='https://publisher.example/content/article'
    html='<title>Research article</title><link rel="canonical" href="canonical"><article><h1>Research article</h1><p>'+('Useful research content with exact names and numbers 42. '*30)+'</p></article>'
    monkeypatch.setattr(research,'baixar',lambda *a,**kw:(final,html))
    result=research._recuperar_um({'url':'https://publisher.example/redirect'},None,3,'research')
    assert result['final']==final
    assert result['metadados']['canonica']=='https://publisher.example/content/canonical'


def test_publication_and_update_remain_distinct_in_normalized_source():
    row=research._fonte_de({'texto':'Research content '*30,'lida':True,
        'metadados':{'publicado_em':'2026-10-20','atualizado_em':'2026-10-24'}},
        {'url':'https://publisher.example/research','titulo':'Research'},'Research')
    assert row['publicado_em']=='2026-10-20'
    assert row['atualizado_em']=='2026-10-24'


@pytest.mark.parametrize('text',[
    'Pesquisa profunda sobre notícias em Fortaleza hoje',
    'Pesquise a fundo sobre notícias em Faro nos últimos sete dias',
])
def test_explicit_deep_news_reaches_job_and_keeps_requested_depth(monkeypatch,text):
    import pc_agent
    assert pc_agent.cmd_dados_atuais(None,text,'qa','chat',{}) is None
    calls=[]
    def start(db,req,owner):
        calls.append((req,owner));return {'type':'research_job','job_id':'rj-test'}
    monkeypatch.setattr(pc_agent,'_cmd_analisar_tabular',lambda *a:'')
    monkeypatch.setattr(pc_agent,'_cmd_intervencao',lambda *a:'')
    monkeypatch.setattr(pc_agent,'rjob_start',start)
    result=pc_agent.cmd_pesquisa(None,text,'qa','chat')
    assert 'rj-test' in result and len(calls)==1
    req,owner=calls[0]
    assert req['modo']=='profunda' and req['conv']=='chat' and owner=='qa'
    assert 'notícias' in req['objetivo']
