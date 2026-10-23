"""V5.9.5 regression contracts. All fixtures; not external offers or inventory."""
from datetime import datetime, timezone, timedelta
import json

import pytest
import academic_research as ar
import query_intelligence as qi
import search_verticals as sv
import search_orchestrator as orch
import search_providers as sp
import research_agents as ra
import research_view
import shopping
from test_research_parallel_reading import research_job

NOW = datetime(2026, 10, 23, 12, tzinfo=timezone.utc)


@pytest.mark.parametrize('product_request', ['celular Galaxy A56', 'notebook Lenovo', 'tênis de basquete',
    'fone Bluetooth', 'geladeira', 'máquina de lavar', 'livro', 'furadeira',
    'pastilha de freio', 'resistor', 'bola de basquete', 'sofá', 'cimento'])
def test_unrelated_tv_never_becomes_exact_match_or_alternative(product_request):
    criteria = shopping.extrair_criterios('Preço de ' + product_request)
    product = {'id': 'tv', 'nome': 'Smart TV Samsung Crystal UHD', 'preco': 1000,
               'moeda': 'BRL', 'preco_confirmado': True, 'specs': {}}
    inside, outside = shopping.aplicar_filtros([product], criteria)
    assert not inside and outside
    assert 'tipo_produto_diferente' in outside[0]['excluido_codigos']
    assert shopping.separar_alternativas(outside, criteria) == []


def test_same_category_variant_remains_an_explicit_alternative():
    criteria = shopping.extrair_criterios('Celular Galaxy A56 256 GB')
    product = {'id': 'a36', 'nome': 'Celular Samsung Galaxy A36 256 GB', 'preco': 1000,
               'moeda': 'BRL', 'preco_confirmado': True, 'specs': {}}
    inside, outside = shopping.aplicar_filtros([product], criteria)
    assert not inside and shopping.separar_alternativas(outside, criteria)


def test_shopping_downloads_requested_model_before_other_individual_items(research_job, monkeypatch):
    import research
    monkeypatch.setattr(research, '_ips_globais', lambda host: None)
    db, job = research_job
    candidates = [{'titulo':f'Celular Samsung Galaxy {model} 256 GB',
                   'url':f'https://shop.example/produto/galaxy-{model.lower()}', 'trecho':model}
                  for model in ('S25','A56')]
    calls = []
    def download(url):
        calls.append(url)
        data = {'@type':'Product', 'name':'Celular Samsung Galaxy A56 256 GB',
                'brand':{'name':'Samsung'}, 'offers':{'@type':'Offer','price':'1500.10',
                'priceCurrency':'BRL','url':url,'availability':'https://schema.org/InStock'}}
        return {'final':url,'texto':'<html><head><title>Galaxy A56 256 GB</title></head><body>'
                '<script type="application/ld+json">'+json.dumps(data)+'</script></body></html>'}
    result = shopping.pesquisar(db, job['owner'], 'Celular Samsung Galaxy A56 256 GB',
        buscar_fn=lambda q:candidates, baixar_fn=download, teto_paginas=1, usar_cache=False)
    assert calls[0].endswith('/galaxy-a56')
    assert result['source_trace']
    assert all(not p['stock_independently_verified'] for p in result['source_trace'])


def test_capabilities_are_json_safe_declarations_not_e2e_success():
    caps = sp.capacidades()
    json.dumps(caps)
    assert 'price' not in caps['ddg']['declared_fields']
    assert 'doi' in caps['crossref']['declared_fields']
    assert all(not c['e2e_verified_fields'] for c in caps.values())


def test_provider_block_is_not_retried_in_same_process(monkeypatch):
    import research
    monkeypatch.setattr(research, '_circuito', {})
    calls = []
    def blocked(*args, **kwargs):
        calls.append(True)
        raise sp.ErroProvedor('fixture refused', 'bloqueado')
    monkeypatch.setitem(sp.PROVEDORES, 'fixture-block', {'fn': blocked, 'tipo':'pagina'})
    for _ in range(2):
        with pytest.raises(sp.ErroProvedor):
            sp.buscar('fixture-block', 'query')
    assert len(calls) == 1


def test_evaluation_dataset_rejects_path_ids_and_duplicate_ids(tmp_path):
    from tools.evaluate_live_research import load_cases
    path = tmp_path/'dataset.json'
    for cases in ([['../escape','research','query']], [['same','research','query']]*2):
        path.write_text(json.dumps({'cases':cases}), encoding='utf-8')
        with pytest.raises(ValueError):
            load_cases(path)


def test_universal_dataset_covers_existing_routes():
    from tools.evaluate_live_research import load_cases
    from pathlib import Path
    cases = load_cases(Path(__file__).resolve().parents[1]/'benchmarks/universal_sources_v595.json')
    assert len(cases) == 16
    assert {'products','flights','events','science','documentation','currency','weather','images','videos','pdfs','deep_research'} <= {c[0] for c in cases}


def test_hours_and_city_state_are_preserved():
    req = qi.analyze('Notícias de Ubatã/BA nas últimas 24 horas', now=NOW)
    assert req['parameters']['location'] == 'Ubatã'
    assert req['parameters']['region'] == 'BA'
    start = datetime.fromisoformat(req['parameters']['start_at'])
    end = datetime.fromisoformat(req['parameters']['end_at'])
    assert end - start == timedelta(hours=24)
    assert 'article_text' in req['required_data']


@pytest.mark.parametrize('published,expected', [
    ('2026-10-22T13:00:00Z', True), ('2026-10-22T10:00:00Z', False), ('2026-10-23', False), ('', False)])
def test_news_needs_an_actual_timestamp_for_exact_hour_window(published, expected):
    req = qi.analyze('Notícias de Ubatã/BA nas últimas 24 horas', now=NOW)
    source = {'titulo': 'Ubatã Bahia inaugura ponte municipal', 'url': 'https://example.org/ponte',
              'trecho': 'Ubatã na Bahia abriu a ponte.', 'publicado_em': published}
    assert sv.assess(req, source)['eligible'] is expected


def test_news_index_is_not_a_recent_article():
    req = qi.analyze('Últimas notícias de Salvador', now=NOW)
    source = {'titulo': 'Últimas notícias de Salvador', 'url': 'https://example.org/noticias/',
              'trecho': 'Salvador', 'publicado_em': NOW.isoformat()}
    assert not sv.assess(req, source)['eligible']


def test_rss_cannot_displace_original_article_by_earlier_feed_date():
    title = 'Ubatã Bahia inaugura nova ponte municipal'
    feed = {'titulo': title, 'url': 'https://news.google.com/rss/articles/test',
            'content_scope': 'feed_metadata', 'publicado_em': '2026-10-20'}
    original = {'titulo': title, 'url': 'https://example.org/ponte', 'publicado_em': '2026-10-21'}
    unique, discarded = orch.deduplicar([feed, original])
    assert len(unique) == 1 and unique[0]['url'] == original['url']


def test_feed_only_search_continues_to_original_discovery(monkeypatch):
    called = []
    def search(name, query, **kwargs):
        called.append(name)
        item = {'titulo': 'Ubatã inaugura ponte', 'trecho': 'Ubatã ponte', 'tipo': 'noticia',
                'publicado_em': NOW.isoformat(), 'url': 'https://example.org/ponte'}
        return [{**item, 'url': 'https://news.google.com/rss/articles/test', 'content_scope': 'feed_metadata'}] if name == 'google-news' else [item]
    monkeypatch.setattr(sp, 'buscar', search)
    orch.pesquisar('Notícias de Ubatã', provedores=['google-news','bing-news'], orcamento={'max_consultas': 1})
    assert called == ['google-news', 'bing-news']


@pytest.mark.parametrize('period,day', [('hoje', '2026-10-23'), ('amanhã', '2026-10-24'), ('depois de amanhã', '2026-10-25')])
def test_relative_travel_dates_do_not_become_destination(period, day):
    req = qi.analyze(f'Voos de Salvador para São Paulo {period} para um adulto', now=NOW)
    assert req['parameters']['destination'] == 'São Paulo'
    assert req['parameters']['departure_date'] == day
    assert req['parameters']['adults'] == 1


def test_expired_fare_is_never_a_current_price():
    req = qi.analyze('Voos de Salvador para São Paulo amanhã para um adulto', now=NOW)
    source = {'titulo': 'Voos Salvador São Paulo', 'url': 'https://example.org/flight',
              'structured': [{'kind':'air_travel','departureAirport':'Salvador','arrivalAirport':'São Paulo',
                              'departureTime':'2026-10-24T12:00:00-03:00','adults':1,'declared_price':'100.00',
                              'currency':'BRL','validThrough':'2026-10-01'}]}
    result = sv.assess(req, source)
    assert 'price' not in result['data'] and 'EXPIRED_FARE' in result['reasons']
    source['structured'][0]['validThrough'] = '2026-10-25'
    result = sv.assess(req, source)
    assert result['retrieval_state'] == 'PRICE_FOUND'
    assert result['data']['price'] == '100.00' and result['data']['inventory_state'] == 'not_verified'


@pytest.mark.parametrize('question,domain,destination', [
    ('Passagem de Salvador para São Paulo amanhã de avião', 'air_travel', 'São Paulo'),
    ('Passagem de ônibus de Salvador para Feira de Santana amanhã', 'bus_travel', 'Feira de Santana'),
    ('Ônibus de Itabuna para Salvador amanhã', 'bus_travel', 'Salvador')])
def test_singular_ticket_and_regional_bus_routes(question, domain, destination):
    req = qi.analyze(question, now=NOW)
    assert req['domain'] == domain and req['parameters']['departure_date'] == '2026-10-24'
    assert req['parameters']['destination'] == destination


def test_oa_html_is_read_without_claiming_whole_document_or_pdf():
    record = {'titulo':'Quantum optical methods experiment', 'doi':'10.1234/test',
              'open_access': True, 'landing_url':'https://example.org/open-article'}
    calls = []
    def fetch(candidate, timeout):
        calls.append(candidate)
        return {'texto':'Quantum optical methods experiment 10.1234/test ' * 40, 'lida':True,
                'final':candidate['url'], 'secoes':[{'titulo':'Methods','texto':'Bounded section.'}]}
    result = ar.read_open_text(record, 2, fetch)
    assert len(calls) == 1 and not calls[0]['pdf_expected']
    assert result['full_text_format'] == 'html' and not result['full_document_read']
    card = research_view.source_card({**record, **result, 'url':record['landing_url']})
    assert 'HTML' in card['escopo'] and 'PDF' not in card['escopo']
    record['open_access'] = False
    assert ar.read_open_text(record, 2, lambda *a: pytest.fail('closed document')) is None


def test_openalex_does_not_attach_repository_licence_to_closed_landing():
    record = ar.normalize_openalex({'title':'Quantum optical methods experiment',
        'primary_location':{'landing_page_url':'https://closed.example/article','is_oa':False},
        'locations':[{'landing_page_url':'https://repo.example/open','is_oa':True,'license':'cc-by'}]}, 'https://api.openalex.org/works')
    assert record['open_access'] and record['landing_url'] == 'https://repo.example/open'


def test_document_format_and_bounded_scope_survive_sqlite(research_job):
    db, job = research_job
    source = {'titulo':'Open HTML study', 'url':'https://example.org/open', 'texto_lido':True,
              'full_text_fetched':True,'full_text_format':'html','extraction_scope':'bounded_text',
              'full_document_read':False, 'sections':[{'title':'Methods','text':'Bounded section.'}]}
    ra.registrar_evidencia(db, job, source, 'The extracted passage.')
    restored = ra.listar_evidencias(db, job['owner'], job['id'])[0]
    assert restored['full_text_format'] == 'html' and not restored['full_document_read']
    assert restored['sections'][0]['title'] == 'Methods'
    assert 'HTML' in research_view.source_card(restored)['escopo']


def test_partial_required_fields_are_not_treated_as_covered(research_job):
    db, job = research_job
    ra.montar_plano(db, job)
    step = next(s for s in job['plano'] if s['tipo'] == 'ler')
    step['_evidencias'] = [{'id':'route','texto_lido':True,'vertical':{'data_complete':False}}]
    assert ra._lacunas(job)
    step['_evidencias'][0]['vertical']['data_complete'] = True
    assert not ra._lacunas(job)


def test_source_card_excerpt_and_travel_disclaimer_survive_validation():
    import jdui
    item = {'titulo':'Voo declarado', 'url':'https://example.org/flight','texto_lido':True,
            'trecho':'x '*148+'1234567890 unidades.',
            'vertical':{'kind':'air_travel','verification':'MATCHED_DECLARED_FARE',
                'data':{'price':'100.10','currency':'BRL','departureAirport':'Salvador','arrivalAirport':'São Paulo',
                        'departureTime':'2026-10-24T12:00:00-03:00','arrivalTime':'2026-10-24T14:00:00-03:00','provider':'Fixture'}}}
    card = research_view.source_card(item)
    message = {'version':jdui.VERSION,'blocks':[{'type':'ui','component':'sources','props':{'items':[card]}}]}
    ok, normalized, _ = jdui.validar_mensagem(message)
    assert ok
    displayed = normalized['blocks'][0]['props']['items'][0]
    assert '1234' not in displayed['trecho']
    assert 'não confirmada' in displayed['detalhes'][0]
    assert '100.10 BRL' in displayed['detalhes'][1]


def test_undated_news_is_replaced_before_it_can_be_evidence(research_job):
    db, job = research_job
    job['objetivo'] = 'Notícias inteligência artificial nas últimas 24 horas'
    sources = [{'id':x, 'titulo':job['objetivo'], 'url':f'https://example.org/{x}', 'trecho':job['objetivo']} for x in ('undated','dated')]
    def read(url):
        return {'titulo':job['objetivo'],'texto':job['objetivo']+' Relatório publicado.', 'texto_lido':True,
                'metadados':{'publicado_em':(datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat() if url.endswith('/dated') else ''}}
    evidence = ra.agente_analista(db, job, {'alvo':job['objetivo']}, sources, read, teto_paginas=1)
    assert len(evidence) == 1 and evidence[0]['url'].endswith('/dated')


def test_planner_keeps_hour_window_and_city_instead_of_rendered_range(research_job):
    db, job = research_job
    job['objetivo'] = 'Notícias de Ubatã/BA nas últimas 24 horas'
    ra.montar_plano(db, job)
    search = next(s for s in job['plano'] if s['tipo'] == 'busca')
    request = qi.analyze(search['alvo'], now=NOW)
    assert request['parameters']['location'] == 'Ubatã'
    assert 'start_at' in request['parameters']


def test_resume_keeps_original_request_time_for_source_validation(research_job):
    db, job = research_job
    job['objetivo'] = 'Notícias de Ubatã/BA nas últimas 24 horas'
    job['ajustes']['request'] = qi.analyze(job['objetivo'], now=NOW)
    source = {'id':'old','titulo':'Ubatã Bahia inaugura ponte municipal',
              'url':'https://example.org/ponte', 'trecho':'Ubatã na Bahia inaugura ponte'}
    def read(url):
        return {'titulo':source['titulo'], 'texto':source['trecho'], 'texto_lido':True,
                'metadados':{'publicado_em':'2026-10-22T11:30:00Z'}}
    assert ra.agente_analista(db, job, {'alvo':job['objetivo']}, [source], read) == []
