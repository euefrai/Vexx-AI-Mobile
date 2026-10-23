"""Real worker threads with controlled readers; no external network or inference."""
import threading
import time

import pytest

import pc_agent
import research_agents as ra


@pytest.fixture
def research_job(tmp_path):
    db = pc_agent.open_db(tmp_path / 'reading.sqlite')
    job = ra.criar_job(db, 'qa-reading', 'Bateria ZX capacidade nominal', manual='pro')
    yield db, job
    db.close()


def hits(*names):
    return [{'id': name, 'titulo': 'Bateria ZX',
             'url': f'https://example.com/{name}', 'trecho': 'Bateria ZX'}
            for name in names]


def content(url):
    return {'titulo': 'Bateria ZX', 'texto': 'Bateria ZX capacidade nominal de 500 ciclos.',
            'final': url, 'texto_lido': True}


def test_deadline_keeps_completed_page_behind_stalled_first_source(research_job):
    db, job = research_job
    release = threading.Event()
    finished = threading.Event()
    slow_finished = threading.Event()

    def read(url):
        if url.endswith('/slow'):
            release.wait(2)
            slow_finished.set()
        else:
            finished.set()
        return content(url)

    started = time.monotonic()
    try:
        evidence = ra.agente_analista(db, job, {'alvo': job['objetivo']},
            hits('slow', 'fast'), read, prazo=started + 0.5)
        assert finished.is_set()
        assert [e['url'] for e in evidence] == ['https://example.com/fast']
        assert time.monotonic() - started < 1.5
        persisted = ra.listar_evidencias(db, job['owner'], job['id'])
        assert len(persisted) == 1 and persisted[0]['texto_lido'] is True
        assert job['usados']['paginas'] == 2
        release.set()
        assert slow_finished.wait(1)
        assert len(ra.listar_evidencias(db, job['owner'], job['id'])) == 1
        reused = ra.agente_analista(db, job, {'alvo': job['objetivo']}, hits('fast'),
                                   lambda url: pytest.fail('already read'))
        assert reused[0]['id'] == evidence[0]['id']
        assert job['usados']['paginas'] == 2
    finally:
        release.set()


def test_cancellation_does_not_wait_for_blocked_reader(research_job):
    db, job = research_job
    release = threading.Event()
    cancel = threading.Event()
    started_reading = threading.Event()
    timer = threading.Timer(0.2, cancel.set)

    def read(url):
        started_reading.set()
        timer.start()
        release.wait(2)
        return content(url)

    started = time.monotonic()
    try:
        assert ra.agente_analista(db, job, {'alvo': job['objetivo']},
            hits('slow'), read, deve_parar=cancel.is_set) == []
        assert started_reading.is_set() and cancel.is_set()
        assert time.monotonic() - started < 1.5
        assert ra.listar_evidencias(db, job['owner'], job['id']) == []
    finally:
        release.set()
        timer.cancel()


def test_success_preserves_search_order_not_thread_completion_order(research_job):
    db, job = research_job
    second_finished = threading.Event()

    def read(url):
        if url.endswith('/first'):
            assert second_finished.wait(1)
        else:
            second_finished.set()
        return content(url)

    evidence = ra.agente_analista(db, job, {'alvo': job['objetivo']},
        hits('first', 'second'), read)
    assert [e['url'] for e in evidence] == [h['url'] for h in hits('first', 'second')]
    assert job['usados']['paginas'] == 2


def test_expired_deadline_does_not_spend_page_budget(research_job):
    db, job = research_job
    evidence = ra.agente_analista(db, job, {'alvo': job['objetivo']},
        hits('unused'), lambda url: pytest.fail('expired read'), prazo=time.monotonic() - 1)
    assert evidence == []
    assert job['usados']['paginas'] == 0


def test_failure_does_not_hide_success_and_budget_still_caps_downloads(research_job):
    db, job = research_job
    job['orcamento']['paginas'] = 2
    called = []

    def read(url):
        called.append(url)
        if url.endswith('/broken'):
            raise OSError('fixture failure')
        return content(url)

    evidence = ra.agente_analista(db, job, {'alvo': job['objetivo']},
        hits('broken', 'good', 'over-budget'), read)
    assert len(evidence) == 1 and evidence[0]['url'].endswith('/good')
    assert len(called) == 2 and job['usados']['paginas'] == 2


def test_unread_result_never_becomes_read_evidence(research_job):
    db, job = research_job
    evidence = ra.agente_analista(db, job, {'alvo': job['objetivo']}, hits('snippet'),
        lambda url: {**content(url), 'texto_lido': False, 'access_state': 'snippet_only'})
    assert len(evidence) == 1 and evidence[0]['texto_lido'] is False
    assert all(v['estado'] not in ('SUPPORTED', 'CONTRADICTED')
               for v in ra.agente_verificador(db, job, evidence))
