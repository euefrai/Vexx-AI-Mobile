"""Bounded public-source recovery. Fixtures do not claim access to real stores."""
import pytest

import pc_agent
import research
import shopping
import research_agents as ra
import search_providers
from test_research_parallel_reading import research_job, hits, content
from test_shopping_v55 import PAGINA_PRODUTO


@pytest.mark.parametrize('wrapper', ['<script>{}</script>', '<style>{}</style>',
                                  '<template>{}</template>', '<!-- {} -->'])
def test_error_strings_inside_inactive_markup_do_not_discard_readable_page(wrapper,monkeypatch):
    html = wrapper.format('access denied; checking your browser; anomaly-modal') + '<h1>Notebook Gamer X 16GB RAM</h1>'
    assert not research.pagina_bloqueada(html)
    monkeypatch.setattr(research,'baixar',lambda url,**kw:(url,html))
    assert research._recuperar_um({'url':'https://store.example/product'},None,1)['lida']


@pytest.mark.parametrize('page', [
    '<title>Just a moment...</title><p>Verifying you are human</p>',
    '<form class="anomaly-modal"><input name="captcha"></form>',
    '<div id="cf-browser-verification"></div>',
    '<script>'+('x'*10000)+'</script><h1>Access denied</h1>',
    'Unusual traffic',
])
def test_real_challenge_signatures_are_still_rejected(page):
    assert research.pagina_bloqueada(page)
    with pytest.raises(search_providers.ErroProvedor):
        search_providers._verificar_bloqueio(page)


def test_captcha_subject_or_embedded_widget_is_not_itself_a_block():
    page='<title>Documentação de CAPTCHA</title><script src="https://www.google.com/recaptcha/api.js"></script><p>Exemplo de integração do CAPTCHA.</p>'
    assert not research.pagina_bloqueada(page)
    search_providers._verificar_bloqueio(page)


def test_challenge_with_product_json_never_becomes_offer():
    report=[]
    blocked='<h1>Verify you are human</h1>'+PAGINA_PRODUTO
    assert shopping._recuperar_ofertas('https://loja.com/produto/x','Notebook',
        lambda url:{'texto':blocked,'final':url},relatorio=report)==[]
    assert report[0]['access_reason']=='challenge_page'
    assert report[0]['http']==200


def test_deep_research_tries_independent_host_after_block(research_job):
    db,job=research_job
    candidates=hits('blocked','same-host')+[dict(hits('good')[0],url='https://other.example/good')]
    calls=[]
    def read(url):
        calls.append(url)
        if 'example.com' in url:
            raise research.ResearchErro('Challenge','bloqueado')
        return content(url)
    evidence=ra.agente_analista(db,job,{'alvo':job['objetivo']},candidates,read,teto_paginas=1)
    assert calls==['https://example.com/blocked','https://other.example/good']
    assert len(evidence)==1 and evidence[0]['texto_lido']
    assert job['usados']['paginas']==2


@pytest.mark.parametrize('status,reason', [(401,'authentication_required'),
    (403,'access_denied'),(429,'rate_limited')])
def test_http_denial_is_not_reported_as_confirmed_captcha(status,reason):
    def fail(url):
        error=research.ResearchErro('HTTP access refused','bloqueado')
        error.http=status
        raise error
    report=[]
    assert shopping._recuperar_ofertas('https://loja.com/produto/x','Notebook',fail,relatorio=report)==[]
    assert report[0]['access_reason']==reason and report[0]['http']==status


@pytest.mark.parametrize('blocked_host',['blocked.example','www.kabum.com.br'])
def test_other_store_is_read_before_budget_is_spent_on_one_blocked_host(tmp_path,monkeypatch,blocked_host):
    monkeypatch.setattr(research,'_ips_globais',lambda host:None)
    candidates=[{'url':f'https://{blocked_host}/produto/{n}',
                 'titulo':'Notebook Gamer X 16GB RAM','trecho':'Notebook Gamer X 16GB RAM'} for n in range(6)]
    candidates.append({'url':'https://loja.com/produto/x','titulo':'Notebook Gamer X 16GB RAM','trecho':'Notebook Gamer X 16GB RAM'})
    monkeypatch.setattr(shopping,'buscar_com_fallback',lambda *a,**kw:(candidates,[]))
    calls=[]
    def read(url):
        calls.append(url)
        if blocked_host in url:
            error=research.ResearchErro('HTTP access refused','bloqueado');error.http=403
            raise error
        return {'final':url,'texto':PAGINA_PRODUTO}
    db=pc_agent.open_db(tmp_path/'qa.sqlite')
    try:
        result=shopping.pesquisar(db,'qa','notebook gamer 16gb',baixar_fn=read,teto_paginas=1,usar_cache=False)
        assert len(calls)==2
        assert calls[-1]=='https://loja.com/produto/x'
        assert result['produtos'] and all(p['link_veredito']=='verificado' for p in result['produtos'])
        assert shopping.ultima_consulta(db,'qa','')['resultado']['produtos']
    finally:
        db.close()
