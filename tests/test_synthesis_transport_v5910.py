"""Response shape and failure metadata, with controlled HTTP responses only."""
import io,json,threading
import pytest
import hermes_bridge as hb
import pc_agent


def test_content_parts_are_text_not_python_repr():
 body={'choices':[{'message':{'content':[{'type':'text','text':'{"points":[]}'},{'type':'tool_use','input':'never execute'}]}}]}
 assert hb.extrair_texto(body)=='{"points":[]}'
 assert hb.extrair_delta({'choices':[{'delta':{'content':[{'type':'text','text':'hello'}]}}]})=='hello'


def test_reasoning_is_not_substituted_for_answer():
 assert hb.extrair_texto({'choices':[{'message':{'content':None,'reasoning':'private chain'}}]})==''


def test_empty_http_success_preserves_closed_diagnostic_metadata(monkeypatch):
 body={'model':'qa:free','choices':[{'message':{'content':None,'reasoning':'private reasoning'},'finish_reason':'length'}],
       'usage':{'completion_tokens':1800,'secret':'not copied'}}
 monkeypatch.setattr(hb.urllib.request,'urlopen',lambda *a,**k:io.BytesIO(json.dumps(body).encode()))
 with pytest.raises(hb.BridgeErro) as caught:hb.chat_complete('http://127.0.0.1:8645/v1','qa:free',[])
 meta=caught.value.response_metadata
 assert meta['finish_reason']=='length' and meta['usage']=={'completion_tokens':1800}
 assert meta['answer_chars']==0 and 'private' not in str(meta) and 'secret' not in str(meta)


def test_research_writer_classifies_reported_empty_truncation(monkeypatch):
 def empty(*a,**kw):
  e=hb.BridgeErro('empty','vazia');e.response_metadata={'finish_reason':'length','usage':{}};raise e
 monkeypatch.setattr(pc_agent,'gerar_texto',empty)
 write=pc_agent._research_writer({},threading.Event())
 import research_synthesis as rs
 with pytest.raises(rs.ModelOutputError) as caught:write([{'role':'system','content':'system'}],15)
 assert caught.value.reason=='model_truncated'
