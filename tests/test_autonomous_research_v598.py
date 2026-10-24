"""Controlled gap/controller contracts, not proof of live discovery/inference."""
import copy

import research_gaps as gaps
import research_agents as ra
import research_view
from test_research_parallel_reading import research_job


def job():
    return {'id':'rj-test','objetivo':'Compare estudos de baterias de estado sólido: métodos, resultados e limitações',
            'plano':[],'usados':{},'orcamento':{'buscas':8,'paginas':8,'replans':2}}


def paper(i, **updates):
    return {'id':'ev-'+str(i),'url':f'https://papers.example/{i}', 'doi':f'10.1234/paper{i}',
            'trecho':'Observed extracted scientific passage from the source.', 'texto_lido':True,
            'content_scope':'document_text', 'scientific_sections':[
                {'kind':'methods','text':'The experiment used 50 cells at 25 C and controlled pressure.'},
                {'kind':'results','text':'The measured capacity was 100 mAh/g in these cells.'},
                {'kind':'limitations','text':'These observations are limited to laboratory cells.'}],**updates}


def test_abstracts_create_precise_doi_queries_without_claiming_read():
    records=gaps.identify(job(),[paper(1,texto_lido=False,content_scope='abstract_only')])
    assert len(records)==5 and all(g['status']=='OPEN' for g in records)
    assert all('"10.1234/paper1"' in g['query'] for g in records)
    assert all(g['observed_publications']==0 and not g['evidence_ids'] for g in records)
    assert gaps.decision(job(),records)['action']=='REPLAN'


def test_methods_for_one_paper_do_not_cover_two_study_comparison():
    records=gaps.identify(job(),[paper(1),paper(2,scientific_sections=[])])
    methods=next(g for g in records if g['dimension']=='methods')
    assert methods['status']=='OPEN' and methods['observed_publications']==1
    assert methods['evidence_ids']==['ev-1']


def test_distinct_read_studies_resolve_extraction_gaps_without_claiming_truth():
    records=gaps.identify(job(),[paper(1),paper(2)])
    assert all(g['status']=='RESOLVED' for g in records)
    assert gaps.decision(job(),records)['action']=='SYNTHESIZE'
    assert all('no claim' in g['scope'] for g in records)


def test_same_doi_is_not_two_publications():
    p=paper(1);other=paper(2,doi=p['doi'])
    assert all(g['status']=='OPEN' for g in gaps.identify(job(),[p,other]))


def test_completed_or_planned_queries_are_not_scheduled_again():
    j=job();p=paper(1,texto_lido=False)
    first=gaps.identify(j,[p])
    j['plano']=[{'tipo':'busca','alvo':g['query'],'status':'feita'} for g in first]
    again=gaps.identify(j,[p])
    assert all(not g['query'] and len(g['previous_attempts'])==1 for g in again)
    assert gaps.decision(j,again)['action']=='STOP_PARTIAL'


def test_budget_and_provider_block_stop_expansion():
    j=job();records=gaps.identify(j,[])
    j['usados']['paginas']=8
    assert gaps.decision(j,records)['action']=='STOP_PARTIAL'
    j['usados']={'research_outcome':{'state':'blocked'}}
    assert gaps.decision(j,records)['reason']=='provider_blocked'


def test_general_question_does_not_spawn_scientific_dimensions():
    j=job();j['objetivo']='Como funciona asyncio.TaskGroup?'
    assert len(gaps.identify(j,[]))==1


def test_only_explicit_methods_quantities_cover_conditions():
    p=paper(1,scientific_sections=[{'kind':'methods','text':'Cells were tested. Temperature was not provided.'}])
    records=gaps.identify(job(),[p,paper(2)])
    condition=next(g for g in records if g['dimension']=='conditions')
    assert condition['status']=='OPEN' and condition['observed_publications']==1


def test_gap_ids_and_queries_stay_scoped_and_stable():
    a=job();b=copy.deepcopy(a);b['id']='rj-other'
    first=gaps.identify(a,[]);again=gaps.identify(a,[]);other=gaps.identify(b,[])
    assert first==again and {g['id'] for g in first}.isdisjoint(g['id'] for g in other)


def test_discovered_feed_is_not_information_gain(research_job):
    db,j=research_job
    result=ra._avaliar_rodada(db,j,{'id':'step'},[{'id':'feed','texto_lido':False,'content_scope':'feed_metadata'}])
    assert result['new_evidence']==0
    assert j['usados']['research_gaps'][0]['status']=='OPEN'


def test_open_scientific_gap_keeps_outcome_partial_and_visible():
    j=job();j['usados']['research_gaps']=gaps.identify(j,[paper(1)])
    assert ra._completion_outcome(j,[paper(1)],[])['state']=='partial'
    view=research_view.build_view({'id':j['id'],'usados':j['usados']},[])
    assert any(b.get('component')=='accordion' and any('falta confirmar' in i['title']
        for i in b['props']['items']) for b in view['blocks'])


def test_energy_per_mass_is_not_energy_per_volume_or_specific_capacity():
    import units
    import evidence_graph
    import research_synthesis
    mass=evidence_graph.extrair_quantidades('Density 300 Wh/kg')[0]
    volume=evidence_graph.extrair_quantidades('Density 300 Wh/L')[0]
    capacity=evidence_graph.extrair_quantidades('Capacity 300 mAh/g')[0]
    assert mass['unidade'].lower()=='wh/kg'
    assert not units.compativeis(mass,volume) and not units.compativeis(mass,capacity)
    assert research_synthesis.quantities('300 Wh/kg')!=research_synthesis.quantities('300 Wh/L')


def test_explicit_deep_research_chat_command_keeps_deep_mode(research_job,monkeypatch):
    import pc_agent
    db,j=research_job;captured=[]
    monkeypatch.setattr(pc_agent,'rjob_start',lambda db,req,owner:captured.append(req) or
                        {'type':'research_job','job_id':'rj-controlled'})
    pc_agent.cmd_pesquisa(db,'Faça uma pesquisa profunda sobre baterias sólidas',j['owner'],'qa')
    assert captured[0]['modo']=='profunda'


def test_feed_gap_uses_observed_headline_and_keeps_city():
    j=job();j['objetivo']='Notícias de Ubatã Bahia nos últimos sete dias'
    records=gaps.identify(j,[{'id':'rss','content_scope':'feed_metadata',
                            'titulo':'Biblioteca municipal recebe livros','url':'https://news.example/rss'}])
    assert '"Biblioteca municipal recebe livros"' in records[0]['query']
    assert 'Ubatã Bahia' in records[0]['query'] and records[0]['status']=='OPEN'


def test_live_news_happened_in_city_never_falls_back_to_national_headlines(monkeypatch):
    import live_data
    from datetime import datetime,timezone,timedelta
    from email.utils import format_datetime
    now=datetime(2026,10,23,18,tzinfo=timezone.utc)
    rows=[{'titulo':'Notícia de Santa Catarina','url':'https://news.example/national',
           'meta':{'publicado_em':format_datetime(now-timedelta(hours=1))}},
          {'titulo':'Ubatã Bahia recebe biblioteca','url':'https://news.example/local',
           'meta':{'publicado_em':format_datetime(now-timedelta(days=5))}}]
    live_data._cache.clear()
    monkeypatch.setattr(live_data.search_providers,'buscar_bing_news',lambda *a,**k:rows)
    out=live_data.news('Quais notícias aconteceram em Ubatã, Bahia, nos últimos sete dias?',{'timezone':'America/Bahia'},now)
    assert 'news.example/local' in out and 'news.example/national' not in out
    assert 'artigos completos não foram lidos' in out


def test_actual_pipeline_replans_for_methods_and_preserves_scientific_sections():
    from pathlib import Path
    from tools.bench_autonomous_v598 import run
    result=run(Path(__file__).resolve().parents[1])
    assert result['replans']==1 and result['duplicate_reads']==0
    assert result['read_sources']==4
    assert all(g['status']=='RESOLVED' for g in result['gaps'])
    assert 'methods sample experimental' in result['queries'][1]
    assert result['outcome']['state']=='partial'  # Extraction coverage is not grounded synthesis.
    unresolved=result['outcome']['unresolved_fronts']
    assert len(unresolved)==len(set(unresolved))


def test_gallery_only_intent_does_not_request_article_methods():
    j=job();j['objetivo']='Mostre imagens da Ponte Estaiada'
    assert gaps.identify(j,[])==[]
    assert gaps.decision(j,[])['action']=='STOP_PARTIAL'


def test_cancelled_job_never_requests_more_searches():
    j=job();records=gaps.identify(j,[]);j['status']='cancelada'
    assert gaps.decision(j,records)['reason']=='interrupted_or_cancelled'


def test_real_image_search_uses_shared_retrieval_not_generated_claims(research_job,monkeypatch):
    import pc_agent
    db,j=research_job;captured=[]
    monkeypatch.setattr(pc_agent.research,'pesquisa_rapida',lambda db,owner,query:captured.append((owner,query)) or
                        {'midia':[{'type':'image','title':'Ponte Estaiada','url':'https://upload.wikimedia.org/ponte.jpg',
                                   'source_url':'https://commons.wikimedia.org/wiki/File:Ponte.jpg'}]})
    result=pc_agent.cmd_pesquisa(db,'Pesquise e mostre imagens reais da Ponte Estaiada de São Paulo.',j['owner'],'qa')
    assert captured[0][0]==j['owner'] and 'Ponte Estaiada' in captured[0][1]
    assert '"component": "media"' in result and 'não foram analisados' in result
    assert 'verificadas' not in result
    assert pc_agent.cmd_pesquisa(db,'Crie imagens de um gato.',j['owner'],'qa')==''


def test_explicit_official_docs_request_starts_evidence_workflow(research_job,monkeypatch):
    import pc_agent
    db,j=research_job;captured=[]
    monkeypatch.setattr(pc_agent,'rjob_start',lambda db,req,owner:captured.append(req) or
                        {'type':'research_job','job_id':'rj-controlled'})
    response=pc_agent.cmd_pesquisa(db,'Pesquise na documentação oficial como funciona asyncio.TaskGroup em Python.',j['owner'],'qa')
    assert captured and 'Pesquisa técnica' in response
    assert pc_agent.cmd_pesquisa(db,'Explique asyncio.TaskGroup em Python.',j['owner'],'qa')==''


def test_hour_window_does_not_reject_same_local_day_after_utc_midnight():
    from datetime import datetime,timezone
    import query_intelligence,search_verticals
    req=query_intelligence.analyze('Notícias inteligência artificial nas últimas 24 horas',
        now=datetime(2026,10,24,0,20,tzinfo=timezone.utc),timezone_name='America/Bahia')
    result=search_verticals.assess(req,{'titulo':'Notícias inteligência artificial',
        'trecho':'Relatório publicado sobre inteligência artificial.',
        'url':'https://news.example/story','publicado_em':'2026-10-24T00:19:00+00:00','texto_lido':True})
    assert result['eligible'],result


def test_science_starts_with_subject_not_blind_method_fronts():
    queries=ra._subconsultas_unicas('Faça uma pesquisa profunda sobre baterias de estado sólido, comparando estudos, métodos e limitações.',4)
    import query_intelligence
    assert len(queries)<=2 and queries[0].endswith('baterias de estado sólido')
    assert all(query_intelligence.analyze(q)['domain']=='science' for q in queries)
    assert any('solid-state batteries' in q for q in queries)
    subject=gaps.science_subject('Compare estudos sobre sódio e lítio desde 2024: métodos e resultados')
    assert 'sódio e lítio desde 2024' in subject


def test_encyclopedia_is_not_counted_as_original_scientific_study():
    source=paper(1);source.pop('doi');source['publication_type']='encyclopedia'
    assert all(g['observed_publications']==0 for g in gaps.identify(job(),[source]))


def test_checkpoint_compacts_repeated_claim_excerpts_without_losing_evidence(research_job):
    import json
    db, current = research_job
    sources = [{'evidence_id':f'ev-{i}', 'url':'https://example.org/'+'x'*480,
                'title':'t'*160, 'used_excerpt':'á'*500, 'relation':'MENTIONS',
                'read':True, 'access_state':'read'} for i in range(12)]
    current['achados'] = [{'afirmacao':f'Claim {i}', 'estado':'UNVERIFIED',
                         'evidence_ids':[s['evidence_id'] for s in sources], 'fontes':sources}
                         for i in range(12)]
    assert len(json.dumps(current['achados'],ensure_ascii=False)) > 60000
    ra.salvar_job(db,current)
    loaded=ra.carregar_job(db,current['owner'],current['id'])
    assert len(loaded['achados']) == 12
    assert loaded['usados']['claim_sources_compacted']
    assert loaded['achados'][0]['evidence_ids'] == current['achados'][0]['evidence_ids']
    assert loaded['achados'][0]['fontes'][0]['relation'] == 'MENTIONS'
    assert len(current['achados'][0]['fontes'][0]['used_excerpt']) == 500
