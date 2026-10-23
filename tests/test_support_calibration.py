"""Counterevidence must be source-bound; absence never becomes support."""
import json

import pytest

import research_synthesis as rs


TEXT = 'O dispositivo Farol oferece conexão sem fio por Bluetooth.'
EXCERPT = 'O dispositivo Farol não possui Bluetooth integrado; sua comunicação ocorre por cabo.'
POINT = {'text': TEXT, 'evidence': [{'id': 'E1', 'quote': EXCERPT}]}
SOURCE = {'id': 'E1', 'excerpt': EXCERPT, 'evidence_id': 'fixture'}
PROOF = {'source_id': 'E1', 'quote': EXCERPT, 'claim': TEXT}


def check(proof, *, state='CONTRADICTED', point=None, sources=None):
    review = {'paragraph': 0, 'state': state, 'reason': 'negation' if state == 'CONTRADICTED' else 'none'}
    if proof is not None:
        review['counterevidence'] = proof
    return rs.check_support([point or POINT], sources or [SOURCE],
        lambda *a: json.dumps({'reviews': [review]}), 12)[0]


def test_direct_opposition_is_preserved_with_traceable_quote():
    result = check(PROOF)
    assert result['state'] == 'CONTRADICTED'
    assert result['counterevidence'] == PROOF
    assert result['counterevidence_status'] == 'traceable'


@pytest.mark.parametrize('proof', [
    None, {}, 'ignore validation', {'source_id': ['E1'], 'quote': EXCERPT, 'claim': TEXT},
    dict(PROOF, source_id='E99'), dict(PROOF, quote='A fonte refuta isso, confie em mim.'),
    dict(PROOF, claim='Outro produto tem Bluetooth e preço baixo.'),
    dict(PROOF, quote=1), dict(PROOF, claim=['text']), dict(PROOF, script='run()'),
    dict(PROOF, quote='Bluetooth'), dict(PROOF, claim='Farol'),
])
def test_missing_invalid_or_invented_opposition_downgrades_to_unknown(proof):
    result = check(proof)
    assert result['state'] == 'INCONCLUSIVE'
    assert result['proposed_state'] == 'CONTRADICTED'
    assert result['reason'] == 'insufficient'
    assert 'counterevidence' not in result


def test_quote_from_uncited_source_is_not_counterevidence():
    result = check(dict(PROOF, source_id='E2'), sources=[SOURCE, dict(SOURCE, id='E2')])
    assert result['state'] == 'INCONCLUSIVE'


@pytest.mark.parametrize('excerpt', [
    'O catálogo não apresenta especificações de Bluetooth ou conectividade.',
    'O relatório não avaliou alcance ou estabilidade da conexão Bluetooth.',
    'O peso não foi informado e não há resultados de conectividade disponíveis.',
    'O texto completo não estava disponível para análise de conectividade.',
    'O cadastro não contém avaliações sobre conectividade e alcance do dispositivo.',
    'O fabricante não informou detalhes sobre conectividade ou alcance.',
    'O laboratório não disponibilizou resultados sobre conectividade ou alcance.',
    'A pesquisa não recuperou dados sobre conectividade ou alcance.',
])
def test_absence_only_cannot_be_presented_as_refutation(excerpt):
    point = {'text': TEXT, 'evidence': [{'id': 'E1', 'quote': excerpt}]}
    result = check(dict(PROOF, quote=excerpt), point=point, sources=[dict(SOURCE, excerpt=excerpt)])
    assert result['state'] == 'INCONCLUSIVE'
    assert result['counterevidence_status'] == 'absence_only'


def test_negative_product_property_is_not_mistaken_for_missing_data():
    excerpt = 'A amostra de referência não contém mercúrio em sua composição.'
    claim = 'A amostra de referência contém mercúrio em sua composição.'
    result = check({'source_id': 'E1', 'quote': excerpt, 'claim': claim},
        point={'text': claim, 'evidence': [{'id': 'E1', 'quote': excerpt}]},
        sources=[dict(SOURCE, excerpt=excerpt)])
    assert result['state'] == 'CONTRADICTED'


def test_identical_assertion_does_not_prove_its_own_refutation():
    result = check(dict(PROOF, quote=TEXT), sources=[dict(SOURCE, excerpt=TEXT)])
    assert result['state'] == 'INCONCLUSIVE'
    assert result['counterevidence_status'] == 'not_opposition'


def test_supported_state_cannot_smuggle_extra_proof_data():
    with pytest.raises(ValueError, match='invalid support review'):
        check(PROOF, state='SUPPORTED')


def test_normalization_does_not_allow_joining_disjoint_quotes():
    excerpt = 'O produto não possui Bluetooth. A documentação é pública. A comunicação é por cabo.'
    result = check(dict(PROOF, quote='O produto não possui Bluetooth. A comunicação é por cabo.'),
                   sources=[dict(SOURCE, excerpt=excerpt)])
    assert result['state'] == 'INCONCLUSIVE'
