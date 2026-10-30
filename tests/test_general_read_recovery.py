"""Offline pipeline recovery after plausible search metadata leads to failed reads."""
import sqlite3
from urllib.parse import urlsplit

import pytest

import research
import search_orchestrator as orch
import search_providers as sp


def hits(host, count=3):
    return [{'url': f'https://{host}/{i}', 'titulo': f'Photosynthesis {i}',
             'trecho': 'Photosynthesis converts light into chemical energy in plants.',
             'origem': 'bing', 'tipo': 'pagina'} for i in range(count)]


@pytest.fixture
def db(monkeypatch):
    conn = sqlite3.connect(':memory:')
    research.criar_tabelas(conn)
    monkeypatch.setattr(orch, 'fontes_preferenciais', lambda _: [])
    monkeypatch.setattr(orch, '_escolher_provedores', lambda *args: ['bing', 'marginalia'])
    # Every test must install its own offline discovery. Any accidental network fails.
    monkeypatch.setattr(sp, 'buscar', lambda *a, **kw: pytest.fail('Unmocked discovery'))
    monkeypatch.setattr(research, '_abrir', lambda *a, **kw: pytest.fail('Network attempted'))
    yield conn
    conn.close()


def good_read(url):
    return {'titulo': 'Photosynthesis', 'texto': 'Photosynthesis converts light into chemical energy in plants. '*8,
            'final': url, 'lida': True}


@pytest.mark.parametrize('failure', ['blocked', 'irrelevant', 'empty'])
def test_native_recovery_reads_independent_sources_and_caches_final_evidence(db, monkeypatch, failure):
    calls, reads = [], []
    def discover(provider, query, **kwargs):
        calls.append((provider, query))
        return hits('failed.example' if provider == 'bing' else 'independent.example')
    def read(url):
        reads.append(url)
        if 'failed.example' in url:
            if failure == 'blocked':
                raise research.ResearchErro('Access denied', 'bloqueado')
            if failure == 'empty':
                return {'texto': '', 'lida': False}
            return {'titulo': 'Brasilia', 'texto': 'Brasilia is the capital of Brazil. '*10}
        return good_read(url)
    monkeypatch.setattr(sp, 'buscar', discover)
    result = research.pesquisa_rapida(db, 'qa', 'photosynthesis', recuperar_fn=read)
    assert [p for p, _ in calls] == ['bing', 'marginalia']
    assert len(reads) == len(set(reads)) == 6
    assert result['fontes_uteis'] == 3 and result['estado'] == 'ok'
    assert [f['id'] for f in result['fontes']] == ['S1', 'S2', 'S3']
    assert all(f['status'] == 'aberta' and 'independent.example' in f['url'] for f in result['fontes'])
    trace = result['read_recovery']
    assert trace['executed'] and trace['initial_useful_reads'] == 0
    assert trace['attempts'] == 1 and trace['new_candidates'] == trace['useful_reads'] == 3
    assert set(trace['read_urls']) == set(reads[3:]) and trace['total_reads'] == 6
    assert trace['seconds'] >= 0 and trace['origin'] == 'post_read'
    cached = research.pesquisa_rapida(db, 'qa', 'photosynthesis', recuperar_fn=lambda _: pytest.fail('Cache missed'))
    assert cached['de_cache'] and cached['fontes'] == result['fontes']
    assert len(calls) == 2


def test_injected_search_never_gains_implicit_native_discovery(db):
    calls = []
    result = research.pesquisa_rapida(db, 'qa', 'photosynthesis',
        buscar_fn=lambda q: calls.append(q) or hits('failed.example'),
        recuperar_fn=lambda _: {'texto': '', 'lida': False})
    assert len(calls) == 1 and not result['read_recovery']['executed']
    assert result['read_recovery']['reason'] == 'injected_search'


def test_excluded_canonical_urls_do_not_satisfy_discovery_gates(db, monkeypatch):
    calls = []
    known = hits('failed.example')
    def discover(provider, query, **kwargs):
        calls.append(provider)
        if provider == 'bing':
            return [{**row, 'url': row['url']+'/?utm_source=duplicate#copy'} for row in known]
        return hits('independent.example')
    monkeypatch.setattr(sp, 'buscar', discover)
    result = orch.pesquisar('photosynthesis', provedores=['bing', 'marginalia'],
        excluir_urls=[row['url'] for row in known], orcamento={'max_consultas': 1})
    assert calls == ['bing', 'marginalia']
    assert all('independent.example' in row['url'] for row in result['achados'])
    assert result['tentativas_busca'][0]['excluded'] == 3


@pytest.mark.parametrize('budget', [{'max_tentativas': 1}, {'max_consultas_total': 1}])
def test_recovery_does_not_reset_total_attempt_or_query_limits(db, monkeypatch, budget):
    calls = []
    monkeypatch.setattr(sp, 'buscar', lambda provider, query, **kw: calls.append(provider) or hits('failed.example'))
    result = research.pesquisa_rapida(db, 'qa', 'photosynthesis',
        recuperar_fn=lambda _: {'texto': '', 'lida': False}, orcamento=budget)
    assert calls == ['bing']
    assert not result['read_recovery']['executed'] and result['read_recovery']['reason'] == 'budget_exhausted'


def test_elapsed_initial_reads_spend_recovery_time_budget(db, monkeypatch):
    clock, calls = [0.0], []
    monkeypatch.setattr(orch.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(sp, 'buscar', lambda provider, query, **kw: calls.append(provider) or hits('failed.example'))
    def read(_):
        clock[0] += 2
        return {'texto': '', 'lida': False}
    result = research.pesquisa_rapida(db, 'qa', 'photosynthesis', recuperar_fn=read, orcamento={'timeout_total': 1})
    assert calls == ['bing'] and result['read_recovery']['reason'] == 'budget_exhausted'
    assert result['read_recovery']['remaining_seconds'] == 0


@pytest.mark.parametrize('code', ['bloqueado', 'rate_limited', 'http'])
def test_recovery_does_not_revisit_provider_with_observed_block_or_429(db, monkeypatch, code):
    calls = []
    monkeypatch.setattr(orch, '_escolher_provedores', lambda *a: ['bing', 'marginalia', 'wikipedia'])
    def discover(provider, query, **kwargs):
        calls.append(provider)
        if provider == 'bing':
            error = sp.ErroProvedor('Access denied', code)
            if code == 'http':
                error.http, error.categoria = 429, 'http'
            raise error
        return hits('failed.example' if provider == 'marginalia' else 'independent.example')
    def read(url):
        if 'failed.example' in url:
            raise research.ResearchErro('Access denied', 'bloqueado')
        return good_read(url)
    monkeypatch.setattr(sp, 'buscar', discover)
    result = research.pesquisa_rapida(db, 'qa', 'photosynthesis', recuperar_fn=read)
    assert calls == ['bing', 'marginalia', 'wikipedia']
    assert result['read_recovery']['executed'] and result['fontes_uteis'] == 3
    assert result['provedores']['falhas'][0]['provedor'] == 'bing'


def test_explicit_source_scope_is_preserved_during_recovery(db, monkeypatch):
    calls, reads = [], []
    initial = [{**row, 'titulo': row['titulo'] + ' docs.example.com'} for row in hits('docs.example.com')]
    recovered = [{**row, 'url': row['url'].replace('/0', '/new0').replace('/1', '/new1').replace('/2', '/new2')}
                 for row in initial]
    def discover(provider, query, **kwargs):
        calls.append((provider, query))
        return initial if provider == 'bing' else hits('outside.example') + recovered
    def read(url):
        reads.append(url)
        if url in {row['url'] for row in initial}:
            raise research.ResearchErro('Access denied', 'bloqueado')
        return good_read(url)
    monkeypatch.setattr(sp, 'buscar', discover)
    result = research.pesquisa_rapida(db, 'qa', 'photosynthesis site:docs.example.com', recuperar_fn=read)
    assert result['read_recovery']['executed']
    assert result['read_recovery']['allowed_domains'] == ['docs.example.com']
    assert all('site:docs.example.com' in query for _, query in calls)
    assert all(urlsplit(url).hostname == 'docs.example.com' for url in reads)
    assert all(urlsplit(row['url']).hostname == 'docs.example.com' for row in result['fontes'])


@pytest.mark.parametrize('when', ['initial', 'discovery'])
def test_cancellation_prevents_recovery_or_its_new_reads(db, monkeypatch, when):
    stopped, calls, reads = [False], [], []
    def discover(provider, query, **kwargs):
        calls.append(provider)
        if provider != 'bing' and when == 'discovery':
            stopped[0] = True
        return hits('failed.example' if provider == 'bing' else 'independent.example')
    def read(url):
        reads.append(url)
        if when == 'initial':
            stopped[0] = True
        return {'texto': '', 'lida': False}
    monkeypatch.setattr(sp, 'buscar', discover)
    result = research.pesquisa_rapida(db, 'qa', 'photosynthesis', recuperar_fn=read, deve_parar=lambda: stopped[0])
    assert len(reads) == 3 and not result['read_recovery']['read_urls']
    assert calls == (['bing'] if when == 'initial' else ['bing', 'marginalia'])
    assert result['read_recovery']['read_skip_reason'] == 'cancelled'


def test_recovered_private_url_uses_existing_ssrf_guard(db, monkeypatch):
    calls = []
    private = {'url': 'http://127.0.0.1/private', 'titulo': 'Photosynthesis',
               'trecho': 'Photosynthesis in plants'}
    monkeypatch.setattr(sp, 'buscar', lambda provider, query, **kw:
        hits('failed.example') if provider == 'bing' else [private])
    def read(url):
        calls.append(url)
        if url == private['url']:
            return research._recuperar_um(private, None, 1, 'photosynthesis')
        return {'texto': '', 'lida': False}
    result = research.pesquisa_rapida(db, 'qa', 'photosynthesis', recuperar_fn=read)
    assert private['url'] in calls and result['fontes_uteis'] == 0
    trace = next(row for row in result['candidate_reservoir']['items'] if row['url'] == private['url'])
    assert not trace['read'] and 'FETCH_FAILED' in trace['losses']


def test_useful_initial_read_skips_recovery(db, monkeypatch):
    calls = []
    monkeypatch.setattr(sp, 'buscar', lambda provider, query, **kw: calls.append(provider) or hits('useful.example'))
    result = research.pesquisa_rapida(db, 'qa', 'photosynthesis', recuperar_fn=good_read)
    assert calls == ['bing'] and result['fontes_uteis'] == 3
    assert not result['read_recovery']['executed'] and result['read_recovery']['reason'] == 'not_needed'


def test_pertinent_requested_media_skips_native_read_recovery(db, monkeypatch):
    row = {'titulo': 'Ponte Estaiada Sao Paulo', 'url': 'https://commons.wikimedia.org/wiki/File:Ponte.jpg',
           'tipo': 'imagem', 'origem': 'commons', 'trecho': 'Ponte Estaiada em Sao Paulo',
           'meta': {'original_url': 'https://upload.wikimedia.org/wikipedia/commons/0/00/Ponte.jpg',
                    'pagina': 'https://commons.wikimedia.org/wiki/File:Ponte.jpg'}}
    monkeypatch.setattr(research, '_buscar_orquestrado', lambda *a, **kw:
        ([row], {'tentativas_busca': [{'provedor': 'commons', 'consulta': 'Ponte'}]}))
    result = research.pesquisa_rapida(db, 'qa', 'Imagens da Ponte Estaiada de Sao Paulo')
    assert result['midia'] and result['fontes_lidas'] == 0
    assert result['read_recovery']['reason'] == 'requested_media_available'


def test_second_wave_prefers_new_host_after_observed_read_block(db, monkeypatch):
    reads = []
    recovered_same_host = [{**row, 'url': row['url'].replace('failed.example/', 'failed.example/new')} for row in hits('failed.example')]
    monkeypatch.setattr(sp, 'buscar', lambda provider, query, **kw:
        hits('failed.example', 6) if provider == 'bing' else recovered_same_host + hits('independent.example'))
    def read(url):
        reads.append(url)
        if urlsplit(url).hostname == 'failed.example':
            raise research.ResearchErro('Access denied', 'bloqueado')
        return good_read(url)
    result = research.pesquisa_rapida(db, 'qa', 'photosynthesis', recuperar_fn=read)
    assert len(reads) == 6 and all(urlsplit(url).hostname == 'independent.example' for url in reads[3:])
    assert result['fontes_uteis'] == 3


def test_discovery_exhausting_remaining_time_cannot_start_more_reads(db, monkeypatch):
    clock, reads, timeouts = [0.0], [], []
    monkeypatch.setattr(orch.time, 'monotonic', lambda: clock[0])
    def discover(provider, query, **kwargs):
        timeouts.append(kwargs['timeout'])
        if provider == 'marginalia':
            clock[0] = 20
        return hits('failed.example' if provider == 'bing' else 'independent.example')
    def read(url):
        reads.append(url)
        clock[0] += 0.1
        return {'texto': '', 'lida': False}
    monkeypatch.setattr(sp, 'buscar', discover)
    result = research.pesquisa_rapida(db, 'qa', 'photosynthesis', recuperar_fn=read,
        timeout_busca=20, orcamento={'timeout_total': 10})
    assert len(reads) == 3 and timeouts[1] <= 9.7
    assert result['read_recovery']['executed'] and result['read_recovery']['read_skip_reason'] == 'budget_exhausted'
    assert not result['read_recovery']['read_urls']


def test_deep_search_forwards_cancellation_before_post_read_recovery(db, monkeypatch):
    stopped, calls = [False], []
    monkeypatch.setattr(sp, 'buscar', lambda provider, query, **kw: calls.append(provider) or hits('failed.example'))
    def read(_):
        stopped[0] = True
        return {'texto': '', 'lida': False}
    result = research.pesquisa_aprofundada(db, 'qa', 'photosynthesis', recuperar_fn=read,
        deve_parar=lambda: stopped[0])
    assert calls == ['bing'] and 'interrompida pelo usuário' in result['etapas']
