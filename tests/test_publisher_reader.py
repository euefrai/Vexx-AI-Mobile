"""Publisher REST contracts, relevance gates and persisted research evidence."""
import copy
import json
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlsplit

import pytest
import pc_agent
import publisher_reader as publisher
import query_intelligence as qi
import research
import research_agents as agents
import search_orchestrator as orch
import search_providers as sp

URL = 'https://ubatanoticias.com.br/ubata-projeto-municipal/'
QUERY = 'Notícias de hoje de Ubatã e região'
NOW = datetime(2026,11,4,18,tzinfo=timezone.utc)


@pytest.mark.parametrize('tail',['e mostre as fontes.','e inclua links diretos.','e cite as referências utilizadas.'])
def test_citation_request_does_not_become_part_of_the_location(tail):
    request=qi.analyze('Pesquise as notícias de hoje de Ubatã e região '+tail,now=NOW)
    assert request['parameters']['location']=='Ubatã'
    assert 'Gongogi' in request['parameters']['nearby_locations']
    assert request['search_query']=='"Ubatã" notícias'
    substantive=qi.analyze('Notícias sobre fontes de energia em Ubatã',now=NOW)
    assert substantive['parameters']['topic']=='fontes de energia'


def post(**overrides):
    return {'id':10,'status':'publish','link':URL,'date':'2026-11-04T10:00:00',
            'date_gmt':'2026-11-04T13:00:00','title':{'rendered':'Ubatã: projeto municipal'},
            'content':{'protected':False,'rendered':'<p>Ubatã recebeu um projeto municipal de educação. '
                       'O relatório apresenta os detalhes publicados e as atividades locais. '
                       'A comunidade pode consultar os horários e os documentos oficiais.</p>'},**overrides}


@pytest.fixture(autouse=True)
def active(monkeypatch):
    monkeypatch.setenv('JULIA_PUBLISHER_REST','1')
    monkeypatch.setattr(research,'url_segura',lambda url:url)


def transport(monkeypatch, records):
    calls=[]
    def fetch(url, **kw):
        calls.append((url,kw))
        return url,json.dumps(records)
    monkeypatch.setattr(research,'baixar',fetch)
    return calls


@pytest.mark.parametrize('bad',[
    'https://ubatanoticias.com.br.evil.test/article/', 'https://evil.test/article/',
    'http://ubatanoticias.com.br/article/', 'https://user:pass@ubatanoticias.com.br/article/',
    'https://ubatanoticias.com.br:444/article/', 'https://ubatanoticias.com.br/',
    'https://ubatanoticias.com.br/wp-admin/article/', 'https://ubatanoticias.com.br/category/local/',
    'https://ubatanoticias.com.br/%2e%2e/article/', 'https://ubatanoticias.com.br/article/?token=secret'])
def test_no_arbitrary_host_private_paths_or_query_forwarding(bad,monkeypatch):
    monkeypatch.setattr(research,'baixar',lambda *a,**kw:pytest.fail('unexpected read'))
    assert not publisher.eligible(bad) and publisher.read(bad,QUERY) is None


def test_exact_public_article_uses_content_not_excerpt_and_keeps_original_url(monkeypatch):
    calls=transport(monkeypatch,[post(excerpt={'rendered':'Wrong summary'})])
    rec=publisher.read(URL,QUERY)
    assert rec['final']==URL and rec['texto_lido'] and rec['lida']
    assert rec['content_scope']=='publisher_article' and 'Wrong summary' not in rec['texto']
    assert 'atividades locais' in rec['texto']
    assert rec['metadados']['publicado_em']=='2026-11-04T13:00:00Z'
    assert rec['metadados']['read_method']=='publisher_rest'
    params=parse_qs(urlsplit(calls[0][0]).query)
    assert params['slug']==['ubata-projeto-municipal'] and params['context']==['view']
    assert calls[0][1]['aceitar']=='json'


@pytest.mark.parametrize('change',[
    {'link':'https://other.test/ubata-projeto-municipal/'}, {'link':'https://ubatanoticias.com.br/other/'},
    {'status':'draft'}, {'status':'private'}, {'id':True}, {'content':{'protected':True,'rendered':'private'}},
    {'content':{'protected':False,'rendered':''}}, {'date_gmt':'invalid'}, {'title':{'rendered':''}}])
def test_other_articles_protected_posts_and_invalid_metadata_are_not_read(monkeypatch,change):
    transport(monkeypatch,[post(**change)])
    assert publisher.read(URL,QUERY) is None


def test_api_redirect_mismatch_and_unavailable_keep_html_fallback(monkeypatch):
    monkeypatch.setattr(research,'baixar',lambda *a,**kw:('https://other.test/wp-json/wp/v2/posts','[]'))
    assert publisher.read(URL,QUERY) is None
    def fail(*a,**kw):raise research.ResearchErro('unavailable','rede')
    monkeypatch.setattr(research,'baixar',fail)
    monkeypatch.setattr('public_store_reader.fetch',lambda *a,**kw:(URL,'<main><h1>Ubatã</h1><p>'+'Notícia local. '*30+'</p></main>'))
    rec=research._recuperar_um({'url':URL,'titulo':'Ubatã'},None,4,QUERY)
    assert rec['lida'] and rec['final']==URL


def test_cancellation_and_ssrf_are_never_swallowed(monkeypatch):
    for code in ('cancelada','ssrf'):
        def fail(*a,**kw):raise research.ResearchErro('stop',code)
        monkeypatch.setattr(research,'baixar',fail)
        with pytest.raises(research.ResearchErro) as caught:publisher.read(URL,QUERY)
        assert caught.value.codigo==code


def test_syndication_footer_cleanup_never_crosses_real_article_paragraphs():
    story='<p>O post publicado pela Prefeitura de Ubatã apresenta o projeto.</p><p>Detalhes locais preservados.</p>'
    footer='<p>O post <a href="https://example.test/">Projeto</a> apareceu primeiro em Ubatã Notícias.</p>'
    record=publisher._record(post(content={'protected':False,'rendered':story+footer}))
    assert record['markup']==story


def test_discovery_filters_wrong_date_location_topic_and_unread_state(monkeypatch):
    request=qi.analyze(QUERY,now=NOW)
    monkeypatch.setattr(qi,'analyze',lambda *a,**kw:request)
    wrong=post(link=URL.replace('ubata','salvador'),title={'rendered':'Salvador: projeto'},
               content={'protected':False,'rendered':'<p>Projeto em Salvador, Bahia.</p>'})
    old=post(date_gmt='2026-10-01T13:00:00')
    nearby=post(link='https://ubatanoticias.com.br/gongogi-projeto/',title={'rendered':'Gongogi: projeto'},
                content={'protected':False,'rendered':'<p>Atividade em Gongogi.</p>'})
    calls=transport(monkeypatch,[post(),wrong,old,nearby])
    found=publisher.discover(QUERY)
    assert len(found)==2 and all(row['content_scope']=='article_candidate' for row in found)
    assert all(not row.get('texto_lido') for row in found)
    params=parse_qs(urlsplit(calls[0][0]).query)
    assert params['per_page']==['20'] and params['after']==['2026-11-04T00:00:00']
    assert 'search' not in params  # Preserve nearby-city coverage.


def test_rest_candidates_can_satisfy_discovery_without_generic_search(monkeypatch):
    request=qi.analyze(QUERY,now=NOW)
    monkeypatch.setattr(qi,'analyze',lambda *a,**kw:request)
    transport(monkeypatch,[post()])
    monkeypatch.setattr(sp,'buscar',lambda *a,**kw:pytest.fail('already enough candidates'))
    result=orch.pesquisar(QUERY,orcamento={'min_resultados':1,'max_tentativas':3})
    assert result['achados'][0]['url']==URL
    assert result['tentativas_busca'][0]['provedor']=='publisher-rest'


@pytest.mark.parametrize('credit', [' (Ubatã Notícias)',
    '<figcaption class="wp-caption-text">— Crédito: Ubatã Notícias</figcaption>',
    '<p>O post Teste apareceu primeiro em Ubatã Notícias.</p>'])
def test_publisher_credit_does_not_make_national_news_local(monkeypatch,credit):
    request=qi.analyze(QUERY,now=NOW)
    monkeypatch.setattr(qi,'analyze',lambda *a,**kw:request)
    row=post(title={'rendered':'Fux defende proibição das apostas online no Brasil'},
             content={'protected':False,'rendered':'<p>O STF discute as apostas online no Brasil.</p>'+credit})
    transport(monkeypatch,[row])
    assert publisher.discover(QUERY)==[]
    import search_verticals
    legacy={'titulo':row['title']['rendered'],'trecho':'O STF discute apostas no Brasil. (Ubatã Notícias)',
            'url':URL,'tipo':'noticia','publicado_em':'2026-11-04T13:00:00Z'}
    assert 'ENTITY_MISMATCH' in search_verticals.assess(request,legacy)['reasons']
    rec=publisher.read(URL,QUERY)
    if rec:
        source=research._fonte_de(rec,{'url':URL,'titulo':row['title']['rendered'],'tipo':'noticia'},QUERY)
        assert source['relevante'] is False


def test_failed_rest_and_feed_keep_a_general_search_attempt(monkeypatch):
    monkeypatch.setenv('JULIA_PREFERRED_NEWS_FEEDS','1')
    monkeypatch.setattr(publisher,'discover',lambda *a,**kw:[])
    monkeypatch.setattr(sp,'buscar_feed_preferencial',lambda *a,**kw:[])
    calls=[]
    def search(name,query,**kw):calls.append(query);return []
    monkeypatch.setattr(sp,'buscar',search)
    result=orch.pesquisar(QUERY,orcamento={'max_tentativas':3,'max_consultas':2,'max_provedores':2})
    assert any('site:' not in query for query in calls)
    assert len(result['tentativas_busca'])<=3


def test_api_read_reaches_common_sources_and_deep_persistent_evidence(monkeypatch,tmp_path):
    request=qi.analyze(QUERY,now=NOW)
    monkeypatch.setattr(qi,'analyze',lambda *a,**kw:request)
    transport(monkeypatch,[post()])
    monkeypatch.setattr('public_store_reader.fetch',lambda *a,**kw:pytest.fail('HTML not needed'))
    source={'url':URL,'titulo':'Ubatã: projeto municipal','tipo':'noticia','publicado_em':'2026-11-04T13:00:00Z'}
    rec=research._recuperar_um(source,None,4,QUERY)
    common=research._fonte_de(rec,source,QUERY)
    assert common['status']=='aberta' and common['relevante'] and common['url_final']==URL
    db=pc_agent.open_db(tmp_path/'news.sqlite')
    try:
        job=agents.criar_job(db,'qa',QUERY)
        evidence=agents.agente_analista(db,job,{'alvo':QUERY},[source])
        persisted=agents.listar_evidencias(db,'qa',job['id'])
        assert len(evidence)==len(persisted)==1
        assert persisted[0]['texto_lido'] is True and persisted[0]['url']==URL
        assert persisted[0]['content_scope']=='publisher_article'
    finally:db.close()
