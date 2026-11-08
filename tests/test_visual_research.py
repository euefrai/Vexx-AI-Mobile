"""Testes de integração de Visão Computacional (YOLOv8 + RapidOCR) na Área de Pesquisa e Deep Research."""
import sqlite3
import pytest
from unittest.mock import patch

import research_agents as ra
import research_synthesis as rs
import agentic_deep_research as adr


@pytest.fixture
def memory_db():
    conn = sqlite3.connect(":memory:")
    ra.criar_tabelas(conn)
    return conn


def test_criar_job_com_imagem_injeta_contexto_visual(memory_db):
    fake_vis = {
        "status": "sucesso",
        "tags_busca": "laptop, keyboard, apple",
        "texto_extraido": "MacBook Pro M3 Max 36GB",
        "total_objetos": 3,
        "total_textos": 1,
        "deteccoes": [
            {"tipo": "objeto", "objeto": "laptop", "confianca": 0.95, "ponto_clique": {"x": 100, "y": 200}},
            {"tipo": "objeto", "objeto": "keyboard", "confianca": 0.91, "ponto_clique": {"x": 110, "y": 220}},
        ],
        "textos_lidos": [
            {"tipo": "texto", "texto": "MacBook Pro M3 Max 36GB", "confianca": 0.98}
        ],
        "alvos_clique": []
    }

    with patch("vision_service.analisar_imagem", return_value=fake_vis):
        job = ra.criar_job(memory_db, "user-test", "comparar precos de notebook",
                           modo="pro", imagem="data:image/png;base64,iVBORw0KGgoAAAANSUhEUg==")

    assert "visual_context" in job["ajustes"]
    assert job["ajustes"]["visual_context"]["tags_busca"] == "laptop, keyboard, apple"
    assert len(job["midia"]) == 1
    assert "laptop" in job["midia"][0]["rotulos"]
    assert job["midia"][0]["texto_ocr"] == "MacBook Pro M3 Max 36GB"

    # Verifica persistência no banco
    loaded = ra.carregar_job(memory_db, "user-test", job["id"])
    assert loaded["ajustes"]["visual_context"]["tags_busca"] == "laptop, keyboard, apple"
    assert len(loaded["midia"]) == 1


def test_montar_plano_com_contexto_visual_enriquece_subconsultas(memory_db):
    job = {
        "id": "rj-vis1", "owner": "u1", "conv": "", "modo": "pro",
        "objetivo": "qual o desempenho do notebook?",
        "plano": [], "plano_versao": 1, "status": "criada",
        "orcamento": {"subs": 4, "buscas": 4, "paginas": 6},
        "usados": {"buscas": 0, "paginas": 0}, "midia": [],
        "achados": [], "pendencias": [], "erros": [],
        "ajustes": {
            "visual_context": {
                "tags_busca": "benchmark, gpu, rtx 4060",
                "texto_extraido": "Cinebench R23 15000 pts"
            }
        }
    }
    plano_res = ra.montar_plano(memory_db, job)
    alvos = [p["alvo"] for p in plano_res["plano"] if p["tipo"] == "busca"]
    # Garante que as tags visuais foram integradas nas buscas do plano
    assert any("benchmark" in a or "gpu" in a for a in alvos)


def test_research_synthesis_com_visual_context_comunica_com_ia():
    sources = [
        {"id": "E1", "evidence_id": "ev-1", "title": "Review Tech", "url": "https://tech.com/review",
         "excerpt": "O teste de renderizacao atingiu 15000 pontos em benchmark.",
         "scope": "page_text", "accessed_at": "2026-11-08"}
    ]
    verdicts = [{"afirmacao": "Pontuacao 15000", "estado": "SUPPORTED"}]
    vis_ctx = {
        "tags_busca": "laptop, screen",
        "texto_extraido": "15000 pts GPU",
        "deteccoes": [{"objeto": "laptop"}, {"objeto": "screen"}]
    }

    recorded_messages = []
    call_count = 0

    def mock_llm_fn(messages, timeout):
        nonlocal call_count
        call_count += 1
        recorded_messages.extend(messages)
        if call_count == 1:
            return '{"points": [{"text": "O notebook atingiu 15000 pontos no teste de renderizacao.", "evidence": [{"id": "E1", "quote": "O teste de renderizacao atingiu 15000 pontos em benchmark."}]}]}'
        return '{"reviews": [{"paragraph": 0, "state": "SUPPORTED", "reason": "none"}]}'

    mock_llm_fn.literal_quote_ids = False

    res = rs.generate(
        objective="Qual foi a pontuacao no teste?",
        sources=sources,
        verdicts=verdicts,
        generate_fn=mock_llm_fn,
        visual_context=vis_ctx
    )

    assert res is not None
    assert len(recorded_messages) >= 2
    # Verifica que o payload de mensagem enviado para a LLM contém as evidências visuais
    sys_content = recorded_messages[0]["content"]
    assert "YOLOv8" in sys_content or "visuais" in sys_content
    user_payload = recorded_messages[1]["content"]
    assert "visual_evidence" in user_payload
    assert "15000 pts GPU" in user_payload


def test_deep_investigate_topic_com_imagem_incorpora_evidencia_visual(monkeypatch):
    fake_vis = {
        "status": "sucesso",
        "tags_busca": "solar panel, inverter",
        "texto_extraido": "Eficiencia 22.5% Inversor 5kW",
        "total_objetos": 2,
        "total_textos": 1,
        "deteccoes": [{"objeto": "solar panel"}, {"objeto": "inverter"}]
    }

    fake_candidates = [
        {
            "title": "Paineis Solares 2026",
            "url": "https://solar.org/info-2026",
            "snippet": "A eficiencia media dos paineis solares alcancou 22.5% com inversores modernos.",
            "provider": "exa",
        },
        {
            "title": "Mercado Solar Global",
            "url": "https://global-energy.com/solar",
            "snippet": "Crescimento anual de 25% no setor fotovoltaico em 2026.",
            "provider": "tavily",
        },
        {
            "title": "Inversores Fotovoltaicos",
            "url": "https://inversores-tech.com/specs",
            "snippet": "Inversores de 5kW dominam a instalacao residencial.",
            "provider": "serper",
        },
    ]

    monkeypatch.setattr(adr.research, "url_segura", lambda u: u)
    monkeypatch.setattr(adr, "execute_parallel_searches", lambda *a, **kw: fake_candidates)
    monkeypatch.setattr(
        adr,
        "scrape_url_markdown",
        lambda url, fallback_snippet="", fallback_title="", **kw: {
            "url": url,
            "domain": adr._domain_of(url),
            "title": fallback_title,
            "markdown": f"# {fallback_title}\n\nA eficiencia alcancou 22.5% em 2026 com inversores de 5kW. " * 3,
            "method": "jina_reader",
            "ok": True,
            "structured": {},
        },
    )

    with patch("vision_service.analisar_imagem", return_value=fake_vis):
        resultado = adr.deep_investigate_topic(
            query="analise de mercado de energia solar",
            min_deep_links=3,
            max_retries=1,
            image="data:image/png;base64,fakeimage"
        )

        assert resultado["ok"] is True
        assert resultado["visual_context"] is not None
        assert resultado["visual_context"]["tags_busca"] == "solar panel, inverter"
        # O relatório em Markdown determinístico inclui a seção visual
        assert "Evidências Visuais e Análise de Imagem (YOLOv8 + RapidOCR)" in resultado["report_markdown"]
        assert "solar panel, inverter" in resultado["report_markdown"]
        assert "Eficiencia 22.5% Inversor 5kW" in resultado["report_markdown"]
