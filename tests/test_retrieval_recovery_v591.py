"""Regressions for real retrieval failures; fixtures never represent live offers."""
import copy
import json
import sqlite3
from datetime import datetime, timezone

import docs_agent
import search_orchestrator as orch
import search_providers as providers
import research
import shopping
import pytest


def _page(name='Notebook Lenovo 16GB RAM', price='2999.90', expiry=''):
    data = {'@context': 'https://schema.org', '@type': 'Product', 'name': name,
            'brand': {'@type': 'Brand', 'name': 'Lenovo'},
            'image': 'https://shop.test/notebook.jpg',
            'description': 'Produto com características e condições descritas nesta página individual.',
            'offers': {'@type': 'Offer', 'price': price, 'priceCurrency': 'BRL',
                       'availability': 'https://schema.org/InStock', 'priceValidUntil': expiry}}
    return '<html><title>' + name + '</title><script type="application/ld+json">' + json.dumps(data) + '</script><main><h1>' + name + '</h1><p>Comprar produto. Entrega e condições da loja. ' + name + '</p></main></html>'


def test_item_beyond_first_budget_is_validated_and_delivered_to_jdui():
    db = sqlite3.connect(':memory:')
    shopping.criar_tabelas(db)
    categories = [{'titulo': 'Notebooks', 'url': f'https://shop.test/categoria/notebook-{i}'} for i in range(9)]
    target = 'https://shop.test/produto/notebook-lenovo-16gb'
    fetched = []
    def download(url):
        fetched.append(url)
        return {'final': url, 'texto': _page() if url == target else '<html>Categoria</html>'}
    result = shopping.pesquisar(db, 'qa', 'Notebook Lenovo com 16 GB RAM até R$ 3.000.',
        buscar_fn=lambda q: categories + [{'titulo': 'Notebook Lenovo 16GB RAM', 'url': target}],
        baixar_fn=download, teto_paginas=1, usar_cache=False)
    assert fetched == [target]
    assert result['descoberta']['confirmadas'] == 1
    assert result['produtos'][0]['correspondencia_tipo'] == 'EXACT_MATCH'
    fence = shopping.fence_resultado(result)
    assert 'productcard' in fence and target in fence
    assert shopping.ultima_consulta(db, 'qa', '')['resultado']['produtos'][0]['nome'] == 'Notebook Lenovo 16GB RAM'
    assert any(d['codigo'] == 'extraida' for d in result['diagnostico_paginas'])


def test_missing_requested_ram_and_expired_prices_are_not_confirmed():
    p = shopping._recuperar_ofertas('https://shop.test/produto/x', 'Notebook Lenovo',
        baixar_fn=lambda u: {'texto': _page(name='Notebook Lenovo')})[0]
    valid, _ = shopping.aplicar_filtros([p], shopping.extrair_criterios('Notebook Lenovo 16GB RAM até 3000'))
    assert valid[0]['correspondencia_tipo'] == 'PARTIAL_MATCH'
    assert shopping._tier(valid[0]) == 'parcial'
    expired = shopping._recuperar_ofertas('https://shop.test/produto/x', 'Notebook Lenovo',
        baixar_fn=lambda u: {'texto': _page(expiry='2001-01-01')})[0]
    assert not shopping._preco_vigente(expired)
    assert shopping._tier(expired) == 'parcial'


def test_identity_query_parameters_are_not_deduplicated_as_tracking():
    a = 'https://shop.test/produto/phone?sku=256&utm_source=ads'
    assert shopping._mesmo_recurso(a, 'https://shop.test/produto/phone?sku=256')
    assert not shopping._mesmo_recurso(a, 'https://shop.test/produto/phone?sku=128')


def test_storage_constraint_is_extracted_without_word_storage():
    c = shopping.extrair_criterios('Celular Samsung Galaxy A56 256 GB, menor preço.')
    assert c['specs']['armazenamento_gb'] == 256
    assert c['specs']['armazenamento_exato']
    p = {'nome': 'Samsung Galaxy A56 512GB', 'preco': 2000, 'preco_confirmado': True,
         'preco_texto': 'R$ 2.000', 'marca': 'Samsung', 'link_veredito': 'verificado'}
    inside, outside = shopping.aplicar_filtros([p], c)
    assert not inside and 'armazenamento_diferente' in outside[0]['excluido_codigos']


def test_scientific_adapter_uses_existing_normalizer_and_safe_bounded_fetch(monkeypatch):
    seen = []
    monkeypatch.setattr(research, '_circuito', {})
    def fetch(url, timeout):
        seen.append((url, timeout))
        return {'message': {'items': [{'DOI': '10.1234/fixture', 'title': ['Solid-state batteries research'],
            'URL': 'https://publisher.test/paper', 'type': 'journal-article',
            'published-online': {'date-parts': [[2025, 2, 3]]},
            'author': [{'given': 'Ana', 'family': 'Silva'}],
            'abstract': '<jats:p>Solid-state batteries with solid electrolytes. A fictional abstract used only for pipeline verification and limitations.</jats:p>'}]}}
    monkeypatch.setattr(providers, '_json', fetch)
    result = providers.buscar_crossref('Estudos científicos recentes sobre baterias de estado sólido', timeout=1.25)
    source = result[0]
    assert 'solid-state+batteries' in seen[0][0] and 'from-pub-date' in seen[0][0]
    assert seen[0][1] == 1.25
    assert source['review_status'] is None
    assert source['authors'] == ['Ana Silva'] and source['year'] == 2025
    assert source['publication_type'] == 'journal-article'
    rec = research._recuperar_um(source, None, 1, 'baterias de estado sólido')
    normalized = research._fonte_de(rec, source, 'baterias de estado sólido')
    assert normalized['relevante'] and normalized['content_scope'] == 'abstract_only'
    assert normalized['full_text_fetched'] is False
    assert 'página original não aberta' in research.bloco_grounding([normalized], '22/10/2026')
    unique, discarded = orch.deduplicar([source, {**source, 'url': 'https://repository.test/paper'}])
    assert len(unique) == 1 and len(discarded) == 1


def test_blocked_academic_provider_is_not_retried(monkeypatch):
    monkeypatch.setattr(research, '_circuito', {})
    calls = []
    def blocked(url, timeout):
        calls.append(url)
        raise providers.ErroProvedor('403', 'bloqueado')
    monkeypatch.setattr(providers, '_json', blocked)
    for _ in range(2):
        with pytest.raises(providers.ErroProvedor):
            providers.buscar_crossref('baterias estado sólido')
    assert len(calls) == 1


def test_generic_categories_do_not_stop_specific_discovery():
    categories = [{'titulo': 'Celulares em promoção', 'url': 'https://shop.test/categoria/celular'}]
    assert not shopping._descoberta_suficiente(categories, 'Samsung Galaxy A56 256GB comprar oferta')


def test_matching_product_after_first_four_jsonld_records_is_not_lost():
    html = ''.join(_page(name='Notebook Dell 8GB RAM', price='8000') for _ in range(4))
    html += _page(name='Notebook Lenovo 16GB RAM', price='2999')
    offers = shopping.extrair_ofertas_jsonld(html, 'Notebook Lenovo 16GB RAM até R$ 3000')
    assert len(offers) == 4
    assert offers[0]['nome'] == 'Notebook Lenovo 16GB RAM'


def test_item_price_change_is_filtered_again_before_delivery():
    db = sqlite3.connect(':memory:')
    shopping.criar_tabelas(db)
    item = 'https://shop.test/produto/lenovo-16gb'
    category = 'https://shop.test/categoria/notebooks'
    old = _page(price='2499').replace('"priceCurrency": "BRL"', '"priceCurrency": "BRL", "url": "' + item + '"')
    def download(url):
        return {'final': url, 'texto': _page(price='3500') if url == item else old}
    result = shopping.pesquisar(db, 'qa', 'Notebook Lenovo 16GB RAM até R$ 3000',
        buscar_fn=lambda q: [{'titulo': 'Notebook Lenovo 16GB RAM', 'url': category}],
        baixar_fn=download, usar_cache=False)
    assert not result['produtos']
    assert result['descoberta']['confirmadas'] == 0
    assert 'BUDGET_MISMATCH' in result['descoberta']['diagnosticos']


def test_expired_offer_is_not_reused_from_cache():
    db = sqlite3.connect(':memory:')
    shopping.criar_tabelas(db)
    result = {'produtos': [{'nome': 'Notebook Lenovo', 'preco_valido_ate': '2000-01-01'}]}
    shopping.salvar_consulta(db, 'qa', 'chat', 'notebook lenovo', {}, result)
    assert shopping.consulta_em_cache(db, 'qa', 'notebook lenovo') is None
    rendered = shopping._jdui_produto({'nome': 'Notebook', 'preco': 1000,
        'preco_texto': 'R$ 1.000', 'preco_valido_ate': '2000-01-01'})
    assert rendered['preco_valor'] is None
    assert 'expirado' in rendered['specs']['Validade']


def test_followup_does_not_present_expired_cached_prices_as_current():
    db = sqlite3.connect(':memory:')
    shopping.criar_tabelas(db)
    shopping.salvar_consulta(db, 'qa', 'chat', 'notebook', {},
                             {'produtos': [{'nome': 'Notebook', 'preco': 1000}]})
    db.execute("UPDATE shopping_consultas SET expira_em='2000-01-01T00:00:00+00:00'")
    response = shopping.responder_followup(db, 'qa', 'chat', 'Qual o mais barato?')
    assert response['produtos'] == [] and response['fence'] == ''
    assert 'verificados novamente' in response['texto']


def test_opengraph_fallback_preserves_unknown_stock_and_actual_price():
    html = '''<html><title>Notebook Lenovo 16GB RAM</title>
    <meta property="og:type" content="product">
    <meta property="og:title" content="Notebook Lenovo 16GB RAM">
    <meta property="product:price:amount" content="2499.90">
    <meta property="product:price:currency" content="BRL">
    <meta property="og:image" content="https://shop.test/notebook.jpg">
    <main><h1>Notebook Lenovo 16GB RAM</h1><p>Comprar notebook com 16 GB de RAM e condições de entrega descritas na loja.</p></main></html>'''
    p = shopping._recuperar_ofertas('https://shop.test/produto/lenovo', 'Notebook Lenovo',
        baixar_fn=lambda u: {'texto': html})[0]
    assert p['preco'] == 2499.90 and p['moeda'] == 'BRL'
    assert p['preco_origem'] == 'opengraph'
    assert p['disponibilidade'] == 'desconhecida'
    assert p['imagem'] == 'https://shop.test/notebook.jpg'


def test_academic_publication_date_keeps_origin_and_precision():
    import academic_research
    item = {'DOI': '10.1234/dates', 'title': ['Fixture paper'], 'type': 'journal-article',
            'published-print': {'date-parts': [[2025, 5]]},
            'published-online': {'date-parts': [[2024, 12, 3]]},
            'indexed': {'date-time': '2026-10-22T00:00:00Z'}}
    record = academic_research.normalize_crossref(item, 'https://api.crossref.org/works')
    assert record['publicado_em'] == '2024-12-03'
    assert record['publication_date_origin'] == 'published-online'
    item.pop('published-online')
    record = academic_research.normalize_crossref(item, 'https://api.crossref.org/works')
    assert record['publicado_em'] == '2025-05'
    assert record['year'] == 2025
