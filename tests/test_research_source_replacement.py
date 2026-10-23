"""Bounded reading recovery, without model calls or external network."""
import threading
import time

import pytest

import research
import research_agents as ra
from test_research_parallel_reading import research_job, hits, content


@pytest.mark.parametrize('failure', ['blocked', 'network', 'empty', 'irrelevant', 'unread'])
def test_failed_read_is_replaced_by_next_candidate(research_job, failure):
    db, job = research_job
    called = []

    def read(url):
        called.append(url)
        if url.endswith('/bad'):
            if failure == 'blocked':
                raise research.ResearchErro('fixture blocked', 'bloqueado')
            if failure == 'network':
                raise OSError('fixture network')
            if failure == 'empty':
                return {**content(url), 'texto': '', 'texto_lido': False}
            if failure == 'irrelevant':
                return {'titulo': 'Receita de bolo', 'texto': 'Farinha, ovos e açúcar.', 'texto_lido': True}
            return {**content(url), 'texto_lido': False, 'access_state': 'snippet_only'}
        return content(url)

    evidence = ra.agente_analista(db, job, {'alvo': job['objetivo']},
        hits('bad', 'good', 'unused'), read, teto_paginas=1)
    assert called == [h['url'] for h in hits('bad', 'good')]
    assert any(e['url'].endswith('/good') and ra._evidencia_lida(e) for e in evidence)
    assert not any(e['url'].endswith('/bad') and ra._evidencia_lida(e) for e in evidence)
    assert job['usados']['paginas'] == 2
    events = ra.eventos_desde(db, job['owner'], job['id'])
    assert sum(e['tipo'] == 'source_replacement_started' for e in events) == 1
    assert any(e['url'].endswith('/good') for e in ra.listar_evidencias(db, job['owner'], job['id']))


def test_success_needs_no_replacement(research_job):
    db, job = research_job
    called = []
    def read(url):
        called.append(url)
        return content(url)
    evidence = ra.agente_analista(db, job, {'alvo': job['objetivo']},
        hits('good', 'unused'), read, teto_paginas=1)
    assert len(evidence) == 1 and len(called) == 1


def test_replacement_cannot_spend_reserved_or_exhausted_global_budget(research_job):
    db, job = research_job
    job['orcamento']['paginas'] = 2
    job['usados']['paginas'] = 1
    called = []
    def read(url):
        called.append(url)
        raise OSError('fixture')
    assert ra.agente_analista(db, job, {'alvo': job['objetivo']},
        hits('bad', 'unused'), read, teto_paginas=1) == []
    assert len(called) == 1 and job['usados']['paginas'] == 2


def test_replacement_chain_is_bounded(research_job):
    db, job = research_job
    called = []
    def read(url):
        called.append(url)
        raise OSError('fixture')
    assert ra.agente_analista(db, job, {'alvo': job['objetivo']},
        hits('bad', 'also-bad', 'unused'), read, teto_paginas=1) == []
    assert len(called) == 2 and job['usados']['paginas'] == 2


def test_duplicate_urls_do_not_consume_replacement_slot(research_job):
    db, job = research_job
    called = []
    def read(url):
        called.append(url)
        if '/bad' in url:
            raise OSError('fixture')
        return content(url)
    candidates = hits('bad') + [{**hits('bad')[0], 'url': 'https://example.com/bad?utm_source=test#top'}] + hits('good')
    evidence = ra.agente_analista(db, job, {'alvo': job['objetivo']},
        candidates, read, teto_paginas=1)
    assert len(called) == 2 and any(e['url'].endswith('/good') for e in evidence)


def test_cancellation_prevents_replacement(research_job):
    db, job = research_job
    cancelled = threading.Event()
    called = []
    def read(url):
        called.append(url)
        cancelled.set()
        raise OSError('fixture')
    assert ra.agente_analista(db, job, {'alvo': job['objetivo']},
        hits('bad', 'unused'), read, teto_paginas=1, deve_parar=cancelled.is_set) == []
    assert len(called) == 1 and job['usados']['paginas'] == 1


def test_deadline_does_not_start_replacement_or_persist_late_result(research_job):
    db, job = research_job
    release = threading.Event()
    called = []
    def read(url):
        called.append(url)
        release.wait(2)
        return content(url)
    try:
        assert ra.agente_analista(db, job, {'alvo': job['objetivo']},
            hits('slow', 'unused'), read, teto_paginas=1, prazo=time.monotonic() + 0.3) == []
        assert len(called) == 1 and job['usados']['paginas'] == 1
        assert ra.listar_evidencias(db, job['owner'], job['id']) == []
    finally:
        release.set()


def test_malformed_url_is_skipped_without_spending_budget(research_job):
    db, job = research_job
    candidates = [{**hits('bad')[0], 'url': 'https://example.com:invalid/bad'}] + hits('good')
    evidence = ra.agente_analista(db, job, {'alvo': job['objetivo']},
        candidates, content, teto_paginas=1)
    assert len(evidence) == 1 and evidence[0]['url'].endswith('/good')
    assert job['usados']['paginas'] == 1


def test_academic_abstract_keeps_its_scope_without_unnecessary_replacement(research_job):
    db, job = research_job
    abstract = {**hits('abstract')[0], 'metadata_source': 'academic_provider',
                'abstract': content('')['texto'], 'content_scope': 'abstract_only'}
    def read(url):
        pytest.fail('academic abstract does not use custom page reader')
    evidence = ra.agente_analista(db, job, {'alvo': job['objetivo']},
        [abstract] + hits('unused'), read, teto_paginas=1)
    assert len(evidence) == 1 and evidence[0]['content_scope'] == 'abstract_only'
    assert evidence[0]['full_text_fetched'] is False and evidence[0]['texto_lido'] is False
    assert job['usados']['paginas'] == 1
