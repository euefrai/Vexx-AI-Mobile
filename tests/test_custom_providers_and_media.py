"""Testes direcionados para provedores externos customizados, tunelamento,
rotas de latencia sem HTTP 500 e filtragem de icones/lixo de midia."""
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import custom_providers
import media_evidence
import providers
import server
from pc_modules import research_commands


def setup_module():
    os.environ["JULIA_USERNAME"] = "efrai"
    os.environ["JULIA_PASSWORD_HASH"] = PasswordHasher().hash("strong-example-password")
    os.environ["JULIA_SESSION_SECRET"] = "a" * 64
    os.environ["JULIA_AGENT_TOKEN"] = "b" * 64
    server.login_failures.clear()


def _login(client: TestClient) -> str:
    resp = client.post(
        "/api/login",
        json={"username": "efrai", "password": "strong-example-password"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["csrf"]


def test_custom_providers_crud_and_routing(tmp_path, monkeypatch):
    storage_file = tmp_path / "custom_providers.json"
    monkeypatch.setattr(custom_providers, "CUSTOM_PROVIDERS_FILE", storage_file)

    reg = custom_providers.salvar_custom_provider(
        {
            "id": "meu_ollama",
            "label": "Ollama GPU",
            "base": "http://192.168.1.50:11434/v1",
            "api_key": "tok-secreto-teste",
            "device_type": "ollama",
            "modelos": ["llama3:8b", "meta-llama/llama-3.3-70b"],
        }
    )
    assert reg["id"] == "custom_meu_ollama"
    assert reg["source"] == "custom_external"
    assert providers.definicao("custom_meu_ollama")["base"] == "http://192.168.1.50:11434/v1"
    assert providers.chave("custom_meu_ollama") == "tok-secreto-teste"

    # Roteamento tanto com modelo simples quanto modelo contendo barra "/"
    assert providers.dividir("custom_meu_ollama/llama3:8b") == ("custom_meu_ollama", "llama3:8b")
    assert providers.dividir("custom_meu_ollama/meta-llama/llama-3.3-70b") == (
        "custom_meu_ollama",
        "meta-llama/llama-3.3-70b",
    )
    assert providers.selection_error("custom_meu_ollama/meta-llama/llama-3.3-70b") is None

    assert custom_providers.remover_custom_provider("custom_meu_ollama") is True
    assert custom_providers.carregar_custom_providers() == {}


def test_tunnel_guide_no_hardcoded_secret_and_supports_all_modes():
    for tipo in ("ssh_reverse", "cloudflare", "ngrok", "localtunnel", "outro_pc_agente"):
        guide = custom_providers.gerar_instrucoes_tunel(tipo, 8008, "user@vps.example.com")
        assert guide.get("titulo")
        assert guide.get("comando")
        assert "510c2e" not in json.dumps(guide)


def test_routes_custom_providers_and_latency_no_500(tmp_path, monkeypatch):
    storage_file = tmp_path / "custom_providers.json"
    monkeypatch.setattr(custom_providers, "CUSTOM_PROVIDERS_FILE", storage_file)
    monkeypatch.setattr(server.relay, "ws", None)

    async def no_exchange(*args, **kwargs):
        raise RuntimeError("offline")

    monkeypatch.setattr(server.relay, "exchange", no_exchange)

    with TestClient(server.app) as client:
        csrf = _login(client)
        headers = {"X-CSRF-Token": csrf}

        # Rota sem autenticar falha por auth (401/403), nao vaza
        assert client.get("/api/tunnel/guide").status_code in (401, 403)

        guide_resp = client.get("/api/tunnel/guide?tipo=outro_pc_agente", headers=headers)
        assert guide_resp.status_code == 200
        assert guide_resp.json().get("comando")

        save_resp = client.post(
            "/api/providers/custom",
            headers=headers,
            json={
                "id": "remoto1",
                "label": "Servidor Externo",
                "base": "https://ia.exemplo.org/v1",
                "chave": "token-nunca-ecoar",
                "modelos": ["qwen2.5:14b"],
            },
        )
        assert save_resp.status_code == 200
        saved_json = save_resp.json()
        assert "token-nunca-ecoar" not in save_resp.text
        assert saved_json["provider"]["has_key"] is True

        models_resp = client.get("/api/ai/models")
        assert models_resp.status_code == 200
        models_data = models_resp.json()
        assert "custom_remoto1/qwen2.5:14b" in models_data["models"]

        # Rotas de latencia nunca devolvem HTTP 500 com PC offline/erro simulado
        r_ai_lat = client.post("/api/ai/latency-test", headers=headers)
        assert r_ai_lat.status_code == 200
        r_vis_lat = client.post("/api/vision/latency-test", headers=headers)
        assert r_vis_lat.status_code == 200

        del_resp = client.delete("/api/providers/custom/custom_remoto1", headers=headers)
        assert del_resp.status_code == 200
        assert del_resp.json()["removed"] is True


def test_media_evidence_filters_notification_bell_and_svg_icons():
    html = """
    <html><body>
      <img src="https://assets-v4.metroimg.com/sino-notificacoes.svg" alt="Sino das Notificações" width="64" height="64"/>
      <img src="https://cdn.exemplo.com/icons/notification-bell-logo.png" alt="Icone Logo"/>
      <img src="https://i.metroimg.com/fotos/celebridade-tapete-vermelho.jpg" alt="Ator no festival de cinema em Paris 2026" width="800" height="530"/>
    </body></html>
    """
    itens = media_evidence.extrair_midia(html, "https://www.exemplo.com/noticia", "Celebridades 2026")
    urls = [m["url"] for m in itens]
    assert "https://i.metroimg.com/fotos/celebridade-tapete-vermelho.jpg" in urls
    assert all("sino" not in u.lower() and "bell" not in u.lower() and not u.lower().endswith(".svg") for u in urls)


def test_research_commands_visual_filters_junk_before_media_fence(tmp_path):
    import pc_agent
    db = pc_agent.open_db(tmp_path / "vis.sqlite")
    fake_res = {
        "midia": [
            {
                "type": "image",
                "url": "https://assets-v4.metroimg.com/bell.png",
                "thumb": "https://assets-v4.metroimg.com/bell.png",
                "title": "Sino das Notificações",
                "source_title": "Metrópoles",
                "source_url": "https://www.exemplo.com",
            },
            {
                "type": "image",
                "url": "https://i.metroimg.com/fotos/ator-famoso-2026.jpg",
                "thumb": "https://i.metroimg.com/fotos/ator-famoso-2026.jpg",
                "title": "Foto oficial do evento em Paris",
                "source_title": "Metrópoles",
                "source_url": "https://www.exemplo.com",
            },
        ],
        "fontes": [{"titulo": "Celebridades", "url": "https://www.exemplo.com"}],
    }
    try:
        with patch("research.pesquisa_rapida", return_value=fake_res):
            res = research_commands.cmd_pesquisa(db, "mostre fotos de celebridades famosas", "alice", "conv-1")
    finally:
        db.close()
    assert "ator-famoso-2026.jpg" in res
    assert "Sino das Notificações" not in res
    assert "assets-v4.metroimg.com" not in res
