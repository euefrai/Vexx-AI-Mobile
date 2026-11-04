"""Writer/reviewer protocol must describe the validator's existing constraints."""
import json

import pytest
import research_synthesis as synthesis


TEXT='TaskGroup cancels remaining tasks when a task fails.'
SOURCE={'id':'E1','excerpt':TEXT,'scope':'page_text','url':'https://docs.python.org/test'}
POINT={'text':TEXT,'evidence':[{'id':'E1','quote':TEXT}]}
REQ={'id':'R1','entity':'TaskGroup','attribute':'cancellation','description':'Cancelamento', 'type':'explicit_attribute'}


@pytest.mark.parametrize('mode', ['valid', 'unknown_requirement', 'foreign_paragraph', 'list_value'])
def test_keyed_review_answers_keep_the_same_literal_binding(mode):
    def reviewer(messages, timeout):
        assert 'answers como objeto' in messages[0]['content']
        payload = json.loads(messages[-1]['content'])
        option = next(iter(payload['paragraphs'][0]['answer_options']))
        rid = 'invented' if mode == 'unknown_requirement' else 'R1'
        if mode == 'foreign_paragraph':option = 'A1-0'
        if mode == 'list_value':option = [option]
        return json.dumps({'reviews':[{'paragraph':0,'state':'SUPPORTED','reason':'none',
                                      'answers':{rid:option}}]})
    if mode == 'valid':
        review = synthesis.check_support([POINT], [SOURCE], reviewer, 10, requirements=[REQ])
        assert review[0]['answers'] == [{'requirement_id':'R1','answer':TEXT}]
    else:
        with pytest.raises(ValueError, match='invalid support review'):
            synthesis.check_support([POINT], [SOURCE], reviewer, 10, requirements=[REQ])


def test_duplicate_json_requirement_keys_still_reject_the_review():
    raw = '{"reviews":[{"paragraph":0,"state":"SUPPORTED","reason":"none",' \
          '"answers":{"R1":"A0-0","R1":"A0-0"}}]}'
    with pytest.raises(ValueError, match='invalid support review'):
        synthesis.check_support([POINT], [SOURCE], lambda *a:raw, 10, requirements=[REQ])


def test_no_answer_catalog_requested_when_no_explicit_requirement_exists():
    def reviewer(messages, timeout):
        payload = json.loads(messages[-1]['content'])
        assert 'requirements' not in payload
        assert all('answer_options' not in p for p in payload['paragraphs'])
        assert 'answers como objeto' not in messages[0]['content']
        return json.dumps({'reviews':[{'paragraph':0,'state':'SUPPORTED','reason':'none'}]})
    reviews = synthesis.check_support([POINT], [SOURCE], reviewer, 10, requirements=[])
    assert reviews[0]['answers'] == []


@pytest.mark.parametrize('mode',['valid','duplicate','paraphrase','another_paragraph'])
def test_review_prompt_and_strict_answer_mapping(mode):
    def reviewer(messages, timeout):
        assert 'no máximo uma vez' in messages[0]['content']
        assert 'literal contíguo' in messages[0]['content']
        answer={'requirement_id':'R1','answer':TEXT if mode!='paraphrase' else 'This is an invented paraphrase of the paragraph.'}
        rows=[{'paragraph':i,'state':'SUPPORTED','reason':'none',
               'answers':[answer,dict(answer)] if mode=='duplicate' else [answer]}
              for i in range(2 if mode=='another_paragraph' else 1)]
        return json.dumps({'reviews':rows})
    points=[POINT]* (2 if mode=='another_paragraph' else 1)
    if mode in ('duplicate','paraphrase'):
        with pytest.raises(ValueError,match='invalid support review'):
            synthesis.check_support(points,[SOURCE],reviewer,10,requirements=[REQ])
    else:
        result=synthesis.check_support(points,[SOURCE],reviewer,10,requirements=[REQ])
        assert len(result)==len(points) and all(r['state']=='SUPPORTED' for r in result)


@pytest.mark.parametrize('mode',['valid','foreign_paragraph','unknown','duplicate'])
def test_reviewer_can_select_only_literal_answer_ids_from_its_paragraph(mode):
    def reviewer(messages, timeout):
        payload=json.loads(messages[-1]['content'])
        rows=[]
        for i, paragraph in enumerate(payload['paragraphs']):
            option=next(iter(paragraph['answer_options']))
            if mode=='foreign_paragraph':option=f'A{1-i}-0'
            if mode=='unknown':option='invented'
            answer={'requirement_id':'R1','answer_id':option}
            rows.append({'paragraph':i,'state':'SUPPORTED','reason':'none',
                         'answers':[answer,dict(answer)] if mode=='duplicate' else [answer]})
        return json.dumps({'reviews':rows})
    if mode=='valid':
        reviews=synthesis.check_support([POINT,POINT],[SOURCE],reviewer,10,requirements=[REQ])
        assert all(r['answers']==[{'requirement_id':'R1','answer':TEXT}] for r in reviews)
    else:
        with pytest.raises(ValueError,match='invalid support review'):
            synthesis.check_support([POINT,POINT],[SOURCE],reviewer,10,requirements=[REQ])
