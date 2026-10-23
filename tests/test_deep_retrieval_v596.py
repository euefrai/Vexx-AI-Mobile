"""Fixtures and frozen captures: never evidence of live offers or original articles."""
import copy
import json
from pathlib import Path

import pytest
import shopping
import search_orchestrator as orch
import search_providers as sp


@pytest.mark.parametrize('name,specs,expected', [
    ('Notebook Lenovo IdeaPad 8GB, SSD 512GB', {}, 8),
    ('Notebook Lenovo 16GB, 512GB SSD, RTX 4050 6GB', {}, 16),
    ('Notebook Lenovo SSD 512GB', {}, None),
    ('Celular 256GB', {}, None),
    ('Notebook Lenovo 8GB RAM', {'Memória RAM':'16GB'}, 8),
    ('Notebook Lenovo', {'Memória RAM':'16GB'}, 16),
    ('Notebook Lenovo SSD 32GB', {}, None),
    ('Notebook Lenovo 8GB RAM Plus', {}, 0),
])
def test_physical_ram_from_title_and_keyed_specs(name, specs, expected):
    result = shopping._ram_do_produto({'nome':name,'specs':specs})
    assert (result[0] if result else None) == expected


def test_real_frozen_lenovo_title_cannot_satisfy_16gb():
    capture = Path(__file__).parents[1]/'qa-artifacts/v595/live-shopping/lenovo.json'
    data = json.loads(capture.read_text(encoding='utf-8'))
    product = copy.deepcopy(data['result']['produtos'][0])
    inside, outside = shopping.aplicar_filtros([product], shopping.extrair_criterios('Notebook Lenovo 16 GB RAM'))
    assert not inside
    assert 'ram_abaixa' in outside[0]['excluido_codigos']


def test_feed_headline_recovery_stays_at_declared_publisher(monkeypatch):
    calls=[]
    title='Ubatã Bahia inaugura biblioteca municipal para estudantes'
    def search(name, query, **kwargs):
        calls.append((name,query))
        if name=='google-news':
            return [{'titulo':title+' - Jornal Local', 'url':'https://news.google.com/rss/articles/opaque',
                     'publisher_url':'https://jornal.example', 'publicador':'Jornal Local',
                     'content_scope':'feed_metadata','tipo':'noticia'}]
        if 'site:jornal.example' in query:
            return [{'titulo':title,'url':'https://jornal.example/noticia/biblioteca'},
                    {'titulo':title,'url':'https://jornal.example.evil.test/forged'}]
        return []
    monkeypatch.setattr(sp,'buscar',search)
    result=orch.pesquisar('Notícias de Ubatã Bahia nos últimos sete dias',
        provedores=['google-news','bing'],orcamento={'max_tentativas':5,'timeout_total':3})
    recovered=[x for x in result['achados'] if x.get('source_recovery')]
    assert len(recovered)==1
    assert recovered[0]['source_recovery']['state']=='original_candidate'
    assert not recovered[0].get('texto_lido')
    assert sum('site:jornal.example' in query for _,query in calls)==1
    assert len(calls)<=5


def test_recovery_does_not_retry_blocked_provider(monkeypatch):
    calls=[]
    def search(name,query,**kwargs):
        calls.append(name)
        if name=='google-news':
            return [{'titulo':'Ubatã Bahia inaugura biblioteca municipal para estudantes',
                'url':'https://news.google.com/rss/articles/x','publisher_url':'https://publisher.example',
                'content_scope':'feed_metadata'}]
        raise sp.ErroProvedor('blocked','bloqueado')
    monkeypatch.setattr(sp,'buscar',search)
    orch.pesquisar('Notícias de Ubatã Bahia', provedores=['google-news','bing'])
    assert calls.count('bing')==1
