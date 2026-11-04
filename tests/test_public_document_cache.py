"""Cache contracts, conditional HTTP and query-independent extraction."""
import threading
from concurrent.futures import ThreadPoolExecutor
from urllib.error import HTTPError

import pytest
import public_document_cache as cache
import research
import research_view


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setenv('JULIA_PUBLIC_DOCUMENT_CACHE','1')
    monkeypatch.setattr(cache,'_bodies',cache.OrderedDict())
    monkeypatch.setattr(research,'url_segura',lambda url:url)


def page(text='Public document body.', **headers):
    return cache.PublicBody(text,{k.replace('_','-'):str(v) for k,v in headers.items()})


def test_owner_separation_and_fresh_body_reuse_without_storing_evidence(monkeypatch):
    calls=[]
    def fetch(url,**kw):calls.append(url);return url,page(cache_control='public, max-age=300')
    monkeypatch.setattr(research,'baixar',fetch)
    one=cache.reader('alice','História da linguagem Rust');two=cache.reader('bob','História da linguagem Rust')
    url='https://example.org/article'
    first=one.fetch(url)[1];second=one.fetch(url)[1];third=two.fetch(url)[1]
    assert len(calls)==2 and str(first)==str(second)==str(third)
    assert second.cache_state=='fresh_cache' and second.fetched_at==first.fetched_at
    second.cache_headers['cache-control']='no-store'
    assert one.fetch(url)[1].cache_headers['cache-control']=='public, max-age=300'


@pytest.mark.parametrize('headers',[{'cache_control':'no-store, max-age=300'},
    {'cache_control':'private, max-age=300'}, {'cache_control':'max-age=300','set_cookie':'present'},
    {'cache_control':'max-age=300','vary':'Cookie'}, {'cache_control':'max-age=300','vary':'*'}, {}])
def test_unsafe_or_unverifiable_bodies_are_not_retained(monkeypatch,headers):
    calls=[]
    def fetch(url,**kw):calls.append(1);return url,page(**headers)
    monkeypatch.setattr(research,'baixar',fetch)
    reader=cache.reader('owner','documentação');url='https://example.org/article'
    reader.fetch(url);reader.fetch(url)
    assert len(calls)==2 and not cache._bodies


def test_conditional_revalidation_keeps_collection_date_and_updates_check_time(monkeypatch):
    calls=[]
    def fetch(url,**kw):
        calls.append(kw)
        if len(calls)==1:return url,page(etag='"v1"',cache_control='no-cache')
        return url,cache.PublicBody('',{'etag':'"v1"','cache-control':'max-age=300'},304,checked_at='2026-11-04T21:00:00+00:00')
    monkeypatch.setattr(research,'baixar',fetch)
    reader=cache.reader('owner','Documento');url='https://example.org/article'
    first=reader.fetch(url)[1];second=reader.fetch(url)[1]
    assert calls[1]['validadores']=={'If-None-Match':'"v1"'}
    assert first==second and second.cache_state=='revalidated'
    assert second.fetched_at==first.fetched_at and second.checked_at=='2026-11-04T21:00:00+00:00'


def test_price_requests_always_revalidate_and_never_fall_back_to_stale(monkeypatch):
    calls=[]
    def fetch(url,**kw):
        calls.append(kw)
        if len(calls)>1:raise research.ResearchErro('Access denied','bloqueado')
        return url,page(cache_control='max-age=300',etag='"price-v1"')
    monkeypatch.setattr(research,'baixar',fetch)
    reader=cache.reader('owner','Pesquise uma RTX 3050 6 GB com preço atual');url='https://example.org/product'
    assert reader.max_age==0
    reader.fetch(url)
    with pytest.raises(research.ResearchErro):reader.fetch(url)
    assert len(calls)==2 and calls[-1]['validadores']


def test_mismatched_304_is_rejected_without_serving_old_body(monkeypatch):
    calls=[]
    def fetch(url,**kw):
        calls.append(1)
        return (url,page(etag='"v1"',cache_control='no-cache')) if len(calls)==1 else (url,cache.PublicBody('',{'etag':'"other"'},304))
    monkeypatch.setattr(research,'baixar',fetch)
    reader=cache.reader('owner','Documento');url='https://example.org/article';reader.fetch(url)
    with pytest.raises(research.ResearchErro):reader.fetch(url)
    assert not cache._bodies


def test_last_modified_can_gain_etag_after_valid_304(monkeypatch):
    calls=[]
    def fetch(url,**kw):
        calls.append(kw)
        if len(calls)==1:return url,page(last_modified='Wed, 04 Nov 2026 10:00:00 GMT',cache_control='no-cache')
        return url,cache.PublicBody('',{'etag':'"v1"'},304)
    monkeypatch.setattr(research,'baixar',fetch)
    reader=cache.reader('owner','Documento');url='https://example.org/article';reader.fetch(url)
    assert reader.fetch(url)[1].cache_state=='revalidated'
    assert calls[1]['validadores']=={'If-Modified-Since':'Wed, 04 Nov 2026 10:00:00 GMT'}


def test_late_revalidation_cannot_overwrite_another_requests_new_body(monkeypatch):
    reader=cache.reader('owner','Documento');reader.max_age=0;url='https://example.org/article'
    monkeypatch.setattr(research,'baixar',lambda url,**kw:(url,page('old',etag='"v1"',cache_control='max-age=300')))
    reader.fetch(url);started=threading.Event();release=threading.Event()
    def fetch(url,**kw):
        if threading.current_thread().name.startswith('late'):
            started.set();assert release.wait(2)
            return url,cache.PublicBody('',{'etag':'"v1"'},304)
        return url,page('new',etag='"v2"',cache_control='max-age=300')
    monkeypatch.setattr(research,'baixar',fetch)
    with ThreadPoolExecutor(max_workers=1,thread_name_prefix='late') as pool:
        late=pool.submit(reader.fetch,url);assert started.wait(1)
        assert reader.fetch(url)[1]=='new'
        release.set();assert late.result()[1]=='old'
    entry=next(iter(cache._bodies.values()))
    assert entry[0]=='new' and entry[0].cache_headers['etag']=='"v2"' and entry[2]==0


def test_oversized_body_is_not_cached(monkeypatch):
    monkeypatch.setattr(research,'baixar',lambda url,**kw:(url,page('x'*(cache.MAX_BODY+1),cache_control='max-age=300')))
    cache.reader('owner','Documento').fetch('https://example.org/article')
    assert not cache._bodies


def test_age_no_cache_vary_and_oversized_headers_are_conservative():
    assert cache._freshness({'cache-control':'max-age=300','age':'600','etag':'"v1"'},0)==0
    assert cache._freshness({'cache-control':'no-cache, max-age=300','etag':'"v1"'},0)==0
    assert cache._freshness({'cache-control':'max-age=300','vary':'Accept-Encoding'},0)==300
    assert cache._freshness({'cache-control':'max-age='+('9'*1000)},0)==31_536_000
    body=cache.response_body('document',{'Cache-Control':'max-age=300,'+'x'*5000+',no-store','ETag':'"v1"'})
    assert cache._freshness(body.cache_headers,0) is None


def test_query_capabilities_redirect_aliases_and_storage_bounds(monkeypatch):
    def fetch(url,**kw):return url,page(cache_control='max-age=300')
    monkeypatch.setattr(research,'baixar',fetch);reader=cache.reader('owner','Documento')
    reader.fetch('https://example.org/article?token=secret')
    assert not cache._bodies
    monkeypatch.setattr(research,'baixar',lambda url,**kw:('https://other.org/article',page(cache_control='max-age=300')))
    reader.fetch('https://example.org/article')
    assert not cache._bodies
    monkeypatch.setattr(research,'baixar',fetch)
    for i in range(12):reader.fetch('https://example.org/'+str(i))
    assert len(cache._bodies)==cache.MAX_PER_OWNER
    for owner in range(40):cache.reader(str(owner),'Documento').fetch('https://example.org/article')
    assert len(cache._bodies)==cache.MAX_ENTRIES


def test_cancellation_and_ssrf_are_checked_even_for_fresh_hits(monkeypatch):
    monkeypatch.setattr(research,'baixar',lambda url,**kw:(url,page(cache_control='max-age=300')))
    reader=cache.reader('owner','Documento');url='https://example.org/article';reader.fetch(url)
    with pytest.raises(research.ResearchErro) as caught:reader.fetch(url,cancelar=lambda:True)
    assert caught.value.codigo=='cancelada'
    def deny(url):raise research.ResearchErro('Private address','ssrf')
    monkeypatch.setattr(research,'url_segura',deny)
    with pytest.raises(research.ResearchErro) as caught:reader.fetch(url)
    assert caught.value.codigo=='ssrf'


def test_unknown_request_options_and_expired_budget_never_use_a_fresh_body(monkeypatch):
    calls=[]
    def fetch(url,**options):calls.append(options);return url,page(cache_control='max-age=300')
    monkeypatch.setattr(research,'baixar',fetch)
    reader=cache.reader('owner','Documento');url='https://example.org/article';reader.fetch(url)
    reader.fetch(url,timeout=0)
    reader.fetch(url,abrir=lambda *args:None)
    assert len(calls)==3 and calls[1]['timeout']==0 and 'abrir' in calls[2]


def test_raw_document_is_reselected_for_another_question(monkeypatch):
    def table(name,founder):
        return ('<table><tr><th colspan="2">'+name+'</th></tr><tr><th>Fundação</th>'
                '<td>19 de agosto de 1994</td></tr><tr><th>Fundador(es)</th><td>'+founder+'</td></tr></table>')
    body='<main><h1>Empresas</h1><p>'+'Introdução documental. '*1500+'</p>'+table('Empresa Atlas','Maria Silva')+table('Empresa Boreal','João Souza')+'</main>'
    calls=[]
    def fetch(url,**kw):calls.append(1);return url,page(body,cache_control='max-age=300')
    monkeypatch.setattr(research,'baixar',fetch)
    source={'url':'https://example.org/article','titulo':'Empresa Atlas'}
    one=research._recuperar_um(source,None,4,'Quem fundou a Empresa Atlas e em que ano ela foi criada?',cache=cache.reader('owner','Empresa Atlas'))
    two=research._recuperar_um(source,None,4,'Quem fundou a Empresa Boreal e em que ano ela foi criada?',cache=cache.reader('owner','Empresa Boreal'))
    assert len(calls)==1 and 'João Souza' in two['texto']
    assert two['cache_state']=='fresh_cache' and two['fetched_at']==one['fetched_at']
    import evidence_graph as eg
    first=eg.requirement_coverage('Quem fundou a Empresa Atlas e em que ano ela foi criada?',[{**one,'url':source['url']}])
    second=eg.requirement_coverage('Quem fundou a Empresa Boreal e em que ano ela foi criada?',[{**two,'url':source['url']}])
    assert first['complete'] and second['complete']
    assert 'Maria Silva' in str(eg.select_answer_passages(first))
    assert 'Maria Silva' not in str(eg.select_answer_passages(second))
    assert 'João Souza' in str(eg.select_answer_passages(second))


def test_native_http_304_and_header_forwarding(monkeypatch):
    monkeypatch.setattr(research,'_ips_globais',lambda host:None)
    seen=[]
    def opener(url,timeout,user_agent='',headers=None):
        seen.append(headers)
        raise HTTPError(url,304,'Not Modified',{'ETag':'"v1"'},None)
    final,body=research.baixar('https://example.org/article',abrir=opener,validadores={'If-None-Match':'"v1"'})
    assert body.http_status==304 and body.cache_headers['etag']=='"v1"'
    assert seen==[{'If-None-Match':'"v1"'}]
    with pytest.raises(research.ResearchErro):
        research.baixar(final,abrir=opener,validadores={'Authorization':'secret'})


def test_chat_budget_keeps_sources_without_mutating_workspace_view():
    cards=[research_view.source_card({'titulo':'Fonte '+str(i),'url':'https://example.org/'+str(i),
            'texto_lido':True,'trecho':'Trecho verificado. '*15}) for i in range(10)]
    view={'blocks':[{'type':'text','content':'Texto factual. '*230},
                    {'type':'ui','component':'sources','props':{'items':cards}}]}
    blocks=research_view.chat_blocks(view,limit=7000)
    selected=next(b['props']['items'] for b in blocks if b.get('component')=='sources')
    assert 1<=len(selected)<10 and len(cards)==10 and blocks[0]==view['blocks'][0]
    assert all(item['url'].startswith('https://example.org/') for item in selected)


def test_document_fragments_share_raw_body_but_keep_the_requested_anchor(monkeypatch):
    calls=[]
    def fetch(url,**kw):calls.append(url);return url,page(cache_control='max-age=300')
    monkeypatch.setattr(research,'baixar',fetch);reader=cache.reader('owner','Python')
    reader.fetch('https://docs.python.org/types#list.append')
    final,body=reader.fetch('https://docs.python.org/types#list.pop')
    assert len(calls)==1 and final.endswith('#list.pop') and body.cache_state=='fresh_cache'


def test_single_large_card_is_compacted_before_the_factual_answer_is_lost():
    card=research_view.source_card({'titulo':'Fonte','url':'https://example.org/article','texto_lido':True})
    card['detalhes']=['Informações contextuais. '*30 for _ in range(6)]
    original={'type':'text','content':'Resposta citada. '*240}
    blocks=research_view.chat_blocks({'blocks':[original,{'type':'ui','component':'sources','props':{'items':[card]}}]},limit=4700)
    assert blocks[0]==original
    source=next(b for b in blocks if b.get('component')=='sources')['props']['items'][0]
    assert source['url']==card['url'] and len(source['detalhes'])<6 and len(card['detalhes'])==6


def test_final_chat_prioritizes_read_sources_and_preserves_workspace_discovery():
    found=research_view.source_card({'titulo':'Prévia','url':'https://example.org/preview','status':'encontrada'})
    read=research_view.source_card({'titulo':'Artigo','url':'https://example.org/article','texto_lido':True})
    view={'blocks':[{'type':'ui','component':'sources','props':{'items':[found,read]}}]}
    blocks=research_view.chat_blocks(view)
    assert blocks[0]['props']['items']==[read]
    assert len(view['blocks'][0]['props']['items'])==2 and found['leitura']=='FOUND'
