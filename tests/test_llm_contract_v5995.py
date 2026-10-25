"""Safe structural JSON recovery and actual completion metadata contracts."""
import json
import threading
import urllib.request

import pytest
import hermes_bridge as bridge
import pc_agent
import research_synthesis as rs


@pytest.mark.parametrize('value',['{"points":[]}','```JSON\n{"points":[]}\n```','```json {"points":[]} ```'])
def test_one_complete_json_value_or_fence(value):
    assert rs._parse_json(value,1000)=={'points':[]}


@pytest.mark.parametrize('value',[
    '{"points":[],"points":[1]}','{"x":NaN}','{"x":Infinity}',
    '{} {}','prefix {"points":[]}','```json\n{}\n```\n```json\n{}\n```',
    '{"x":"\\u202eunsafe"}', '{"x":"\\u0000unsafe"}', '{"x":"\\ud800"}', '{"points":[',
])
def test_no_guessing_duplicate_keys_constants_prose_or_truncated_values(value):
    with pytest.raises(ValueError):rs._parse_json(value,1000)


def test_normal_unicode_and_quantities_are_preserved():
    value={'text':'A operação não muda o original; custa R$ 2,50. العربية עברית'}
    assert rs._parse_json(json.dumps(value),1000)==value


def test_bridge_exposes_bounded_finish_reason_and_token_usage(monkeypatch):
    class Response:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self):return json.dumps({'choices':[{'finish_reason':'length','message':{'content':'{"points":['}}],
                'usage':{'prompt_tokens':12,'completion_tokens':18,'total_tokens':30,'secret':'no','cached':True}}).encode()
    monkeypatch.setattr(urllib.request,'urlopen',lambda *a,**kw:Response())
    result=bridge.chat_complete('http://127.0.0.1:8645/v1','fixture',[])
    assert result['finish_reason']=='length' and result['truncada']
    assert result['usage']=={'prompt_tokens':12,'completion_tokens':18,'total_tokens':30}


def test_research_writer_rejects_transport_truncation_without_retry(monkeypatch):
    calls=[]
    def generate(cfg,messages,**kwargs):
        calls.append(cfg)
        return {'texto':'{"points":[]}', 'finish_reason':'length','usage':{'completion_tokens':1800}}
    monkeypatch.setattr(pc_agent,'gerar_texto',generate)
    writer=pc_agent._research_writer({'fallbacks':['paid-model']},threading.Event())
    with pytest.raises(rs.ModelOutputError) as exc:writer([{'role':'system','content':'fixture'}],20)
    assert rs.failure_detail(exc.value)=='model_truncated'
    assert len(calls)==1 and calls[0]['fallbacks']==[]
    assert writer.last_metadata=={'finish_reason':'length','usage':{'completion_tokens':1800}}
