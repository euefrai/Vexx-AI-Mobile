"""V5.6: fundações de montagem, novos comandos e (adiante) catálogo/pesquisa."""
import copy
import json
import subprocess
from pathlib import Path

import pytest
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
    validos = [cena_grupos(), model3d.validate(scene('geometry')),
               model3d.validate(dict(props_primitivo(), precision='conceitual'))]
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
