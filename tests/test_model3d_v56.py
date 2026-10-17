"""V5.6: fundações de montagem, novos comandos e (adiante) catálogo/pesquisa."""
import copy
import json
import subprocess
from pathlib import Path

import pytest
import jdui
import model3d
from model3d_education import scene

ROOT = Path(__file__).resolve().parents[1]


def cena_grupos():
    return model3d.validate({
        'id': 'dev-test', 'version': 1, 'title': 'Aparelho didático',
        'description': 'Bancada ilustrativa com peças internas e externas.',
        'education': 'device',
        'objects': [
            {'id': 'shell', 'kind': 'cube', 'label': 'Carcaça', 'group': 'external',
             'role': 'structural', 'order': 1, 'dimensions': [2, 1.4, 2], 'color': '#8890a8',
             'description': 'Revestimento externo ilustrativo.', 'related': ['placa']},
            {'id': 'placa', 'kind': 'cube', 'label': 'Placa interna', 'group': 'internal',
             'role': 'functional', 'order': 2, 'description': 'Módulo interno ilustrativo.',
             'related': ['shell']},
            {'id': 'botao', 'kind': 'sphere', 'label': 'Botão', 'group': 'external',
             'role': 'optional', 'order': 3, 'description': 'Botão ilustrativo.', 'related': []},
        ],
        'steps': [{'title': 'Externo', 'text': 'A carcaça protege o conjunto.', 'selected': 'shell'}],
    })


def props_primitivo():
    return {'id': 'test', 'version': 1, 'objects': [{'id': 'cube', 'kind': 'cube'}]}


def test_v56_precisao_derivada_e_explicita():
    assert cena_grupos()['precision'] == 'aproximado'
    assert model3d.validate(scene('computer'))['precision'] == 'educativo'
    assert model3d.validate(scene('solar'))['precision'] == 'educativo'
    assert model3d.validate(props_primitivo())['precision'] == 'exato'
    assert model3d.validate(dict(props_primitivo(), model='demo-cube', objects=[]))['precision'] == 'exato'
    assert model3d.validate(dict(cena_grupos(), precision='conceitual'))['precision'] == 'conceitual'
    with pytest.raises(ValueError):
        model3d.validate(dict(cena_grupos(), precision='talvez'))


def test_v56_papel_grupo_e_ordem_por_peca():
    p = model3d.validate(scene('computer'))
    assert [o['role'] for o in p['objects']] == ['functional'] * 4
    assert all(o['group'] == '' and o['order'] == 0 for o in p['objects'])
    assert cena_grupos()['objects'][0]['role'] == 'structural'
    assert cena_grupos()['objects'][2]['role'] == 'optional'
    for patch in ({'role': 'chefe'}, {'group': 'interna'}, {'group': 'externa'},
                  {'order': -1}, {'order': 33}, {'order': True}, {'order': '2'}):
        q = copy.deepcopy(cena_grupos())
        q['objects'][0].update(patch)
        with pytest.raises(ValueError):
            model3d.validate(q)


def test_v56_fontes_controladas():
    base = {'id': 'dev', 'version': 1, 'title': 'Peça', 'education': 'device',
            'objects': [{'id': 'a', 'kind': 'cube'}]}
    for fonte in ('Catálogo local V5.6 — aparelho compacto',
                  'Aproximado por referências públicas — exemplo.com, outro.org',
                  'Modelo conceitual educativo — aspirador de pó'):
        assert model3d.validate(dict(base, source=fonte))['source'] == fonte
    assert model3d.validate(dict(base, source='Geometria procedural local'))['source'] == 'Geometria procedural local'
    ruins = ('Inventada', 'Catálogo local V5.6 — ' + 'x' * 200,
             'Catálogo local V5.6 — <script>', 'Aproximado por referências públicas — a\\nb')
    for fonte in ruins:
        with pytest.raises(ValueError):
            model3d.validate(dict(base, source=fonte))
    cubo = dict(props_primitivo(), model='demo-cube', objects=[])
    with pytest.raises(ValueError):
        model3d.validate(dict(cubo, source='Catálogo local V5.6 — aparelho'))
    assert model3d.validate(cubo)['source'] == 'Vexx AI — cubo GLB local original (CC0)'


def test_v56_paridade_py_js_schema_novo():
    import model3d_catalog as cat
    validos = [cena_grupos(), model3d.validate(scene('geometry')),
               model3d.validate(dict(props_primitivo(), precision='conceitual'))]
    validos.extend(model3d.validate(cat.cena(key)) for key in cat._FABRICAS)
    invalidos = []
    for patch in ({'role': 'x'}, {'group': 'interna'}, {'order': 33}, {'order': True}, {'order': '1'},
                  {'precision': 'talvez'}, {'source': 'Inventada'},
                  {'source': 'Catálogo local V5.6 — ' + 'y' * 200}):
        q = copy.deepcopy(cena_grupos())
        (q['objects'][0] if 'role' in patch or 'group' in patch or 'order' in patch else q).update(patch)
        invalidos.append(q)
    values = validos + invalidos
    code = """const fs=require('fs'),vm=require('vm');global.window=global;
    vm.runInThisContext(fs.readFileSync('public/model3d-schema.js','utf8'));
    console.log(JSON.stringify(JSON.parse(fs.readFileSync(0,'utf8')).map(p=>{
      try{return validateModel3D(p)}catch(e){return null}})));"""
    output = subprocess.run(['node', '-e', code], input=json.dumps(values), capture_output=True,
                            text=True, encoding='utf-8', cwd=ROOT, check=True)
    results = json.loads(output.stdout)
    for index, value in enumerate(values):
        if index < len(validos):
            assert model3d.validate(value) == results[index]
        else:
            with pytest.raises(ValueError):
                model3d.validate(value)
            assert results[index] is None


def test_v56_mostrar_apenas_internas_ou_externas():
    cena = cena_grupos()
    texto, p = model3d.respond('Mostre apenas as peças internas', cena)
    assert 'internas' in texto
    assert p['interaction']['hidden'] == ['shell', 'botao']
    texto, p = model3d.respond('Mostre apenas as peças externas', p)
    assert p['interaction']['hidden'] == ['placa']
    texto, p = model3d.respond('Oculte as partes externas', p)
    assert p['interaction']['hidden'] == ['shell', 'botao']
    texto, p = model3d.respond('Veja só as partes internas', p)
    assert p['interaction']['hidden'] == ['shell', 'botao']
    texto, p = model3d.respond('Mostre apenas as peças internas', scene('computer'))
    assert p is None and 'não classifica' in texto


def test_v56_isolate_por_frase_natural():
    p = scene('computer')
    texto, q = model3d.respond('Deixe só a placa-mãe', p)
    assert q['interaction']['isolated'] == 'motherboard' and texto
    _, q = model3d.respond('Mostre só a memória RAM', p)
    assert q['interaction']['isolated'] == 'ram'
    _, q = model3d.respond('Mostre somente a GPU', p)
    assert q['interaction']['isolated'] == 'gpu'
    # Pedido de cena 3D não vira filtro de parte.
    req = model3d.request('Mostre só um cubo em 3D')
    assert req['action'] == 'create' and req['kinds'] == ['cube']


def test_v56_esconda_a_peca():
    texto, p = model3d.respond('Esconda a GPU', scene('computer'))
    assert p['interaction']['hidden'] == ['gpu'] and texto


def test_v56_conexoes_entre_partes():
    p = scene('computer')
    _, p = model3d.respond('Destaque a CPU', p)
    texto, q = model3d.respond('Mostre como isso se conecta', p)
    assert 'Processador se conecta a: Placa-mãe, Memória RAM.' in texto
    assert q['interaction']['selected'] == 'cpu'
    texto, _ = model3d.respond('Mostre as conexões da placa-mãe', p)
    assert 'Placa-mãe se conecta a: Processador, Memória RAM, Placa de vídeo.' in texto
    texto, _ = model3d.respond('Mostre as conexões de Terra', scene('solar'))
    assert 'Terra se conecta a: Sol.' in texto
    texto, q = model3d.respond('Mostre as conexões de botão', cena_grupos())
    assert q['interaction']['selected'] == 'botao' and 'Nenhuma conexão' in texto
    texto, q = model3d.respond('Mostre as conexões', scene('computer'))
    assert q is None and 'Selecione' in texto
    texto, q = model3d.respond('Mostre as conexões do SSD', scene('computer'))
    assert q is None and 'Não encontrei' in texto


def test_v56_explique_como_funciona():
    p = scene('computer')
    texto, q = model3d.respond('Explique como funciona', p)
    assert q is not None and q['details'] and 'conceitual' in texto
    _, p = model3d.respond('Destaque a CPU', p)
    texto, q = model3d.respond('Explique como funciona', p)
    assert 'Em destaque: Processador' in texto


def test_v56_comandos_antigos_intactos():
    p = scene('computer')
    for comando, chave, valor in (('Separe as peças', 'exploded', True),
                                  ('Próximo passo', 'step', 1),
                                  ('Destaque a RAM', 'selected', 'ram'),
                                  ('Oculte a GPU', 'hidden', ['gpu'])):
        _, q = model3d.respond(comando, p)
        assert q['interaction'][chave] == valor
    for texto in ('Pause o vídeo', 'Gire o mouse'):
        assert model3d.respond(texto) is None
    texto, q = model3d.respond('Mostre um dragão em 3D')
    assert q is None and 'Não tenho um modelo' in texto


# --- FASE 6: catálogo local de dispositivos aproximados ---

def test_v56_catalogo_local_completo_e_honesto():
    import model3d_catalog as cat
    for chave in cat._FABRICAS:
        s = model3d.validate(cat.cena(chave))
        assert s['id'].startswith('dev-') and s['education'] == 'device'
        assert s['precision'] == 'aproximado'
        assert s['source'].startswith('Catálogo local V5.6 — ')
        assert 1 <= len(s['objects']) <= 32 and len(s['steps']) >= 3
        assert len(json.dumps(s, ensure_ascii=False, separators=(',', ':')).encode('utf-8')) <= 20000
        ids = [o['id'] for o in s['objects']]
        assert len(ids) == len(set(ids))
        for o in s['objects']:
            assert o['role'] in ('structural', 'functional', 'optional')
            assert o['group'] in ('', 'internal', 'external')
            assert 0 <= o['order'] <= 32
        assert 'aproximada' in s['description'].lower() or 'aproximado' in s['description'].lower()


def test_v56_cenas_com_grupos_internos_e_externos():
    import model3d_catalog as cat
    for chave in ('xbox', 'gabinete', 'celular', 'motor_v8', 'controle'):
        s = model3d.validate(cat.cena(chave))
        grupos = {o['group'] for o in s['objects']}
        assert 'internal' in grupos and 'external' in grupos, chave
        texto, q = model3d.respond('Mostre apenas as peças internas', s)
        assert q is not None and set(q['interaction']['hidden']) == {
            o['id'] for o in s['objects'] if o['group'] == 'external'}, chave


def test_v56_pedidos_de_dispositivo_viram_cena_aproximada():
    casos = (('me mostre um Xbox Series S em 3D', 'dev-console-branco', 'xbox series s'),
             ('cria um modelo 3D de um controle', 'dev-controle', 'controle'),
             ('quero ver um celular em 3D', 'dev-celular', 'celular'),
             ('me mostre um motor V8 em 3D', 'dev-motor-v8', 'motor v8'),
             ('mostre um gabinete gamer em 3D', 'dev-gabinete', 'gabinete gamer'),
             ('me mostra um monitor em 3D', 'dev-monitor', 'monitor'),
             ('mostre uma mesa gamer em 3D', 'dev-mesa', 'mesa gamer'),
             ('crie um modelo 3D de suporte de celular', 'dev-suporte-celular', 'suporte celular'),
             ('me mostre um headset em 3D', 'dev-headset', 'headset'),
             ('me mostra um PS2 em 3D', 'dev-console-escuro', 'ps2'))
    for texto, cena_id, assunto in casos:
        req = model3d.request(texto)
        assert req['action'] == 'create' and req.get('device'), texto
        assert req.get('topic') == assunto, texto
        resposta, p = model3d.respond(texto)
        assert p is not None and p['id'] == cena_id, texto
        assert p['education'] == 'device' and 'aproximada' in resposta, texto
    # Sem verbo, sem captura.
    assert model3d.request('xbox 3d') is None


def test_v56_notebook_e_placa_mae_na_rota_de_computador():
    for texto, cena_id in (('quero ver um notebook em 3D', 'dev-notebook'),
                           ('me mostre uma placa-mãe em 3D', 'dev-placa-mae')):
        _, p = model3d.respond(texto)
        assert p['id'] == cena_id and p['education'] == 'computer', texto
        assert p['precision'] == 'aproximado' and len(p['objects']) >= 9, texto
    _, classico = model3d.respond('Mostre um computador em 3D')
    assert classico['id'] == 'edu-computer'


def test_v56_interacao_conversacional_no_dispositivo():
    _, xbox = model3d.respond('me mostre um xbox series s em 3D')
    texto, q = model3d.respond('Destaque o corpo', xbox)
    assert q['interaction']['selected'] == 'corpo'
    texto, q = model3d.respond('Mostre como isso se conecta', q)
    assert q['interaction']['selected'] == 'corpo'
    assert 'Corpo se conecta a:' in texto
    texto, q = model3d.respond('Explique a ventoinha', q)
    assert 'ventoinha interna' in texto.lower()
    texto, q = model3d.respond('Separe as peças', q)
    assert q['interaction']['exploded']


# --- FASE 6/9: fluxo durável no pc_agent, sem LLM ---

def unpack(texto):
    return json.loads(jdui.extrair_fences(texto)[0])['blocks'][0]['props']


def test_v56_fluxo_de_dispositivo_continuacoes_e_isolamento(tmp_path, monkeypatch):
    import pc_agent
    db = pc_agent.open_db(tmp_path / 'v56.sqlite3')
    monkeypatch.setattr(pc_agent, 'gerar_texto',
                        lambda *a, **k: pytest.fail('Pedidos 3D não podem usar LLM'))
    pedido = dict(conversation_id='conv-v56', owner='u-alice', model='test')
    first = pc_agent.ai_completa(db, dict(pedido, message_id='v56-user-01',
                                          text='me mostre um Xbox Series S em 3D'), {'model': 'test'})
    props = unpack(first['response_text'])
    assert props['id'] == 'dev-console-branco'
    assert props['education'] == 'device' and props['precision'] == 'aproximado'
    second = pc_agent.ai_completa(db, dict(pedido, message_id='v56-user-02',
                                           text='mostre apenas as peças internas'), {'model': 'test'})
    p2 = unpack(second['response_text'])
    assert set(p2['interaction']['hidden']) == {
        o['id'] for o in p2['objects'] if o['group'] == 'external'}
    third = pc_agent.ai_completa(db, dict(pedido, message_id='v56-user-03',
                                          text='isso não está em 3D, reconstrua em 3D'), {'model': 'test'})
    p3 = unpack(third['response_text'])
    assert p3['id'] == 'dev-console-branco' and p3['autoRotate']
    # Resposta anterior foi texto: o pedido de dispositivo é reaproveitado na reconstrução.
    pc_agent.persist_messages(db, [
        dict(id='v56b-user-01', conversation_id='conv-v56b', origin='mobile', role='user',
             text='me mostre um gabinete gamer em 3D', created_at='2026-10-17T12:00:00.000Z'),
        dict(id='v56b-a01', conversation_id='conv-v56b', origin='mobile', role='assistant',
             text='Desenho em texto que não é 3D.', created_at='2026-10-17T12:00:02.000Z')], 'u-alice')
    out = pc_agent.ai_completa(db, {'message_id': 'v56b-user-02', 'conversation_id': 'conv-v56b',
                                    'text': 'isso não está em 3D, reconstrua em 3D', 'owner': 'u-alice'},
                               {'model': 'test'})
    assert unpack(out['response_text'])['id'] == 'dev-gabinete'
    # Sem referência acessível, comandos curtos não capturam ações de outros recursos.
    alheio = pc_agent.cmd_model3d(db, 'Amplie.', 'u-bob', 'conv-v56')
    assert alheio is None
    assert pc_agent.cmd_model3d(db, 'Amplie.', 'u-alice', 'outra-conversa') is None
    proprio = unpack(pc_agent.cmd_model3d(db, 'Amplie.', 'u-alice', 'conv-v56'))
    assert proprio['id'] == p3['id']
    assert proprio['camera']['distance'] < p3['camera']['distance']
    db.close()
