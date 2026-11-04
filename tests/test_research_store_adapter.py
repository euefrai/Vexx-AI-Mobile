"""Deep discovery reuses the public store adapter without declaring offers read."""
import pytest

import research
import search_orchestrator as orchestrator
import search_providers as providers
import store_discovery
import pc_agent
import research_agents as agents


def test_native_catalog_precedes_general_index_only_for_shopping(monkeypatch):
    monkeypatch.setenv('JULIA_NATIVE_STORE_SEARCH', '1')
    query = 'Placa de video RTX 3050 6GB preco para comprar no Brasil'
    info = orchestrator.classificar(query)
    assert info['produto']
    assert orchestrator._escolher_provedores(info['classes'], info,
        ['kabum', 'bing', 'ddg'])[0] == 'kabum'
    other = orchestrator.classificar('Historia da filosofia')
    assert 'kabum' not in orchestrator._escolher_provedores(other['classes'], other,
        ['kabum', 'bing', 'ddg'])


@pytest.mark.parametrize('model,capacity,eligible', [('3050', 6, True), ('3050', 8, False), ('4060', 6, False)])
def test_price_and_link_instructions_do_not_hide_exact_product_or_admit_wrong_variant(model, capacity, eligible):
    query = 'por uma placa de video RTX 3050 de 6 GB a venda no Brasil. Quero preco atual e link direto do produto'
    row = {'titulo': f'Placa de Video GeForce RTX {model} {capacity}GB GDDR6',
           'url': 'https://www.kabum.com.br/produto/123/gpu', 'trecho': 'Descricao da placa de video.'}
    terms = orchestrator._termos_correspondencia(query)
    assert not {'atual', 'link', 'direto', 'produto'} & set(terms)
    assert '3050' in terms
    assert orchestrator._util_para_pedido(row, terms, query) is eligible


def test_native_discovery_is_optional_and_keeps_timeout_and_direct_url(monkeypatch):
    calls = []
    row = {'url': 'https://www.kabum.com.br/produto/123/test', 'titulo': 'Placa RTX 3050 6GB'}
    def native(query, limit, timeout):
        calls.append((query, limit, timeout))
        return [dict(row)]
    monkeypatch.setattr(store_discovery, 'search_kabum', native)
    monkeypatch.setattr(research, '_circuito_fechado', lambda _: False)
    assert 'kabum' not in providers.disponiveis()
    with pytest.raises(providers.ErroProvedor): providers.buscar('kabum', 'RTX 3050')
    assert not calls
    monkeypatch.setenv('JULIA_NATIVE_STORE_SEARCH', '1')
    results = providers.buscar('kabum', 'RTX 3050', limite=3, timeout=1.5)
    assert calls == [('RTX 3050', 3, 1.5)]
    assert results[0]['url'] == row['url']
    assert not results[0].get('texto_lido') and 'price' not in results[0]


def test_native_failure_remains_failure_not_fake_product(monkeypatch):
    monkeypatch.setenv('JULIA_NATIVE_STORE_SEARCH', '1')
    monkeypatch.setattr(research, '_circuito_fechado', lambda _: False)
    def blocked(*args, **kwargs):
        raise research.ResearchErro('blocked fixture', 'bloqueado')
    monkeypatch.setattr(store_discovery, 'search_kabum', blocked)
    with pytest.raises(providers.ErroProvedor) as exc:
        providers.buscar('kabum', 'RTX 3050')
    assert exc.value.codigo == 'bloqueado'


def test_deep_shopping_reaches_orchestrator_before_general_candidates(tmp_path, monkeypatch):
    db = pc_agent.open_db(tmp_path / 'shop.sqlite')
    try:
        query = 'RTX 3050 6GB preco para comprar no Brasil'
        job = agents.criar_job(db, 'qa', query)
        seen = []
        web = agents.ProvedorOrquestrado()
        class General:
            nome = 'general'
            def buscar(self, *args):
                pytest.fail('General index must not hide the specialized shopping path')
        def search(*args):
            seen.append('web')
            return [{'titulo': 'RTX 3050 6GB preco no Brasil', 'trecho': 'Placa de video',
                     'url': 'https://www.kabum.com.br/produto/123/rtx-3050-6gb'}]
        monkeypatch.setattr(web, 'buscar', search)
        results = agents.agente_busca(db, job, {'id': 'qa-step', 'alvo': query}, [General(), web], set())
        assert seen == ['web'] and results
    finally:
        db.close()
