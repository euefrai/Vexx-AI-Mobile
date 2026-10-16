"""Identidade central nos caminhos reais de montagem e continuação do chat."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pc_agent
from assistant_identity import IDENTITY_RULES


@pytest.mark.parametrize('custom', [None, '', '   ', 'Você é a Júlia. ' + 'x' * 2500])
def test_config_preserves_identity_after_custom_prompt(monkeypatch, custom):
    if custom is None:
        monkeypatch.delenv('JULIA_SYSTEM_PROMPT', raising=False)
    else:
        monkeypatch.setenv('JULIA_SYSTEM_PROMPT', custom)
    system = pc_agent.ai_config()['system']
    assert system.endswith(IDENTITY_RULES)
    assert system.count(IDENTITY_RULES) == 1
    if not (custom or '').strip():
        assert pc_agent.SYSTEM_PADRAO in system


def test_identity_applies_to_existing_and_new_conversations(tmp_path, monkeypatch):
    monkeypatch.delenv('JULIA_SYSTEM_PROMPT', raising=False)
    cfg = dict(pc_agent.ai_config(), memoria_global=False, pesquisa_web=False)
    path = tmp_path / 'identity.sqlite3'
    db = pc_agent.open_db(path)
    pc_agent.persist_messages(db, [{
        'id': 'identity-user-01', 'conversation_id': 'old', 'origin': 'mobile',
        'role': 'user', 'text': 'Olá Júlia', 'created_at': pc_agent.agora_iso(),
    }])
    db.close()
    db = pc_agent.open_db(path)
    try:
        for conv in ('old', 'new'):
            messages, _ = pc_agent.ai_montar_mensagens(db, conv, cfg, 'Oi')
            assert messages[0]['role'] == 'system'
            assert messages[0]['content'].count(IDENTITY_RULES) == 1
        assert pc_agent.list_messages(db)[0]['text'] == 'Olá Júlia'
    finally:
        db.close()


def test_continue_applies_identity_even_with_legacy_config(tmp_path, monkeypatch):
    db = pc_agent.open_db(tmp_path / 'continue.sqlite3')
    mid = 'identity-user-02'
    pc_agent.ai_marcar(db, mid, 'old', 'm', 'completed',
                       reply_id=mid + '-r1', response_text='Primeira parte.')
    captured = []

    def generate(cfg, messages, **kwargs):
        captured.extend(messages)
        return {'texto': 'Segunda parte.', 'model_usado': 'm'}

    monkeypatch.setattr(pc_agent, 'gerar_texto', generate)
    try:
        result = pc_agent.ai_continuar(
            db, {'message_id': mid, 'conversation_id': 'old'},
            {'system': 'Você é o Vexx AI.', 'context': 5, 'model': 'm'})
        assert captured[0]['content'].count(IDENTITY_RULES) == 1
        assert result['response_text'] == 'Primeira parte. Segunda parte.'
    finally:
        db.close()
