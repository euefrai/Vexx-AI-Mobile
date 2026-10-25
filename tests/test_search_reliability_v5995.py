"""Controlled regressions for observed provider/candidate-stage failures."""
import urllib.parse

import pytest
import research
import search_providers as sp


def test_marginalia_wait_page_is_blocked_without_following_challenge(monkeypatch):
    calls=[]
    def fetch(url, timeout):
        calls.append(url)
        return url, '<h1>Wait For A Moment</h1><p>The search engine is currently barraged by queries from bots.</p><a href="https://creativecommons.org/licenses/by-sa/4.0/">CC BY-SA</a>'
    monkeypatch.setattr(sp, '_baixar', fetch)
    with pytest.raises(sp.ErroProvedor) as exc:
        sp.buscar_marginalia('Object.assign JavaScript reference')
    assert exc.value.codigo=='bloqueado'
    assert len(calls)==1 and 'sst=' not in calls[0]


def test_marginalia_ignores_footer_navigation_and_license(monkeypatch):
    html='''<nav><a href="https://example.org/nav">Navigation title</a></nav>
      <main><a href="https://docs.example.org/api"><b>Actual API reference</b></a>
      <a rel="license" href="https://creativecommons.org/licenses/by-sa/4.0/">CC BY-SA 4.0</a></main>
      <footer><div><a href="https://example.org/footer">Footer reference</a></div></footer>'''
    monkeypatch.setattr(sp,'_baixar',lambda url, timeout:(url,html))
    rows=sp.buscar_marginalia('API')
    assert [r['url'] for r in rows]==['https://docs.example.org/api']
    assert rows[0]['titulo']=='Actual API reference'


def test_worldbank_requests_exact_indicator_never_unsupported_q(monkeypatch):
    calls=[]
    def data(url,timeout):
        calls.append(urllib.parse.urlsplit(url))
        return [{},[{'id':'SP.POP.TOTL','name':'Population, total','note':'Total population.'},
                     {'id':'SI.POV.DDAY','name':'Poverty headcount'}]]
    monkeypatch.setattr(sp,'_json',data)
    rows=sp.buscar_worldbank('Brazil population')
    assert calls[0].path=='/v2/indicator/SP.POP.TOTL'
    assert 'q' not in urllib.parse.parse_qs(calls[0].query)
    assert len(rows)==1 and rows[0]['meta']['indicador']=='SP.POP.TOTL'
    assert rows[0]['content_scope']=='metadata_only'


@pytest.mark.parametrize('query',['unrelated universal question','population growth','população rural','SP.POP.TOTL NY.GDP.MKTP.CD'])
def test_worldbank_does_not_substitute_unrelated_indicator(monkeypatch,query):
    def forbidden(*args):raise AssertionError('unsupported query must not fetch the catalogue')
    monkeypatch.setattr(sp,'_json',forbidden)
    with pytest.raises(sp.ErroProvedor) as exc:sp.buscar_worldbank(query)
    assert exc.value.codigo=='vazio'


def test_incomplete_academic_metadata_can_reach_reading_without_becoming_evidence():
    row={'url':'https://example.org/paper','titulo':'Effect of thermal treatments',
         'trecho':'','metadata_source':'academic_provider'}
    selected=research.selecionar_candidatos_leitura([row],'Qual o efeito e a duração dos tratamentos térmicos?')
    assert selected==[row]
    assert 'lida' not in row and 'answer_passages' not in row
