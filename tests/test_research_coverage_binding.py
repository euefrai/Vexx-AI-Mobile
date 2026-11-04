import copy
import pytest
import query_intelligence as qi
import research_synthesis as sy

QUERY='Compare tasks.collect e tasks.gather quanto a cancelamento e exceções com documentação oficial'
QUOTE='Once all tasks finish, their exceptions are combined in an ExceptionGroup which is then raised.'


def context():
    heading={'level':7,'text':'class tasks.collect','source_span':{'start':0,'end':19,'sha256':'a'*64}}
    src={'id':'E1','evidence_id':'ev1','url':'https://docs.python.org/3/library/api.html','scope':'page_text',
         'excerpt':QUOTE,'passage_ranges':[{'start':0,'end':len(QUOTE),'section_path':[heading],
          'source_span':{'start':80,'end':80+len(QUOTE),'sha256':'a'*64}}]}
    point={'text':'Após todas as tarefas terminarem, as exceções são combinadas em ExceptionGroup e levantadas.',
           'evidence':[{'id':'E1','quote':QUOTE}]}
    req=next(r for r in qi.answer_requirements(QUERY) if r['entity']=='tasks.collect' and r['attribute']=='exceptions')
    return req,point,[src]


@pytest.mark.parametrize('fault',[None,'other_api','ambiguous','bad_hash','unread_authority','numeric_limit','different_attribute','invented_api'])
def test_implicit_subject_requires_unanimous_verified_scope(monkeypatch,fault):
    import python_docs_discovery as docs
    monkeypatch.setattr(docs,'has_read_authority',lambda *a:fault!='unread_authority')
    req,point,sources=context()
    if fault=='other_api':point['text']='tasks.gather: '+point['text']
    if fault=='ambiguous':
        span=copy.deepcopy(sources[0]['passage_ranges'][0]);span['section_path'][0]['text']='class tasks.gather'
        sources[0]['passage_ranges'].append(span)
    if fault=='bad_hash':sources[0]['passage_ranges'][0]['source_span']['sha256']='b'*64
    if fault=='numeric_limit':req['constraints']['must_preserve']=True
    if fault=='different_attribute':req['attribute']='cancellation'
    if fault=='invented_api':point['text']='other.execute: '+point['text']
    assert bool(sy._reviewed_api_links(req,point,sources,QUERY)) == (fault is None)


def test_video_card_keeps_price_requirement_but_gallery_does_not():
    for query in ['Pesquise placa de vídeo RTX 3050 de 6 GB com preço atual',
                  'Pesquise placas de videos GTX 1660 com preço']:
        assert any(r['attribute']=='price' for r in qi.answer_requirements(query))
    assert qi.answer_requirements('Mostre fotos de placas de vídeo com preços')==[]
    assert qi.answer_requirements('Vídeos sobre preços de jogos')==[]
