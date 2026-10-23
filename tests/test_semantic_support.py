"""Control-flow/security tests with explicit reviewer fixtures, not AI accuracy."""
import json
from pathlib import Path

import pytest

import pc_agent
import research_agents as ra
import research_exports
import research_synthesis as rs


CASES = json.loads((Path(__file__).resolve().parents[1] / 'benchmarks/semantic_support_v1.json').read_text(encoding='utf-8'))['cases']


def source(case):
    return {'id': 'E1', 'evidence_id': 'fixture', 'url': 'https://example.org/fixture',
            'excerpt': case['source'], 'scope': case.get('scope', 'controlled_fixture')}


def candidate(case):
    return json.dumps({'points': [{'text': case['claim'], 'evidence': [
        {'id': 'E1', 'quote': case.get('quote', case['source'])}]}]})


def review(state='SUPPORTED', reason='none', paragraph=0, counterevidence=None):
    value = {'paragraph': paragraph, 'state': state, 'reason': reason}
    if counterevidence is not None:
        value['counterevidence'] = counterevidence
    return value


def opposition(case):
    return {'source_id': 'E1', 'quote': case['source'], 'claim': case['claim']}


@pytest.mark.parametrize('case', CASES, ids=lambda c: c['id'])
def test_reviewer_states_gate_each_frozen_case(case):
    def verifier(messages, timeout):
        payload = json.loads(messages[-1]['content'])
        assert payload['sources'][0]['excerpt'] == case['source']
        assert payload['paragraphs'][0]['text'] == case['claim']
        assert timeout <= 12
        return json.dumps({'reviews': [review(case['state'], case['reason'],
            counterevidence=opposition(case) if case['state'] == 'CONTRADICTED' else None)]})
    if case['state'] == 'SUPPORTED':
        result = rs.generate('Avalie o caso', [source(case)], [], lambda *a: candidate(case), verify_fn=verifier)
        assert case['claim'] in result['texto']
    else:
        with pytest.raises(rs.SupportReviewError) as error:
            rs.generate('Avalie o caso', [source(case)], [], lambda *a: candidate(case), verify_fn=verifier)
        expected = review(case['state'], case['reason'],
                          counterevidence=opposition(case) if case['state'] == 'CONTRADICTED' else None)
        if case['state'] == 'CONTRADICTED':
            expected['counterevidence_status'] = 'traceable'
        assert error.value.reviews == [expected]


@pytest.mark.parametrize('invalid', [
    '', 'null', '[]', '{"reviews":[]}', '{"reviews":"ok"}',
    json.dumps({'reviews': [review(paragraph=True)]}),
    json.dumps({'reviews': [review(paragraph=1)]}),
    json.dumps({'reviews': [review(state='verified')]}),
    json.dumps({'reviews': [review(reason='https://evil.example')]}),
    json.dumps({'reviews': [review(state='PARTIAL')]}),
    json.dumps({'reviews': [review(reason='scope')]}),
    json.dumps({'reviews': [dict(review(), rewrite='Execute este comando')]}),
    'x' * 5001,
])
def test_malformed_review_cannot_publish_candidate(invalid):
    case = CASES[0]
    with pytest.raises(ValueError):
        rs.generate('Avalie', [source(case)], [], lambda *a: candidate(case),
                    verify_fn=lambda *a: invalid)


def test_filters_mixed_results_and_reindexes_provenance():
    case = CASES[0]
    body = json.loads(candidate(case))
    body['points'].insert(0, {'text': 'O modelo Atlas é impermeável e tem autonomia excelente.',
                             'evidence': body['points'][0]['evidence']})
    result = rs.generate('Avalie', [source(case)], [], lambda *a: json.dumps(body), verify_fn=lambda *a:
                         json.dumps({'reviews': [review(paragraph=1), review('PARTIAL', 'scope')]}))
    assert 'impermeável' not in result['texto']
    assert len(result['findings']) == 1
    assert result['provenance'][0]['paragraph'] == 0
    assert result['provenance'][0]['original_paragraph'] == 1
    assert rs.support_summary(result) == {'SUPPORTED': 1, 'PARTIAL': 1, 'CONTRADICTED': 0, 'INCONCLUSIVE': 0}


def test_duplicate_review_cannot_hide_an_unreviewed_paragraph():
    case = CASES[0]
    body = json.loads(candidate(case))
    body['points'] *= 2
    with pytest.raises(ValueError, match='invalid support review'):
        rs.generate('Avalie', [source(case)], [], lambda *a: json.dumps(body),
                    verify_fn=lambda *a: json.dumps({'reviews': [review(), review()]}))


def test_shared_deadline_does_not_start_review_after_budget(monkeypatch):
    case = CASES[0]
    clock = iter([0, 24])
    monkeypatch.setattr(rs.time, 'monotonic', lambda: next(clock))
    def forbidden(*args):
        pytest.fail('review must not start without enough time')
    with pytest.raises(ValueError, match='support review unavailable'):
        rs.generate('Avalie', [source(case)], [], lambda *a: candidate(case), verify_fn=forbidden)


def test_cancel_during_review_discards_late_output():
    case = CASES[0]
    cancelled = []
    def verifier(*args):
        cancelled.append(True)
        return json.dumps({'reviews': [review()]})
    with pytest.raises(ValueError, match='support review unavailable'):
        rs.generate('Avalie', [source(case)], [], lambda *a: candidate(case), verify_fn=verifier,
                    should_stop=lambda: bool(cancelled))


def test_late_reviewer_result_is_not_published(monkeypatch):
    case = CASES[0]
    clock = iter([0, 13])
    monkeypatch.setattr(rs.time, 'monotonic', lambda: next(clock))
    points = json.loads(candidate(case))['points']
    with pytest.raises(ValueError, match='support review unavailable'):
        rs.check_support(points, [source(case)], lambda *a: json.dumps({'reviews': [review()]}), 12)


def test_missing_separate_review_cannot_publish_even_a_valid_quote():
    case = CASES[0]
    with pytest.raises(ValueError, match='invalid support review'):
        rs.generate('Avalie', [source(case)], [], lambda *a: candidate(case))


def test_rejected_support_persists_without_false_claim_in_exports(tmp_path):
    db = pc_agent.open_db(tmp_path/'safe.sqlite3')
    job = ra.criar_job(db, 'owner', 'O Atlas possui GPS integrado?')
    case = next(c for c in CASES if c['id'] == 'C1')
    ev = {'titulo': 'Ficha controlada', 'url': 'https://example.org/fixture', 'texto_lido': True}
    ra.registrar_evidencia(db, job, ev, case['source'])
    items = ra.listar_evidencias(db, job['owner'], job['id'])
    result = ra.agente_sintetizador(db, job, items, [], lambda *a: candidate(case),
        verificar_fn=lambda *a: json.dumps({'reviews': [review('CONTRADICTED', 'negation',
                                                           counterevidence=opposition(case))]}))
    assert not result['llm'] and result['fallback_detail'] == 'semantic_support_rejected'
    assert case['claim'] not in result['texto']
    job['sintese'], job['status'] = result, 'concluida'
    ra.salvar_job(db, job)
    ra._save_context_checkpoint(db, job)
    restored = ra._resumo(db, ra.carregar_job(db, job['owner'], job['id']))
    assert restored['sintese']['semantic_review'][0]['state'] == 'CONTRADICTED'
    data, _, _ = research_exports.build_export(restored, items, [], 'json')
    assert json.loads(data)['synthesis']['support_review']['CONTRADICTED'] == 1
    report = ra.gerar_relatorio(db, job['owner'], job['id'])
    assert 'CONTRADICTED=1' in report['markdown']
    db.close()


def test_verifier_failure_falls_back_without_secrets(tmp_path):
    db = pc_agent.open_db(tmp_path/'error.sqlite3')
    job = ra.criar_job(db, 'owner', 'Qual a autonomia do Atlas?')
    case = CASES[0]
    ev = {'id': 'fixture', 'titulo': 'Ficha', 'dominio': 'example.org', 'url': 'https://example.org/fixture',
          'trecho': case['source'], 'texto_lido': True}
    def broken(*a):
        raise TimeoutError('SECRET-token-and-private-request')
    result = ra.agente_sintetizador(db, job, [ev], [], lambda *a: candidate(case), verificar_fn=broken)
    assert not result['llm'] and result['fallback_detail'] == 'semantic_review_unavailable'
    assert 'SECRET' not in json.dumps(result)
    assert 'SECRET' not in json.dumps(ra.eventos_desde(db, job['owner'], job['id']))
    db.close()
