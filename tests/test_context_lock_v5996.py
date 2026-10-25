"""Context invariants at both planning and the actual provider boundary."""
import json
from pathlib import Path

import pytest
import query_intelligence as qi
import research
import research_agents as ra
import pc_agent

CORPUS = json.loads((Path(__file__).resolve().parents[1] /
                    'benchmarks/context_lock_v5996.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('case', CORPUS, ids=lambda c: c['id'])
def test_planning_preserves_context(case):
    for planner in (research.dividir_subconsultas, ra._subconsultas_unicas):
        queries = planner(case['question'], 4)
        assert queries
        assert len({qi.normalized(q) for q in queries}) == len(queries)
        for query in queries:
            for term in case['required']:
                assert qi.normalized(term) in qi.normalized(query), (query, term)
            for term in case.get('presentation', []):
                assert qi.normalized(term) not in qi.normalized(query)


@pytest.mark.parametrize('case', CORPUS[:6], ids=lambda c: c['id'])
def test_actual_provider_queries_keep_context(case, tmp_path):
    db = pc_agent.open_db(tmp_path / 'qa.sqlite3')
    received = []

    class Provider:
        nome = 'controlled-provider'

        def buscar(self, consulta, limite=6):
            received.append(consulta)
            return []

    try:
        job = ra.criar_job(db, 'qa-context', case['question'], manual='pro')
        ra.montar_plano(db, job)
        for step in job['plano']:
            if step['tipo'] == 'busca':
                ra.agente_busca(db, job, step, [Provider()], set())
        assert received
        for query in received:
            for term in case['required']:
                assert qi.normalized(term) in qi.normalized(query), (query, term)
    finally:
        db.close()


def test_recovery_fragment_uses_same_subject():
    request = qi.analyze('Como usar JavaScript Object.assign, qual a sintaxe e o que retorna?')
    assert 'Object.assign' in qi.constrain_discovery('valor retornado', request)
    assert 'Object.assign' in qi.requirement_query(
        {'entity': 'Object.assign', 'description': 'Valor retornado'}, request['original_request'])


def test_short_original_is_not_rejected():
    assert ra._subconsultas_unicas('Python', 4) == ['Python']


def test_return_relation_does_not_accept_other_methods():
    import evidence_graph as eg
    req = next(r for r in qi.answer_requirements('O que retorna Object.assign?')
               if r['attribute'] == 'return_value')
    assert eg._passage_support(req, {'text': 'Object.assign returns the modified target object.'}, {}) == 'DIRECT_SUPPORT'
    assert eg._passage_support(req, {'text': 'Object.keys returns an array of strings.'}, {}) is None


def test_trace_opt_in_bounded_private_and_nested():
    import retrieval_trace as trace
    source = {'url': 'https://user:password@example.org/private?token=secret'}
    trace.record('private-job', 'step', source, 'SELECTED')
    with trace.observe(limit=2) as rows:
        trace.record('private-job', 'step', source, 'SELECTED', charged=True)
        with trace.observe() as nested:
            trace.record('other-job', 'step', source, 'FETCH_FAILED')
        trace.record('private-job', 'step', source, 'CONTENT_EMPTY')
        trace.record('private-job', 'step', source, 'IGNORED')
    assert len(rows) == 2 and len(nested) == 1
    assert sum(row['slot_charged'] for row in rows) == 1
    assert rows[0]['candidate_ref'] == rows[1]['candidate_ref']
    assert rows[0]['http_status'] is None
    assert not any(word in json.dumps(rows) for word in ('password', 'secret', 'private-job', 'example.org'))


def test_trace_charges_match_real_pipeline_budget():
    import retrieval_trace as trace
    from tools.bench_autonomous_v598 import run
    with trace.observe() as rows:
        result = run(Path(__file__).resolve().parents[1])
    assert sum(row['slot_charged'] for row in rows) == result['read_sources']
    assert any(row['state'] == 'EVIDENCE_STORED' for row in rows)


def test_replan_and_stale_request_do_not_change_subject(tmp_path):
    db = pc_agent.open_db(tmp_path / 'qa.sqlite3')
    try:
        job = ra.criar_job(db, 'qa-owner', 'Como usar Object.assign, qual a sintaxe?', manual='profunda')
        job['ajustes']['request'] = qi.analyze('Quem fundou a WEG?')
        ra.montar_plano(db, job)
        assert job['ajustes']['request']['original_request'] == job['objetivo']
        initial = len(job['plano'])
        ra.replanejar(db, job, ['valor retornado'])
        searches = [s for s in job['plano'][initial:] if s['tipo'] == 'busca']
        assert searches and all('Object.assign' in s['alvo'] for s in searches)
        assert all('WEG' not in s['alvo'] for s in searches)
        assert all('valor retornado' in s['alvo'] for s in searches)
    finally:
        db.close()
