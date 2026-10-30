"""V5.8: deep research, media provenance, JDUI 4.0 and export contracts."""
import json
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import jdui
import media_evidence
import pc_agent
import research_agents as ra
import research_exports
import research_view


def _db():
    return pc_agent.open_db(Path(tempfile.mkdtemp()) / "v58.sqlite3")


def _msg(component, props):
    return {"version": jdui.VERSION,
            "blocks": [{"type": "ui", "component": component, "props": props}]}


def test_media_discovery_is_metadata_only_safe_and_deduplicated():
    html = """
    <html><head><title>Relatório</title>
    <meta property="og:image" content="https://cdn.example.com/hero.jpg">
    <meta property="og:image" content="https://cdn.example.com/hero.jpg">
    <meta property="article:published_time" content="2026-01-02">
    </head><body>
    <img src="https://cdn.example.com/logo.png" alt="">
    <img src="https://cdn.example.com/chart.png" alt="Gráfico de vendas">
    <a href="/arquivos/estudo.pdf">PDF</a>
    <a href="https://www.youtube.com/watch?v=abc123DEF45">Vídeo</a>
    <iframe src="https://www.youtube.com/embed/xyz987GHI65"></iframe>
    <a href="javascript:alert(1)">ruim</a>
    </body></html>
    """
    items = media_evidence.extrair_midia(html, "https://example.com/noticia", "Relatório")
    assert len(items) == 5
    assert {item["type"] for item in items} == {"image", "video", "document"}
    assert all(item["evidence"] is False and item["used_excerpt"] == "" for item in items)
    assert all(item["analysis_state"] == "not_analyzed" for item in items)
    assert all(item["source_url"] == "https://example.com/noticia" for item in items)
    assert all(not item["url"].startswith(("javascript:", "data:")) for item in items)
    assert len({item["url"] for item in items}) == len(items)
    image = next(item for item in items if item["title"] == "Gráfico de vendas")
    assert image["access_state"] == "metadata_only"
    assert image["rights"] == "não informado"
    doc = next(item for item in items if item["type"] == "document")
    assert doc["url"] == "https://example.com/arquivos/estudo.pdf"
    assert doc["access_state"] == "link_only"
    assert media_evidence.resumo_midia(items) == {
        "total": 5, "images": 2, "videos": 2, "documents": 1,
        "metadata_only": 2, "link_only": 3, "validated": 0, "analyzed": 0,
        "evidence": 0,
    }


def test_media_does_not_accept_unsafe_base_or_implicit_logo():
    assert media_evidence.extrair_midia("<img src='x' alt='foto'>", "javascript:alert(1)") == []
    html = "<html><img src='https://example.com/logo.png' alt=''><img src='data:image/png;base64,AA' alt='x'></html>"
    assert media_evidence.extrair_midia(html, "https://example.com/") == []


def test_plan_component_computes_progress_and_ignores_spoofed_percent():
    props = {
        "title": "Investigação", "objective": "Testar hipótese", "mode": "profunda",
        "status": "running",
        "progress": {"percent": 99, "done": 99, "total": 99},
        "steps": [
            {"id": "p1", "title": "Buscar", "status": "feita", "dependencias": []},
            {"id": "p2", "title": "Ler", "status": "em_andamento", "dependencias": ["p1"]},
            {"id": "p3", "title": "Auditar", "status": "pendente", "dependencias": ["p2"]},
        ],
        "budgets": {"buscas": 8, "paginas": 12}, "used": {"buscas": 2, "paginas": 1},
    }
    ok, norm, errs = jdui.validar_mensagem(_msg("researchplan", props))
    assert ok, errs
    painel = norm["blocks"][0]["props"]
    assert painel["progress"] == {"done": 1, "total": 3, "skipped": 0,
                                  "errors": 0, "percent": 33.3}
    assert painel["steps"][1]["status"] == "doing"
    assert painel["budgets"]["buscas"] == 8 and painel["used"]["buscas"] == 2


def test_evidence_component_requires_real_source_and_computes_counts():
    props = {"claims": [
        {"statement": "A dose é segura.", "state": "SUPPORTED", "method": "lexical",
         "coverage": 0.8,
         "sources": [
             {"id": "e1", "title": "Ensaio", "url": "https://example.com/ensaio",
              "relation": "SUPPORTS", "read": True, "excerpt": "400 mg"},
             {"id": "e2", "title": "Crítica", "url": "https://example.com/critica",
              "relation": "CONTRADICTS", "read": False, "excerpt": "risco"},
         ]},
        {"statement": "Nenhum dado específico.", "state": "UNVERIFIED", "sources": []},
    ]}
    ok, norm, errs = jdui.validar_mensagem(_msg("evidence", props))
    assert ok, errs
    claims = norm["blocks"][0]["props"]["claims"]
    assert claims[0]["found_count"] == 2
    assert claims[0]["read_count"] == 1
    assert claims[0]["supporting_count"] == 1
    assert claims[0]["contradicting_count"] == 1
    bad = {"claims": [{"statement": "Sem fonte", "state": "SUPPORTED", "sources": []}]}
    assert jdui.validar_mensagem(_msg("evidence", bad))[0] is False


def test_media_component_forces_discovery_to_non_evidence():
    props = {"items": [{
        "type": "image", "title": "Foto", "url": "https://example.com/foto.jpg",
        "source_url": "https://example.com/materia", "rights": "© site",
        "access_state": "metadata_only", "analysis_state": "visually_analyzed",
        "evidence": True,
    }]}
    ok, norm, errs = jdui.validar_mensagem(_msg("media", props))
    assert ok, errs
    item = norm["blocks"][0]["props"]["items"][0]
    assert item["evidence"] is False
    assert item["analysis_state"] == "not_analyzed"
    assert item["rights"] == "© site"


def test_filecard_accepts_only_real_export_or_remote_url():
    ok, norm, _ = jdui.validar_mensagem(_msg("filecard", {"files": [
        {"name": "Relatório", "url": "/api/research/export?job_id=rj-abc&formato=md",
         "kind": "md", "status": "available"},
        {"name": "PDF", "url": "https://example.com/a.pdf", "kind": "pdf"},
    ]}))
    assert ok
    assert norm["blocks"][0]["props"]["files"][0]["url"].startswith("/api/research/export?")
    for url in ("/api/admin/export?job_id=rj-abc", "javascript:alert(1)",
                "/api/research/export?job_id=../x&formato=md"):
        bad = {"files": [{"name": "x", "url": url, "kind": "md"}]}
        assert jdui.validar_mensagem(_msg("filecard", bad))[0] is False


def test_filecard_aceita_arquivo_gerado_e_rejeita_rota_ampla():
    ok, norm, erros = jdui.validar_mensagem(_msg("filecard", {"files": [
        {"name": "app.py", "url": "/api/files/file-0123456789ab/download",
         "kind": "code", "status": "generated"},
    ]}))
    assert ok, erros
    assert norm["blocks"][0]["props"]["files"][0]["kind"] == "code"
    for url in ("/api/files/file-0123456789ab",
                "/api/files/file-0123456789ab/download?x=1",
                "/api/files/../../admin/download",
                "/api/files/file-xyz/download"):
        bad = _msg("filecard", {"files": [
            {"name": "x.py", "url": url, "kind": "code"}]})
        assert jdui.validar_mensagem(bad)[0] is False


def _resumo():
    return {
        "id": "rj-abc123", "objetivo": "Testar a segurança do café",
        "modo": "profunda", "status": "concluida", "plano_versao": 2,
        "etapas": [
            {"id": "p1", "tipo": "busca", "alvo": "café segurança",
             "status": "feita", "objetivo_etapa": "localizar fontes",
             "criterio_conclusao": "fonte lida", "dependencias": []},
            {"id": "p2", "tipo": "auditar", "alvo": "", "status": "feita",
             "objetivo_etapa": "checar citações", "dependencias": ["p1"]},
        ],
        "orcamento": {"buscas": 8, "paginas": 12, "midia": 16},
        "usados": {"buscas": 3, "paginas": 2},
        "evidencias": 2,
        "achados": [{"afirmacao": "O café é seguro em doses de 400 mg.",
                     "estado": "SUPPORTED", "metodo": "lexical", "cobertura_lexica": 0.9,
                     "fontes": [{"evidence_id": "ev1", "title": "Ensaio",
                                 "url": "https://example.com/ensaio", "domain": "example.com",
                                 "relation": "SUPPORTS", "read": True,
                                 "access_state": "read", "used_excerpt": "400 mg"}]}],
        "hipoteses": [{"statement": "O café causa insônia?",
                       "cadeia": [{"rotulo": "HIPÓTESE", "texto": "O café causa insônia?"},
                                  {"rotulo": "CONCLUSÃO", "texto": "EM ABERTO"}]}],
        "midia": [{"type": "image", "title": "Gráfico", "url": "https://example.com/g.png",
                   "source_url": "https://example.com/materia", "publisher": "example.com",
                   "access_state": "metadata_only", "validation_state": "unverified",
                   "analysis_state": "not_analyzed", "evidence": False,
                   "rights": "não informado", "date": "2026-01-01"}],
        "midia_resumo": {"total": 1},
    }


def test_research_view_validates_real_data_and_links_exports():
    message = research_view.build_view(_resumo())
    ok, norm, errs = jdui.validar_mensagem(message)
    assert ok, errs
    components = [block.get("component") for block in norm["blocks"] if block["type"] == "ui"]
    assert components == ["researchplan", "evidence", "accordion", "media", "filecard"]
    assert norm["blocks"][0]["content"].startswith("**Objetivo:**")
    files = norm["blocks"][-1]["props"]["files"]
    assert all("/api/research/export?job_id=rj-abc123&formato=" in item["url"] for item in files)
    assert norm["blocks"][-2]["props"]["items"][0]["evidence"] is False


def test_research_view_omits_invalid_component_without_raw_json():
    resumo = _resumo()
    resumo["midia"][0]["url"] = "javascript:alert(1)"
    message = research_view.build_view(resumo)
    ok, norm, errs = jdui.validar_mensagem(message)
    assert ok, errs
    assert all(block.get("component") != "media" for block in norm["blocks"])
    assert "Componentes omitidos" in norm["blocks"][0]["content"]
    assert "javascript" not in json.dumps(norm)


def test_exports_are_real_bounded_bytes_and_csv_safe():
    resumo = _resumo()
    resumo["achados"][0]["afirmacao"] = "=SUM(A1:A2) café"
    evidence = [{"id": "ev1", "titulo": "Ensaio", "url": "https://example.com/ensaio",
                 "dominio": "example.com", "status": "recuperada",
                 "texto_lido": True, "access_state": "read",
                 "trecho": "O café é seguro em doses de 400 mg.", "publicado_em": "2026-01-01"}]
    hypotheses = [{"hypothesis_id": "h1", "statement": "Café causa insônia?",
                   "status": "open", "result_summary": "em aberto",
                   "chain": [{"label": "HIPÓTESE", "text": "Café causa insônia?"},
                             {"label": "CONCLUSÃO", "text": "EM ABERTO"}]},
                  {"hypothesis_id": "h2", "statement": "Chá melhora o sono?",
                   "status": "open",
                   "cadeia": [{"rotulo": "HIPÓTESE", "texto": "Chá melhora o sono?"},
                              {"rotulo": "CONCLUSÃO", "texto": "EM ABERTO"}]}]
    md, mime, name = research_exports.build_export(resumo, evidence, hypotheses, "md")
    assert mime.startswith("text/markdown") and name.endswith(".md")
    assert b"# Relat" in md and b"400 mg" in md and b"n\xc3\xa3o s\xc3\xa3o evid" in md
    assert b"**HIP\xc3\x93TESE:**" in md and b"Ch\xc3\xa1 melhora o sono?" in md
    csv_bytes, mime_csv, name_csv = research_exports.build_export(
        resumo, evidence, hypotheses, "csv")
    assert mime_csv.startswith("text/csv") and name_csv.endswith(".csv")
    assert csv_bytes.startswith(b"\xef\xbb\xbf")
    text = csv_bytes.decode("utf-8-sig")
    assert "'=SUM(A1:A2)" in text
    assert "javascript" not in text
    js, mime_json, _ = research_exports.build_export(resumo, evidence, hypotheses, "json")
    data = json.loads(js.decode("utf-8"))
    assert data["schema"] == "vexx-research-export/v1"
    assert data["claims"][0]["estado"] == "SUPPORTED"
    assert data["media"][0]["evidence"] is False
    with pytest.raises(research_exports.ExportError):
        research_exports.build_export(resumo, evidence, hypotheses, "html")


def test_exports_reject_oversize(monkeypatch):
    monkeypatch.setattr(research_exports, "MAX_EXPORT_BYTES", 10)
    with pytest.raises(research_exports.ExportError):
        research_exports.build_export(_resumo(), [], [], "json")


def test_analyst_persists_media_and_verifier_records_read_sources():
    db = _db()
    try:
        job = ra.criar_job(db, "u-v58", "café é seguro em doses de 400 mg?", manual="pro")
        ra.montar_plano(db, job)
        etapa = next(s for s in job["plano"] if s["tipo"] == "ler")
        html = ('<html><head><title>Ensaio</title>'
                '<meta property="og:image" content="https://example.com/grafico.png"></head>'
                '<body><a href="https://example.com/estudo.pdf">PDF</a></body></html>')

        def recuperar(_url):
            return {"titulo": "Ensaio", "texto": "O café é seguro em doses de 400 mg.",
                    "final": "https://example.com/ensaio", "texto_lido": True,
                    "trecho_usado": "O café é seguro em doses de 400 mg.",
                    "access_state": "read",
                    "midia": media_evidence.extrair_midia(html, "https://example.com/ensaio")}

        evs = ra.agente_analista(
            db, job, etapa,
            [{"id": "f1", "titulo": "Ensaio", "url": "https://example.com/ensaio",
              "trecho": "O café é seguro em doses de 400 mg.", "dominio": "example.com"}],
            recuperar_fn=recuperar)
        assert len(evs) == 1
        assert evs[0]["texto_lido"] is True and evs[0]["access_state"] == "read"
        assert job["midia"] and all(item["evidence"] is False for item in job["midia"])
        ra.salvar_job(db, job)
        salvo = ra.carregar_job(db, "u-v58", job["id"])
        assert len(salvo["midia"]) == len(job["midia"])
        assert any(ev["tipo"] == "media_discovered"
                   for ev in ra.eventos_desde(db, "u-v58", job["id"]))
        vereditos = ra.agente_verificador(db, job, ra.listar_evidencias(db, "u-v58", job["id"]))
        assert vereditos
        primeiro = vereditos[0]
        assert primeiro["fontes"] and primeiro["fontes"][0]["read"] is True
        assert primeiro["fontes"][0]["used_excerpt"]
        assert primeiro["fontes_encontradas"] >= 1
    finally:
        db.close()


def test_relay_view_and_export_routes_return_real_validated_bytes():
    import os
    import threading
    from argon2 import PasswordHasher
    from fastapi.testclient import TestClient
    import server
    from test_auth import _agente_generico, _login_legacy

    os.environ["JULIA_USERNAME"] = "owneruser"
    os.environ["JULIA_PASSWORD_HASH"] = PasswordHasher().hash("strong-example-password")
    os.environ["JULIA_SESSION_SECRET"] = "a" * 64
    os.environ["JULIA_AGENT_TOKEN"] = "b" * 64
    server.login_failures.clear()
    resumo = _resumo()

    def fake(req):
        tipo = req.get("type")
        if tipo == "research_job_status":
            if req.get("job_id") == "rj-none":
                return {"type": "research_error", "codigo": "ausente",
                        "error": "Pesquisa não encontrada"}
            return {"type": "research_status", "resumo": resumo,
                    "eventos": [{"seq": 1, "tipo": "research_completed"}]}
        if tipo == "research_job_evidence":
            return {"type": "research_evidence", "evidencias": [{
                "id": "ev1", "titulo": "Ensaio", "url": "https://example.com/ensaio",
                "dominio": "example.com", "status": "recuperada", "texto_lido": True,
                "access_state": "read", "trecho": "O café é seguro em 400 mg."}]}
        if tipo == "research_job_hypotheses":
            return {"type": "research_hypotheses", "hypotheses": [{
                "hypothesis_id": "h1", "statement": "Café causa insônia?",
                "status": "open"}]}
        return {"type": "learn_error", "error": "?", "codigo": "erro"}

    with TestClient(server.app) as client:
        with client.websocket_connect(
                "/api/agent/ws", headers={"Authorization": "Bearer " + os.environ["JULIA_AGENT_TOKEN"]}) as ws:
            vistos = {}
            rr = {key: fake for key in ("research_job_status", "research_job_evidence",
                                        "research_job_hypotheses")}
            thread = threading.Thread(target=_agente_generico, args=(ws, rr, vistos), daemon=True)
            thread.start()
            csrf = _login_legacy(client)
            h = {"X-CSRF-Token": csrf}
            r = client.get("/api/research/view?job_id=rj-abc123", headers=h)
            assert r.status_code == 200, r.text
            mensagem = r.json()["message"]
            ok, norm, erros = jdui.validar_mensagem(mensagem)
            assert ok, erros
            assert any(block.get("component") == "filecard" for block in norm["blocks"])
            assert vistos["research_job_status"]["owner"] == "local"
            r = client.get("/api/research/export?job_id=rj-abc123&formato=csv", headers=h)
            assert r.status_code == 200, r.text
            assert r.content.startswith(b"\xef\xbb\xbf")
            assert "text/csv" in r.headers["content-type"]
            assert "attachment" in r.headers["content-disposition"]
            assert r.headers["x-content-type-options"] == "nosniff"
            assert client.get("/api/research/export?job_id=rj-abc123&formato=html",
                              headers=h).status_code == 422
            assert client.get("/api/research/view?job_id=rj-none",
                              headers=h).status_code == 404


def test_plan_rejects_redundant_subquestions_and_duplicate_queries(monkeypatch):
    db = _db()
    try:
        monkeypatch.setattr(ra.research, "dividir_subconsultas",
                            lambda objetivo, limite: ["Café seguro", "cafe seguro!",
                                                      "Café seguro", "Chá verde"])
        job = ra.criar_job(db, "u-dedup", "café e chá", manual="pro")
        ra.montar_plano(db, job)
        buscas = [s for s in job["plano"] if s["tipo"] == "busca"]
        assert [s["alvo"] for s in buscas] == ["Café seguro", "Chá verde"]
        primeira = buscas[0]

        class Provedor:
            nome = "fake"

            def buscar(self, consulta, limite=6):
                return [{"titulo": "Fonte", "url": "https://example.com/fonte",
                         "trecho": "Café seguro."}]

        prov = Provedor()
        ra.agente_busca(db, job, primeira, [prov], vistas=set())
        outra = dict(primeira, id="p99")
        achados = ra.agente_busca(db, job, outra, [prov], vistas=set())
        assert achados == []
        assert any(ev["tipo"] == "search_skipped_duplicate"
                   for ev in ra.eventos_desde(db, "u-dedup", job["id"]))
    finally:
        db.close()
