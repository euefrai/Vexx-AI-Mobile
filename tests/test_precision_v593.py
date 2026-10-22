from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess

import pytest
import academic_research as ar
import pc_agent
import query_intelligence as qi
import research
import research_agents as ra
import research_view
import search_orchestrator as orch
import search_providers as sp
import search_verticals as verticals
import shopping
import web_extract
import jdui

NOW=datetime(2026,10,22,12,tzinfo=timezone.utc)


@pytest.mark.parametrize('query,location,region',[
 ('Últimas notícias de Salvador.','Salvador',None),
 ('O que aconteceu em Ubatã, Bahia, nos últimos sete dias?','Ubatã','bahia'),
 ('Acontecimentos em Feira de Santana recentemente?','Feira de Santana',None)])
def test_local_request_keeps_geography_and_dates(query,location,region):
    r=qi.analyze(query,now=NOW)
    assert r['parameters']['location']==location
    assert r['parameters'].get('region')==region
    assert r['parameters']['start_date']=='2026-10-15'


def test_air_request_does_not_infer_passengers_or_airport():
    r=qi.analyze('Passagens de Manaus (MAO) para Brasília (BSB) daqui a sete dias',now=NOW)
    assert r['domain']=='air_travel' and r['parameters']['destination']=='Brasília (BSB)'
    assert r['parameters']['departure_date']=='2026-10-29' and 'adults' not in r['parameters']


@pytest.mark.parametrize('title',[ 'Capa de proteção para notebook Lenovo X90', 'Notebook Lenovo X80 especificações'])
def test_model_or_accessory_cannot_win_by_name_overlap(title):
    q='Notebook Lenovo X90 especificações'
    assert not orch._util_para_pedido({'titulo':title,'trecho':''},orch._termos_correspondencia(q),q)


def test_consumption_inflection_does_not_drop_counterevidence():
    q='Consumo do processador C62'
    assert orch._util_para_pedido({'titulo':'Teste de laboratório','trecho':'O processador C62 consome 95 W em jogos.'},orch._termos_correspondencia(q),q)


def test_post_read_page_cannot_keep_discovery_title_relevance():
    f=research._fonte_de({'titulo':'Jardins','texto':'Flores em parques municipais.','lida':True},
                        {'titulo':'Notebook Lenovo X90','url':'https://example.org/wrong'},'Notebook Lenovo X90')
    assert f['relevante'] is False


@pytest.mark.parametrize('pub,event,eligible',[
 ('2026-10-22','2020-10-29',False),('2020-10-22','2026-10-29',True),('2026-10-22',None,False)])
def test_event_date_is_not_publication_date(pub,event,eligible):
    r=qi.analyze('Eventos em João Pessoa nas próximas duas semanas',now=NOW)
    s={'titulo':'Evento em João Pessoa','trecho':'Programação cultural','publicado_em':pub,'event_date':event}
    assert verticals.assess(r,s)['eligible'] is eligible


def test_homonymous_municipality_is_not_a_local_report():
    r=qi.analyze('Notícias em São Domingos, Goiás, nos últimos sete dias',now=NOW)
    s={'titulo':'Notícias de São Domingos Maranhão','trecho':'','publicado_em':'2026-10-20'}
    assert 'SOURCE_MISMATCH' in verticals.assess(r,s)['reasons']


def test_structured_event_survives_extraction_and_is_not_confirmed_inventory():
    html='<script type="application/ld+json">'+json.dumps({'@type':'MusicEvent','name':'Concerto público','startDate':'2026-10-29T19:00:00-03:00','location':{'name':'Teatro em João Pessoa'},'organizer':{'name':'Orquestra local'}})+'</script>'
    meta=web_extract.extrair_metadados(html)
    r=qi.analyze('Eventos em João Pessoa nas próximas duas semanas',now=NOW)
    s={'titulo':'Concerto em João Pessoa','structured':meta['structured']}
    contract=verticals.assess(r,s)
    assert contract['eligible'] and contract['verification']=='DECLARED_EVENT'
    assert contract['data']['organizer']=='Orquestra local'
    assert 'price' not in contract['data']


def test_travel_fare_requires_direction_date_passengers_and_keeps_inventory_unknown():
    r=qi.analyze('Voos de Manaus para Brasília daqui a sete dias para um adulto',now=NOW)
    s={'titulo':'Voos Manaus Brasília','structured':[{'kind':'air_travel','departureAirport':'Manaus','arrivalAirport':'Brasília','departureTime':'2026-10-29T09:00:00-03:00','declared_price':'800','currency':'BRL','adults':1}]}
    v=verticals.assess(r,s)
    assert v['verification']=='MATCHED_DECLARED_FARE' and v['data']['inventory_state']=='not_verified'
    s['structured'][0]['departureTime']='2026-11-01T09:00:00-03:00'
    assert 'price' not in verticals.assess(r,s)['data']
    s['structured'][0].update(departureAirport='Brasília',arrivalAirport='Manaus')
    assert 'price' not in verticals.assess(r,s)['data']


def test_tourism_page_does_not_become_a_travel_route_from_incidental_mentions():
    r=qi.analyze('Voos de Salvador para São Paulo daqui a sete dias',now=NOW)
    source={'titulo':'O que fazer em Salvador: passeios imperdíveis','trecho':'Chegue de voos para Salvador. Existem ligações para São Paulo. Conheça restaurantes.'}
    assert 'SOURCE_MISMATCH' in verticals.assess(r,source)['reasons']


def test_news_feed_is_discovery_not_a_page_read(monkeypatch):
    xml='<rss><channel><item><title>Notícia de teste</title><link>https://news.google.com/rss/articles/fixture</link><description>Resumo</description><pubDate>Wed, 21 Oct 2026 12:00:00 GMT</pubDate><source>Veículo de teste</source></item></channel></rss>'
    monkeypatch.setattr(sp,'_baixar',lambda *args,**kwargs:('https://news.google.com/rss/search',xml))
    source=sp.buscar_google_news('notícias de teste')[0]
    monkeypatch.setattr(research,'baixar',lambda *a,**kw:pytest.fail('feed must not pretend article read'))
    rec=research._recuperar_um(source,None,1)
    assert rec['lida'] is False and rec['content_scope']=='feed_metadata'
    assert source['url'].startswith('https://news.google.com/')


def paper():
    return {'title':'Quantum optical test methods','titulo':'Quantum optical test methods',
            'url':'https://example.org/paper','pdf_url':'https://example.org/paper.pdf',
            'open_access':True,'doi':'10.1234/example','metadata_source':'academic_provider',
            'abstract':'Quantum optical test methods abstract.','content_scope':'abstract_only'}


def test_open_text_must_match_identity_and_sufficient_text():
    p=paper();calls=[]
    def fetch(record,timeout):
        calls.append((record['url'],timeout))
        return {'texto':p['title']+' Methods and results. '*100,'lida':True,'final':record['url']}
    r=ar.read_open_text(p,1.5,fetch)
    assert r['full_text_fetched'] and r['content_scope']=='document_text' and calls==[(p['pdf_url'],1.5)]
    assert not ar.read_open_text(p,1,lambda *a:{'texto':'unrelated gardening '*100,'lida':True}).get('full_text_fetched')
    assert ar.read_open_text({**p,'open_access':False},1,lambda *a:pytest.fail('not declared OA')) is None


def test_open_pdf_private_host_falls_back_safely():
    p=paper();p['pdf_url']='http://127.0.0.1/private.pdf'
    r=research._recuperar_um(p,None,0.5)
    assert not r.get('full_text_fetched') and r['content_scope']=='abstract_only' and r['oa_attempt']!='read_identity_matched'


def test_full_text_scope_survives_deep_checkpoint(tmp_path,monkeypatch):
    db=pc_agent.open_db(tmp_path/'evidence.sqlite3')
    job=ra.criar_job(db,'qa','Quantum optical test methods',manual='rapida')
    p=paper()
    monkeypatch.setattr(research,'_recuperar_um',lambda *a,**kw:{'titulo':p['title'],'texto':p['title']+' Methods and results. '*100,'full_text_fetched':True,'full_text_url':p['pdf_url'],'content_scope':'document_text','lida':True})
    ev=ra.agente_analista(db,job,{'alvo':job['objetivo']},[p])
    assert ev and ev[0]['full_text_fetched'] and ev[0]['texto_lido']
    saved=ra.listar_evidencias(db,'qa',job['id'])[0]
    assert saved['content_scope']=='document_text' and saved['full_text_url']==p['pdf_url']
    assert 'Nenhum texto completo foi obtido' not in ra.agente_sintetizador(db,job,ev,[])['texto']
    assert ra.listar_evidencias(db,'other',job['id'])==[]
    db.close()


def test_unread_sources_do_not_trigger_contradiction_searches(tmp_path):
    db=pc_agent.open_db(tmp_path/'unread.sqlite3');job=ra.criar_job(db,'qa','Bateria X capacidade',manual='rapida')
    ev=[{'id':'one','titulo':'Bateria X','trecho':'Capacidade de 500 W','access_state':'snippet_only'},
        {'id':'two','titulo':'Bateria X','trecho':'Capacidade de 600 W','access_state':'snippet_only'}]
    assert ra.investigar_contradicoes_job(db,job,ev)==[]
    db.close()


@pytest.mark.parametrize('query,name,code',[
 ('geladeira 400 litros','Geladeira 300 litros','capacidade_l_diferente'),
 ('furadeira 220 V','Furadeira 127 V','tensao_v_diferente'),
 ('geladeira','Lavadora de roupas','tipo_produto_diferente'),
 ('geladeira','Capa para geladeira','acessorio')])
def test_shopping_constraints_are_not_weakened(query,name,code):
    inside,out=shopping.aplicar_filtros([{'nome':name,'specs':{}}],shopping.extrair_criterios(query))
    assert not inside and code in out[0]['excluido_codigos']


def test_scientific_source_card_uses_publication_not_access_time():
    c=research_view.source_card({**paper(),'authors':['A. Teste'],'year':2024,'acessado_em':'2026-10-22','trecho':'Abstract','access_state':'metadata_only'})
    assert c['data']=='2024' and c['autores']=='A. Teste' and 'Somente resumo' in c['escopo']


def test_contextual_source_python_js_parity_and_safe_links():
    props={'items':[{'titulo':'Evento de teste','url':'https://example.org/event','publicador':'Veículo','autores':'Ana','doi':'10.1234/example',
                     'imagem':'javascript:alert(1)','texto_url':'https://example.org/paper.pdf','detalhes':['Local: teste'],'data_evento':'2026-10-29'}]}
    m={'version':jdui.VERSION,'blocks':[{'type':'ui','component':'sources','props':props}]}
    ok,python,_=jdui.validar_mensagem(m);assert ok
    script="global.window=global;global.location={href:'https://app.example/'};require('./public/jdui.js');process.stdout.write(JSON.stringify(JDUI.validateMessage("+json.dumps(m)+").msg));"
    js=json.loads(subprocess.check_output(['node','-e',script],cwd=Path(__file__).resolve().parents[1]))
    assert js==python and not python['blocks'][0]['props']['items'][0]['imagem']


def test_licence_urls_do_not_spend_product_download_budget():
    assert shopping.classificar_candidato({'url':'https://creativecommons.org/licenses/by-sa/4.0/'})=='IRRELEVANT'


def test_optional_oa_does_not_mask_programming_errors():
    def broken(*a): raise NameError('fixture programming defect')
    with pytest.raises(NameError): ar.read_open_text(paper(),1,broken)


def test_irrelevant_academic_metadata_does_not_trigger_pdf_download(tmp_path,monkeypatch):
    db=pc_agent.open_db(tmp_path/'pdf-filter.sqlite3')
    monkeypatch.setattr(research,'_recuperar_um',lambda *a:pytest.fail('irrelevant PDF must not be downloaded'))
    r=research.pesquisa_rapida(db,'qa','Pesquise estudos científicos sobre Quantum optical methods',buscar_fn=lambda q:[{**paper(),'titulo':'História da jardinagem','abstract':'Jardins e flores','trecho':'Jardins e flores'}])
    assert r['fontes_uteis']==0
    db.close()


def test_useful_later_page_is_not_lost_at_source_limit(tmp_path):
    db=pc_agent.open_db(tmp_path/'quick.sqlite3')
    results=[{'titulo':'Bateria Z12','url':'https://example.org/'+str(i),'trecho':'Bateria Z12 capacidade nominal'} for i in range(3)]
    def read(url):
        return {'titulo':'Bateria Z12' if url.endswith('2') else 'Jardim de rosas','texto':'Bateria Z12 capacidade nominal.' if url.endswith('2') else 'Rosas em parques municipais.'}
    r=research.pesquisa_rapida(db,'qa','Bateria Z12 capacidade nominal',buscar_fn=lambda q:results,recuperar_fn=read,max_fontes=1)
    assert r['fontes'][0]['url'].endswith('2') and r['fontes_uteis']==1
    db.close()
