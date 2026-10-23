"""Failed downloads are job-local and survive ordinary checkpoint/resume."""
import threading

import pytest

import research
import research_agents as ra
from test_research_parallel_reading import research_job, hits, content


@pytest.mark.parametrize('error', [OSError('fixture'), TimeoutError('fixture'),
                                 research.ResearchErro('fixture', 'bloqueado')])
def test_failed_download_is_not_repeated_after_reload(research_job, error):
    db, job = research_job
    def fail(url):
        raise error
    assert ra.agente_analista(db, job, {'alvo': job['objetivo']}, hits('bad'), fail) == []
    ra.salvar_job(db, job)
    resumed = ra.carregar_job(db, job['owner'], job['id'])
    called = []
    def read(url):
        called.append(url)
        return content(url)
    candidates = [{**hits('bad')[0], 'url': 'https://example.com/bad?utm_source=again#top'}] + hits('good')
    evidence = ra.agente_analista(db, resumed, {'alvo': job['objetivo']}, candidates, read, teto_paginas=1)
    assert called == [hits('good')[0]['url']]
    assert len(evidence) == 1 and resumed['usados']['paginas'] == 2
    events = ra.eventos_desde(db, job['owner'], job['id'])
    assert any(e['tipo'] == 'source_failed_read_skipped' for e in events)
    assert 'https://' not in str(resumed['usados']['failed_source_reads'])


def test_irrelevance_can_be_reconsidered_for_another_subquery(research_job):
    db, job = research_job
    assert ra.agente_analista(db, job, {'alvo': job['objetivo']}, hits('topic'),
        lambda url: {'titulo': 'Receita de bolo', 'texto': 'Farinha e ovos.', 'texto_lido': True}) == []
    evidence = ra.agente_analista(db, job, {'alvo': job['objetivo']}, hits('topic'), content)
    assert len(evidence) == 1 and evidence[0]['texto_lido']


def test_cancelled_read_is_retryable(research_job):
    db, job = research_job
    def cancel(url):
        raise research.ResearchErro('fixture', 'cancelada')
    assert ra.agente_analista(db, job, {'alvo': job['objetivo']}, hits('topic'), cancel) == []
    assert ra.agente_analista(db, job, {'alvo': job['objetivo']}, hits('topic'), content)


def test_new_job_and_owner_do_not_inherit_failure_history(research_job):
    db, job = research_job
    def fail(url):
        raise OSError('fixture')
    ra.agente_analista(db, job, {'alvo': job['objetivo']}, hits('topic'), fail)
    ra.salvar_job(db, job)
    another = ra.criar_job(db, 'another-owner', job['objetivo'], manual='pro')
    assert ra.agente_analista(db, another, {'alvo': another['objetivo']}, hits('topic'), content)
    assert another['usados']['paginas'] == 1


def test_skipping_all_failed_sources_does_not_spend_more_pages(research_job):
    db, job = research_job
    def fail(url):
        raise OSError('fixture')
    ra.agente_analista(db, job, {'alvo': job['objetivo']}, hits('bad'), fail)
    assert ra.agente_analista(db, job, {'alvo': job['objetivo']}, hits('bad'),
        lambda url: pytest.fail('already failed')) == []
    assert job['usados']['paginas'] == 1


def test_unexpected_programming_error_is_not_cached_as_network_failure(research_job):
    db, job = research_job
    def fail(url):
        raise RuntimeError('fixture internal error')
    ra.agente_analista(db, job, {'alvo': job['objetivo']}, hits('topic'), fail)
    assert ra.agente_analista(db, job, {'alvo': job['objetivo']}, hits('topic'), content)


def test_cancellation_during_network_error_does_not_poison_history(research_job):
    db, job = research_job
    cancelled = threading.Event()
    def fail(url):
        cancelled.set()
        raise OSError('fixture')
    ra.agente_analista(db, job, {'alvo': job['objetivo']}, hits('topic'), fail,
                      deve_parar=cancelled.is_set)
    assert not job['usados'].get('failed_source_reads')
    assert ra.agente_analista(db, job, {'alvo': job['objetivo']}, hits('topic'), content)
