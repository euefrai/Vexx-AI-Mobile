"""Regressions discovered while operating the real UI; live runs are separate."""
import json
import time
import zlib

import pytest
import pc_agent
import python_docs_discovery as docs
import research
import search_orchestrator as orch
import shopping
import store_discovery as stores


def inventory(body):
    return (b'# Sphinx inventory version 2\n# Project: Python\n# Version: 3.14\n'
            b'# The remainder of this file is compressed using zlib.\n' + zlib.compress(body.encode()))


def test_official_inventory_matches_named_apis_without_command_false_positives(monkeypatch):
    blob = inventory('asyncio py:module 0 library/asyncio.html#$ -\n'
        'asyncio.TaskGroup py:class 1 library/asyncio-task.html#$ -\n'
        'asyncio.gather py:function 1 library/asyncio-task.html#$ -\n'
        'ast.Compare py:class 1 library/ast.html#$ -\n')
    monkeypatch.setattr(docs, '_CACHE', (time.monotonic() + 60, docs.parse_inventory(blob)))
    rows = docs.search('Compare asyncio.TaskGroup e asyncio.gather em Python')
    assert len(rows) == 1
    assert rows[0]['url'].startswith('https://docs.python.org/3/library/asyncio-task.html#')
    assert set(rows[0]['meta']['api_names']) == {'asyncio.TaskGroup', 'asyncio.gather'}
    assert not orch._context_mismatch(rows[0], 'comparando asyncio.TaskGroup e asyncio.gather em Python')
    assert all(r['status'] == 'encontrada' for r in rows)
    assert not docs.search('Compare celulares Android')


def test_inventory_rejects_wrong_project_bombs_and_external_targets(monkeypatch):
    with pytest.raises(ValueError):
        docs.parse_inventory(inventory('x').replace(b'Project: Python', b'Project: Other'))
    with pytest.raises(ValueError):
        docs.parse_inventory(inventory('x' * (docs.MAX_EXPANDED + 1)))
    with pytest.raises(ValueError):
        docs.parse_inventory(inventory('x') + b'trailing data')
    blob = inventory('asyncio.gather py:function 1 http://127.0.0.1/private -\n')
    monkeypatch.setattr(docs, '_CACHE', (time.monotonic() + 60, docs.parse_inventory(blob)))
    assert docs.search('asyncio.gather Python') == []


def test_python_docs_routing_is_scoped_and_can_be_disabled(monkeypatch):
    monkeypatch.setenv('JULIA_PYTHON_DOCS_DISCOVERY', '1')
    info = orch.classificar('Compare asyncio.TaskGroup e asyncio.gather em Python')
    assert orch._escolher_provedores(info['classes'], info)[0] == 'python-docs'
    other = orch.classificar('Documentação oficial de JavaScript fetch')
    assert 'python-docs' not in orch._escolher_provedores(other['classes'], other)
    monkeypatch.setenv('JULIA_PYTHON_DOCS_DISCOVERY', '0')
    assert 'python-docs' not in orch._escolher_provedores(info['classes'], info)


def catalog(items):
    data = {'props': {'pageProps': {'data': {'catalogServer': {'data': items}}}}}
    return '<script id="__NEXT_DATA__" type="application/json">' + json.dumps(data) + '</script>'


def test_catalog_discovers_direct_urls_without_promoting_listing_prices():
    row = {'code': 998334, 'friendlyName': 'placa-rtx-3050-6gb',
           'name': 'RTX 3050 6GB', 'price': 999, 'description': '<p>Memória 6GB</p>'}
    out = stores.extract_kabum(catalog([row, row,
        dict(row, code=10, friendlyName='../../private'),
        dict(row, code='https://evil.example', friendlyName='unsafe')]))
    assert len(out) == 1
    assert out[0]['url'] == 'https://www.kabum.com.br/produto/998334/placa-rtx-3050-6gb'
    assert out[0]['status'] == 'encontrada'
    assert 'preco' not in out[0] and 'price' not in out[0]
    assert stores.catalog_query('GPU RTX 3050 6 GB à venda Brasil. direto comprar oferta') == 'RTX 3050 6GB'


def test_catalog_stops_on_challenge_and_off_site_redirect(monkeypatch):
    monkeypatch.setenv('JULIA_NATIVE_STORE_SEARCH', '1')
    monkeypatch.setattr(stores, '_CACHE', {})
    row = {'code': 998334, 'friendlyName': 'rtx-3050-6gb', 'name': 'RTX 3050 6GB'}
    page = catalog([row])
    monkeypatch.setattr(research, 'baixar', lambda *a, **k: ('https://evil.example/busca/foo', page))
    assert stores.search_kabum('RTX 3050') == []
    monkeypatch.setattr(research, 'baixar', lambda *a, **k: ('https://www.kabum.com.br/busca/foo', '<h1>Confirme que você é humano</h1>' + page))
    assert stores.search_kabum('RTX 3050') == []


def test_explicit_other_store_is_not_replaced_by_kabum(monkeypatch):
    monkeypatch.setattr(shopping, 'buscar_mlb', lambda *a, **k: [])
    monkeypatch.setattr(stores, 'search_kabum', lambda *a, **k: pytest.fail('Named store must be respected'))
    monkeypatch.setattr(shopping, 'buscar_web_v55', lambda *a, **k: ([], []))
    monkeypatch.setattr(shopping, 'buscar_ddg_chain', lambda *a, **k: ([], []))
    shopping.buscar_com_fallback('fone bluetooth', texto_lojas='fone somente na Shopee')


def test_empty_search_does_not_claim_captcha_without_diagnostic_or_promise_more():
    result = {'produtos': [], 'criterios': {'categoria': 'placa de video'},
              'descoberta': {'diagnosticos': ['DISCOVERY_EMPTY']}}
    answer = pc_agent._shopping_sem_ofertas(result)
    assert answer and 'CAPTCHA' not in answer and '403' not in answer
    assert 'aguarde' not in answer.casefold() and 'pesquisa em andamento' not in answer.casefold()
    assert not pc_agent._shopping_sem_ofertas(None)
    assert not pc_agent._shopping_sem_ofertas({'produtos': [{'nome': 'Produto válido'}]})


def test_research_confirmation_language_does_not_list_memory_pending_items(tmp_path):
    db = pc_agent.open_db(tmp_path / 'memory-routing.sqlite')
    try:
        for query in ['Compare as duas primeiras opções, com os preços e as diferenças que você conseguiu confirmar.',
                      'Confirme o preço deste produto.', 'Analise quais dados estão pendentes na pesquisa.']:
            assert pc_agent.interpretar_comando_memoria(db, query, 'local') is None
        for query in ['mostre minhas pendências', 'o que está aguardando confirmação?', 'pendências']:
            assert pc_agent.interpretar_comando_memoria(db, query, 'local')[1] == 'mem_pend_vazia'
    finally:
        db.close()


def test_feminine_comparison_and_publication_week_keep_context():
    import query_intelligence
    query = 'Compare as duas primeiras opções, com os preços e as diferenças que você conseguiu confirmar.'
    assert shopping.eh_followup(query)
    request = query_intelligence.analyze('Quais são as notícias desta semana de Ubatã e região? Traga links das matérias.')
    assert request['parameters']['location'] == 'Ubatã'
    assert 'Ibirapitanga' in request['parameters']['nearby_locations']
    assert shopping._data_br_curta('2026-10-29T00:28:27+00:00') == '28/10/2026'


def test_curated_python_document_keeps_both_api_identifiers_before_dedup():
    query = 'comparando asyncio.TaskGroup e asyncio.gather em Python. Verifique cancelamento e tratamento de exceções, com documentação oficial'
    rows = orch.fontes_preferenciais(query)
    assert rows and rows[0]['url'] == 'https://docs.python.org/3/library/asyncio-task.html'
    assert not orch._context_mismatch(rows[0], query)


def test_portuguese_api_comparison_reads_late_english_relations(tmp_path):
    import query_intelligence as qi
    import evidence_graph as eg
    import research_agents as ra
    query = ('Faça uma pesquisa profunda comparando asyncio.TaskGroup e asyncio.gather em Python. '
             'Verifique cancelamento e tratamento de exceções, com documentação oficial.')
    requirements = qi.answer_requirements(query)
    assert {(r['entity'], r['attribute']) for r in requirements} == {
        (api, facet) for api in ('asyncio.TaskGroup', 'asyncio.gather')
        for facet in ('cancellation', 'exceptions')}
    assert not qi.answer_requirements('Como pedir cancelamento de viagem e tratar exceções?')
    # Synthetic long document: relation text must survive beyond the initial cut.
    body = '<main><h1>Asyncio reference</h1><p>' + ('Introduction to awaitables. ' * 700) + '</p>'
    for api in ('asyncio.TaskGroup', 'asyncio.gather'):
        body += (f'<h2>{api}</h2><p>{api} cancels pending tasks when explicitly cancelled.</p>'
                 f'<p>{api} raises an exception when an operation fails.</p>')
    body += '</main>'
    url = 'https://docs.python.org/3/library/asyncio-task.html'
    document = research.extrair_artigo(body, url, query, teto=1800)
    assert len(document['texto']) <= 1800
    assert document['document_scan']['available_chars'] > 1800
    coverage = eg.requirement_coverage(query, [{**document, 'url': url, 'texto_lido': True}])
    assert all(r['state'] == 'SUPPORTED' for r in coverage['requirements']
               if r['type'] == 'explicit_attribute'), coverage
    assert not coverage['complete']  # Domain/title alone do not prove authority.
    db = pc_agent.open_db(tmp_path / 'api-evidence.sqlite')
    try:
        job = ra.criar_job(db, 'qa', query)
        found = {'titulo': 'Asyncio reference', 'url': url, 'trecho': ''}
        read = {**document, 'texto_lido': True, 'final': url}
        evidence = ra.agente_analista(db, job, {'id': 'api', 'alvo': query}, [found], lambda _: read)
        assert evidence and all(ra._evidencia_lida(e) for e in evidence)
        unrelated = {**read, 'texto': read['texto'].replace('asyncio.', 'unrelated.'),
                     'answer_passages': [], 'secoes': [], 'document_context': {}}
        other = ra.criar_job(db, 'qa', query)
        assert not ra.agente_analista(db, other, {'id': 'bad', 'alvo': query}, [found], lambda _: unrelated)
    finally:
        db.close()


def test_api_signature_scope_is_partial_literal_and_distributed(tmp_path):
    import evidence_graph as eg
    query = 'Compare asyncio.TaskGroup e asyncio.gather: cancelamento e exceptions.'
    html = '<main><h1>API reference</h1><p>' + 'Unrelated introduction. ' * 900 + '</p>'
    for signature in ('class asyncio.TaskGroup', 'awaitable asyncio.gather(*aws)'):
        html += (f'<dl><dt>{signature}</dt><dd><p>Run awaitable operations concurrently.</p>'
                 '<p>Pending tasks are cancelled when the operation is cancelled.</p>'
                 '<p>An exception is propagated to the calling task.</p></dd></dl>')
    html += '</main>'
    url = 'https://docs.python.org/3/library/asyncio-task.html'
    doc = research.extrair_artigo(html, url, query, teto=1600)
    coverage = eg.requirement_coverage(query, [{**doc, 'url': url, 'texto_lido': True}])
    assert len(doc['texto']) <= 1600
    assert len(coverage['requirements']) == 4
    assert all(r['state'] == 'PARTIALLY_SUPPORTED' for r in coverage['requirements']), coverage
    assert not coverage['complete']
    assert {'class asyncio.TaskGroup', 'awaitable asyncio.gather(*aws)'} <= {
        h['text'] for p in doc['answer_passages'] for h in p.get('section_path', [])}
    import research_agents as ra
    db=pc_agent.open_db(tmp_path/'scoped-read.sqlite')
    try:
        job=ra.criar_job(db,'qa',query)
        read={**doc,'texto_lido':True,'final':url}
        found={'url':url,'titulo':'API reference','trecho':''}
        evidence=ra.agente_analista(db,job,{'id':'scoped','alvo':query},[found],lambda _:read)
        assert evidence  # A real signature is context, without inventing a quote.
    finally:
        db.close()
    for passage in doc['answer_passages']:
        for heading in passage.get('section_path', []):
            heading['source_span']['sha256'] = 'invalid'
    broken = eg.requirement_coverage(query, [{**doc, 'url': url, 'texto_lido': True}])
    assert not broken['passages']
