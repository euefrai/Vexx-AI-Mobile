"""V5.3 contract parity, routing, catalog and durable isolated chat paths."""
import copy
import json
import shutil
import struct
import subprocess
from pathlib import Path

import pytest
import intent
import jdui
import model3d
import pc_agent

ROOT = Path(__file__).resolve().parents[1]


def props():
    return {'id':'test', 'version':1, 'objects':[{'id':'cube','kind':'cube'}]}


def envelope(p):
    return {'version':jdui.VERSION,'blocks':[{'type':'ui','component':'model3d','props':p}]}


def cases():
    good = [props(), dict(props(),version=1.0,title='🧊'*120), dict(props(),objects=[{'id':k,'kind':k} for k in model3d.KINDS]),
            dict(props(),model='demo-cube',objects=[]), dict(props(),annotations=[{'objectId':'cube','text':'Uma face.'}])]
    bad = [dict(props(),**patch) for patch in [
        {'version':2}, {'id':'../test'}, {'scale':0}, {'scale':3}, {'scale':True},
        {'rotation':[0,0]}, {'rotation':[0,0,361]}, {'camera':{'distance':100}},
        {'lighting':'shader'}, {'autoRotate':'yes'}, {'color':'red; background:url(x)'},
        {'title':'x'*121}, {'source':'Inventada'}, {'annotations':[{'objectId':'other','text':'x'}]},
        {'objects':[]}, {'objects':[{'id':'x','kind':'torus'}]},
        {'objects':[{'id':'x','kind':'cube','html':'<script>'}]},
        {'objects':[{'id':'same','kind':'cube'}]*2},
        {'objects':[{'id':str(i),'kind':'cube'} for i in range(9)]},
        {'model':'missing'}, {'model':'https://evil.example/a.glb'},
        {'model':'http://127.0.0.1/private'}, {'model':'javascript:alert(1)'},
        {'model':'data:model/gltf-binary;base64,abc'}, {'src':'/models/demo-cube.glb'},
        {'shader':'void main(){}'}, {'onClick':'alert(1)'}, {'camera':None},
        {'objects':[{'id':str(i),'kind':'cube','description':'🧊'*500} for i in range(8)],
         'annotations':[{'objectId':'0','text':'🧊'*300} for _ in range(8)]}]]
    return [(p,True) for p in good] + [(p,False) for p in bad]


@pytest.mark.parametrize('value,valid', cases())
def test_python_contract(value, valid):
    ok, norm, errors = jdui.validar_mensagem(envelope(value))
    assert ok == valid, errors
    if valid:
        assert model3d.validate(norm['blocks'][0]['props']) == norm['blocks'][0]['props']


def test_js_python_parity():
    node = shutil.which('node')
    assert node, 'Node required to test the browser schema'
    code = """const fs=require('fs'),vm=require('vm');global.window=global;
    vm.runInThisContext(fs.readFileSync('public/model3d-schema.js','utf8'));
    vm.runInThisContext(fs.readFileSync('public/jdui.js','utf8'));
    const cases=JSON.parse(fs.readFileSync(0,'utf8'));
    console.log(JSON.stringify(cases.map(p=>JDUI.validateMessage({version:'JULIA-ui-message/v1',blocks:[{type:'ui',component:'model3d',props:p}]}))));"""
    out = subprocess.run([node,'-e',code],input=json.dumps([p for p,_ in cases()]),text=True,
                         encoding='utf-8',capture_output=True,cwd=ROOT,check=True)
    for (value, valid), result in zip(cases(),json.loads(out.stdout)):
        assert result['ok'] == valid
        if valid:
            assert result['msg']['blocks'][0]['props'] == model3d.validate(value)


def test_non_finite():
    for value in (float('nan'),float('inf'),-float('inf')):
        with pytest.raises(ValueError):
            model3d.validate(dict(props(),scale=value))


def test_catalog_glb():
    raw = (ROOT/'public/models/demo-cube.glb').read_bytes()
    assert len(raw) < 65536
    assert struct.unpack_from('<III',raw) == (0x46546c67,2,len(raw))
    length, kind = struct.unpack_from('<II',raw,12)
    assert kind == 0x4e4f534a
    metadata = json.loads(raw[20:20+length])
    assert metadata['accessors'][0]['count'] == 24
    assert metadata['accessors'][2]['count'] == 36
    assert 'uri' not in json.dumps(metadata) and 'images' not in metadata


def test_precompressed_engine():
    import gzip
    import server
    from fastapi.testclient import TestClient
    original = (ROOT/'public/vendor/three-engine.js').read_bytes()
    compressed = (ROOT/'public/vendor/three-engine.js.gz').read_bytes()
    assert gzip.decompress(compressed) == original
    assert len(compressed) < 150000
    with TestClient(server.app) as client:
        for encoding, zipped in [('gzip',True), ('identity',False), ('gzip;q=0',False), ('gzip;q=0.5',True)]:
            response = client.get('/vendor/three-engine.js',headers={'Accept-Encoding':encoding})
            assert response.status_code == 200 and response.content == original
            assert (response.headers.get('content-encoding') == 'gzip') == zipped
            assert response.headers['vary'] == 'Accept-Encoding'


def test_requests_and_controls():
    _, p = model3d.respond('Lucas, mostre um cubo em 3D.')
    original = copy.deepcopy(p)
    for command in ('Gire.', 'Amplie.', 'Pause.', 'Restaure.', 'Mostre os detalhes.'):
        _, p = model3d.respond(command,p)
        assert p['objects'] == original['objects']
    assert p['details'] and p['camera']['distance'] == 6 and not p['autoRotate']
    assert model3d.respond('Mostre uma esfera girando.')[1]['autoRotate']
    assert model3d.respond('Mostre um dragão em 3D')[1] is None
    for text in ('Abra o arquivo 3d.txt','Mostre os arquivos 3D','Gire o mouse','Pause o vídeo','Quero o código da esfera'):
        assert model3d.respond(text) is None
    assert model3d.respond('Pause.') is None
    assert intent.analisar('Mostre um cubo em 3D')['intencao'] == 'model3d'
    assert intent.analisar('Pause.',{'ultimos_resultados':'model3d'})['ferramentas'] == ['deterministico','jdui']
    assert intent.analisar('Pause.')['intencao'] != 'model3d'


def test_durable_complete_stream_and_isolation(tmp_path, monkeypatch):
    path = tmp_path/'3d.sqlite3'
    db = pc_agent.open_db(path)
    cfg = {'model':'test'}
    payload = {'message_id':'model-user-01','conversation_id':'scene-conv','owner':'u-alice','text':'Mostre um cubo em 3D'}
    monkeypatch.setattr(pc_agent,'gerar_texto',lambda *a,**k: pytest.fail('No LLM for 3D'))
    result = pc_agent.ai_completa(db,payload,cfg)
    assert '```jdui' in result['response_text']
    db.close()
    db = pc_agent.open_db(path)
    assert pc_agent.cmd_model3d(db,'Amplie.','u-alice','scene-conv')
    assert pc_agent.cmd_model3d(db,'Amplie.','u-bob','scene-conv') is None
    assert pc_agent.cmd_model3d(db,'Amplie.','u-alice','other-conv') is None
    assert pc_agent.ai_completa(db,payload,cfg)['replay']
    db.close()
    events = []
    monkeypatch.setattr(pc_agent,'enviar_ws',lambda ws,event: events.append(event))
    pc_agent.ai_stream_worker(path,cfg,dict(payload,message_id='model-user-02',text='Pause.'),
                              'req-3d',object(),pc_agent.SessaoStream(),{})
    assert events[-1]['type'] == 'ai_done' and 'Animação pausada' in events[-1]['response_text']
    db = pc_agent.open_db(path)
    assert pc_agent.ai_estado(db,'model-user-02','u-alice')['state'] == 'completed'
    assert not pc_agent.list_messages(db,owner='u-bob')
    db.close()
