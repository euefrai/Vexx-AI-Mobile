"""Tests for VEXX 3D Overhaul: PBR materials, Exploded Views, X-Ray mode,
rich multi-part catalog assemblies, and Generative 3D Architect.
"""
import copy
import json
import os
import shutil
import subprocess
import pytest

import model3d
import model3d_catalog as cat
import model3d_generative
import pc_modules.visual_fences as visual_fences
import jdui

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_new_geometries_and_pbr_validation():
    base = {
        'id': 'test-pbr',
        'version': 1,
        'title': 'Objeto PBR',
        'education': 'device',
        'objects': [
            {
                'id': 'peca_1',
                'kind': 'cone',
                'position': [0, 0, 0],
                'dimensions': [1, 1, 1],
                'color': '#ff0000',
                'roughness': 0.25,
                'metalness': 0.85,
                'opacity': 0.9,
                'transparent': True,
                'wireframe': False,
                'emissive': '#220000',
                'explodeVector': [0, 1.2, 0],
                'role': 'functional',
                'group': 'external',
                'order': 1
            },
            {
                'id': 'peca_2',
                'kind': 'ring',
                'position': [0, -0.5, 0],
                'dimensions': [0.8, 0.8, 0.1],
                'color': '#00ff00',
                'roughness': 0.5,
                'metalness': 0.1,
                'role': 'structural',
                'group': 'internal',
                'order': 2
            }
        ],
        'steps': [
            {'title': 'Passo 1', 'text': 'Visão geral', 'selected': 'peca_1'},
            {'title': 'Passo 2', 'text': 'Raio X', 'selected': 'peca_2', 'xray': True},
            {'title': 'Passo 3', 'text': 'Explodido', 'selected': 'peca_1', 'exploded': True}
        ],
        'interaction': {'xray': False}
    }
    validated = model3d.validate(base)
    assert validated['objects'][0]['roughness'] == 0.25
    assert validated['objects'][0]['metalness'] == 0.85
    assert validated['objects'][0]['opacity'] == 0.9
    assert validated['objects'][0]['explodeVector'] == [0.0, 1.2, 0.0]
    assert validated['interaction']['xray'] is False
    assert validated['steps'][1]['xray'] is True


def test_xray_interaction_and_command():
    cena = cat.cena('turbina_aviao')
    text, resp = model3d.respond('modo raio x', cena)
    assert resp is not None
    assert resp['interaction']['xray'] is True
    assert 'Raio-X ativado' in text

    text2, resp2 = model3d.respond('desative o raio x', resp)
    assert resp2 is not None
    assert resp2['interaction']['xray'] is False
    assert 'Raio-X desativado' in text2


def test_catalog_rich_models():
    novos_modelos = [
        ('turbina_aviao', 19, 'turbina'),
        ('motor_v8', 21, 'v8'),
        ('smartphone_desmontado', 16, 'smartphone desmontado'),
        ('drone_quadricoptero', 14, 'drone'),
        ('coracao_humano', 16, 'coracao'),
        ('carro_eletrico', 20, 'carro eletrico'),
    ]
    for chave, min_pecas, busca in novos_modelos:
        # Resolver por busca natural
        resolvido = cat.resolver(cat._norm(f'quero ver um {busca} em 3d'))
        assert resolvido == chave, f"Resolver falhou para {busca}: obteve {resolvido}"

        # Fabricar e validar cena
        cena = cat.cena(chave)
        val = model3d.validate(cena)
        assert len(val['objects']) >= min_pecas, f"{chave} tem menos peças que o esperado"
        assert len(val['steps']) >= 4, f"{chave} tem menos de 4 etapas"
        assert val['precision'] == 'aproximado'
        assert val['source'].startswith('Catálogo local V5.6 — ')

        # Garantir que possui materiais PBR e explodeVector
        tem_explode = any('explodeVector' in o for o in val['objects'])
        tem_pbr = any('metalness' in o or 'roughness' in o for o in val['objects'])
        assert tem_explode, f"{chave} não possui explodeVector"
        assert tem_pbr, f"{chave} não possui materiais PBR"


def test_generative_3d_architect():
    # Deve sintetizar modelos para assuntos diversos
    for assunto in ['guitarra eletrica', 'estacao espacial', 'satelite orbital', 'microscopio']:
        cena = model3d_generative.gerar_modelo_3d(assunto)
        assert cena['id'].startswith('dev-')
        assert len(cena['objects']) >= 10
        assert len(cena['steps']) >= 3
        assert len(json.dumps(cena, ensure_ascii=False).encode('utf-8')) <= 20000


def test_js_python_parity_advanced_models():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node.js indisponível para teste de paridade')

    cenas = [
        cat.cena('turbina_aviao'),
        cat.cena('motor_v8'),
        cat.cena('smartphone_desmontado'),
        cat.cena('coracao_humano'),
        model3d_generative.gerar_modelo_3d('satelite orbital')
    ]
    validados_py = [model3d.validate(c) for c in cenas]

    code = """const fs=require('fs'),vm=require('vm');global.window=global;
    vm.runInThisContext(fs.readFileSync('public/model3d-schema.js','utf8'));
    const input=JSON.parse(fs.readFileSync(0,'utf8'));
    console.log(JSON.stringify(input.map(p=>validateModel3D(p))));"""

    out = subprocess.run([node, '-e', code], input=json.dumps(cenas),
                         text=True, encoding='utf-8', capture_output=True, cwd=ROOT, check=True)
    validados_js = json.loads(out.stdout)

    assert len(validados_py) == len(validados_js)
    for py, js in zip(validados_py, validados_js):
        assert py == js
