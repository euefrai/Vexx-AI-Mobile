"""Preserve root categories without exposing provider messages or relaxing support."""
import json
import urllib.error

import pytest

import hermes_bridge
import pc_agent
import research_agents as ra
import research_synthesis as rs


EXCERPT = 'O medidor usa pilhas. Não informa resistência a quedas ou impactos.'
CLAIM = 'O medidor usa pilhas e resiste a quedas.'
POINTS = [{'text': CLAIM, 'evidence': [{'id': 'E1', 'quote': EXCERPT}]}]
SOURCES = [{'id': 'E1', 'excerpt': EXCERPT}]


def flat(state='PARTIAL', **kwargs):
    return dict(paragraph=0, state=state, reason='scope', quote=EXCERPT, claim=CLAIM, **kwargs)


def check(body, sources=None):
    return rs.check_support(POINTS, sources or SOURCES, lambda *a: json.dumps({'reviews': [body]}), 12)


@pytest.mark.parametrize('state', ['PARTIAL', 'INCONCLUSIVE'])
def test_source_bound_flat_annotations_preserve_non_publishing_state(state):
    result = check(flat(state))[0]
    assert result == {'paragraph': 0, 'state': state, 'reason': 'scope'}


@pytest.mark.parametrize('body', [
    flat('SUPPORTED'), flat('CONTRADICTED'), flat('CONTRADIICTED'),
    dict(flat(), quote='O modelo inventou esta citação inexistente.'),
    dict(flat(), claim='Uma afirmação diferente não citada no parágrafo.'),
    dict(flat(), paragraph=True), dict(flat(), quote=['text']),
    dict(flat(), claim={'text': CLAIM}), dict(flat(), run='execute()'),
    {'paragraph': 0, 'state': 'PARTIAL', 'reason': 'scope', 'quote': EXCERPT},
])
def test_normalization_does_not_salvage_unknown_states_or_unbound_data(body):
    with pytest.raises(ValueError, match='invalid support review'):
        check(body)


def test_flat_annotation_cannot_bind_to_uncited_source():
    with pytest.raises(ValueError):
        check(flat(), sources=[{'id': 'E2', 'excerpt': EXCERPT}])


@pytest.mark.parametrize('code', ['vazia', 'formato', 'indisponivel', 'rate_limit', 'protocolo_ferramenta', 'auth'])
def test_provider_code_survives_review_and_persistence_without_secret(tmp_path, code):
    def broken(*args):
        raise hermes_bridge.BridgeErro('SECRET-request-and-key', code)
    with pytest.raises(rs.ReviewUnavailableError) as error:
        rs.check_support(POINTS, SOURCES, broken, 12)
    assert error.value.cause == 'provider_error' and error.value.provider_code == code
    db = pc_agent.open_db(tmp_path/'qa.sqlite3')
    job = ra.criar_job(db, 'owner', 'Qual a alimentação do medidor?')
    ev = {'id': 'fixture', 'titulo': 'Ficha sintética', 'dominio': 'example.org', 'url': 'https://example.org/',
          'trecho': EXCERPT, 'texto_lido': True}
    candidate = json.dumps({'points': [{'text': 'O medidor utiliza alimentação por pilhas.',
                                       'evidence': [{'id': 'E1', 'quote': EXCERPT}]}]})
    result = ra.agente_sintetizador(db, job, [ev], [], lambda *a: candidate, verificar_fn=broken)
    assert result['fallback_provider_code'] == code
    assert result['review_failure_cause'] == 'provider_error'
    assert result['llm'] is False
    assert 'SECRET' not in json.dumps(result)
    assert 'SECRET' not in json.dumps(ra.eventos_desde(db, job['owner'], job['id']))
    db.close()


def test_unrecognized_provider_code_and_exception_text_are_not_persisted():
    assert rs.safe_provider_code(hermes_bridge.BridgeErro('SECRET', 'SECRET-code')) == 'unknown'
    error = rs.ReviewUnavailableError('SECRET', 'SECRET-code')
    assert error.cause == 'provider_error' and error.provider_code is None


def test_budget_and_cancel_are_distinct_from_provider_failure():
    def forbidden(*a):
        pytest.fail('must not call the provider')
    with pytest.raises(rs.ReviewUnavailableError) as budget:
        rs.check_support(POINTS, SOURCES, forbidden, 1)
    assert budget.value.cause == 'time_budget'
    with pytest.raises(rs.ReviewUnavailableError) as cancelled:
        rs.check_support(POINTS, SOURCES, forbidden, 12, lambda: True)
    assert cancelled.value.cause == 'cancelled'


@pytest.mark.parametrize('failure,expected', [
    (TimeoutError('private-host'), 'timeout'),
    (urllib.error.URLError(TimeoutError('private-host')), 'timeout'),
    (urllib.error.URLError(OSError('private-host')), 'indisponivel'),
])
def test_bridge_distinguishes_network_from_timeout(monkeypatch, failure, expected):
    def broken(*a, **kw):
        raise failure
    monkeypatch.setattr(hermes_bridge.urllib.request, 'urlopen', broken)
    with pytest.raises(hermes_bridge.BridgeErro) as error:
        hermes_bridge.chat_complete('http://127.0.0.1:8645/v1', 'fixture', [], timeout=2)
    assert error.value.codigo == expected
