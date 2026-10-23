"""V5.9.7 contracts; fixtures do not count as external retrieval."""
import json
import pytest
import research_agents as ra
import evidence_graph as eg
import web_extract
from test_research_parallel_reading import research_job
from test_research_synthesis import context, evidence, EXCERPT


def test_feed_discovery_does_not_consume_original_page_budget(research_job):
    db,job=research_job
    job['objetivo']='Notícias de Ubatã Bahia'
    job['orcamento']['paginas']=1
    leads=[{'titulo':'Notícias Ubatã Bahia','url':f'https://news.google.com/rss/articles/{i}',
            'content_scope':'feed_metadata','trecho':'Ubatã Bahia'} for i in range(5)]
    original={'titulo':'Ubatã Bahia inaugura biblioteca','url':'https://local.example/biblioteca',
              'source_recovery':{'method':'publisher_feed_autodiscovery','state':'original_candidate'}}
    calls=[]
    def fetch(url):
        calls.append(url)
        return {'titulo':original['titulo'],'texto':'Ubatã na Bahia inaugurou uma biblioteca pública municipal para seus moradores.',
                'final':url,'texto_lido':True}
    evidence=ra.agente_analista(db,job,{'alvo':job['objetivo']},leads+[original],fetch,teto_paginas=1)
    assert calls==[original['url']]
    assert job['usados']['paginas']==1
    assert any(e['url']==original['url'] and e['texto_lido'] for e in evidence)
    assert all(not e['texto_lido'] for e in evidence if e.get('content_scope')=='feed_metadata')


def test_empty_unread_documents_are_not_duplicate_publications():
    result=eg.analisar_independencia({'url':'https://a.example/story','texto':''},
                                   {'url':'https://b.example/other','texto':''})
    assert result['relacao']!='DUPLICATES'


def test_found_snippet_with_exact_quantity_does_not_support_claim():
    claim={'texto':'O processador modelo X tem TDP de 65 W.',
           'condicoes':{'quantidades':eg.extrair_quantidades('65 W')}}
    snippet={'id':'feed','trecho':claim['texto'],'texto_lido':False,'content_scope':'feed_metadata'}
    assert eg.verificar_claim(claim,[snippet])['estado']!='SUPPORTED'


@pytest.mark.parametrize('article_type', ['NewsArticle', ['Article', 'NewsArticle']])
def test_article_metadata_takes_priority_over_publisher_graph(article_type):
    url='https://news.example/story'
    nodes=[{'@type':'WebSite','url':url,'name':'Publisher'},
           {'@type':article_type,'url':url,'headline':'Original article',
            'datePublished':'2026-10-21T06:40:00','dateModified':'2026-10-22T12:00:00'}]
    html='<script type="application/ld+json">'+json.dumps({'@graph':nodes})+'</script>'
    meta=web_extract.extrair_metadados(html,url)
    assert meta['titulo']=='Original article'
    assert meta['publicado_em']=='2026-10-21T06:40:00'


def test_modification_or_unrelated_time_is_not_publication():
    html='<time datetime="2026-10-23">Current date</time><script type="application/ld+json">'+json.dumps(
        {'@type':'Article','headline':'Article title','dateModified':'2026-10-22'})+'</script>'
    assert web_extract.extrair_metadados(html)['publicado_em']==''


def test_blocked_writing_preserves_evidence_and_requires_explicit_resume(context):
    db, job = context
    ra.registrar_evidencia(db, job, evidence(), EXCERPT)
    job['plano']=[{'id':'s1','tipo':'sintetizar','status':'pendente','alvo':job['objetivo']}]
    ra.salvar_job(db, job)
    calls=[]
    class RateLimit(Exception):
        codigo='rate_limit'
    def writer(*args):
        calls.append(1)
        raise RateLimit('private provider request must not be persisted')
    first=ra.executar(db,job['id'],job['owner'],[],sintetizar_fn=writer)
    assert first['status']=='interrompida'
    saved=ra.carregar_job(db,job['owner'],job['id'])
    assert saved['usados']['research_outcome']['state']=='blocked'
    assert saved['usados']['research_outcome']['provider_code']=='rate_limit'
    ra._restore_context_checkpoint(db, saved)
    assert EXCERPT in saved['sintese']['texto']
    ra.executar(db,job['id'],job['owner'],[],sintetizar_fn=writer)
    assert len(calls)==1
    assert len(ra.listar_evidencias(db,job['owner'],job['id']))==1
    ra.preparar_retomada(db,job['owner'],job['id'])
    ra.executar(db,job['id'],job['owner'],[],sintetizar_fn=writer)
    assert len(calls)==2
    assert len(ra.listar_evidencias(db,job['owner'],job['id']))==1


def test_metadata_only_never_reports_complete():
    outcome=ra._completion_outcome({'sintese':{},'achados':[]},
        [{'texto_lido':False,'content_scope':'feed_metadata','trecho':'Found'}],[])
    assert outcome['state']=='partial' and outcome['read_sources']==0


def test_blocked_outcome_is_visible_in_research_view():
    import research_view
    view=research_view.build_view({'id':'rj-test','status':'interrompida',
        'usados':{'research_outcome':{'state':'blocked'}}},[])
    assert any('bloqueada pelo provedor' in b.get('content','') for b in view['blocks'])


def test_pdf_reader_stops_extracting_after_character_budget(monkeypatch):
    import sys
    import types
    import docs_agent
    calls=[]
    class Page:
        def extract_text(self):
            calls.append(1)
            return 'Measured text. '*1000
    reader=types.SimpleNamespace(metadata=None,pages=[Page() for _ in range(30)])
    monkeypatch.setitem(sys.modules,'pypdf',types.SimpleNamespace(PdfReader=lambda _:reader))
    text=docs_agent._extrair_pdf(b'%PDF-fixture',max_pages=12,max_chars=800)
    assert len(text)<=800 and len(calls)==1
    assert 'página 1' in text


def test_scientific_sections_preserve_page_and_do_not_invent_missing_fields():
    import academic_research
    sections=academic_research.scientific_sections({'final':'https://paper.example/a.pdf',
        'secoes':[{'titulo':'Página 2 — trecho extraído','pagina':2,
                   'texto':'2. Methods\nCells were tested at 25 C.\n3. Results\nCapacity was 100 mAh/g.'}]})
    assert [s['kind'] for s in sections]==['methods','results']
    assert all(s['page']==2 and s['source_url']=='https://paper.example/a.pdf' for s in sections)
    assert sections[0]['text']=='Cells were tested at 25 C.'
    assert not any(s['kind']=='limitations' for s in sections)
