"""Coverage follows published paragraphs, without erasing rejected candidates."""
import copy
import json

import pytest

import pc_agent
import research_agents as agents


@pytest.fixture
def completed_answer(tmp_path):
    db = pc_agent.open_db(tmp_path / 'coverage.sqlite')
    query = 'Quem fundou Atlas, em que ano foi fundada e quais produtos fabrica?'
    job = agents.criar_job(db, 'qa', query)
    facts = ['Atlas foi fundada em 1981 por Rita Silva.', 'Atlas fabrica motores elétricos.']
    ev = {'id': 'ev-atlas', 'titulo': 'Atlas', 'dominio': 'example.org', 'url': 'https://example.org/atlas',
          'texto_lido': True, 'trecho': ' '.join(facts), 'score': 1}
    def writer(*args):
        return json.dumps({'points': [
            {'text': facts[0], 'evidence': [{'id': 'E1', 'quote': facts[0]}]},
            {'text': 'Atlas fabrica brinquedos para crianças.', 'evidence': [{'id': 'E1', 'quote': facts[1]}]},
            {'text': facts[1], 'evidence': [{'id': 'E1', 'quote': facts[1]}]},
        ]})
    def reviewer(*args):
        return json.dumps({'reviews': [
            {'paragraph': 0, 'state': 'SUPPORTED', 'reason': 'none'},
            {'paragraph': 1, 'state': 'PARTIAL', 'reason': 'scope'},
            {'paragraph': 2, 'state': 'SUPPORTED', 'reason': 'none'},
        ]})
    result = agents.agente_sintetizador(db, job, [ev], [], writer, verificar_fn=reviewer)
    db.close()
    assert result['llm'] and result['answer_coverage']['complete']
    job['sintese'] = result
    job['pendencias'] = ['Preliminary extraction was incomplete']
    job['achados'] = [{'afirmacao': query, 'estado': 'UNVERIFIED'}]
    return job, ev


def test_omitted_paragraph_does_not_make_complete_published_answer_partial(completed_answer):
    job, ev = completed_answer
    result = job['sintese']
    assert len(result['semantic_review']) == 3 and len(result['findings']) == 2
    assert 'brinquedos' not in result['texto']
    assert {p['original_paragraph'] for p in result['provenance']} == {0, 2}
    outcome = agents._completion_outcome(job, [ev], ['old gap'], True)
    assert outcome['state'] == 'complete' and outcome['unresolved_fronts'] == []


@pytest.mark.parametrize('fault', ['missing_provenance', 'wrong_original', 'duplicate_review',
                                 'unpublished_supported', 'incomplete_coverage', 'unread_source'])
def test_missing_or_inconsistent_publication_support_stays_partial(completed_answer, fault):
    job, ev = copy.deepcopy(completed_answer)
    result = job['sintese']
    if fault == 'missing_provenance': result['provenance'].pop()
    elif fault == 'wrong_original': result['provenance'][-1]['original_paragraph'] = 1
    elif fault == 'duplicate_review': result['semantic_review'].append(result['semantic_review'][0])
    elif fault == 'unpublished_supported': result['semantic_review'][1]['state'] = 'SUPPORTED'
    elif fault == 'incomplete_coverage': result['answer_coverage']['complete'] = False
    elif fault == 'unread_source': ev['texto_lido'] = False
    assert agents._completion_outcome(job, [ev], ['old gap'], True)['state'] == 'partial'
