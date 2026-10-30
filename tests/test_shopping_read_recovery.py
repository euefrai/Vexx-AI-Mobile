"""Read-aware discovery regressions with controlled providers and real parsing.

No network/model calls; these tests do not certify access to live merchants.
"""
from collections import Counter
import json
from urllib.parse import urlsplit

import pytest

import pc_agent
import research
import shopping
import source_priority
import store_discovery


QUERY = 'Pesquise uma placa de vídeo RTX 3050 com 6 GB de VRAM para comprar no Brasil.'


def candidate(url, gb=6, origin='web'):
    return {'url':url,'titulo':f'Placa de Vídeo NVIDIA GeForce RTX 3050 {gb}GB',
            'trecho':f'GPU RTX 3050 com {gb}GB de VRAM','origem':origin}


def product_page(url, gb=6, price='1499.99'):
    name=f'Placa de Vídeo NVIDIA GeForce RTX 3050 {gb}GB GDDR6'
    product={'@context':'https://schema.org','@type':'Product','name':name,
             'brand':{'@type':'Brand','name':'NVIDIA'},'sku':f'GPU-{gb}',
             'description':f'Placa de vídeo dedicada com {gb} GB de VRAM.',
             'additionalProperty':[{'@type':'PropertyValue','name':'VRAM','value':f'{gb} GB'}],
             'offers':{'@type':'Offer','price':price,'priceCurrency':'BRL',
                       'availability':'https://schema.org/InStock','url':url}}
    return '<html><head><title>'+name+'</title><script type="application/ld+json">'+json.dumps(product)+'</script></head><body><h1>'+name+'</h1><p>Preço declarado R$ '+price+'</p></body></html>'


@pytest.fixture
def pipeline(monkeypatch,tmp_path):
    monkeypatch.setattr(research,'_ips_globais',lambda host:None)
    monkeypatch.setattr(research,'_abrir',lambda *_a,**_k:pytest.fail('Unexpected network call'))
    native='https://www.kabum.com.br/produto/100001/placa-rtx-3050-6gb'
    other='https://store-b.com/produto/placa-rtx-3050-6gb'
    state={'native':[candidate(native,origin='kabum-search')],'mlb':[],
           'ddg':[],'web':[candidate(other)],'blocked':{native},
           'pages':{other:product_page(other)}}
    calls={key:[] for key in ('native','mlb','ddg','web','read')}
    def native_provider(query,**kwargs):
        calls['native'].append(query);return [dict(row) for row in state['native']]
    def mlb_provider(query,**kwargs):
        calls['mlb'].append(query);return [dict(row) for row in state['mlb']]
    def ddg_provider(query,**kwargs):
        calls['ddg'].append(query);return [dict(row) for row in state['ddg']],['ddg: controlled']
    def web_provider(query,**kwargs):
        calls['web'].append(query);return [dict(row) for row in state['web']],['web: controlled']
    def reader(url):
        calls['read'].append(url)
        if url in state['blocked']:raise research.ResearchErro('Access denied','bloqueado')
        if url not in state['pages']:pytest.fail('Unexpected page read: '+url)
        return {'final':url,'texto':state['pages'][url]}
    monkeypatch.setattr(store_discovery,'search_kabum',native_provider)
    monkeypatch.setattr(shopping,'buscar_mlb',mlb_provider)
    monkeypatch.setattr(shopping,'buscar_ddg_chain',ddg_provider)
    monkeypatch.setattr(shopping,'buscar_web_v55',web_provider)
    db=pc_agent.open_db(tmp_path/'read-recovery.sqlite')
    def run(text=QUERY,teto=2,**kwargs):
        return shopping.pesquisar(db,'qa-recovery',text,'qa-chat',baixar_fn=reader,
                                  teto_paginas=teto,usar_cache=False,**kwargs)
    yield state,calls,run,native,other
    db.close()


def test_blocked_native_discovery_recovers_from_an_independent_source(pipeline):
    state,calls,run,native,other=pipeline
    result=run()
    assert len(result['produtos'])==1
    product=result['produtos'][0]
    assert product['preco_confirmado'] and product['preco']==1499.99
    assert (product.get('url_final') or product['url'])==other
    assert result['criterios']['specs']['vram_gb']==6
    assert result['descoberta']['ondas']==2
    assert len(calls['native'])==2 and len(calls['web'])==1
    assert Counter(calls['read'])==Counter([native,other])


def test_wrong_vram_recovery_keeps_the_original_six_gb_requirement(pipeline):
    state,calls,run,native,other=pipeline
    state['blocked'].clear()
    state['pages'][native]=product_page(native,gb=8)
    state['native']=[candidate(native,gb=8,origin='kabum-search')]
    result=run()
    assert result['produtos'] and all('6GB' in p['nome'] for p in result['produtos'])
    assert all('8GB' not in p['nome'] for p in result['produtos'])
    assert result['criterios']['specs']['vram_gb']==6
    assert len(calls['web'])==1 and result['descoberta']['ondas']==2
    assert Counter(calls['read'])==Counter([native,other])


def test_confirmed_first_wave_does_not_start_supplementary_search(pipeline):
    state,calls,run,native,_=pipeline
    state['blocked'].clear();state['pages'][native]=product_page(native)
    result=run()
    assert len(result['produtos'])==1 and result['produtos'][0]['preco_confirmado']
    assert result['descoberta']['ondas']==1
    assert calls['web']==calls['ddg']==[] and calls['read']==[native]


@pytest.mark.parametrize('provider',['lojas','ddg','web'])
def test_shopee_exclusivity_filters_every_stage_and_never_uses_mlb_or_kabum(monkeypatch,provider):
    own=candidate('https://shopee.com.br/fone-bluetooth-i.123.456')
    foreign=candidate('https://www.mercadolivre.com.br/p/MLB123456')
    calls={'web':[],'ddg':[]}
    monkeypatch.setattr(shopping,'buscar_mlb',lambda *_a,**_k:pytest.fail('MLB must not replace Shopee'))
    monkeypatch.setattr(store_discovery,'search_kabum',lambda *_a,**_k:pytest.fail('KaBuM must not replace Shopee'))
    def web(query,**kwargs):
        calls['web'].append(query)
        include=(provider=='lojas' or (provider=='web' and len(calls['web'])==2))
        return [foreign]+([own] if include else []),['web: controlled']
    def ddg(query,**kwargs):
        calls['ddg'].append(query)
        return [foreign]+([own] if provider=='ddg' else []),['ddg: controlled']
    monkeypatch.setattr(shopping,'buscar_web_v55',web)
    monkeypatch.setattr(shopping,'buscar_ddg_chain',ddg)
    rows,_=shopping.buscar_com_fallback('fone bluetooth',texto_lojas='Quero fone bluetooth apenas na Shopee')
    assert rows and all(urlsplit(row['url']).hostname=='shopee.com.br' for row in rows)
    assert all('site:shopee.com.br' in q for q in calls['web']+calls['ddg'])


def test_recovery_deduplicates_tracking_and_anchor_aliases(pipeline):
    state,calls,run,native,other=pipeline
    alias=native.replace('www.kabum','kabum')+'/?utm_source=recovery#price'
    state['web']=[candidate(alias),candidate(other)]
    result=run(teto=1)
    assert len(result['produtos'])==1
    assert Counter(calls['read'])==Counter([native,other])
    assert alias not in calls['read']
    assert result['descoberta']['paginas_consultadas']==2


def test_recovery_preserves_distinct_sku_identity(pipeline):
    state,calls,run,native,_=pipeline
    base='https://store-c.com/produto/placa-rtx-3050'
    wrong=base+'?sku=8&utm_source=initial#offer'
    right=base+'?sku=6&utm_source=recovery#offer'
    state['blocked'].clear()
    state['native']=[candidate(wrong,gb=8,origin='kabum-search')]
    state['web']=[candidate(right)]
    state['pages']={wrong:product_page(wrong,8),right:product_page(right,6)}
    result=run(teto=1)
    assert len(result['produtos'])==1 and '6GB' in result['produtos'][0]['nome']
    assert Counter(calls['read'])==Counter([wrong,right])


def test_failed_recovery_never_exceeds_two_waves_or_repeats_pages(pipeline):
    state,calls,run,_,_=pipeline
    initial=[candidate(f'https://www.kabum.com.br/produto/{100001+i}/rtx-3050-6gb',origin='kabum-search') for i in range(8)]
    extra=[candidate(f'https://store-b.com/produto/rtx-3050-6gb-{i}') for i in range(8)]
    state['native']=initial;state['web']=extra
    state['blocked']={row['url'] for row in initial+extra}
    result=run(teto=2)
    assert result['produtos']==[]
    assert result['descoberta']['ondas']==2
    assert len(calls['read'])==4 and len(set(calls['read']))==4
    assert len(calls['native'])==2 and len(calls['ddg'])==len(calls['web'])==1
    assert any(urlsplit(u).hostname=='store-b.com' for u in calls['read'])
    assert result['descoberta']['orcamento_esgotado']


def test_injected_discovery_does_not_start_live_recovery(pipeline):
    state,calls,run,native,_=pipeline
    result=run(teto=1,buscar_fn=lambda query:[candidate(native)])
    assert result['produtos']==[]
    assert calls['web']==calls['ddg']==calls['native']==calls['mlb']==[]
    assert calls['read']==[native]


def test_filtered_structured_api_results_do_not_prevent_discovery_without_pages(pipeline):
    state,calls,run,_,other=pipeline
    url='https://www.mercadolivre.com.br/p/MLB123456'
    item={'title':'Placa de Vídeo NVIDIA GeForce RTX 3050 8GB', 'permalink':url,
          'price':1200,'currency_id':'BRL','available_quantity':1,'condition':'new',
          'attributes':[{'id':'BRAND','value_name':'NVIDIA'}]}
    state['mlb']=[{**candidate(url,8,origin='mlb'),'mlb':item}]
    result=run()
    assert len(result['produtos'])==1 and '6GB' in result['produtos'][0]['nome']
    assert result['criterios']['specs']['vram_gb']==6
    assert calls['native']==[] and len(calls['web'])==1
    assert calls['read']==[other]  # API rows do not consume HTTP page slots.
    assert result['descoberta']['ondas']==1


@pytest.mark.parametrize('device',['Echo Dot 5','Fire TV Stick','Kindle Paperwhite'])
def test_amazon_device_brand_does_not_force_an_exclusive_merchant(monkeypatch,device):
    title='Amazon '+device
    row={'titulo':title,'url':'https://www.mercadolivre.com.br/p/MLB123456',
         'origem':'mlb','mlb':{'title':title,'price':399.99}}
    calls=[]
    def official(query,**kwargs):
        calls.append(query);return [row]
    monkeypatch.setattr(shopping,'buscar_mlb',official)
    monkeypatch.setattr(store_discovery,'search_kabum',lambda *_a,**_k:pytest.fail('MLB should satisfy discovery'))
    monkeypatch.setattr(shopping,'buscar_ddg_chain',lambda *_a,**_k:pytest.fail('MLB should satisfy discovery'))
    monkeypatch.setattr(shopping,'buscar_web_v55',lambda *_a,**_k:pytest.fail('MLB should satisfy discovery'))
    text='Pesquise um '+title
    rows,_=shopping.buscar_com_fallback(title,texto_lojas=text)
    assert rows==[row] and calls
    assert source_priority.explicit_store(text)['id']=='amazon'  # Legacy preference remains compatible.
    assert source_priority.explicit_store(text,require_request=True) is None


@pytest.mark.parametrize('text',[
    'Compre um Echo Dot na Amazon',
    'Pesquise Amazon Echo Dot na Amazon',
    'Pesquise um Echo Dot apenas na Amazon',
    'Quero um Echo Dot no site da Amazon',
    'Pesquise https://www.amazon.com.br/dp/B123456789',
])
def test_requested_amazon_store_still_excludes_other_merchants(monkeypatch,text):
    own={'titulo':'Amazon Echo Dot 5','url':'https://www.amazon.com.br/dp/B123456789','origem':'web'}
    foreign={**own,'url':'https://www.mercadolivre.com.br/p/MLB123456'}
    calls=[]
    monkeypatch.setattr(shopping,'buscar_mlb',lambda *_a,**_k:pytest.fail('MLB must not replace requested Amazon'))
    monkeypatch.setattr(store_discovery,'search_kabum',lambda *_a,**_k:pytest.fail('KaBuM must not replace requested Amazon'))
    def web(query,**kwargs):
        calls.append(query);return [foreign,own],['controlled web']
    monkeypatch.setattr(shopping,'buscar_web_v55',web)
    monkeypatch.setattr(shopping,'buscar_ddg_chain',lambda *_a,**_k:([foreign,own],['controlled ddg']))
    rows,_=shopping.buscar_com_fallback('Echo Dot 5',texto_lojas=text)
    assert rows and all(urlsplit(row['url']).hostname=='www.amazon.com.br' for row in rows)
    assert all('site:amazon.com.br' in query for query in calls)


def test_several_requested_stores_do_not_become_one_exclusive_store():
    text='Compare fones na Shopee e no Mercado Livre'
    assert source_priority.explicit_store(text,require_request=True) is None


def test_amazon_device_in_another_store_does_not_request_amazon_exclusivity():
    assert source_priority.explicit_store('Amazon Echo em outra loja',require_request=True) is None


def test_ddg_known_product_urls_do_not_stop_independent_recovery(pipeline):
    state,calls,run,native,other=pipeline
    queries=shopping._consultas_produto(shopping.extrair_criterios(QUERY),QUERY)
    alias=native.replace('www.kabum','kabum')+'?utm_source=ddg#offer'
    state['ddg']=[{**candidate(alias),'trecho':' '.join(queries)}]
    # The result really passes the normal commercial/relevance gate; recovery
    # must discard the known URL before that gate can stop the provider chain.
    assert shopping._descoberta_suficiente(state['ddg'],queries[0])
    result=run(teto=1)
    assert len(result['produtos'])==1 and result['produtos'][0]['preco_confirmado']
    assert len(calls['ddg'])==len(calls['web'])==1
    assert Counter(calls['read'])==Counter([native,other])
    assert result['descoberta']['ondas']==2
