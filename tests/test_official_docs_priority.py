"""Official docs requests must not start with editorial technology websites."""
import pytest

import search_orchestrator as orch
import search_providers as providers
import source_priority


@pytest.mark.parametrize('text', [
    'Pesquise na documentação oficial de Python o que faz asyncio.timeout.',
    'Documentação oficial de JavaScript Array.map, com exemplos.',
    'Find the official documentation for Python asyncio.timeout.',
])
def test_official_documentation_has_no_generic_editorial_priority(text):
    assert source_priority.detect(text) is None


def test_explicitly_named_source_still_takes_precedence():
    plan=source_priority.detect('Pesquise documentação oficial em https://docs.python.org/3/library/asyncio-task.html')
    assert plan and plan['explicit'] and 'docs.python.org' in plan['primary']


def test_ordinary_technology_preference_is_preserved():
    assert source_priority.detect('Quais são as novidades de tecnologia e smartphones?')['id']=='technology'


def test_native_python_docs_provider_is_first_without_editorial_site(monkeypatch):
    calls=[]
    def search(name, query, **kwargs):
        calls.append((name,query))
        return [{'titulo':'asyncio.timeout', 'url':f'https://docs.python.org/3/library/asyncio-task.html#timeout-{i}',
                 'trecho':'asyncio.timeout returns an asynchronous context manager.'} for i in range(3)]
    monkeypatch.setattr(providers,'buscar',search)
    monkeypatch.setattr(orch,'fontes_preferenciais',lambda _query:[])
    monkeypatch.setattr(orch,'_escolher_provedores',lambda *_args:['bing','python-docs'])
    orch.pesquisar('Pesquise na documentação oficial de Python o que faz asyncio.timeout.',
                  orcamento={'max_consultas':1,'max_provedores':2,'max_tentativas':2})
    assert calls and calls[0][0]=='python-docs'
    assert all('site:tecmundo.com.br' not in query for _,query in calls)
