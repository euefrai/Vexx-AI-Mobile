import asyncio
import json
import os

import httpx
import pytest
from fastapi.testclient import TestClient

from pc_companion.ai import AI, endpoint, protect
from pc_companion.app import create_app


@pytest.mark.parametrize('url',['http://public.example/v1','http://169.254.169.254','http://0.0.0.0','https://user:key@example.com','https://example.com?key=secret','file:///tmp/key','http://127.0.0.1:bad'])
def test_ai_rejects_unsafe_or_credential_bearing_endpoints(url):
    with pytest.raises(ValueError):endpoint(url)


def test_ai_credentials_persist_but_are_never_returned_and_endpoint_change_clears_key(tmp_path):
    ai=AI(tmp_path)
    saved=ai.save({'provider':'compatible','base_url':'http://127.0.0.1:8645/v1','api_key':'fixture-key','model':'fixture-model'})
    assert saved['key_set'] and 'fixture-key' not in json.dumps(saved)
    assert AI(tmp_path).status()==saved
    assert protect(ai.config['key'],decrypt=True)=='fixture-key'
    if os.name=='nt':assert 'fixture-key' not in (tmp_path/'ai.json').read_text()
    ai.save({'provider':'compatible','base_url':'http://127.0.0.1:8645/v1','model':'other'})
    assert ai.status()['key_set']
    ai.save({'provider':'compatible','base_url':'http://127.0.0.1:9999/v1','model':'other'})
    assert not ai.status()['key_set']
    ai.save({'provider':'ollama','api_key':'test-key','model':'qa'})
    ai.save({'provider':'ollama','clear_key':True,'model':'qa'})
    assert not ai.status()['key_set']


@pytest.mark.parametrize('provider',['ollama','compatible','openai','hermes'])
def test_ai_protocol_models_and_chat_without_file_or_command_access(tmp_path,monkeypatch,provider):
    ai=AI(tmp_path)
    ai.save({'provider':provider,'base_url':'http://127.0.0.1:9999'+('' if provider=='ollama' else '/v1'),'model':'fixture-model','api_key':'fixture-key'})
    calls=[]
    def handle(request):
        calls.append(request)
        assert request.headers['authorization']=='Bearer fixture-key'
        if request.method=='GET':
            return httpx.Response(200,json={'models':[{'name':'fixture-model'}]} if provider=='ollama' else {'data':[{'id':'fixture-model'}]})
        data=json.loads(request.content)
        assert data['stream'] is False and data['model']=='fixture-model'
        assert 'tools' not in data
        assert 'fixture-key' not in json.dumps(data)
        return httpx.Response(200,json={'message':{'content':'Resposta de teste'}} if provider=='ollama' else {'choices':[{'message':{'content':'Resposta de teste'}}]})
    original=httpx.AsyncClient
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(handle),**kw))
    async def scenario():
        assert (await ai.models())['models']==['fixture-model']
        assert (await ai.chat('Olá'))['reply']=='Resposta de teste'
        assert (await ai.chat('Continue'))['reply']=='Resposta de teste'
    asyncio.run(scenario())
    last=json.loads(calls[-1].content)
    assert last['messages'][-2]=={'role':'assistant','content':'Resposta de teste'}
    assert calls[0].url.path==('/api/tags' if provider=='ollama' else '/v1/models')
    assert calls[1].url.path==('/api/chat' if provider=='ollama' else '/v1/chat/completions')


def test_ai_errors_do_not_echo_provider_secrets_or_follow_redirects(tmp_path,monkeypatch):
    ai=AI(tmp_path);ai.save({'provider':'ollama','model':'qa','api_key':'private-fixture'})
    original=httpx.AsyncClient
    def handle(request):return httpx.Response(302,headers={'location':'https://other.example'},json={'error':'private-fixture'})
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(handle),**kw))
    with pytest.raises(ValueError,match='serviço de IA') as error:asyncio.run(ai.models())
    assert 'private-fixture' not in str(error.value)


def test_ai_settings_and_copilot_require_local_token_and_preserve_commands(tmp_path):
    app=create_app(tmp_path,[])
    with TestClient(app,base_url='http://127.0.0.1') as client:
        assert client.get('/api/ai/config').status_code==401
        assert client.post('/api/ai/config',json={}).status_code==401
        assert client.post('/api/ai/test',json={}).status_code==401
        client.get('/');headers={'X-Vexx-Token':client.get('/api/bootstrap').json()['token']}
        r=client.post('/api/ai/config',headers=headers,json={'provider':'ollama','model':'qa'})
        assert r.status_code==200 and r.json()['enabled']
        r=client.post('/api/copilot',headers=headers,json={'text':'pausar acesso'})
        assert r.status_code==200 and 'pausado' in r.json()['reply']
