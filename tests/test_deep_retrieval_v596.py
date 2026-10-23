"""Fixtures and frozen captures: never evidence of live offers or original articles."""
import copy
import json
from pathlib import Path

import pytest
import shopping
import search_orchestrator as orch
import search_providers as sp
from test_research_parallel_reading import research_job


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
    monkeypatch.setattr(sp,'recuperar_feed_publicador',lambda *args: [])
    orch.pesquisar('Notícias de Ubatã Bahia', provedores=['google-news','bing'])
    assert calls.count('bing')==1


def test_sse_preserves_utf8_split_across_every_byte():
    import hermes_bridge
    parser=hermes_bridge.AcumuladorSSE()
    payload=('data: '+json.dumps({'choices':[{'delta':{'content':'Ubatã: ciência ☀'}}]},ensure_ascii=False)+'\n\n').encode()
    chunks=[]
    for byte in payload: chunks.extend(parser.alimentar(bytes([byte])))
    assert ''.join(text for _,text in chunks)=='Ubatã: ciência ☀'


def test_specific_video_metadata_and_generic_channel_rejected():
    import media_evidence as media
    assert not media._is_video('https://www.youtube.com/')
    assert not media._is_video('https://www.youtube.com/channel/UCtest')
    assert not media._is_video('https://evilyoutube.com/watch?v=abcdefghijk')
    url='https://www.youtube.com/watch?v=abcdefghijk'
    page='<script type="application/ld+json">'+json.dumps({'@graph':[{
        '@type':'VideoObject','url':url,'name':'NASA James Webb',
        'author':{'name':'NASA'},'duration':'PT2M','thumbnailUrl':'https://images.nasa.gov/webb.jpg'}]})+'</script>'
    records=media.extrair_midia(page,'https://science.nasa.gov/webb/','NASA Webb')
    video=next(item for item in records if item['type']=='video')
    assert video['metadata_state']=='METADATA_READ'
    assert video['duration']=='PT2M' and video['publisher']=='NASA'
    assert video['analysis_state']=='not_analyzed' and not video['evidence']


def test_media_topic_gate_rejects_irrelevant_images():
    import media_evidence as media
    records=[{'type':'image','title':'Ponte Estaiada São Paulo','url':'https://example.org/bridge.jpg'},
             {'type':'image','title':'Logotipo da loja','url':'https://example.org/logo.jpg'},
             {'type':'video','title':'Ponte Estaiada São Paulo','url':'https://www.youtube.com/watch?v=abcdefghijk'}]
    result=media.relevant_media(records,'Imagens licenciadas da Ponte Estaiada em São Paulo')
    assert len(result)==1 and result[0]['title']=='Ponte Estaiada São Paulo'


def test_original_feed_is_discovered_not_guessed_or_read():
    lead={'publisher_url':'https://jornal.example','titulo':'Ubatã inaugura biblioteca municipal para estudantes',
          'url':'https://news.google.com/rss/articles/opaque'}
    calls=[]
    def fetch(url,kind):
        calls.append((url,kind))
        if kind=='html':return url,'<link rel="alternate" type="application/rss+xml" href="/noticias.xml">'
        return url,'<rss><channel><item><title>Ubatã inaugura biblioteca municipal para estudantes</title><link>https://jornal.example/ubata-biblioteca</link><pubDate>Fri, 23 Oct 2026 10:00:00 GMT</pubDate></item></channel></rss>'
    records=sp.recuperar_feed_publicador(lead,fetch)
    assert len(calls)==2 and calls[-1][0]=='https://jornal.example/noticias.xml'
    assert records[0]['url']=='https://jornal.example/ubata-biblioteca'
    assert records[0]['source_recovery']['state']=='original_candidate'
    assert not records[0].get('texto_lido') and records[0]['trecho']==''


def test_science_fronts_preserve_topic_and_extracted_sections():
    import research_agents as ra
    import academic_research as ar
    fronts=ra._subconsultas_unicas('Compare estudos sobre baterias de sódio e lítio: métodos e limitações',4)
    assert all('bater' in q for q in fronts)
    assert not any(q in ('métodos','lítio','limitações') for q in fronts)
    sections=ar.scientific_sections({'final':'https://paper.example/open','secoes':[
        {'titulo':'Methods','texto':'Measured 32 samples.','pagina':3},
        {'titulo':'Limitations','texto':'Only one temperature.'}]})
    assert sections[0]['kind']=='methods' and sections[0]['page']==3
    assert sections[1]['kind']=='limitations' and sections[1]['page'] is None


def test_jdui_research_sources_and_exports_validate_together():
    import research_view
    import jdui
    view=research_view.build_view({'id':'rj-v596-test','objetivo':'Documentação Python','status':'concluida'},
        [{'titulo':'Python documentation','url':'https://docs.python.org/','texto_lido':True,'trecho':'Python'}])
    assert jdui.validar_mensagem(view)[0]
    assert {'filecard','sources'} <= {b.get('component') for b in view['blocks']}
    source=next(b for b in view['blocks'] if b.get('component')=='sources')['props']['items'][0]
    assert source['leitura']=='READ'


def test_commons_separates_thumbnail_from_original_file():
    import media_evidence as media
    records=media.discover_search_media([{'titulo':'Ponte Estaiada São Paulo',
        'origem':'commons','tipo':'imagem','url':'https://thumb.wikimedia.org/thumb.jpg',
        'meta':{'original_url':'https://upload.wikimedia.org/original.jpg',
                'thumb_url':'https://thumb.wikimedia.org/thumb.jpg','largura':1200,'altura':750},
        'license':'CC0'}])
    assert records[0]['url']=='https://upload.wikimedia.org/original.jpg'
    assert records[0]['thumb']=='https://thumb.wikimedia.org/thumb.jpg'
    assert records[0]['rights']=='CC0' and not records[0]['evidence']


def test_documentation_navigation_links_do_not_become_media_cards(research_job):
    import research_agents as ra
    db,job=research_job
    job['objetivo']='Documentação oficial Python asyncio TaskGroup'
    ra._agregar_midia(db,job,[{'type':'document','url':'https://docs.python.org/3/contents.html'},
                             {'type':'document','url':'https://docs.python.org/3/manual.pdf'}])
    assert [m['url'] for m in job['midia']]==['https://docs.python.org/3/manual.pdf']


def test_read_paper_does_not_render_reference_links_as_duplicate_file_gallery():
    import research_view
    summary={'id':'rj-v596-paper','objetivo':'Compare estudos sobre baterias',
             'midia':[{'type':'document','title':'Reference link','url':'https://example.org/reference.pdf'}]}
    view=research_view.build_view(summary,[{'titulo':'Paper','url':'https://example.org/paper.pdf',
        'doi':'10.1234/paper','texto_lido':True,'full_text_fetched':True,'trecho':'Bounded paper excerpt.'}])
    components=[b.get('component') for b in view['blocks']]
    assert 'sources' in components and 'media' not in components
    assert len(summary['midia'])==1  # Discovery remains available for provenance/export.
