"""Gap queries must recover the missing paper, not repeat the covered one."""
from copy import deepcopy

import research_gaps


OBJECTIVE = 'Compare estudos cientificos de reciclagem de baterias: metodos, resultados e limitacoes'


def job():
    return {'id':'qa-science-gaps', 'objetivo':OBJECTIVE, 'plano':[], 'usados':{},
            'orcamento':{'buscas':8, 'paginas':8, 'replans':2}}


def paper(doi='10.1234/covered', url='https://papers.example/one'):
    return {'id':'e1', 'url':url, 'doi':doi, 'texto_lido':True, 'content_scope':'document_text',
            'trecho':'Original scientific text beyond abstract.', 'scientific_sections':[
                {'kind':'methods', 'text':'The experiment used 50 cells at 25 C and controlled pressure.'},
                {'kind':'results', 'text':'The measured capacity was 100 mAh/g in the selected cells.'},
                {'kind':'limitations', 'text':'These observations are limited to laboratory cells.'}]}


def missing():
    return {'id':'e2', 'url':'https://papers.example/two', 'doi':'10.1234/missing',
            'texto_lido':False, 'content_scope':'abstract_only', 'trecho':'Discovery metadata only.'}


def test_comparison_targets_paper_still_missing_extracted_dimensions():
    evidence = [paper(), missing()]
    before = deepcopy(evidence)
    gaps = research_gaps.identify(job(), evidence)
    assert len(gaps)==5 and all(g['status']=='OPEN' for g in gaps)
    assert all(g['observed_publications']==1 and g['required_publications']==2 for g in gaps)
    assert all('"10.1234/missing"' in g['query'] and '10.1234/covered' not in g['query'] for g in gaps)
    assert all(g['target_doi']=='10.1234/missing' for g in gaps)
    assert evidence==before  # Selection never upgrades an abstract into read evidence.


def test_dimension_target_can_differ_between_publications():
    second = paper('10.1234/second', 'https://papers.example/two')
    second['id']='e2'
    second['scientific_sections']=[s for s in second['scientific_sections'] if s['kind']=='methods']
    first = paper()
    first['scientific_sections']=[s for s in first['scientific_sections'] if s['kind']!='methods']
    gaps={g['dimension']:g for g in research_gaps.identify(job(), [first, second])}
    assert gaps['original_text']['status']=='RESOLVED'
    assert gaps['methods']['target_doi']=='10.1234/covered'
    assert gaps['results']['target_doi']==gaps['limitations']['target_doi']=='10.1234/second'


def test_duplicate_doi_url_is_one_publication_not_a_complete_comparison():
    duplicate = paper('https://doi.org/10.1234/COVERED', 'https://mirror.example/one')
    duplicate['id']='e2'
    gaps=research_gaps.identify(job(), [paper(), duplicate])
    assert all(g['observed_publications']==1 and g['status']=='OPEN' for g in gaps)
    assert all(not g['target_doi'] and '10.1234/covered' not in g['query'] for g in gaps)
    assert all('reciclagem de baterias' in g['query'] for g in gaps)


def test_attempted_query_and_exhausted_budget_do_not_create_an_extra_attempt():
    current=job()
    gaps=research_gaps.identify(current, [paper(), missing()])
    current['plano']=[{'tipo':'busca','alvo':g['query'],'status':'feita'} for g in gaps]
    assert all(not g['query'] for g in research_gaps.identify(current, [paper(), missing()]))
    current['plano']=[]
    current['usados']={'buscas':8}
    assert all(not g['query'] for g in research_gaps.identify(current, [paper(), missing()]))


def test_long_doi_is_not_truncated_into_a_different_identifier():
    second=missing()
    second['doi']='10.1234/'+('a'*130)
    gaps=research_gaps.identify(job(), [paper(), second])
    assert all('"'+second['doi']+'"' in g['query'] for g in gaps)
    second['doi']='10.1234/'+('a'*240)
    gaps=research_gaps.identify(job(), [paper(), second])
    assert all(not g['target_doi'] and '10.1234/' not in g['query'] for g in gaps)


def test_previously_attempted_missing_doi_does_not_hide_an_untried_paper():
    first=missing()
    second={**first, 'id':'e3', 'url':'https://papers.example/three', 'doi':'10.1234/untried'}
    current=job()
    prior=research_gaps.identify(current, [first, second])
    assert all(g['target_doi']=='10.1234/missing' for g in prior)
    current['plano']=[{'tipo':'busca','alvo':g['query'],'status':'feita'} for g in prior]
    current['usados']={'buscas':5}
    gaps=research_gaps.identify(current, [first, second])
    assert all(g['target_doi']=='10.1234/untried' and g['query'] for g in gaps)
    assert all(g['observed_publications']==0 and g['status']=='OPEN' for g in gaps)
    assert research_gaps.decision(current, gaps)['action']=='REPLAN'
