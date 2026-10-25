"""Causal regressions for discovery; fixtures do not measure live coverage."""
import sqlite3
from datetime import datetime, timezone

import pytest
import query_intelligence as qi
import research
import search_orchestrator as orch
import search_providers as sp


def test_news_today_uses_request_calendar_at_utc_midnight_boundary():
    import search_verticals
    request = qi.analyze('Notícias em Recife hoje', now=datetime(2026, 10, 25, 1, tzinfo=timezone.utc))
    assert request['parameters']['start_date'] == '2026-10-24'
    source = {'titulo': 'Recife anuncia obras', 'url': 'https://publisher.example/obras', 'publicado_em': '2026-10-24'}
    assert search_verticals.assess(request, source)['eligible']
    assert not search_verticals.assess(request, {**source, 'publicado_em': '2026-10-25'})['eligible']


@pytest.mark.parametrize('query,first,required', [
    ('História do Museu do Amanhã fontes oficiais', 'Museu do Amanhã', 'história'),
    ('História da empresa WEG fontes primárias', 'WEG', 'história'),
    ('Documentação oficial WebCrypto SubtleCrypto digest', 'WebCrypto SubtleCrypto digest', 'documentação'),
    ('Especificações oficiais Sony WH-CH520 autonomia', 'Sony WH-CH520 autonomia', 'especificações'),
    ('Relatório público PDF desmatamento Amazônia INPE', 'desmatamento Amazônia INPE', 'PDF'),
])
def test_planner_separates_requested_information_from_the_subject(query, first, required):
    profile = qi.topic_profile(query)
    plan = orch.query_plan(query)
    assert profile['original_request'] == query
    assert plan[0]['type'] == 'TOPIC_FOCUSED'
    assert plan[0]['query'].startswith(first)
    assert required.casefold() in plan[0]['query'].casefold()
    assert any(p['type'] == 'ORIGINAL_QUERY' and p['query'] == query for p in plan)


def test_presentation_is_not_an_entity_and_original_constraints_are_preserved():
    query = 'Pesquise profundamente as últimas novidades sobre inteligência artificial e apresente as principais informações em cards com imagens.'
    p = qi.topic_profile(query)
    assert p['primary_topic'] == 'inteligência artificial'
    assert p['presentation_preferences']
    assert 'cards' not in orch.query_plan(query)[0]['query']
    constrained = 'História da empresa Horizonte Verde em 2020, exceto publicidade e sem dados de outra empresa'
    for item in orch.query_plan(constrained):
        assert all(t in item['query'] for t in ('Horizonte Verde', '2020', 'exceto publicidade', 'sem dados de outra empresa'))


def test_focused_discovery_does_not_relax_model_identity_after_reading():
    query = 'Especificações oficiais Sony WH-CH520 autonomia'
    bad = {'titulo': 'Sony WH-CH720 especificações autonomia', 'texto': 'Sony WH-CH720 autonomia de bateria. ' * 30, 'lida': True}
    result = research._fonte_de(bad, {'url': 'https://publisher.example/report'}, query)
    assert result['relevante'] is False


def test_operation_words_cannot_replace_the_requested_organization():
    query = 'História da empresa WEG fontes primárias'
    assert not orch._util_para_pedido({'titulo': 'História da empresa', 'trecho': 'História das fontes primárias da empresa.'},
                                      orch._termos_correspondencia(query), query)


def test_recovered_original_after_twelve_survives_both_reservoir_cuts():
    db = sqlite3.connect(':memory:'); research.criar_tabelas(db)
    generic = [{'url': f'https://generic{i}.example/report', 'titulo': 'General overview', 'trecho': 'Unrelated text'} for i in range(14)]
    original = {'url': 'https://primary.example/photons', 'titulo': 'Photon detectors', 'source_recovery': {'method': 'publisher_link'}}
    seen = []
    def read(url):
        seen.append(url)
        return {'texto': 'Photon detectors experiments and sensitivity. ' * 30, 'lida': True}
    result = research.pesquisa_rapida(db, 'qa', 'Photon detectors', lambda _: generic + [original], read)
    assert original['url'] in seen and len(seen) <= 6
    assert any(s['url'] == original['url'] and s['relevante'] and s['status'] == 'aberta' for s in result['fontes'])
    assert result['candidate_reservoir']['unique_candidates'] == 12
    db.close()


def test_news_reserves_existing_attempts_for_declared_publisher_feed(monkeypatch):
    calls = []
    def search(name, query, **kwargs):
        calls.append((name, query))
        if name == 'google-news':
            return [{'url': 'https://news.google.com/rss/articles/lead', 'titulo': 'Biblioteca inaugurada em Recife - Publicador',
                     'publisher_url': 'https://publisher.example', 'publicador': 'Publicador', 'content_scope': 'feed_metadata'}]
        return [{'url': 'https://dictionary.example/recife', 'titulo': 'Dictionary'}]
    def fetch(url, *args, **kwargs):
        calls.append(('fetch', url))
        return url, ('<link rel="alternate" type="application/rss+xml" href="/rss">' if url.endswith('.example') else
                     '<rss><channel><item><title>Biblioteca inaugurada em Recife</title><link>https://publisher.example/library</link></item></channel></rss>')
    monkeypatch.setattr(sp, 'buscar', search); monkeypatch.setattr(sp, '_baixar', fetch)
    result = orch.pesquisar('Notícias em Recife hoje', provedores=['google-news', 'bing-news', 'bing'],
        orcamento={'max_tentativas': 6, 'max_consultas': 2, 'timeout_total': 8})
    assert any(a['url'] == 'https://publisher.example/library' for a in result['achados'])
    assert len(result['tentativas_busca']) <= 6
    assert ('fetch', 'https://publisher.example/rss') in calls
    assert not any(a.get('status') == 'aberta' for a in result['achados'])


def test_pdf_request_does_not_approve_html_as_the_requested_document():
    source = research._fonte_de({'titulo': 'Desmatamento Amazônia INPE relatório público PDF',
        'texto': 'Desmatamento Amazônia INPE relatório público PDF. ' * 30, 'lida': True, 'content_scope': 'page_text'},
        {'url': 'https://publisher.example/index'}, 'Relatório público PDF desmatamento Amazônia INPE')
    assert not source['relevante']
    assert 'CONTENT_TYPE_MISMATCH' in source['vertical']['reasons']


def test_unrelated_domains_do_not_count_as_information_gain():
    before = orch._retrato([], 'História da empresa WEG fontes primárias')
    gain = orch._ganho_informacao(before, [{'titulo': 'História geral', 'url': 'https://dictionary.example/history'}],
                                  'História da empresa WEG fontes primárias')
    assert not gain['ganho_real']


def test_topic_economics_without_news_intent_does_not_select_news_provider():
    q = 'Economia circular na indústria têxtil processos limitações'
    info = orch.classificar(q); info['request'] = qi.analyze(q)
    providers = orch._escolher_provedores(info['classes'], info)
    assert providers[0] not in ('bing-news', 'google-news', 'hn')
