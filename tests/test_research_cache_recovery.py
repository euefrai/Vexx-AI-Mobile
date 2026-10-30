"""Controlled cache regressions; no claim of live provider availability."""
import sqlite3
from datetime import datetime

import pytest

import query_intelligence
import research


QUERY = 'Python TaskGroup cancelamento de tarefas'
URL = 'https://docs.python.org/3/library/asyncio-task.html'


@pytest.fixture
def db(monkeypatch):
    monkeypatch.setattr(research, '_ips_globais', lambda _host: None)
    connection = sqlite3.connect(':memory:')
    research.criar_tabelas(connection)
    yield connection
    connection.close()


def source(**extra):
    return {'url':URL, 'titulo':QUERY, 'status':'aberta', 'relevante':True,
            'texto_lido':'Python TaskGroup propaga cancelamento para tarefas.',
            'acessado_em':'2026-10-29T10:00:00+00:00', **extra}


def run(db, mode, search, reader):
    function = research.pesquisa_rapida if mode == 'web' else research.pesquisa_aprofundada
    return function(db, 'qa-cache', QUERY, buscar_fn=search, recuperar_fn=reader)


@pytest.mark.parametrize('mode', ['web', 'web-deep'])
@pytest.mark.parametrize('bad', [
    {'fontes':[]},
    {'fontes':[source(status='encontrada', texto_lido='')]},
    {'fontes':[source(relevante=False)]},
    {'fontes':[source(texto_lido='')], 'fontes_uteis':99},
    {'fontes':[], 'midia':[{'id':'image', 'url':'https://example.org/image.jpg'}]},
])
def test_legacy_failed_cache_cannot_suppress_a_fresh_read(db, mode, bad):
    research.cache_put(db, 'qa-cache', mode, QUERY,
        {'retrieval_version':research.RETRIEVAL_VERSION, **bad}, 3600)
    calls = []
    def search(query):
        calls.append(query)
        return [{'url':URL, 'titulo':QUERY, 'trecho':'Python TaskGroup cancelamento'}]
    result = run(db, mode, search, lambda url:{'titulo':QUERY, 'texto':source()['texto_lido'], 'final':url})
    assert calls and not result['de_cache']
    assert any(f['status']=='aberta' and f['texto_lido'] for f in result['fontes'])


@pytest.mark.parametrize('mode', ['web', 'web-deep'])
def test_useful_cache_preserves_evidence_and_owner_scope(db, mode):
    evidence = source()
    research.cache_put(db, 'qa-cache', mode, QUERY,
        {'retrieval_version':research.RETRIEVAL_VERSION, 'fontes':[evidence]}, 3600)
    result = run(db, mode, lambda _q:pytest.fail('Positive cache should be reused'), None)
    assert result['de_cache'] and result['fontes']==[evidence]
    assert research.cache_get(db, 'another-owner', mode, QUERY) is None


@pytest.mark.parametrize('mode', ['web', 'web-deep'])
def test_failed_read_is_not_written_as_a_positive_cache(db, mode):
    result = run(db, mode,
        lambda _q:[{'url':URL,'titulo':QUERY,'trecho':'Python TaskGroup cancelamento'}],
        lambda _url:(_ for _ in ()).throw(research.ResearchErro('Access denied', 'bloqueado')))
    assert not result['de_cache']
    assert research.cache_get(db, 'qa-cache', mode, QUERY) is None
    if mode=='web-deep':
        assert result['run_id']  # Failed runs remain visible in history.


def test_deep_live_cache_has_short_ttl_and_a_date_sensitive_key(db, monkeypatch):
    day = ['2026-10-29']
    def analyze(text):
        return {'temporal':True, 'requires_live_data':True,
                'resolved_request':text+' '+day[0],
                'parameters':{'start_date':day[0], 'end_date':day[0]}}
    monkeypatch.setattr(query_intelligence, 'analyze', analyze)
    calls = []
    def quick(*args, **kwargs):
        calls.append(kwargs['ttl'])
        return {'fontes':[source()], 'etapas':[], 'estado':'parcial'}
    monkeypatch.setattr(research, 'pesquisa_rapida', quick)
    first = research.pesquisa_aprofundada(db, 'qa-cache', 'notícias de hoje')
    assert not first['de_cache'] and calls and max(calls)<=180
    row = db.execute("SELECT criado_em,expira_em FROM research_cache WHERE provedor='web-deep'").fetchone()
    assert (datetime.fromisoformat(row[1])-datetime.fromisoformat(row[0])).total_seconds()<=181
    count = len(calls)
    assert research.pesquisa_aprofundada(db, 'qa-cache', 'notícias de hoje')['de_cache']
    assert len(calls)==count
    day[0]='2026-10-30'
    assert not research.pesquisa_aprofundada(db, 'qa-cache', 'notícias de hoje')['de_cache']
    assert len(calls)>count


@pytest.mark.parametrize('updates', [
    {'validation_state':'blocked'}, {'validation_state':'invalid'},
    {'url':'http://127.0.0.1/image.jpg'}, {'source_url':'javascript:alert(1)'},
    {'title':'Eiffel Tower Paris', 'source_title':'Paris', 'url':'https://example.org/paris.jpg'},
])
def test_invalid_or_unrelated_media_is_not_a_successful_read_cache(updates):
    media = {'type':'image', 'title':'Ponte Estaiada São Paulo',
             'url':'https://example.org/ponte-estaiada-sao-paulo.jpg',
             'source_url':'https://example.org/ponte', 'validation_state':'unverified'}
    query = 'Imagens da Ponte Estaiada de São Paulo'
    assert research._cache_pesquisa_util({'fontes':[], 'midia':[media]}, query)
    assert not research._cache_pesquisa_util({'fontes':[], 'midia':[{**media, **updates}]}, query)
