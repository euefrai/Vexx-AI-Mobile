from datetime import datetime, timezone
import pytest

import query_intelligence as qi
import search_orchestrator as orch
import search_providers as sp
import search_verticals

NOW=datetime(2026,10,29,1,tzinfo=timezone.utc)  # 28 October in Bahia.


def test_this_week_uses_monday_in_the_request_timezone():
    request=qi.analyze('Notícias desta semana de Ubatã',now=NOW)
    assert request['parameters']['start_date']=='2026-10-26'
    assert request['parameters']['end_date']=='2026-10-28'


def article(title,url,published='Thu, 29 Oct 2026 00:30:00 +0000'):
    return f'<item><title>{title}</title><link>{url}</link><pubDate>{published}</pubDate><description>{title}</description></item>'


def test_local_feed_filters_date_location_and_publisher(monkeypatch):
    query='Notícias de hoje de Ubatã e região'
    request=qi.analyze(query,now=NOW)
    monkeypatch.setattr(qi,'analyze',lambda *a,**kw:request)
    entries=[article('Ubatã: projeto anunciado','https://ubatanoticias.com.br/projeto/'),
             article('Gongogi: serviço municipal','https://ubatanoticias.com.br/gongogi/'),
             article('Salvador: notícia estadual','https://ubatanoticias.com.br/salvador/'),
             article('Ubatã: matéria antiga','https://ubatanoticias.com.br/antiga/','Tue, 27 Oct 2026 10:00:00 +0000'),
             article('Ubatã: fonte alheia','https://evil.example/ubata/')]
    monkeypatch.setattr(sp,'_baixar',lambda url,*a,**kw:(url,'<rss><channel>'+''.join(entries)+'</channel></rss>'))
    rows=sp.buscar_feed_preferencial('https://ubatanoticias.com.br/feed/',query)
    assert [r['titulo'] for r in rows]==['Ubatã: projeto anunciado','Gongogi: serviço municipal']
    assert all(r['content_scope']=='article_candidate' for r in rows)
    assert all(not r.get('texto_lido') for r in rows)


def test_city_only_does_not_implicitly_include_region():
    row={'titulo':'Gongogi: serviço municipal','url':'https://ubatanoticias.com.br/gongogi/',
         'publicado_em':'2026-10-28','tipo':'noticia'}
    assert not search_verticals.assess(qi.analyze('Notícias de hoje de Ubatã',now=NOW),row)['eligible']
    assert search_verticals.assess(qi.analyze('Notícias de hoje de Ubatã e região',now=NOW),row)['eligible']


def test_sufficient_publisher_feed_avoids_search_engine_requests(monkeypatch):
    monkeypatch.setenv('JULIA_PREFERRED_NEWS_FEEDS','1')
    request=qi.analyze('Notícias de hoje de Ubatã',now=NOW)
    monkeypatch.setattr(qi,'analyze',lambda *a,**kw:request)
    rows=[{'titulo':'Ubatã: projeto anunciado','url':'https://ubatanoticias.com.br/projeto/',
           'trecho':'Ubatã: projeto anunciado','tipo':'noticia','origem':'publisher-rss',
           'publicado_em':'2026-10-28','content_scope':'article_candidate'}]
    monkeypatch.setattr(sp,'buscar_feed_preferencial',lambda *a,**kw:rows)
    monkeypatch.setattr(sp,'buscar',lambda *a,**kw:pytest.fail('feed already has sufficient candidates'))
    result=orch.pesquisar('Notícias de hoje de Ubatã',orcamento={'min_resultados':1,'max_tentativas':3})
    assert result['achados'][0]['url']==rows[0]['url']
    assert not result['achados'][0].get('texto_lido')


def test_feed_failure_preserves_general_search_budget(monkeypatch):
    monkeypatch.setenv('JULIA_PREFERRED_NEWS_FEEDS','1')
    def fail(*a,**kw):raise sp.ErroProvedor('Unavailable','rede')
    monkeypatch.setattr(sp,'buscar_feed_preferencial',fail)
    calls=[]
    def search(name,query,**kw):
        calls.append(query)
        if 'site:' in query:raise sp.ErroProvedor('Empty','vazio')
        return []
    monkeypatch.setattr(sp,'buscar',search)
    result=orch.pesquisar('Notícias de hoje de Ubatã',orcamento={'max_tentativas':3,'max_consultas':2,'max_provedores':2})
    assert any('site:' not in query for query in calls)
    assert len(result['tentativas_busca'])<=3
