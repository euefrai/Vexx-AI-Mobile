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


def test_shopping_queries_preserve_product_and_explicit_budget_filter():
    query = 'Notebook Lenovo com 16 GB RAM até R$ 3.000.'
    criteria = shopping.extrair_criterios(query)
    queries = shopping._consultas_produto(criteria, query)
    assert all('lenovo' in q.lower() and '16' in q for q in queries)
    assert any('3000' in q.replace('.', '') for q in queries)
    assert criteria['orcamento']['max'] == 3000


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
    assert result['produtos'][0]['url_final'] in {s['url'] for s in result['fontes']}
    import jdui
    _, blocks, errors = jdui.normalizar(shopping.fence_resultado(result))
    assert blocks and not errors


def test_official_document_candidates_are_not_marked_read():
    sources = orch.fontes_preferenciais('Compare FastAPI e Django usando documentação.')
    assert {s['url'] for s in sources} == {'https://fastapi.tiangolo.com/', 'https://docs.djangoproject.com/en/stable/'}
    assert all(s['status'] == 'encontrada' and not s['trecho'] for s in sources)
    assert orch.fontes_preferenciais('Python e jogos') == []


def test_comparison_intent_survives_query_cleaning():
    sources = [hit('FastAPI', 'https://fastapi.example/docs'), hit('Django', 'https://django.example/docs')]
    result = research.pesquisa_rapida(db(), 'owner', 'Compare FastAPI e Django usando documentação.',
        buscar_fn=lambda q: sources,
        recuperar_fn=lambda url: {'titulo': 'FastAPI' if 'fastapi' in url else 'Django',
            'texto': ('FastAPI' if 'fastapi' in url else 'Django') + ' official documentation. '*20})
    assert result['estado'] == 'ok'
    assert all(s['status'] == 'aberta' for s in result['fontes'])


def test_scholarly_query_keeps_subject_period_and_source_kind():
    query = 'Pesquise estudos científicos recentes sobre baterias de estado sólido em 2025'
    variants = orch.variantes(query, ['academico'])
    assert variants[0].startswith('baterias de estado sólido')
    assert all('2025' in q and 'recentes' in q for q in variants)
    assert orch.classificar(query)['academica']


def test_recovery_does_not_reset_exhausted_query_budget(monkeypatch):
    calls = []
    def search(*args, **kwargs):
        calls.append(kwargs)
        return {'achados': [], 'estado':'sem_resultados', 'consultas':['one'],
                'recuperacao':['two'], 'segundos':0, 'lacunas':['sem fonte']}
    monkeypatch.setattr(orch, 'pesquisar', search)
    result = orch.pesquisar_com_recuperacao('python asyncio', orcamento={'max_consultas':1, 'max_consultas_total':1})
    assert len(calls) == 1 and not result['recuperou']


def test_empty_marketplace_does_not_stop_other_providers(monkeypatch):
    monkeypatch.setattr(shopping, 'buscar_mlb', lambda *a, **k: [])
    expected = [hit('Notebook Lenovo', 'https://shop.example/item')]
    monkeypatch.setattr(shopping, 'buscar_ddg_chain', lambda *a: (expected, ['ddg: 1']))
    result, _ = shopping.buscar_com_fallback('Notebook Lenovo')
    assert result == expected


def test_blocked_marketplace_not_retried_for_variants(monkeypatch):
    calls = []
    def blocked(*a, **k):
        calls.append(1)
        raise research.ResearchErro('HTTP 403', 'bloqueado')
    monkeypatch.setattr(shopping, 'buscar_mlb', blocked)
    monkeypatch.setattr(shopping, 'buscar_ddg_chain', lambda *a: ([], []))
    monkeypatch.setattr(shopping, 'buscar_web_v55', lambda *a: ([], []))
    diag = []
    shopping.buscar_com_fallback('Notebook Lenovo', diag=diag)
    shopping.buscar_com_fallback('Notebook Lenovo até 3000', diag=diag)
    assert len(calls) == 1


def test_pdf_uses_existing_safe_reader_and_reports_parser_failure(monkeypatch):
    import source_check
    import docs_agent
    monkeypatch.setattr(source_check, '_baixar_bytes', lambda *a, **k: ('https://docs.example/source.pdf', 200, 'application/pdf', b'%PDF-fixture'))
    def bounded_reader(*args, **kwargs):
        assert kwargs == {'pdf_max_pages': 12, 'pdf_max_chars': research.MAX_TEXTO_PAGINA}
        return 'Python asyncio supports concurrent tasks. ' * 10
    monkeypatch.setattr(docs_agent, 'extrair_texto', bounded_reader)
    result = research._recuperar_um(hit('Python asyncio', 'https://docs.example/source.pdf'), None, 2, 'Python asyncio')
    assert result['lida'] and result['extrator'] == 'pdf'
    def broken(*a, **kwargs):
        raise docs_agent.DocErro('bad PDF', 'pdf_ilegivel')
    monkeypatch.setattr(docs_agent, 'extrair_texto', broken)
    with pytest.raises(research.ResearchErro) as error:
        research._recuperar_um(hit('Python asyncio', 'https://docs.example/source.pdf'), None, 2, 'Python asyncio')
    assert error.value.codigo == 'pdf_ilegivel'


def test_deep_research_bot_wall_never_becomes_evidence(monkeypatch):
    import research_agents as ra
    conn = db()
    ra.criar_tabelas(conn)
    job = ra.criar_job(conn, 'owner', 'Python asyncio')
    monkeypatch.setattr(research, 'baixar', lambda *a, **k: ('https://docs.example/page', '<title>Just a moment...</title><p>Verifying you are human</p>'))
    evidence = ra.agente_analista(conn, job, {'alvo':'Python asyncio'}, [hit('Python asyncio', 'https://docs.example/page')])
    assert evidence == []
    assert ra.listar_evidencias(conn, 'owner', job['id']) == []


def test_stackexchange_does_not_retry_other_sites_after_block(monkeypatch):
    calls = []
    def blocked(*args):
        calls.append(args)
        raise sp.ErroProvedor('HTTP 403', 'bloqueado')
    monkeypatch.setattr(sp, '_json', blocked)
    with pytest.raises(sp.ErroProvedor):
        sp.buscar_stackexchange('python asyncio')
    assert len(calls) == 1


def test_stackexchange_shares_deadline_across_sites(monkeypatch):
    now, calls = [0.0], []
    monkeypatch.setattr(sp.time, 'monotonic', lambda: now[0])
    def empty(url, timeout):
        calls.append(timeout)
        now[0] += 2
        return {'items': []}
    monkeypatch.setattr(sp, '_json', empty)
    with pytest.raises(sp.ErroProvedor):
        sp.buscar_stackexchange('python asyncio', timeout=1)
    assert calls == [1]


def test_rate_limit_has_distinct_provider_diagnostic():
    error = research.ResearchErro('provider rejected', 'bloqueado')
    error.http = 429
    translated = sp._traduzir(error)
    assert translated.codigo == 'bloqueado'
    assert translated.http == 429 and translated.categoria == 'rate_limited'


def test_numeric_relevance_preserves_brazilian_grouping_separator():
    assert orch._tem_termo('3000', 'até R$ 3.000')
    assert orch._tem_termo('3.000', 'até R$ 3000')


def test_existing_ddg_is_available_as_general_fallback(monkeypatch):
    monkeypatch.setattr(research, '_circuito', {})
    expected = [hit('Solid-state batteries', 'https://papers.example/article')]
    monkeypatch.setattr(research, 'buscar_ddg', lambda *a, **k: expected)
    assert sp.buscar('ddg', 'baterias de estado sólido') == expected


def test_unknown_required_ram_is_partial_and_visible_in_existing_card():
    from decimal import Decimal
    product = {'nome':'Notebook Lenovo IdeaPad', 'marca':'Lenovo', 'preco':Decimal('2500.00'),
               'preco_texto':'R$ 2.500,00', 'preco_confirmado':True, 'link_veredito':'verificado', 'specs':{}}
    inside, _ = shopping.aplicar_filtros([product], shopping.extrair_criterios('Notebook Lenovo 16 GB RAM até R$ 3000'))
    assert inside[0]['correspondencia_tipo'] == 'PARTIAL_MATCH'
    card = shopping._jdui_produto(inside[0])
    assert 'RAM física não informada' in card['specs']['Pedido']
    assert product['preco'] == Decimal('2500.00')


def test_scientific_abstract_wins_over_promotional_paragraphs():
    abstract = 'Transformer architecture uses self-attention. ' * 10
    html = '<html><body><main><blockquote class="abstract mathjax">' + abstract + '</blockquote>'
    html += '<div class="labs">' + ('<p>' + 'Community tools for our website. '*20 + '</p>')*6 + '</div></main></body></html>'
    page = web_extract.extrair_pagina(html, consulta='Transformer architecture', usar_trafilatura=False)
    assert page['content_scope'] == 'abstract_only'
    assert 'self-attention' in page['texto'] and 'Community tools' not in page['texto']


def test_read_but_irrelevant_source_never_makes_research_successful():
    result = research.pesquisa_rapida(db(), 'owner', 'Python asyncio',
        buscar_fn=lambda q: [hit('Python asyncio', 'https://source.example/topic')],
        recuperar_fn=lambda url: {'titulo':'A capital do Brasil', 'texto':'Brasília é a capital do Brasil. '*20})
    assert result['fontes'][0]['status'] == 'aberta'
    assert result['fontes_uteis'] == 0 and result['estado'] == 'sem_correspondencia'
    assert research.fontes_relevantes('Python asyncio', result['fontes']) == []
