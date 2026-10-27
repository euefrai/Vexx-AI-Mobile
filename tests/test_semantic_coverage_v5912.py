"""Controlled review contracts; real inference is recorded separately in QA."""
import json
import pytest
import research_synthesis as rs

QUERY='Quem fundou a Atlas, em que ano foi fundada e quais produtos fabrica?'
FIRST='Atlas foi fundada em 1981 por Rita Silva.'
SECOND='Atlas fabrica motores elétricos e geradores.'
PARAPHRASE='Entre os produtos fabricados pela Atlas estão motores e geradores.'
SOURCE={'id':'E1','evidence_id':'ev-atlas','title':'Atlas','url':'https://example.org/atlas','excerpt':FIRST+' '+SECOND}


def writer(messages,timeout):
    return json.dumps({'points':[
        {'text':FIRST,'evidence':[{'id':'E1','quote':FIRST}]},
        {'text':PARAPHRASE,'evidence':[{'id':'E1','quote':SECOND}]}]})
writer.semantic_coverage=True


def reviewer(change=None):
    def review(messages,timeout):
        payload=json.loads(messages[-1]['content'])
        ids={r['attribute']:r['id'] for r in payload['requirements']}
        reviews=[{'paragraph':0,'state':'SUPPORTED','reason':'none','answers':[
            {'requirement_id':ids['founders'],'answer':'Rita Silva'},
            {'requirement_id':ids['foundation_date'],'answer':'1981'}]},
            {'paragraph':1,'state':'SUPPORTED','reason':'none','answers':[
            {'requirement_id':ids['products'],'answer':'motores e geradores'}]}]
        if change:change(reviews)
        return json.dumps({'reviews':reviews})
    return review


def test_reviewed_paraphrase_covers_aspects_without_surface_phrase_requirement():
    result=rs.generate(QUERY,[SOURCE],[],writer,verify_fn=reviewer())
    assert result['llm'] and result['answer_coverage']['complete']
    assert result['answer_coverage']['method']=='literal_answer_spans_and_separate_support_review'


@pytest.mark.parametrize('change',[
    lambda r:r[1]['answers'][0].update(requirement_id='R-invented'),
    lambda r:r[1]['answers'][0].update(answer='computadores não mencionados'),
    lambda r:r[0]['answers'][1].update(answer='Rita Silva'),
    lambda r:r[1].update(state='PARTIAL',reason='scope')])
def test_fabricated_aspect_or_span_or_date_and_unsupported_coverage_rejected(change):
    with pytest.raises(ValueError,match='support review'):
        rs.generate(QUERY,[SOURCE],[],writer,verify_fn=reviewer(change))


def test_omitted_aspect_stays_pending_even_when_source_contains_the_answer():
    result=rs.generate(QUERY,[SOURCE],[],writer,verify_fn=reviewer(lambda r:r[0]['answers'].pop()))
    assert not result['answer_coverage']['complete']
    assert next(r for r in result['answer_coverage']['requirements'] if r['attribute']=='foundation_date')['state']!='SUPPORTED'


def test_original_undecomposed_demand_is_never_resolved_by_aspect_review():
    result=rs.generate(QUERY+' E quantas fábricas possui?',[SOURCE],[],writer,verify_fn=reviewer())
    assert not result['answer_coverage']['complete']


def test_semantic_answer_still_requires_cited_source_linked_to_requirement():
    other={**SOURCE,'id':'E2','evidence_id':'ev-orion','excerpt':SECOND.replace('Atlas','Orion')}
    def wrong(messages,timeout):
        body=json.loads(writer(messages,timeout));body['points'][1]['evidence']=[{'id':'E2','quote':other['excerpt']}]
        return json.dumps(body)
    wrong.semantic_coverage=True
    result=rs.generate(QUERY,[SOURCE,other],[],wrong,verify_fn=reviewer())
    assert not result['answer_coverage']['complete']
