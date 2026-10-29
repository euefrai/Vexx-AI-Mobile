import json
import urllib.error
import pytest

import research
import public_store_reader as reader

URL='https://www.kabum.com.br/produto/12345/fixture'
PAGE='<h1>Notebook de teste</h1><p>'+('Notebook de teste com memória e armazenamento. '*8)+'</p>'


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setenv('JULIA_PUBLIC_STORE_RENDER','1')
    monkeypatch.setattr(reader,'_cooldown_until',0)
    monkeypatch.setattr(research,'_ips_globais',lambda host:None)


class Response:
    status=200
    def __init__(self,data): self.data=json.dumps(data).encode()
    def read(self,n): return self.data[:n]
    def __enter__(self): return self
    def __exit__(self,*a): pass


def response(page=PAGE,final=URL,status=200):
    return Response({'success':True,'data':{'rawHtml':page,'metadata':{'url':final,'statusCode':status}}})


@pytest.mark.parametrize('url',[
    'http://www.kabum.com.br/produto/1','https://kabum.com.br.evil.example/produto/1',
    'https://www.kabum.com.br/produto/1?token=secret','https://shopee.com.br/account/',
    'https://shopee.com.br/login','https://user:secret@www.kabum.com.br/produto/1',
    'https://127.0.0.1/produto/1','https://www.kabum.com.br:8443/produto/1',
    'https://www.kabum.com.br/produto/1#secret'])
def test_private_or_out_of_scope_urls_are_never_forwarded(url,monkeypatch):
    monkeypatch.setattr(reader,'_open',lambda *a:pytest.fail('must not send'))
    assert reader.render(url,2,4096) is None


def test_empty_shell_is_rendered_anonymously_once_and_records_provenance(monkeypatch):
    monkeypatch.setattr(research,'baixar',lambda *a,**kw:(URL,'<div id="app"></div>'))
    calls=[]
    def open_(request,timeout):
        calls.append(request)
        assert request.full_url==reader.ENDPOINT
        assert not request.has_header('Authorization') and not request.has_header('Cookie')
        body=json.loads(request.data)
        assert body['maxAge']==0 and body['formats']==['rawHtml'] and 'actions' not in body
        assert timeout<=3
        return response()
    monkeypatch.setattr(reader,'_open',open_)
    final,page=reader.fetch(URL,timeout=3)
    assert final==URL and page==PAGE and len(calls)==1
    assert research.extrair_artigo(page,final)['metadados']['retrieval_method']=='firecrawl_public_render'


@pytest.mark.parametrize('status',[401,429])
def test_authentication_and_rate_limit_are_not_retried_elsewhere(status,monkeypatch):
    error=research.ResearchErro('refused','bloqueado');error.http=status
    def fail(*a,**k):raise error
    monkeypatch.setattr(research,'baixar',fail)
    monkeypatch.setattr(reader,'_open',lambda *a:pytest.fail('must not send'))
    with pytest.raises(research.ResearchErro) as result:reader.fetch(URL)
    assert result.value is error


def test_readable_page_uses_only_direct_fetch(monkeypatch):
    monkeypatch.setattr(research,'baixar',lambda *a,**kw:(URL,PAGE))
    monkeypatch.setattr(reader,'_open',lambda *a:pytest.fail('must not send'))
    assert reader.fetch(URL)==(URL,PAGE)


@pytest.mark.parametrize('final,status,page',[
    ('https://127.0.0.1/produto/1',200,PAGE),
    ('https://shopee.com.br/',200,PAGE),
    ('https://www.kabum.com.br/login',200,PAGE),
    (URL,403,PAGE),(URL,200,'<h1>Verify you are human</h1>'+PAGE),
    (URL,200,'<script>empty</script>'),(URL,200,'X'*10000)])
def test_rendered_errors_redirects_challenges_and_oversize_are_rejected(final,status,page,monkeypatch):
    monkeypatch.setattr(reader,'_open',lambda *a:response(page,final,status))
    assert reader.render(URL,2,4096) is None


def test_provider_quota_opens_circuit_without_losing_original_error(monkeypatch):
    calls=[]
    original=research.ResearchErro('denied','bloqueado');original.http=403
    def direct(*a,**k):raise original
    def fail(*a):
        calls.append(1)
        raise urllib.error.HTTPError(reader.ENDPOINT,429,'quota',{},None)
    monkeypatch.setattr(research,'baixar',direct)
    monkeypatch.setattr(reader,'_open',fail)
    for _ in range(2):
        with pytest.raises(research.ResearchErro) as result:reader.fetch(URL)
        assert result.value is original
    assert calls==[1]


def test_no_render_after_budget_is_used_or_when_disabled(monkeypatch):
    monkeypatch.setattr(research,'baixar',lambda *a,**kw:(URL,''))
    monkeypatch.setattr(reader,'_open',lambda *a:pytest.fail('must not send'))
    assert reader.fetch(URL,timeout=.5)==(URL,'')
    monkeypatch.setenv('JULIA_PUBLIC_STORE_RENDER','0')
    assert reader.fetch(URL,timeout=3)==(URL,'')
