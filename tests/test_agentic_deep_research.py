"""Testes para o módulo `agentic_deep_research.py` e endpoints de webhook."""
import hashlib
import hmac
import json
import threading
from fastapi.testclient import TestClient

import agentic_deep_research as adr
import server


def test_decompose_complex_query_and_self_correction():
    q1 = adr.decompose_complex_query("Qual a tendência de mercado de IA generativa vs Cloud em 2026?", attempt=1)
    assert 2 <= len(q1) <= 3
    q2 = adr.decompose_complex_query(
        "Qual a tendência de mercado de IA generativa vs Cloud em 2026?",
        attempt=2,
        failure_reason="zero resultados",
        previous_queries=q1,
    )
    assert 2 <= len(q2) <= 3
    assert set(q2) != set(q1)


def test_scrape_url_markdown_cascades_to_jina_on_403(monkeypatch):
    monkeypatch.setattr(adr.research, "url_segura", lambda u: u)

    def fake_get(url, headers=None, timeout=15.0, max_bytes=2097152):
        if url.startswith("https://r.jina.ai/"):
            return (
                200,
                url,
                "# Tênis Esportivo Corrida Pro\n\nPreço: R$ 349,90\nTamanhos disponíveis: 39, 40, 41, 42.\n"
                "Cores: Preto, Azul e Branco. Ideal para corrida e treino diário com amortecimento.",
            )
        raise PermissionError("HTTP 403 Forbidden - Anti-bot wall")

    monkeypatch.setattr(adr, "_http_get_text", fake_get)
    res = adr.scrape_url_markdown("https://loja-exemplo.com.br/tenis-pro")
    assert res["ok"] is True
    assert res["method"] == "jina_reader"
    assert "R$ 349,90" in res["markdown"]


def test_search_and_compare_products_retries_and_extracts_attributes(monkeypatch):
    monkeypatch.setattr(adr.research, "url_segura", lambda u: u)
    calls = {"attempt": 0}

    def fake_parallel(queries, max_results_per_query=5, timeout=12.0):
        calls["attempt"] += 1
        if calls["attempt"] == 1:
            return []  # Simula falha na 1ª tentativa para acionar o Loop Agêntico
        return [
            {
                "title": "Tênis Runner Pro Masculino",
                "url": "https://loja1.exemplo.com.br/runner-pro",
                "snippet": "Oferta Tênis Runner Pro",
                "provider": "tavily",
            },
            {
                "title": "Tênis Runner Pro Original",
                "url": "https://loja2.exemplo.com.br/runner-pro",
                "snippet": "Tênis Runner Pro com desconto",
                "provider": "serper",
            },
        ]

    pages = {
        "https://loja1.exemplo.com.br/runner-pro": {
            "url": "https://loja1.exemplo.com.br/runner-pro",
            "domain": "loja1.exemplo.com.br",
            "title": "Tênis Runner Pro Masculino - Loja 1",
            "markdown": (
                "# Tênis Runner Pro Masculino\n"
                "Por apenas R$ 299,90 à vista.\n"
                "Tamanhos: 38, 39, 40, 41, 42 e GG.\n"
                "Cores: Preto, Vermelho e Branco.\n"
                "Estilo: Esportivo Running."
            ),
            "method": "jina_reader",
            "ok": True,
            "structured": {},
        },
        "https://loja2.exemplo.com.br/runner-pro": {
            "url": "https://loja2.exemplo.com.br/runner-pro",
            "domain": "loja2.exemplo.com.br",
            "title": "Tênis Runner Pro Masculino - Loja 2",
            "markdown": (
                "# Tênis Runner Pro Masculino\n"
                "Preço promocional: R$ 279,00.\n"
                "Tamanhos: 40, 41, 42.\n"
                "Cores: Azul e Cinza.\n"
                "Estilo: Casual e Corrida."
            ),
            "method": "direct_html",
            "ok": True,
            "structured": {},
        },
    }

    monkeypatch.setattr(adr, "execute_parallel_searches", fake_parallel)
    monkeypatch.setattr(adr, "scrape_url_markdown", lambda url, **kw: pages[url])

    result = adr.search_and_compare_products("Tênis Runner Pro Masculino")
    assert result["ok"] is True
    assert result["attempts_used"] == 2
    assert len(result["products"]) == 2
    assert result["best_offer"]["price"] == 279.00
    assert result["best_offer"]["store"] == "loja2.exemplo.com.br"
    assert "Preto" in result["products"][1]["colors"]
    assert "40" in result["products"][0]["sizes"]
    assert "| Produto | Loja | Preço |" in result["markdown_table"]


def test_deep_investigate_topic_reads_3_deep_links_and_cross_references(monkeypatch):
    monkeypatch.setattr(adr.research, "url_segura", lambda u: u)

    fake_candidates = [
        {
            "title": "Relatório IA 2026 - Fonte A",
            "url": "https://analise-a.exemplo.org/ia-2026",
            "snippet": "Crescimento de 42% em agentes autônomos.",
            "provider": "exa",
        },
        {
            "title": "Panorama Mercado Cloud & IA - Fonte B",
            "url": "https://dados-b.exemplo.com/cloud-ia",
            "snippet": "Investimentos atingiram US$ 120 bilhões em 2026.",
            "provider": "tavily",
        },
        {
            "title": "Tendências Corporativas - Fonte C",
            "url": "https://instituto-c.exemplo.net/tendencias",
            "snippet": "Adoção empresarial cresceu 35% no último trimestre.",
            "provider": "serper",
        },
    ]

    monkeypatch.setattr(adr, "execute_parallel_searches", lambda *a, **kw: fake_candidates)
    monkeypatch.setattr(
        adr,
        "scrape_url_markdown",
        lambda url, fallback_snippet="", fallback_title="", **kw: {
            "url": url,
            "domain": adr._domain_of(url),
            "title": fallback_title,
            "markdown": f"# {fallback_title}\n\nO mercado apresentou crescimento de 42% em 2026. {fallback_snippet} " * 3,
            "method": "jina_reader",
            "ok": True,
            "structured": {},
        },
    )

    res = adr.deep_investigate_topic("Mercado de Agentes de IA em 2026", min_deep_links=3)
    assert res["ok"] is True
    assert res["met_min_deep_links"] is True
    assert res["sources_count"] >= 3
    assert res["cross_reference"]["independent_domains_count"] == 3
    assert res["cross_reference"]["confidence_level"] == "alta"
    assert "Relatório de Pesquisa Profunda" in res["report_markdown"]


def test_handle_webhook_response_and_fastapi_endpoint(monkeypatch):
    monkeypatch.setenv("JULIA_WEBHOOK_SECRET", "segredo-webhook-vexx")
    monkeypatch.setattr(adr.research, "url_segura", lambda u: u)

    delivered = []
    done_event = threading.Event()

    def fake_deliver(url, envelope, secret="", timeout=8.0, max_attempts=3):
        delivered.append((url, envelope))
        done_event.set()
        return {"delivered": True, "http_status": 200, "attempt": 1}

    monkeypatch.setattr(adr, "_deliver_webhook_sync", fake_deliver)
    monkeypatch.setattr(
        adr,
        "deep_investigate_topic",
        lambda q, **kw: {
            "ok": True,
            "mode": "deep_investigation",
            "query": q,
            "sources_count": 3,
            "report_markdown": "## Relatório OK",
        },
    )

    with TestClient(server.app) as client:
        resp = client.post(
            "/api/research/webhook",
            headers={"X-Vexx-Webhook-Token": "segredo-webhook-vexx"},
            json={
                "query": "Tendências de semicondutores 2026",
                "mode": "deep_investigate",
                "webhook_url": "https://webhook.exemplo.com/vexx-callback",
                "async_dispatch": True,
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["accepted"] is True
        assert body["status"] == "processing"

    assert done_event.wait(timeout=5.0)
    assert len(delivered) == 1
    assert delivered[0][0] == "https://webhook.exemplo.com/vexx-callback"
    assert delivered[0][1]["query"] == "Tendências de semicondutores 2026"
