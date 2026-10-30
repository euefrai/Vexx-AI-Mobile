"""A failed discovery must not become a six-hour terminal shopping answer."""
import json

import pytest

import pc_agent
import shopping


@pytest.fixture
def db(tmp_path):
    connection = pc_agent.open_db(tmp_path / 'negative-shopping-cache.sqlite')
    yield connection
    connection.close()


def offer(**updates):
    product = {'nome': 'Produto de teste', 'preco': 1299.99, 'preco_confirmado': True,
               'url': 'https://example.org/produto/1', 'link_veredito': 'verificado'}
    product.update(updates)
    return product


def save(db, result, conv='original', criteria=None):
    result = {'produtos': [], 'alternativas': [], 'criterios': criteria or {}, **result}
    shopping.salvar_consulta(db, 'qa', conv, 'celular samsung', criteria or {}, result)
    return result


@pytest.mark.parametrize('result', [
    {},
    {'erro': 'provedor_indisponivel'},
    {'encontrados': [{'nome': 'Referência', 'url': 'https://example.org/produto/1'}]},
    {'produtos': [offer(preco_confirmado=False)]},
    {'produtos': [offer(preco=0)]},
    {'produtos': [offer(preco=-10)]},
    {'produtos': [offer(preco=float('nan'))]},
    {'produtos': [offer(preco=float('inf'))]},
    {'alternativas': [offer(preco_confirmado=False)]},
    {'produtos': [offer()], 'erro': 'provedor_indisponivel'},
])
def test_empty_references_errors_and_unconfirmed_prices_do_not_serve_cache(db, result):
    save(db, result)
    assert shopping.consulta_em_cache(db, 'qa', 'celular samsung') is None
    # Failure evidence/history remains available; no data cleanup or deletion.
    assert shopping.ultima_consulta(db, 'qa', 'original') is not None


def test_legacy_empty_row_allows_a_new_discovery_every_time(db, monkeypatch):
    query = 'celular Samsung'
    criteria = shopping.extrair_criterios(query)
    key = (criteria['categoria'] + ' ' + ' '.join(criteria['marcas'])).strip()
    # Reproduce a row written by the old release, still valid far into the future.
    shopping.salvar_consulta(db, 'qa', 'old-chat', key, criteria,
                            {'produtos': [], 'alternativas': [], 'criterios': criteria},
                            expira_em='2999-01-01T00:00:00+00:00')
    calls = []
    def empty_search(query, **kwargs):
        calls.append(query)
        return [], ['controlled empty discovery']
    monkeypatch.setattr(shopping, 'buscar_com_fallback', empty_search)
    first = shopping.pesquisar(db, 'qa', query, 'new-chat')
    assert calls and first['de_cache'] is False
    count = len(calls)
    second = shopping.pesquisar(db, 'qa', query, 'new-chat')
    assert len(calls) > count and second['de_cache'] is False
    assert shopping.ultima_consulta(db, 'qa', 'old-chat')['expira_em'].startswith('2999-')


@pytest.mark.parametrize('updates', [{}, {'link_veredito': 'nao_verificado'}])
def test_positive_declared_prices_preserve_existing_historical_cache_contract(db, updates):
    verified_at = '2026-10-29T08:00:00+00:00'
    save(db, {'produtos': [offer(**updates)], 'verificado_em': verified_at})
    before = shopping.ultima_consulta(db, 'qa', 'original')
    cached = shopping.consulta_em_cache(db, 'qa', 'celular samsung')
    assert cached and cached['de_cache'] is True
    assert cached['verificado_em'] == verified_at
    assert cached['cache_expira_em'] == before['expira_em']
    after = shopping.ultima_consulta(db, 'qa', 'original')
    assert after['expira_em'] == before['expira_em']
    assert json.dumps(after['resultado'], sort_keys=True) == json.dumps(before['resultado'], sort_keys=True)
    assert shopping.consulta_em_cache(db, 'other-owner', 'celular samsung') is None
    assert shopping.ultima_consulta(db, 'qa', 'other-chat') is None


def test_criteria_mismatch_and_expired_declared_price_still_reject_cache(db):
    save(db, {'produtos': [offer()], 'criterios': {'categoria': 'celular'}}, criteria={'categoria': 'celular'})
    assert shopping.consulta_em_cache(db, 'qa', 'celular samsung', {'categoria': 'notebook'}) is None
    db.execute('UPDATE shopping_consultas SET resultado=?',
               (json.dumps({'produtos': [offer(preco_valido_ate='2000-01-01')], 'criterios': {}}),))
    db.commit()
    assert shopping.consulta_em_cache(db, 'qa', 'celular samsung') is None


def test_legacy_numeric_price_without_flag_stays_partial_and_historical(db):
    product=offer();product.pop('preco_confirmado');product['link_veredito']='nao_verificado'
    save(db, {'produtos':[product]})
    result=shopping.consulta_em_cache(db, 'qa', 'celular samsung')
    assert result and result['de_cache']
    assert 'preco_confirmado' not in result['produtos'][0]
    assert shopping._tier(result['produtos'][0])=='parcial'
