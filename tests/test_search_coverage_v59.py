"""Regressions from the seven V5.9 live probes; deterministic and offline."""
import json
import sqlite3

import pytest

import research
import search_orchestrator as orch
import search_providers as sp
import shopping
import web_extract


def db():
    conn = sqlite3.connect(':memory:')
    research.criar_tabelas(conn)
    shopping.criar_tabelas(conn)
    return conn


def hit(title, url='https://source.example/article', text=''):
    return {'titulo': title, 'url': url, 'trecho': text, 'origem': 'bing', 'tipo': 'pagina'}


def test_generic_architecture_does_not_stop_transformer_fallback(monkeypatch):
    calls = []
    def search(provider, query, **kwargs):
        calls.append(provider)
        if provider == 'bing':
            return [hit('Arquitetura: conceito e estilos', f'https://decor.example/{i}') for i in range(3)]
        return [hit('Transformer architecture: self-attention', 'https://arxiv.org/abs/1706.03762')]
    monkeypatch.setattr(sp, 'buscar', search)
    result = orch.pesquisar('Como funciona a arquitetura Transformer? Fontes técnicas.',
        provedores=['bing', 'marginalia'], orcamento={'max_consultas': 2})
    assert 'marginalia' in calls
    assert result['achados'][0]['url'] == 'https://arxiv.org/abs/1706.03762'


def test_substring_is_not_topic_evidence():
    assert not orch._util_para_pedido(hit('A capital do Brasil'), ['api'])


def test_provider_loop_respects_elapsed_budget_and_records_failures(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(orch.time, 'monotonic', lambda: clock[0])
    calls = []
    def search(provider, query, **kwargs):
        calls.append((provider, kwargs['timeout']))
        clock[0] += 5
        raise sp.ErroProvedor('network unavailable', 'rede')
    monkeypatch.setattr(sp, 'buscar', search)
    result = orch.pesquisar('python asyncio', provedores=['bing', 'marginalia', 'wikipedia'],
        timeout=8, orcamento={'timeout_total': 2, 'max_consultas': 2})
    assert len(calls) == 1
    assert calls[0][1] <= 2
    assert result['provedores']['falhas'][0]['codigo'] == 'rede'


def test_unreadable_or_irrelevant_page_is_not_successful_research():
    result = research.pesquisa_rapida(db(), 'owner', 'Python asyncio',
        buscar_fn=lambda q: [hit('Python asyncio', 'https://docs.example/asyncio')],
        recuperar_fn=lambda url: {'titulo': 'Ajuda do Google Maps', 'texto': 'Escolha seu destino no Google Maps. ' * 20,
            'ilegivel': True, 'lida': True})
    assert result['estado'] != 'ok'
    assert not any(s['status'] == 'aberta' for s in result['fontes'])


def test_read_source_preserves_tables_sections_author_and_date(monkeypatch):
    monkeypatch.setattr(research, 'baixar', lambda *a, **kw: ('https://docs.example/page',
        '<html><head><title>Python asyncio</title><meta name="author" content="Example author"></head>'
        '<body><main><h1>Python asyncio</h1><p>Python asyncio supports concurrent tasks. ' + 'Details about asyncio. '*30 + '</p>'
        '<h2>Timings</h2><table><tr><th>Method</th><th>Time</th></tr><tr><td>await</td><td>2 ms</td></tr></table></main></body></html>'))
    result = research.pesquisa_rapida(db(), 'owner', 'Python asyncio',
        buscar_fn=lambda q: [hit('Python asyncio', 'https://docs.example/page')])
    source = result['fontes'][0]
    assert source['status'] == 'aberta'
    assert source['tabelas'][0][1] == ['await', '2 ms']
    assert source['secoes']
    assert source['autor'] == 'Example author'


def test_shopping_cache_never_reuses_other_budget_or_model():
    conn = db()
    first = shopping.pesquisar(conn, 'owner', 'Notebook Lenovo 16 GB RAM até R$ 3000', buscar_fn=lambda q: [])
    second = shopping.pesquisar(conn, 'owner', 'Notebook Lenovo 16 GB RAM até R$ 1500', buscar_fn=lambda q: [])
    assert not second['de_cache']
    assert second['criterios']['orcamento']['max'] == 1500
    third = shopping.pesquisar(conn, 'owner', 'Notebook Lenovo 16 GB RAM até R$ 3000', buscar_fn=lambda q: [])
    assert third['de_cache']


def test_all_shopping_queries_preserve_explicit_constraints():
    query = 'Notebook Lenovo com 16 GB RAM até R$ 3.000.'
    queries = shopping._consultas_produto(shopping.extrair_criterios(query), query)
    assert all('lenovo' in q.lower() and '16' in q and '3000' in q.replace('.', '') for q in queries)


@pytest.mark.parametrize('valid_index,page_limit', [(2, 2), (10, 6)])
def test_shopping_second_wave_runs_until_offer_matches_budget(monkeypatch, valid_index, page_limit):
    monkeypatch.setattr(research, '_ips_globais', lambda host: None)
    candidates = [hit(f'Notebook Lenovo 16GB RAM {i}', f'https://shop.example/item-{i}') for i in range(12)]
    def download(url, **kwargs):
        number = int(url.rsplit('-', 1)[-1])
        price = '2500.00' if number == valid_index else '4500.00'
        product = {'@context':'https://schema.org','@type':'Product','name':f'Notebook Lenovo 16GB RAM {number}',
            'brand':{'@type':'Brand','name':'Lenovo'},'offers':{'@type':'Offer','price':price,'priceCurrency':'BRL',
                'url':url,'availability':'https://schema.org/InStock'}}
        return {'final':url, 'texto':'<html><head><title>Notebook Lenovo 16GB RAM</title></head><body><script type="application/ld+json">' + json.dumps(product) + '</script></body></html>'}
    result = shopping.pesquisar(db(), 'owner', 'Notebook Lenovo 16 GB RAM até R$ 3000',
        buscar_fn=lambda q: candidates, baixar_fn=download, teto_paginas=page_limit, usar_cache=False)
    assert result['produtos'], result['descoberta']
    assert all(p['preco'] <= 3000 for p in result['produtos'])
    assert result['descoberta']['ondas'] == 2
