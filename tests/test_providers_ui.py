"""V5.4.3 — menu "Provedores de IA" na interface: a chave é salva SÓ no PC
(.env local), com status/origem honestos, remoção que restaura o sistema e
relay que transporta sem persistir, sem logar e sem ecoar a chave."""
import json
import os
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
import env_local
import providers
import server


RAIZ = Path(__file__).resolve().parents[1]
CHAVE_FAKE = "gsk_teste_fake_1234567890"


def setup_module():
    os.environ["JULIA_USERNAME"] = "efrai"
    os.environ["JULIA_PASSWORD_HASH"] = PasswordHasher().hash("strong-example-password")
    os.environ["JULIA_SESSION_SECRET"] = "a" * 64
    os.environ["JULIA_AGENT_TOKEN"] = "b" * 64
    server.login_failures.clear()


def login(client):
    r = client.post("/api/login", json={"username": "efrai",
                                        "password": "strong-example-password"})
    assert r.status_code == 200, r.text
    return r.json()["csrf"]


@pytest.fixture
def env_arquivo(tmp_path, monkeypatch):
    """Aponta o .env local para um arquivo descartável (nunca o do repo)."""
    caminho = tmp_path / "env-de-teste.env"
    monkeypatch.setenv("JULIA_ENV_FILE", str(caminho))
    for env in providers.PROVIDER_KEY_ENVS:
        monkeypatch.delenv(env, raising=False)
    return caminho


def test_variaveis_de_chave_batem_com_o_registro_de_provedores():
    assert env_local.PROVIDER_KEY_ENVS == providers.PROVIDER_KEY_ENVS
    assert "OPENAI_API_KEY" in providers.PROVIDER_KEY_ENVS


def test_salvar_e_remover_chave_preserva_o_resto_do_env(env_arquivo):
    env_arquivo.write_text("# topo\nJULIA_ENV=development\nOUTRA=1\n", encoding="utf-8")
    env_local.salvar_chave("GROQ_API_KEY", CHAVE_FAKE)
    texto = env_arquivo.read_text(encoding="utf-8")
    assert ("GROQ_API_KEY=" + CHAVE_FAKE) in texto
    assert "# topo" in texto and "OUTRA=1" in texto
    env_local.salvar_chave("GROQ_API_KEY", CHAVE_FAKE + "2")
    texto = env_arquivo.read_text(encoding="utf-8")
    assert texto.count("GROQ_API_KEY=") == 1  # atualiza no lugar, sem duplicar
    assert (CHAVE_FAKE + "2") in texto
    env_local.remover_chave("GROQ_API_KEY")
    texto = env_arquivo.read_text(encoding="utf-8")
    assert "GROQ_API_KEY" not in texto and "OUTRA=1" in texto
    with pytest.raises(ValueError):
        env_local.salvar_chave("GROQ_API_KEY", "quebra\nlinha")


def test_chave_do_arquivo_vence_a_do_sistema_e_origem_e_arquivo(env_arquivo, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "chave-antiga-do-sistema")
    env_local.salvar_chave("GROQ_API_KEY", CHAVE_FAKE)
    env_local.carregar_env_local()  # raiz=None → JULIA_ENV_FILE (como o agente)
    assert os.environ["GROQ_API_KEY"] == CHAVE_FAKE
    assert providers.chave("groq") == CHAVE_FAKE
    assert providers.chave_origem("groq") == "arquivo"
    env_local.remover_chave("GROQ_API_KEY")
    # Sem a linha no arquivo, o que resta no processo veio do ambiente (o
    # agente restaura/limpa isso no remover_chave_provedor — teste abaixo).
    assert providers.chave_origem("groq") == "sistema"


def test_agente_salva_valida_e_remove_chave(env_arquivo, monkeypatch):
    import pc_agent
    monkeypatch.setenv("GROQ_API_KEY", "chave-antiga-do-sistema")

    res = pc_agent.definir_chave_provedor({"provider": "groq", "key": CHAVE_FAKE})
    assert res == {"ok": True, "provider": "groq", "configured": True, "source": "arquivo"}
    assert CHAVE_FAKE not in json.dumps(res)  # resposta nunca devolve a chave
    assert os.environ["GROQ_API_KEY"] == CHAVE_FAKE  # efeito imediato, sem reiniciar
    assert CHAVE_FAKE in env_arquivo.read_text(encoding="utf-8")
    assert providers.chave_origem("groq") == "arquivo"

    for ruim in ({"provider": "hermes", "key": CHAVE_FAKE},
                 {"provider": "nao-existe", "key": CHAVE_FAKE},
                 {"provider": "groq", "key": "curta"},
                 {"provider": "groq", "key": "tem espaço na chave 123"},
                 {"provider": "groq", "key": "quebra\nlinha na chave"}):
        erro = pc_agent.definir_chave_provedor(ruim)
        assert erro.get("error") and erro.get("codigo") in ("provedor", "chave")
        assert CHAVE_FAKE not in json.dumps(erro)

    res2 = pc_agent.remover_chave_provedor({"provider": "groq"})
    assert res2["ok"] is True
    assert os.environ["GROQ_API_KEY"] == "chave-antiga-do-sistema"  # sistema voltou
    assert res2["configured"] is True and res2["source"] == "sistema"
    assert "GROQ_API_KEY" not in env_arquivo.read_text(encoding="utf-8")
    # Sem chave de sistema, remover deixa o provedor realmente sem chave.
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    pc_agent.definir_chave_provedor({"provider": "groq", "key": CHAVE_FAKE})
    res3 = pc_agent.remover_chave_provedor({"provider": "groq"})
    assert res3["configured"] is False and res3["source"] == ""


def test_relay_transporta_chave_do_provedor_e_nunca_ecoa():
    with TestClient(server.app) as client:
        # Sem login: 401. Logado sem CSRF: 403. Nada passa.
        r = client.post("/api/providers", json={"provider": "groq", "action": "set",
                                                "key": CHAVE_FAKE})
        assert r.status_code == 401
        csrf = login(client)
        r = client.post("/api/providers", json={"provider": "groq", "action": "set",
                                                "key": CHAVE_FAKE})
        assert r.status_code == 403 and CHAVE_FAKE not in r.text
        out = {}
        with client.websocket_connect(
                "/api/agent/ws",
                headers={"Authorization": "Bearer " + os.environ["JULIA_AGENT_TOKEN"]}) as ws:

            def chama():
                out["r"] = client.post("/api/providers",
                                       json={"provider": "groq", "action": "set",
                                             "key": CHAVE_FAKE},
                                       headers={"X-CSRF-Token": csrf})

            t = threading.Thread(target=chama)
            t.start()
            for _ in range(4):
                req = ws.receive_json()
                if req.get("type") == "sess_revogados":
                    ws.send_json({"request_id": req["request_id"],
                                  "type": "sess_revogados", "sids": []})
                    continue
                break
            assert req["type"] == "provider_key"
            assert req["provider"] == "groq" and req["action"] == "set"
            assert req["key"] == CHAVE_FAKE  # transporte PC-side (memória, sem persistir)
            assert req["owner"] == "local"  # dono vem da sessão, nunca do cliente
            ws.send_json({"request_id": req["request_id"], "type": "provider_key_ok",
                          "ok": True, "provider": "groq", "configured": True,
                          "source": "arquivo"})
            t.join(timeout=8)
            r = out["r"]
            assert r.status_code == 200
            assert r.json() == {"ok": True, "provider": "groq",
                                "configured": True, "source": "arquivo"}
            assert CHAVE_FAKE not in r.text  # resposta nunca carrega a chave

        # Tamanho inválido: 422 sem ecoar a chave.
        r = client.post("/api/providers", json={"provider": "groq", "action": "set",
                                                "key": "curta"},
                        headers={"X-CSRF-Token": csrf})
        assert r.status_code == 422 and "curta" not in r.text
        # Provedor com formato inválido: 422 do schema (sem eco do campo chave).
        r = client.post("/api/providers", json={"provider": "MAU!", "action": "set",
                                                "key": CHAVE_FAKE},
                        headers={"X-CSRF-Token": csrf})
        assert r.status_code == 422 and CHAVE_FAKE not in r.text


def test_agente_responde_erro_honesto_do_pc():
    """Erro vindo do PC chega ao app como 503 com o motivo, sem chave."""
    with TestClient(server.app) as client:
        csrf = login(client)
        with client.websocket_connect(
                "/api/agent/ws",
                headers={"Authorization": "Bearer " + os.environ["JULIA_AGENT_TOKEN"]}) as ws:
            out = {}

            def chama():
                out["r"] = client.post("/api/providers",
                                       json={"provider": "groq", "action": "del"},
                                       headers={"X-CSRF-Token": csrf})

            t = threading.Thread(target=chama)
            t.start()
            for _ in range(4):
                req = ws.receive_json()
                if req.get("type") == "sess_revogados":
                    ws.send_json({"request_id": req["request_id"],
                                  "type": "sess_revogados", "sids": []})
                    continue
                break
            assert req["type"] == "provider_key" and req["action"] == "del"
            assert req["key"] == ""  # remoção não carrega chave nenhuma
            ws.send_json({"request_id": req["request_id"], "type": "ai_error",
                          "error": "Provedor desconhecido ou sem chave gerenciável.",
                          "codigo": "provedor"})
            t.join(timeout=8)
            r = out["r"]
            assert r.status_code == 503
            assert "Provedor desconhecido" in r.json()["detail"]


def test_frontend_tem_o_menu_de_provedores_sem_guardar_chave():
    html = (RAIZ / "public" / "index.html").read_text(encoding="utf-8")
    js = (RAIZ / "public" / "app.js").read_text(encoding="utf-8", errors="replace")
    assert 'id="providersDialog"' in html
    assert 'id="providersOpen"' in html and "Provedores de IA" in html
    assert 'id="popProvidersRow"' in html  # atalho no status do chat
    assert "As chaves ficam" in html and "só neste PC" in html
    assert "'/api/providers'" in js
    assert ".type = 'password'" in js and "entrada.value = ''" in js
    assert "abrirProvedores" in js and "renderProviders" in js
    assert "Remover chave deste PC" in js
    # O app nunca persiste a chave (nem no navegador, nem no .env).
    assert "julia-providers" not in js and "providers.env" not in js
