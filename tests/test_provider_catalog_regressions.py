"""Key persistence and discovery regression tests; no external services."""
import json
import os
from pathlib import Path
import subprocess
import sys
import threading

from fastapi.testclient import TestClient
import pytest

import env_local
import hermes_bridge
import pc_agent
import providers
import server


@pytest.fixture
def isolated_keys(tmp_path, monkeypatch):
    path = tmp_path / 'providers.env'
    monkeypatch.setenv('JULIA_ENV_FILE', str(path))
    monkeypatch.setattr(pc_agent, '_ORIGINAIS_PROVEDOR', {})
    for name in providers.PROVIDER_KEY_ENVS:
        monkeypatch.delenv(name, raising=False)
    return path


def test_saved_key_survives_new_process_and_is_used_for_streaming(isolated_keys, monkeypatch):
    key = 'qa-provider-secret-2026'
    result = pc_agent.definir_chave_provedor({'provider': 'groq', 'key': key})
    assert result['configured'] and key not in json.dumps(result)
    child_env = dict(os.environ)
    child_env.pop('GROQ_API_KEY', None)
    code = "import env_local,providers;env_local.carregar_env_local();assert providers.chave('groq')=='qa-provider-secret-2026';assert providers.chave_origem('groq')=='arquivo'"
    child = subprocess.run([sys.executable, '-c', code], env=child_env,
                           cwd=Path(__file__).resolve().parents[1], capture_output=True)
    assert child.returncode == 0, child.stderr.decode(errors='replace')
    seen = {}

    def stream(base, model, messages, on_delta, *args, **kwargs):
        seen.update(base=base, model=model, key=kwargs['api_key'])
        on_delta(1, 'fixture response')
        return {'texto': 'fixture response'}

    monkeypatch.setattr(hermes_bridge, 'chat_stream', stream)
    deltas = []
    providers.chat_stream('groq', 'fixture-model', [], lambda seq, text: deltas.append(text))
    assert seen == {'base': providers.PROVIDERS['groq']['base'], 'model': 'fixture-model', 'key': key}
    assert deltas == ['fixture response']


def test_discovery_parallel_and_free_models_survive_limits(isolated_keys, monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'qa-openai')
    monkeypatch.setenv('GROQ_API_KEY', 'qa-groq')
    barrier = threading.Barrier(3)

    def models(base, **kwargs):
        barrier.wait(timeout=5)  # Serial discovery would break this barrier.
        return [f'model-{i:04}' for i in range(550)] + ['last/free-model:free']

    monkeypatch.setattr(hermes_bridge, 'listar_modelos', models)
    catalog = providers.listar_tudo()
    assert len(catalog['models']) > 500
    for name in ['hermes', 'openai', 'groq']:
        items = [i for i in catalog['items'] if i['provider'] == name]
        assert items[0]['free'] is True
        assert len(items) == (500 if name == 'hermes' else 200)
    assert 'qa-openai' not in json.dumps(catalog)


def test_relay_keeps_late_provider_and_metadata(monkeypatch):
    items = [{'id': f'proxy/model-{i}', 'provider': 'hermes', 'free': False} for i in range(500)]
    items.append({'id': 'groq/fixture:free', 'provider': 'groq', 'free': True, 'key': 'never-return'})

    async def exchange(payload, **kwargs):
        return {'type': 'ai_models', 'models': [i['id'] for i in items], 'items': items,
                'providers': [{'id': 'groq', 'configured': True, 'source': 'arquivo'}]}

    monkeypatch.setattr(server, 'sessao_usuario', lambda request: 'local')
    monkeypatch.setattr(server.relay, 'exchange', exchange)
    with TestClient(server.app) as client:
        response = client.get('/api/ai/models')
    assert response.status_code == 200
    data = response.json()
    assert data['models'][-1] == 'groq/fixture:free'
    assert data['items'][-1] == {'id': 'groq/fixture:free', 'provider': 'groq', 'free': True}
    assert 'never-return' not in response.text
