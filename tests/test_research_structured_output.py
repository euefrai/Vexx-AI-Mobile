import io
import json
import threading

import pytest
import hermes_bridge as bridge
import pc_agent
import research_output as output
import research_synthesis as synthesis


def test_draft_schema_binds_quote_ids_to_their_source():
    payload = {'sources':[{'id':'E1','quotes':[{'id':'Q1'}]}, {'id':'E2','quotes':[{'id':'Q2'}]}]}
    schema = output.response_format([{'content':json.dumps(payload)}])['json_schema']['schema']
    refs = schema['properties']['points']['items']['properties']['evidence']['items']['anyOf']
    assert [(r['properties']['id']['enum'],r['properties']['quote_id']['enum']) for r in refs] == [(['E1'],['Q1']),(['E2'],['Q2'])]
    assert schema['properties']['points']['maxItems'] == 5


def test_review_schema_null_is_absent_coverage_not_a_verified_answer():
    text = 'A bateria tem autonomia de dez horas no ensaio.'
    point = {'text':text,'evidence':[{'id':'E1','quote':text}]}
    source = {'id':'E1','excerpt':text}
    req = {'id':'R1','entity':'bateria','attribute':'battery','description':'Bateria'}
    def verify(messages, timeout):
        schema = output.response_format(messages)
        assert schema['json_schema']['name'] == 'research_review'
        return json.dumps({'reviews':[{'paragraph':0,'state':'SUPPORTED','reason':'none','answers':{'R1':None}}]})
    rows = synthesis.check_support([point],[source],verify,10,requirements=[req])
    assert rows[0]['answers'] == []
    with pytest.raises(ValueError):
        synthesis.check_support([point],[source],lambda *a: json.dumps({'reviews':[{
            'paragraph':0,'state':'SUPPORTED','reason':'none','answers':{'foreign':None}}]}),10,requirements=[req])


@pytest.mark.parametrize('available', [True,False])
def test_transport_uses_format_only_for_advertised_model(monkeypatch, available):
    output._CAPABILITIES.clear()
    calls=[]
    def urlopen(req, timeout):
        if isinstance(req,str):
            calls.append('catalog')
            return io.BytesIO(json.dumps({'data':[{'id':'test:free','supported_parameters':
                ['response_format','structured_outputs'] if available else []}]}).encode())
        body=json.loads(req.data);calls.append(body)
        assert ('response_format' in body) == available
        return io.BytesIO(json.dumps({'choices':[{'message':{'content':'{"points":[]}'},'finish_reason':'stop'}]}).encode())
    monkeypatch.setattr(output.urllib.request,'urlopen',urlopen)
    bridge._CIRCUITO.clear()
    cfg={'proxy':'http://127.0.0.1:8645/v1','model':'test:free','fallbacks':[], 'max_tokens':100,
         '_research_response_format':{'type':'json_schema'}}
    for _ in range(2):pc_agent.gerar_texto(cfg,[{'role':'user','content':'JSON'}])
    assert calls.count('catalog') == 1
    assert all(c['model']=='test:free' for c in calls if isinstance(c,dict))


def test_normal_chat_does_not_fetch_capabilities_or_add_format(monkeypatch):
    monkeypatch.setattr(output,'supported',lambda *a,**k:pytest.fail('Normal chat must not probe'))
    def generate(*args, **kwargs):
        assert 'response_format' not in kwargs
        return {'texto':'hello'}
    monkeypatch.setattr(bridge,'tentar_modelos',generate)
    pc_agent.gerar_texto({'proxy':bridge.DEFAULT_PROXY_URL,'model':'test:free','max_tokens':50},[])


@pytest.mark.parametrize('failure', ['empty','refusal','length','content_filter'])
def test_empty_strict_format_recovery_is_once_same_model_and_bounded(monkeypatch,failure):
    output._CAPABILITIES.clear();bridge._CIRCUITO.clear();calls=[]
    def urlopen(req,timeout):
        if isinstance(req,str):
            return io.BytesIO(json.dumps({'data':[{'id':'test:free',
                'supported_parameters':['response_format','structured_outputs','reasoning_effort'],
                'reasoning':{'mandatory':True,'supported_efforts':['low']}}]}).encode())
        body=json.loads(req.data);calls.append((body,timeout))
        if len(calls)==1:
            finish={'empty':'stop','refusal':'stop','length':'length','content_filter':'content_filter'}[failure]
            msg={'content':None,'refusal':'Declined' if failure=='refusal' else None}
        else:
            assert len(calls)==2
            finish='stop';msg={'content':'{"points":[]}'}
        return io.BytesIO(json.dumps({'choices':[{'message':msg,'finish_reason':finish}]}).encode())
    monkeypatch.setattr(output.urllib.request,'urlopen',urlopen)
    cfg={'proxy':'http://127.0.0.1:8645/v1','model':'test:free','fallbacks':[],
         'max_tokens':1800,'_research_response_format':{'type':'json_schema'}}
    if failure=='empty':
        result=pc_agent.gerar_texto(cfg,[{'role':'user','content':'JSON'}],timeout=20)
        assert result['structured_output_fallback']=='empty_content'
        first,second=[body for body,_ in calls]
        assert first.pop('response_format')=={'type':'json_schema'}
        assert first==second and second['reasoning_effort']=='low'
        assert all(0<t<=20 for _,t in calls)
    else:
        with pytest.raises(bridge.BridgeErro) as caught:
            pc_agent.gerar_texto(cfg,[{'role':'user','content':'JSON'}],timeout=20)
        assert caught.value.codigo==('recusa' if failure=='refusal' else 'vazia')
        assert len(calls)==1


def test_empty_strict_format_has_no_retry_without_time_budget(monkeypatch):
    monkeypatch.setattr(output,'supported',lambda *a,**k:True)
    monkeypatch.setattr(output,'reasoning_effort',lambda *a:None)
    calls=[]
    def generate(*args,**kw):
        calls.append(kw);exc=bridge.BridgeErro('empty','vazia')
        exc.response_metadata={'finish_reason':'stop'};raise exc
    monkeypatch.setattr(bridge,'tentar_modelos',generate)
    cfg={'proxy':bridge.DEFAULT_PROXY_URL,'model':'test:free','fallbacks':[],
         'max_tokens':1800,'_research_response_format':{'type':'json_schema'}}
    with pytest.raises(bridge.BridgeErro):pc_agent.gerar_texto(cfg,[],timeout=4)
    assert len(calls)==1


def test_writer_attaches_schema_without_changing_explicit_model(monkeypatch):
    def generate(cfg, messages, **kwargs):
        assert cfg['model']=='test:free' and cfg['fallbacks']==[]
        assert cfg['_research_response_format']['json_schema']['name']=='research_draft'
        return {'texto':'{"points":[]}'}
    monkeypatch.setattr(pc_agent,'gerar_texto',generate)
    writer=pc_agent._research_writer({'model':'test:free'},threading.Event())
    writer([{'role':'system','content':'JSON'},{'role':'user','content':json.dumps({
        'sources':[{'id':'E1','quotes':[{'id':'Q1'}]}]})}],10)


@pytest.mark.parametrize('proof', ['valid','different_hash','heading_after_passage'])
def test_reviewer_gets_only_bound_api_section_context(proof):
    text = 'If a submitted task fails, the other tasks continue running.'
    heading = {'level':7,'text':'class tasks.collect','source_span':{'start':0,'end':19,'sha256':'a'*64}}
    if proof == 'different_hash':heading['source_span']['sha256']='b'*64
    if proof == 'heading_after_passage':heading['source_span']['end']=100
    source = {'id':'E1','excerpt':text,'passage_ranges':[{'start':0,'end':len(text),
        'source_span':{'start':80,'end':80+len(text),'sha256':'a'*64},'section_path':[heading]}]}
    reviewed = synthesis._review_source(source)
    assert reviewed['excerpt']==text and 'passage_ranges' not in reviewed
    assert bool(reviewed.get('section_context')) == (proof=='valid')
    if proof=='valid':assert reviewed['section_context'][0]=={'api':'class tasks.collect','text':text}


def test_review_compaction_keeps_table_header_context():
    text = 'Camera ZX with battery and memory card: 710 g.'
    result = synthesis._review_source({'id':'E1','excerpt':text,'passage_ranges':[
        {'start':0,'end':len(text),'table_header':'Model / Weight with battery and card'}]})
    assert result['section_context'][0]['table_header']=='Model / Weight with battery and card'


@pytest.mark.parametrize('mandatory,efforts,expected', [(True,['low','medium'],'low'),
    (False,['low'],None),(True,['medium'],None)])
def test_low_reasoning_only_when_advertised_and_mandatory(monkeypatch,mandatory,efforts,expected):
    output._CAPABILITIES.clear()
    body={'data':[{'id':'test:free','supported_parameters':['response_format','structured_outputs','reasoning_effort'],
                   'reasoning':{'mandatory':mandatory,'supported_efforts':efforts}}]}
    monkeypatch.setattr(output.urllib.request,'urlopen',lambda *a,**k:io.BytesIO(json.dumps(body).encode()))
    assert output.supported(bridge.DEFAULT_PROXY_URL,'test:free')
    assert output.reasoning_effort(bridge.DEFAULT_PROXY_URL,'test:free')==expected
