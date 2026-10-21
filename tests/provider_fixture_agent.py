"""Test-only agent: real persistence/RPC, deterministic model discovery/inference."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pc_agent
import hermes_bridge


def models(base, **kwargs):
    key = kwargs.get('api_key')
    if key:
        if not key.startswith('qa-valid-provider-'):
            raise hermes_bridge.BridgeErro('Fixture rejected key', 'auth')
        return ['fixture-chat', 'fixture-reasoning']
    return [f'fixture/model-{i:04}' for i in range(510)] + ['fixture/fast:free']


def stream(base, model, messages, on_delta, *args, **kwargs):
    if not kwargs.get('api_key', '').startswith('qa-valid-provider-'):
        raise hermes_bridge.BridgeErro('Fixture requires saved key', 'auth')
    text = 'Resposta de teste com a chave salva e o modelo ' + model + '.'
    on_delta(1, text)
    return {'texto': text, 'model': model}


hermes_bridge.listar_modelos = models
hermes_bridge.chat_stream = stream

if __name__ == '__main__':
    pc_agent.run()
