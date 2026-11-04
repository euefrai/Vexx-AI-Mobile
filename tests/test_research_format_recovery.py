"""Bounded model format recovery never substitutes for evidence validation."""
import json

import pytest

import research_synthesis as synthesis

TEXT = 'A bateria do modelo ZX tem capacidade nominal de 500 ciclos.'
SOURCE = {'id': 'E1', 'evidence_id': 'ev1', 'excerpt': TEXT,
          'scope': 'page_text', 'url': 'https://example.org/specs'}
POINT = {'text': TEXT, 'evidence': [{'id': 'E1', 'quote': TEXT}]}


def approved(messages, timeout):
    payload = json.loads(messages[-1]['content'])
    return json.dumps({'reviews': [{'paragraph': p['paragraph'], 'state': 'SUPPORTED',
                                   'reason': 'none'} for p in payload['paragraphs']]})


def test_one_format_repair_keeps_source_binding():
    calls = []
    def writer(messages, timeout):
        calls.append((messages, timeout))
        return json.dumps({'points': [POINT] * (6 if len(calls) == 1 else 1)})
    result = synthesis.generate('Capacidade da bateria ZX', [SOURCE], [], writer, 40, verify_fn=approved)
    assert result['llm'] and len(calls) == 2
    assert calls[1][1] <= 10
    assert json.loads(calls[1][0][-1]['content']) == json.loads(calls[0][0][-1]['content'])
    assert result['provenance'][0]['quote'] == TEXT
    assert result['format_normalization'] == ['draft_format_repair']


def six_points():
    texts = [f'O ensaio {chr(65+i)} mediu autonomia de {10+i} horas com brilho baixo.' for i in range(6)]
    source = {**SOURCE, 'excerpt':' '.join(texts)}
    points = [{'text':text, 'evidence':[{'id':'E1','quote':text}]} for text in texts]
    return source, points


def test_adjacent_points_are_joined_without_losing_claims_or_review():
    source, points = six_points()
    calls = []
    def writer(messages, timeout):
        calls.append(True)
        return json.dumps({'points':points})
    def reviewer(messages, timeout):
        paragraphs = json.loads(messages[-1]['content'])['paragraphs']
        assert len(paragraphs) == 5
        assert paragraphs[0]['text'] == points[0]['text'] + ' ' + points[1]['text']
        assert len(paragraphs[0]['citations']) == 2
        return approved(messages, timeout)
    result = synthesis.generate('Resultados dos ensaios', [source], [], writer, verify_fn=reviewer)
    assert len(calls) == 1 and len(result['findings']) == 5
    assert all(p['text'] in result['texto'] for p in points)
    assert len(result['provenance']) == 6
    assert [p['paragraph'] for p in result['provenance']] == [0,0,1,2,3,4]
    assert result['format_normalization'] == ['adjacent_paragraphs_joined']


def test_join_cannot_borrow_a_neighbours_number_to_pass_original_quote_gate():
    source, points = six_points()
    points[0]['text'] = points[0]['text'].replace('10 horas', '11 horas')
    def uncalled(*args):
        pytest.fail('Invalid original point cannot reach the reviewer')
    with pytest.raises(ValueError, match='unsupported number'):
        synthesis.generate('Resultados dos ensaios', [source], [],
                           lambda *a: json.dumps({'points':points}), verify_fn=uncalled)


def test_join_does_not_promote_a_rejected_paragraph():
    source, points = six_points()
    def reviewer(messages, timeout):
        payload = json.loads(approved(messages, timeout))
        payload['reviews'][0].update(state='PARTIAL', reason='scope')
        return json.dumps(payload)
    result = synthesis.generate('Resultados dos ensaios', [source], [],
                               lambda *a: json.dumps({'points':points}), verify_fn=reviewer)
    assert points[0]['text'] not in result['texto'] and points[1]['text'] not in result['texto']
    assert len(result['findings']) == 4


@pytest.mark.parametrize('kind', ['disjoint_sources', 'too_long', 'too_many_refs', 'too_many_points'])
def test_unmergeable_draft_still_requires_a_model_repair(kind):
    _, points = six_points()
    if kind == 'disjoint_sources':
        for i,p in enumerate(points):p['evidence'][0]['id'] = 'E'+str(i+1)
    elif kind == 'too_long':
        for p in points:p['text'] = p['text'] + ' contexto' * 50
    elif kind == 'too_many_refs':
        for p in points:p['evidence'] = [dict(p['evidence'][0],quote=p['text']+str(i)) for i in range(3)]
    else:points += points[:3]
    with pytest.raises(ValueError, match='invalid synthesis paragraphs'):
        synthesis._draft_envelope(json.dumps({'points':points}), [])


def test_repair_does_not_publish_invented_numbers():
    calls = []
    def writer(messages, timeout):
        calls.append(timeout)
        point = {**POINT, 'text': TEXT.replace('500', '999')}
        return 'invalid JSON' if len(calls) == 1 else json.dumps({'points': [point]})
    with pytest.raises(ValueError, match='unsupported number'):
        synthesis.generate('Capacidade da bateria ZX', [SOURCE], [], writer, 40, verify_fn=approved)
    assert len(calls) == 2


def test_failed_repair_is_not_retried_forever():
    calls = []
    def writer(messages, timeout):
        calls.append(timeout)
        return 'invalid JSON'
    with pytest.raises(ValueError):
        synthesis.generate('Capacidade da bateria ZX', [SOURCE], [], writer, 40)
    assert len(calls) == 2


@pytest.mark.parametrize('raw', ['', '{}', '[]', 'null'])
def test_empty_candidate_is_not_a_repairable_draft(raw):
    calls = []
    def writer(messages, timeout):
        calls.append(timeout)
        return raw
    with pytest.raises(ValueError):
        synthesis.generate('Capacidade da bateria ZX', [SOURCE], [], writer, 40)
    assert len(calls) == 1


def test_no_repair_after_deadline_or_cancellation(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(synthesis.time, 'monotonic', lambda: clock[0])
    calls = []
    def writer(messages, timeout):
        calls.append(timeout)
        clock[0] = 39
        return 'invalid JSON'
    with pytest.raises(ValueError):
        synthesis.generate('Capacidade da bateria ZX', [SOURCE], [], writer, 40)
    assert len(calls) == 1
    calls.clear()
    assert synthesis.generate('Capacidade da bateria ZX', [SOURCE], [], writer, 40,
                              should_stop=lambda: True) is None
    assert not calls


def test_review_repair_can_reject_previous_claim():
    calls = []
    def review(messages, timeout):
        calls.append(timeout)
        if len(calls) == 1:
            return 'invalid JSON'
        return json.dumps({'reviews': [{'paragraph': 0, 'state': 'INCONCLUSIVE', 'reason': 'insufficient'}]})
    rows = synthesis.check_support([POINT], [SOURCE], review, 12)
    assert len(calls) == 2 and rows[0]['state'] == 'INCONCLUSIVE'


@pytest.mark.parametrize('reason', ['model_truncated', 'model_filtered'])
@pytest.mark.parametrize('repair', [False, True])
def test_review_preserves_safe_transport_reason(reason, repair):
    calls = []
    def review(messages, timeout):
        calls.append(timeout)
        if repair and len(calls) == 1:
            return 'invalid JSON'
        raise synthesis.ModelOutputError(reason)
    with pytest.raises(synthesis.ReviewUnavailableError) as exc:
        synthesis.check_support([POINT], [SOURCE], review, 12)
    assert exc.value.cause == reason
    assert exc.value.provider_code is None
    assert len(calls) == (2 if repair else 1)
