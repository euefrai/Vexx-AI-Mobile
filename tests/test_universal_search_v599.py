"""Deterministic regressions; not a live recall/quality benchmark."""
from datetime import datetime, timezone
import json
import sqlite3

import pytest
import query_intelligence as qi
import research
import research_view
import search_verticals as sv
import pc_agent
import jdui


NOW = datetime(2026,10,24,14,tzinfo=timezone.utc)


@pytest.mark.parametrize('query,city,start,end',[
    ('Notícias sobre Ubatã, Bahia, na última semana','Ubatã','2026-10-17','2026-10-24'),
    ('Notícias de Recife hoje','Recife','2026-10-24','2026-10-24'),
    ('Notícias em Manaus ontem','Manaus','2026-10-23','2026-10-23'),
    ('Principais notícias do Brasil hoje','Brasil','2026-10-24','2026-10-24'),
])
def test_news_entity_and_calendar_are_hard_constraints(query,city,start,end):
    parsed=qi.analyze(query,now=NOW)
    p=parsed['parameters']
    assert p['location']==city and p['start_date']==start and p['end_date']==end
    assert parsed['constraints']['hard']['location']==city
    assert parsed['constraints']['hard']['start_date']==start


def test_topic_does_not_disappear_from_discovery_or_final_precision():
    parsed=qi.analyze('Notícias sobre acidentes em Recife hoje',now=NOW)
    assert parsed['parameters']['location']=='Recife'
    assert parsed['parameters']['topic']=='acidentes'
    assert 'acidentes' in parsed['search_query']
    wrong={'titulo':'Recife anuncia festival','trecho':'Festival em Recife', 'publicado_em':'2026-10-24'}
    assert 'TOPIC_MISMATCH' in sv.assess(parsed,wrong)['reasons']


@pytest.mark.parametrize('city,other',[('Ubatã','Salvador'),('Recife','Olinda'),('Manaus','Manacapuru')])
def test_other_city_is_never_a_confirmed_local_article(city,other):
    parsed=qi.analyze(f'Notícias em {city} hoje',now=NOW)
    source={'titulo':f'Notícia em {other}','trecho':f'Evento ocorrido em {other}', 'publicado_em':'2026-10-24'}
    assert not sv.assess(parsed,source)['eligible']


def test_final_source_gate_keeps_publication_date_after_actual_read():
    today=datetime.now(timezone.utc).astimezone(__import__('zoneinfo').ZoneInfo('America/Bahia')).date().isoformat()
    query='Notícias em Recife hoje'
    found={'titulo':'Recife anuncia obras','url':'https://example.org/recife/obras','publicado_em':today}
    rec={'texto':'Recife anuncia novas obras e intervenções nas ruas da cidade. '*10,'lida':True}
    source=research._fonte_de(rec,found,query)
    assert source['publicado_em']==today and source['relevante']
    assert research.fontes_relevantes(query,[source])==[source]
    stale={**source,'publicado_em':'2020-01-01'}
    assert not research.fontes_relevantes(query,[stale])


def commons_result():
    return {'titulo':'Ponte Estaiada São Paulo','url':'https://commons.wikimedia.org/wiki/File:Ponte.jpg',
            'tipo':'imagem','origem':'commons','trecho':'Ponte Estaiada em São Paulo',
            'meta':{'original_url':'https://upload.wikimedia.org/wikipedia/commons/0/00/Ponte.jpg',
                    'pagina':'https://commons.wikimedia.org/wiki/File:Ponte.jpg',
                    'thumb_url':'https://upload.wikimedia.org/wikipedia/commons/0/00/Ponte.jpg'}}


def test_media_survives_retrieval_cache_message_and_sqlite_reload(tmp_path):
    db=sqlite3.connect(tmp_path/'qa.sqlite')
    research.criar_tabelas(db)
    db.execute('create table messages (id text primary key,text text)')
    calls=[]
    def search(query): calls.append(query);return [commons_result()]
    result=research.pesquisa_rapida(db,'qa','Imagens da Ponte Estaiada de São Paulo',search,lambda url:{'texto':'','lida':False})
    assert len(result['midia'])==1
    assert result['fontes_lidas']==0
    cached=research.pesquisa_rapida(db,'qa','Imagens da Ponte Estaiada de São Paulo',search,lambda url:pytest.fail('Cache missed'))
    assert cached['de_cache'] and len(calls)==1
    final=pc_agent.anexar_fontes('Mídia encontrada.',[],midia=cached['midia'])
    fences=jdui.extrair_fences(final)
    parsed=json.loads(fences[0]);assert parsed['blocks'][0]['component']=='media'
    assert parsed['blocks'][0]['props']['items'][0]['analysis_state']=='not_analyzed'
    db.execute('insert into messages values (?,?)',('qa-message',final));db.commit();db.close()
    reopened=sqlite3.connect(tmp_path/'qa.sqlite')
    assert reopened.execute('select text from messages').fetchone()[0]==final
    reopened.close()


def test_source_cards_general_documents_and_media_do_not_depend_on_model_markup():
    source={'titulo':'TaskGroup documentation','url':'https://docs.python.org/3/library/asyncio-task.html',
            'status':'aberta','texto_lido':'TaskGroup','trecho':'TaskGroup','relevante':True}
    fence=research_view.contextual_fence([source])
    assert json.loads(jdui.extrair_fences(fence)[0])['blocks'][0]['component']=='sources'
    assert not research_view.media_fence([])
    assert not research_view.media_fence([{'type':'image','url':'javascript:alert(1)'}])


def test_reservoir_is_bounded_stable_and_explains_exclusion():
    candidates=[{'titulo':f'Article {i}','url':f'https://example.org/{i}'} for i in range(50)]
    source={**candidates[0],'relevante':False,'vertical':{'reasons':['ENTITY_MISMATCH']}}
    report=research.candidate_report(candidates,[source],'qa',limit=5)
    assert len(report['items'])==5 and report['omitted']==45
    assert report['items'][0]['state']=='REJECTED'
    assert report['items'][0]['reasons']==['ENTITY_MISMATCH']
    assert report['items'][0]['id']==research.candidate_report(candidates[:1],[],'other query')['items'][0]['id']


def test_reformulation_keeps_required_place_and_topic():
    parsed=qi.analyze('Notícias sobre acidentes em Recife hoje',now=NOW)
    query=qi.constrain_discovery('acidentes últimas manchetes',parsed)
    assert 'Recife' in query
    assert qi.analyze('Notícias em Recife ontem',now=NOW)['temporal']


def test_news_day_followup_never_crosses_owner_chat_current_message_or_topic():
    import conversation_followups as followups
    db=sqlite3.connect(':memory:')
    db.execute('create table messages (id text,owner_id text,conversation_id text,role text,origin text,text text)')
    def add(ident,text,owner='qa',conv='chat'):
        db.execute('insert into messages values (?,?,?,?,?,?)',(ident,owner,conv,'user','mobile',text))
    add('one','Notícias em Recife hoje');add('other','Notícias em Manaus hoje','other')
    add('two','E as de ontem?');add('future','Notícias em Salvador hoje')
    assert followups.news_request(db,'qa','chat','E as de ontem?','two')=='Notícias em Recife ontem'
    assert not followups.news_request(db,'qa','other-chat','E as de ontem?','two')
    add('break','Explique Python');add('three','E as de ontem?')
    assert not followups.news_request(db,'qa','chat','E as de ontem?','three')
    db.close()


def test_chat_news_uses_shared_retrieval_not_the_feed_shortcut(tmp_path,monkeypatch):
    db=pc_agent.open_db(tmp_path/'qa.sqlite')
    calls=[]
    monkeypatch.setattr(research,'pesquisa_rapida',lambda db,owner,text:(calls.append((owner,text)) or {'fontes':[]}))
    result=pc_agent.cmd_dados_atuais(db,'Notícias em Recife hoje','local','qa',{})
    assert calls==[('local','Notícias em Recife hoje')]
    assert 'fontes utilizáveis' in result
    db.close()


def test_visual_request_returns_actual_gallery_without_a_background_job(tmp_path,monkeypatch):
    import media_evidence
    db=pc_agent.open_db(tmp_path/'qa.sqlite')
    media=media_evidence.discover_search_media([commons_result()])
    monkeypatch.setattr(research,'pesquisa_rapida',lambda *a,**kw:{'midia':media})
    monkeypatch.setattr(pc_agent,'rjob_start',lambda *a,**kw:pytest.fail('Simple gallery started a job'))
    response=pc_agent.cmd_pesquisa(db,'Pesquise imagens da Ponte Estaiada de São Paulo','local','qa')
    assert json.loads(jdui.extrair_fences(response)[0])['blocks'][0]['component']=='media'
    assert 'não foram analisados' in response
    db.close()


def test_feed_leads_do_not_hide_original_articles_from_reader_budget(tmp_path):
    db=sqlite3.connect(tmp_path/'qa.sqlite');research.criar_tabelas(db)
    today=datetime.now(timezone.utc).date().isoformat()
    feeds=[{'titulo':'Recife anuncia obras','url':f'https://news.google.com/{i}',
            'trecho':'Recife anuncia obras','content_scope':'feed_metadata', 'meta':{'publicado_em':today}}
            for i in range(6)]
    original={'titulo':'Recife anuncia obras','url':'https://example.org/obras','publicado_em':today}
    opened=[]
    def read(url):opened.append(url);return {'texto':'Recife anuncia obras. '*20,'lida':True}
    result=research.pesquisa_rapida(db,'qa','Notícias em Recife hoje',lambda q:feeds+[original],read)
    assert opened==[original['url']]
    assert result['fontes'][0]['url']==original['url'] and result['fontes_uteis']==1
    assert all(s['content_scope']=='feed_metadata' for s in result['fontes'][1:])
    db.close()


def test_document_and_video_requests_really_enter_search():
    assert pc_agent.intencao_pesquisa('Encontre na documentação oficial como usar asyncio.TaskGroup.')
    assert pc_agent.intencao_pesquisa('Encontre vídeos explicativos sobre motores elétricos.')


def test_model_cards_and_fake_tool_markup_cannot_impersonate_retrieval():
    fake='```jdui\n'+json.dumps({'version':jdui.VERSION,'blocks':[{'type':'ui','component':'media','props':{'items':[{'type':'image','url':'https://example.org/invented.jpg'}]}}]})+'\n```'
    cleaned=pc_agent.anexar_fontes(fake,[],pesquisa_executada=True)
    assert cleaned.strip() and 'invented.jpg' not in cleaned
    source={'id':'S1','titulo':'TaskGroup','url':'https://docs.python.org/3/library/asyncio-task.html',
            'trecho':'TaskGroup creates tasks.','texto_lido':'TaskGroup creates tasks.', 'status':'aberta','relevante':True}
    output=pc_agent.anexar_fontes('Procurarei.<tool_call>Search(query="TaskGroup")',[source],pesquisa_executada=True,consulta='TaskGroup')
    assert '<tool_call>' not in output and 'TaskGroup creates tasks.' in output
    for draft in ('Vou pesquisar a documentação oficial.','Não tenho acesso à web nesta conversa.'):
        result=pc_agent.anexar_fontes(draft,[source],pesquisa_executada=True,consulta='TaskGroup')
        assert 'TaskGroup creates tasks.' in result and draft not in result


def test_qualified_api_identifier_survives_semantic_html_spacing():
    import search_orchestrator as orch
    assert orch._tem_termo('asyncio.TaskGroup','asyncio . TaskGroup ()')
    assert orch._tem_termo('httpx.AsyncClient','httpx . AsyncClient')
    assert not orch._tem_termo('asyncio.TaskGroup','myasyncio . TaskGroup')


def test_news_without_city_still_requires_topic_not_a_generic_dictionary():
    import search_orchestrator as orch
    query='Pesquise as principais novidades sobre inteligência artificial e compare os acontecimentos mais relevantes.'
    terms=orch._termos_correspondencia(query)
    junk={'titulo':'Principais significado','trecho':'Principais é plural de principal'}
    relevant={'titulo':'Inteligência artificial: novos modelos','trecho':'Novos modelos de inteligência artificial'}
    assert not orch._util_para_pedido(junk,terms,query)
    assert orch._util_para_pedido(relevant,terms,query)


def test_instruction_words_cannot_outrank_a_specific_primary_document():
    import search_orchestrator as orch
    query='Encontre na documentação oficial como usar asyncio.TaskGroup.'
    candidates=orch.fontes_preferenciais(query)+[{'titulo':'Documentação significado','url':'https://example.org/dictionary',
        'trecho':'Documentação conceito','origem':'bing','tipo':'pagina'}]
    info=orch.classificar(query)
    ranked=orch.ranquear(candidates,query,info['classes'],info)
    assert ranked[0]['url'].startswith('https://docs.python.org/')
