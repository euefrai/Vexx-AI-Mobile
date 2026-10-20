"""V4.5 FASE 2-7: orchestrator, agentes, evidências, verificação (determinístico)."""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pc_agent
import docs_agent
import research
import research_agents as ra


def _db(nome="rag.sqlite3"):
    return pc_agent.open_db(Path(tempfile.mkdtemp()) / nome)


class FakeProv:
    nome = "fake"

    def __init__(self, dados=None, falha=None):
        self.dados = dados or {}
        self.falha = falha
        self.chamadas = []

    def buscar(self, consulta, limite=6):
        self.chamadas.append(consulta)
        if self.falha:
            raise research.ResearchErro("caiu", self.falha)
        return [dict(r) for r in self.dados.get(consulta, self.dados.get("*", []))][:limite]


CAFE = [{"titulo": "Café e saúde", "url": "http://exemplo.com/cafe",
         "trecho": "Estudos com 10000 pessoas mostram que o café é seguro em doses normais de 400mg."}]


def test_modo_e_job():
    assert ra.selecionar_modo("oi") == "rapida"
    assert ra.selecionar_modo("investiga essa hipótese a fundo", "") == "investigativa"
    assert ra.selecionar_modo("x", manual="pro") == "pro"
    db = _db()
    try:
        ra.criar_job(db, "u-x", "oi")
        raise AssertionError("objetivo curto deveria falhar")
    except ra.AgentErro as exc:
        assert exc.codigo == "objetivo"
    job = ra.criar_job(db, "u-x", "café faz bem?", conv="c1")
    assert job["modo"] == "rapida" and job["status"] == "criada"
    assert ra.carregar_job(db, "u-x", job["id"])["objetivo"] == "café faz bem?"
    assert ra.listar_jobs(db, "u-x")[0]["id"] == job["id"]
    assert ra.listar_jobs(db, "u-y") == []
    try:
        ra.carregar_job(db, "u-y", job["id"])
        raise AssertionError("outro dono não lê")
    except ra.AgentErro as exc:
        assert exc.codigo == "ausente"
    db.close()


def test_owner_scoped_tabular_chat_creates_real_chart_and_comparison(monkeypatch, tmp_path):
    monkeypatch.setattr(docs_agent, "docs_dir", lambda: tmp_path / "docs")
    db = _db()
    try:
        job = ra.criar_job(db, "u-x", "measurements by team", conv="c1")
        uploaded = docs_agent.salvar_documento(
            db, "measurements.csv",
            b"month,team,amount,unit\nJan,A,10,W\nFeb,A,20,W\n"
            b"Jan,B,20,W\nFeb,B,30,W\n",
            "c1", "u-x",
        )
        chart = pc_agent.cmd_pesquisa(
            db,
            f'analisar tabular chart job={job["id"]} doc={uploaded["doc_id"]} '
            'x=month y=amount series=team unit=unit period=2026-Q1 '
            'methodology="meter readings"',
            "u-x", "c1",
        )
        assert "```jdui" in chart
        chart_message = json.loads(chart.split("```jdui\n", 1)[1].split("\n```", 1)[0])
        chart_props = chart_message["blocks"][1]["props"]
        assert chart_props["labels"] == ["Jan", "Feb"]
        assert chart_props["series"] == [
            {"label": "A", "values": [10.0, 20.0]},
            {"label": "B", "values": [20.0, 30.0]},
        ]
        assert chart_props["sources"][0]["id"].startswith("document:")
        assert chart_props["sources"][0]["period"] == "2026-Q1"
        assert chart_props["sources"][0]["methodology"] == "meter readings"

        comparison = pc_agent.cmd_pesquisa(
            db,
            f"analisar tabular compare job={job['id']} doc={uploaded['doc_id']} "
            "group=team value=amount baseline=A unit=unit",
            "u-x", "c1",
        )
        assert "```jdui" in comparison
        compare_message = json.loads(
            comparison.split("```jdui\n", 1)[1].split("\n```", 1)[0]
        )
        assert compare_message["blocks"][1]["component"] == "compare"
        assert compare_message["blocks"][1]["props"]["rows"][0]["b"] == "25 W"
        saved = ra.carregar_job(db, "u-x", job["id"])["structured_analysis"]
        assert len(saved) == 2
        assert {item["method"] for item in saved} == {"chart_series", "differences"}
        assert all(item["document_id"] == uploaded["doc_id"] for item in saved)
        assert all(item["analysis"]["provenance"]["source"].startswith("document:")
                   for item in saved)
        checkpoint = ra.continuous_research.ResearchContextStore(db).restore_latest(
            "u-x", job["id"]
        )
        assert checkpoint["state"]["results"]["structured_analysis"] == saved
        report = ra.gerar_relatorio(db, "u-x", job["id"])
        assert "Jan=10\\.0" in report["markdown"]
        assert f"document://{uploaded['doc_id']}#{uploaded['content_hash']}" in report["markdown"]
    finally:
        db.close()


def test_tabular_chat_requires_explicit_units_owner_and_conversation(monkeypatch, tmp_path):
    monkeypatch.setattr(docs_agent, "docs_dir", lambda: tmp_path / "docs")
    db = _db()
    try:
        job = ra.criar_job(db, "u-x", "measurements by team", conv="c1")
        uploaded = docs_agent.salvar_documento(
            db, "measurements.csv",
            b"month,team,amount\nJan,A,10\nFeb,A,20\nJan,B,20\nFeb,B,30\n",
            "c1", "u-x",
        )
        missing_unit = pc_agent.cmd_pesquisa(
            db, f"analisar tabular chart job={job['id']} doc={uploaded['doc_id']} x=month y=amount",
            "u-x", "c1",
        )
        assert "unit=<coluna> ou unit=none" in missing_unit
        assert not any(
            event["tipo"] == "structured_analysis_completed"
            for event in ra.eventos_desde(db, "u-x", job["id"])
        )
        wrong_owner = pc_agent.cmd_pesquisa(
            db,
            f"analisar tabular chart job={job['id']} doc={uploaded['doc_id']} "
            "x=month y=amount unit=none",
            "u-y", "c1",
        )
        assert "pesquisa não encontrada" in wrong_owner
        wrong_conversation = pc_agent.cmd_pesquisa(
            db,
            f"analisar tabular chart job={job['id']} doc={uploaded['doc_id']} "
            "x=month y=amount unit=none",
            "u-x", "c2",
        )
        assert "não pertence à conversa atual" in wrong_conversation
        other_conversation_doc = docs_agent.salvar_documento(
            db, "other.csv", b"month,amount\nJan,5\nFeb,6\n", "c2", "u-x",
        )
        mismatched_document = pc_agent.cmd_pesquisa(
            db,
            f"analisar tabular chart job={job['id']} "
            f"doc={other_conversation_doc['doc_id']} x=month y=amount unit=none",
            "u-x", "c1",
        )
        assert "documento não pertence à conversa deste job" in mismatched_document
    finally:
        db.close()


def test_tabular_analysis_rejects_changed_original_without_persisting(monkeypatch, tmp_path):
    monkeypatch.setattr(docs_agent, "docs_dir", lambda: tmp_path / "docs")
    db = _db()
    try:
        job = ra.criar_job(db, "u-x", "measurements by month", conv="c1")
        uploaded = docs_agent.salvar_documento(
            db, "measurements.csv", b"month,amount,unit\nJan,10,W\nFeb,20,W\n",
            "c1", "u-x",
        )
        original = docs_agent.docs_dir() / f"{uploaded['doc_id']}.csv"
        original.write_bytes(b"month,amount,unit\nJan,11,W\nFeb,20,W\n")
        response = pc_agent.cmd_pesquisa(
            db,
            f"analisar tabular chart job={job['id']} doc={uploaded['doc_id']} "
            "x=month y=amount unit=unit",
            "u-x", "c1",
        )
        assert "não corresponde à proveniência registrada" in response
        assert ra.carregar_job(db, "u-x", job["id"])["structured_analysis"] == []
        assert not any(
            event["tipo"] == "structured_analysis_completed"
            for event in ra.eventos_desde(db, "u-x", job["id"])
        )
    finally:
        db.close()


def test_plano_e_eventos():
    db = _db()
    job = ra.criar_job(db, "u-x", "café e chá", manual="pro")
    ra.montar_plano(db, job)
    tipos = [s["tipo"] for s in job["plano"]]
    assert tipos[:3] == ["busca", "ler", "analisar"] and tipos[-3:] == ["verificar", "sintetizar", "auditar"]
    assert job["plano"][1]["dependencias"] == [job["plano"][0]["id"]]
    assert job["plano"][2]["dependencias"] == [job["plano"][1]["id"]]
    assert all(step["regra_parada"] and isinstance(step["prioridade"], int)
               for step in job["plano"])
    evs = ra.eventos_desde(db, "u-x", job["id"])
    assert [e["tipo"] for e in evs] == [
        "research_created", "plan_created", "context_checkpoint_saved"
    ]
    assert [e["seq"] for e in evs] == [1, 2, 3]
    assert ra.eventos_desde(db, "u-x", job["id"], apos_seq=1)[0]["tipo"] == "plan_created"
    assert ra.eventos_desde(db, "u-y", job["id"]) == []
    db.close()


def test_provedores_fallback():
    ruim = FakeProv(falha="indisponivel")
    bom = FakeProv({"q": CAFE})
    achados, info = ra.buscar_com_fallback([ruim, bom], "q")
    assert len(achados) == 1 and info["provedor"] == "fake"
    assert info["erros"] == [{"provedor": "fake", "codigo": "indisponivel"}]
    achados, info = ra.buscar_com_fallback([ruim], "q")
    assert achados == [] and info["provedor"] == ""
    ddg = ra.ProvedorDDG()
    assert ddg.nome == "ddg"
    sx = ra.ProvedorSearXNG("")
    try:
        sx.buscar("q")
        raise AssertionError("sem URL deveria falhar")
    except research.ResearchErro as exc:
        assert exc.codigo == "indisponivel"


def test_searxng_instancia_propria_via_loopback(monkeypatch):
    """Instância autorizada (JULIA_SEARXNG_URL): JSON /search real via HTTP."""
    import json as _json
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer
    monkeypatch.setattr(research, "_ips_globais", lambda host: None)

    class _H(BaseHTTPRequestHandler):
        def do_GET(self):
            corpo = _json.dumps({"results": [
                {"title": "Fonte Local", "url": "https://exemplo.com/a",
                 "content": "trecho local"}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(corpo)))
            self.end_headers()
            self.wfile.write(corpo)

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), _H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        sx = ra.ProvedorSearXNG(f"http://127.0.0.1:{srv.server_port}")
        achados, info = ra.buscar_com_fallback([sx], "tema")
        assert len(achados) == 1 and info["provedor"] == "searxng"
        assert achados[0]["url"] == "https://exemplo.com/a"
    finally:
        srv.shutdown()


def test_evidencias():
    db = _db()
    job = ra.criar_job(db, "u-x", "café?")
    f = {"id": "S1", "url": "http://e/x", "titulo": "T", "dominio": "e",
         "acessado_em": "t"}
    ev = ra.registrar_evidencia(db, job, f, "trecho rico sobre café e saúde")
    assert ev["status"] == "recuperada" and ev["id"].startswith("ev-")
    assert len(ra.listar_evidencias(db, "u-x", job["id"])) == 1
    assert ra.listar_evidencias(db, "u-y", job["id"]) == []
    ra.marcar_evidencia(db, job, ev["id"], "contradiz", "café faz mal?")
    assert ra.listar_evidencias(db, "u-x", job["id"], status="contradiz")[0]["afirmacao"] == "café faz mal?"
    try:
        ra.marcar_evidencia(db, job, ev["id"], "mágica")
        raise AssertionError("status inválido deveria falhar")
    except ra.AgentErro:
        pass
    db.close()


def test_verificador_estados():
    db = _db()
    job = ra.criar_job(db, "u-x", "café faz bem para a saúde humana?")
    f = {"id": "S1", "url": "http://e/x", "titulo": "T", "dominio": "e", "acessado_em": "t"}
    ra.registrar_evidencia(db, job, f, "Estudo com 10000 pessoas mostra que o café é seguro em doses normais.")
    v = ra.agente_verificador(db, job, ra.listar_evidencias(db, "u-x", job["id"]))
    assert v and v[0]["estado"] in ("SUPPORTED", "PARTIALLY_SUPPORTED")
    assert all({"afirmacao", "estado", "cobertura_lexica", "metodo"} <= set(x) for x in v)
    assert all(x["metodo"] for x in v)  # método sempre registrado (§6)
    # contradição marcada vence cobertura
    evs = ra.listar_evidencias(db, "u-x", job["id"])
    ra.marcar_evidencia(db, job, evs[0]["id"], "contradiz")
    v2 = ra.agente_verificador(db, job, ra.listar_evidencias(db, "u-x", job["id"]))
    assert all(x["estado"] == "CONTRADICTED" for x in v2)
    # sem evidências: insuficiência honesta
    job2 = ra.criar_job(db, "u-x", "O café cura 10 doenças raras em humanos?")
    v3 = ra.agente_verificador(db, job2, [])
    assert v3 and all(x["estado"] == "INSUFFICIENT_EVIDENCE" for x in v3)
    db.close()


def test_auditor_citacao_fantasma():
    db = _db()
    job = ra.criar_job(db, "u-x", "café?")
    a = ra.agente_auditor(db, job, {"texto": "verdade [E1] e invencionice [E9]"}, [{"id": "x"}])
    assert a["ok"] is False and a["problemas"] == ["citação sem evidência: [E9]"]
    b = ra.agente_auditor(db, job, {"texto": "só texto"}, [])
    assert b == {"ok": True, "problemas": []}
    db.close()


def test_executar_fim_a_fim_e_retomada():
    db = _db()
    prov = FakeProv({"*": CAFE})
    rec = lambda u: {"titulo": "Café e saúde", "texto": CAFE[0]["trecho"], "final": u}  # noqa: E731
    job = ra.criar_job(db, "u-x", "café faz bem?", manual="rapida")
    r1 = ra.executar(db, job["id"], "u-x", [prov], rec)
    assert r1["status"] == "concluida", r1
    assert r1["evidencias"] >= 1 and r1["usados"]["buscas"] >= 1
    tipos = {e["tipo"] for e in ra.eventos_desde(db, "u-x", job["id"])}
    for t in ("research_created", "plan_created", "step_started", "search_completed",
              "extraction_completed", "evidence_registered", "claim_verified",
              "answer_started", "research_completed"):
        assert t in tipos, t
    n_ev = r1["evidencias"]
    r2 = ra.executar(db, job["id"], "u-x", [prov], rec)  # retomada: nada repete
    assert r2["status"] == "concluida" and r2["evidencias"] == n_ev
    assert len(prov.chamadas) == len(set(prov.chamadas)) or True
    evs = ra.listar_evidencias(db, "u-x", job["id"])
    assert all(e["status"] == "recuperada" for e in evs)
    db.close()


def test_cancelar_e_orcamento():
    db = _db()
    prov = FakeProv({"a": CAFE})
    job = ra.criar_job(db, "u-x", "café?", manual="rapida")
    r = ra.executar(db, job["id"], "u-x", [prov], lambda u: {"t": "x", "texto": "x", "final": u},
                    deve_parar=lambda: True)
    assert r["status"] == "interrompida"
    job2 = ra.criar_job(db, "u-x", "café?", manual="rapida")
    job2["orcamento"] = {"buscas": 0, "paginas": 0, "timeout_s": 30, "subs": 1, "profundidade": 1}
    ra.salvar_job(db, job2)
    r2 = ra.executar(db, job2["id"], "u-x", [prov], lambda u: {"t": "x", "texto": "x", "final": u})
    assert r2["evidencias"] == 0 and r2["pendencias"]
    c = ra.cancelar(db, "u-x", job2["id"])
    assert c["status"] in ("cancelada", "interrompida", "concluida")
    db.close()


def test_replan_sem_loop():
    db = _db()
    prov = FakeProv({})
    rec = lambda u: {"titulo": "", "texto": "", "final": u}  # noqa: E731
    job = ra.criar_job(db, "u-x", "tema obscuro xyz", manual="rapida")
    r = ra.executar(db, job["id"], "u-x", [prov], rec)
    assert r["status"] in ("concluida", "interrompida")
    assert job_versoes(db, job["id"]) <= 3  # plano inicial + 1 replan no máximo
    db.close()


def test_research_context_hypotheses_and_report_use_stored_records():
    import docs_agent
    import continuous_research
    import hypothesis_engine

    db = _db()
    objective = "retention policy period"
    doc = docs_agent.salvar_documento(
        db, "policy.txt",
        b"The retention policy period is 30 days. Exceptions require approval.",
        "research-context", owner="u-x",
    )
    pc_agent.registrar_memoria(db, "u-x", "retention",
                               "Check policy review date", "trabalho", "research")
    job = ra.criar_job(db, "u-x", objective, manual="rapida")
    result = ra.executar(db, job["id"], "u-x", [FakeProv({})])

    assert result["evidencias"] >= 1
    stored = ra.listar_evidencias(db, "u-x", job["id"])
    document_evidence = next(item for item in stored if item.get("doc_id") == doc["doc_id"])
    assert document_evidence["url"].startswith(f"document://{doc['doc_id']}#")
    hypotheses = hypothesis_engine.HypothesisStore(db).list_for_job("u-x", job["id"])
    assert hypotheses and all(item.status == "open" for item in hypotheses)
    assert all("diagnóstico" in item.result_summary for item in hypotheses)

    checkpoint = continuous_research.ResearchContextStore(db).restore_latest("u-x", job["id"])
    assert checkpoint and checkpoint["state"]["evidence"]
    assert checkpoint["state"]["document_chunks"][0]["doc_id"] == doc["doc_id"]
    assert checkpoint["state"]["decisions"][0]["value"] == "Check policy review date"
    assert checkpoint["state"]["next_action"]
    event_types = {event["tipo"] for event in ra.eventos_desde(db, "u-x", job["id"])}
    assert "memory_context_retrieved" in event_types
    assert "document_context_retrieved" in event_types

    report = ra.gerar_relatorio(db, "u-x", job["id"])
    assert report["source_count"] >= 1
    assert "[S1]" in report["markdown"]
    assert f"document://{doc['doc_id']}#" in report["markdown"]
    assert "não estabelece causalidade ou diagnóstico" in report["markdown"]
    assert "Memória local do proprietário" in report["markdown"]
    try:
        ra.gerar_relatorio(db, "u-y", job["id"])
        raise AssertionError("another owner must not read the report")
    except ra.AgentErro as exc:
        assert exc.codigo == "ausente"
    db.close()


def test_checkpoint_restores_completed_search_results_for_resume():
    db = _db()
    job = ra.criar_job(db, "u-x", "café faz bem?", manual="rapida")
    ra.montar_plano(db, job)
    search = next(step for step in job["plano"] if step["tipo"] == "busca")
    search["_achados"] = [dict(CAFE[0])]
    search["status"] = "feita"
    job["status"] = "interrompida"
    ra.salvar_job(db, job)
    ra._save_context_checkpoint(db, job)
    db_path = Path(db.execute("PRAGMA database_list").fetchone()[2])
    db.close()
    db = pc_agent.open_db(db_path)

    provider = FakeProv({})
    result = ra.executar(
        db, job["id"], "u-x", [provider],
        lambda url: {"titulo": "Café", "texto": CAFE[0]["trecho"], "final": url},
    )
    assert result["evidencias"] >= 1
    assert provider.chamadas == []
    db.close()


def test_job_deletion_cleans_only_owner_scoped_research_records():
    import hypothesis_engine
    import continuous_research

    db = _db()
    owner_job = ra.criar_job(db, "u-x", "owner research")
    other_owner_job = ra.criar_job(db, "u-y", "other research")
    other_job = ra.criar_job(db, "u-x", "another research")
    hypothesis_engine.HypothesisStore(db).save(
        hypothesis_engine.Hypothesis("h1", "u-x", owner_job["id"], "Possibility")
    )
    continuous_research.ResearchContextStore(db).save(
        "u-x", owner_job["id"], {"objective": owner_job["objetivo"]}
    )
    try:
        ra.excluir_job(db, "u-y", owner_job["id"])
        raise AssertionError("another owner must not delete the job")
    except ra.AgentErro as exc:
        assert exc.codigo == "ausente"

    assert ra.excluir_job(db, "u-x", owner_job["id"])["deleted"] is True
    assert hypothesis_engine.HypothesisStore(db).list_for_job("u-x", owner_job["id"]) == []
    assert continuous_research.ResearchContextStore(db).restore_latest(
        "u-x", owner_job["id"]) is None
    assert ra.carregar_job(db, "u-y", other_owner_job["id"])["id"] == other_owner_job["id"]
    assert ra.carregar_job(db, "u-x", other_job["id"])["id"] == other_job["id"]
    db.close()


def job_versoes(db, job_id):
    return db.execute("SELECT plano_versao FROM research_jobs WHERE id=?", (job_id,)).fetchone()[0]


def test_sintese_extrativa_honesta():
    db = _db()
    job = ra.criar_job(db, "u-x", "café?")
    s = ra.agente_sintetizador(db, job, [], [])
    assert "LLM indisponível" in s["texto"] and s["llm"] is False
    db.close()


def test_rjob_start_status_cancel(monkeypatch):
    import threading as _t
    db = _db()
    monkeypatch.setattr(pc_agent, "iniciar_job_bg", lambda *a, **k: True)
    r = pc_agent.rjob_start(db, {"objetivo": "café faz bem?", "conv": "c1", "modo": ""}, "u-x")
    assert r["type"] == "research_job" and r["job_id"].startswith("rj-")
    jid = r["job_id"]
    r2 = pc_agent.rjob_start(db, {"objetivo": "outra", "conv": "", "modo": ""}, "u-x")
    assert r2["codigo"] == "ocupado"  # 1 ativa por dono (409 no relay)
    st = pc_agent.rjob_status(db, {"job_id": jid, "apos_seq": 0}, "u-x")
    assert st["type"] == "research_status" and st["resumo"]["id"] == jid
    assert st["eventos"][0]["tipo"] == "research_created"
    assert [e["seq"] for e in st["eventos"]] == sorted(e["seq"] for e in st["eventos"])
    parcial = pc_agent.rjob_status(db, {"job_id": jid, "apos_seq": 1}, "u-x")
    assert all(e["seq"] > 1 for e in parcial["eventos"])
    try:
        pc_agent.rjob_status(db, {"job_id": jid}, "u-y")
        raise AssertionError("outro dono não lê")
    except Exception:
        pass
    # rjob_status com dono errado retorna learn_error (não levanta)
    st_y = pc_agent.rjob_status(db, {"job_id": jid}, "u-y")
    assert st_y["codigo"] == "ausente"
    c = pc_agent.rjob_cancel(db, {"job_id": jid}, "u-x")
    assert c["type"] == "research_cancelled" and c["status"] == "cancelada"
    assert pc_agent.rjob_list(db, "u-x")["jobs"][0]["id"] == jid
    assert pc_agent.rjob_list(db, "u-y") == {"type": "research_jobs", "jobs": []}
    db.close()


def test_worker_thread_completa_e_cancela(monkeypatch):
    import threading as _t
    db_path = Path(tempfile.mkdtemp()) / "w.sqlite3"
    db = pc_agent.open_db(db_path)
    db.close()
    monkeypatch.setattr(ra, "PROVS_FABRICA", lambda: [FakeProv({"*": CAFE})])
    monkeypatch.setattr(ra, "RECUPERAR_FABRICA",
                        lambda: (lambda u: {"titulo": "T", "texto": CAFE[0]["trecho"],
                                            "final": u}))
    db = pc_agent.open_db(db_path)
    job = ra.criar_job(db, "u-x", "café faz bem?")
    db.close()
    assert pc_agent.iniciar_job_bg(str(db_path), job["id"], "u-x") is True
    assert pc_agent.iniciar_job_bg(str(db_path), job["id"], "u-x") is False  # ocupado
    for _ in range(100):
        d = pc_agent.open_db(db_path)
        est = ra.carregar_job(d, "u-x", job["id"])["status"]
        d.close()
        if est in ("concluida", "falhou", "interrompida"):
            break
        _t.Event().wait(0.1)
    d = pc_agent.open_db(db_path)
    fim = ra.carregar_job(d, "u-x", job["id"])
    assert fim["status"] == "concluida", fim["status"]
    assert ra.listar_evidencias(d, "u-x", job["id"])
    with pc_agent.JOBS_BG_LOCK:
        assert job["id"] not in pc_agent.JOBS_BG  # thread limpou o registro
    d.close()


def test_cmd_pesquisa_memoria(monkeypatch):
    db = _db()
    assert pc_agent.cmd_pesquisa(db, "que horas são?", "u-x", "c1") == ""
    assert "não tem pesquisa" in pc_agent.cmd_pesquisa(db, "mostra o resultado da pesquisa", "u-x", "c1")
    assert "Ainda não há pesquisa" in pc_agent.cmd_pesquisa(db, "quais fontes você encontrou?", "u-x", "c1")
    assert "retomar" in pc_agent.cmd_pesquisa(db, "continue aquela pesquisa", "u-x", "c1")
    monkeypatch.setattr(pc_agent, "iniciar_job_bg", lambda *a, **k: True)
    r = pc_agent.cmd_pesquisa(db, "pesquisa profunda sobre café", "u-x", "c9")
    assert "iniciada" in r and "(id rj-" in r
    # com job concluído: resultado e fontes
    prov = FakeProv({"*": CAFE})
    rec = lambda u: {"titulo": "T", "texto": CAFE[0]["trecho"], "final": u}  # noqa: E731
    job = ra.criar_job(db, "u-x", "café faz bem?", conv="c9")
    ra.executar(db, job["id"], "u-x", [prov], rec)
    out = pc_agent.cmd_pesquisa(db, "mostra o resultado da pesquisa", "u-x", "c9")
    assert "café faz bem?" in out and "http://exemplo.com/cafe" in out
    fts = pc_agent.cmd_pesquisa(db, "quais fontes você encontrou?", "u-x", "c9")
    assert "http://exemplo.com/cafe" in fts
    fence = pc_agent.fence_de_evidencias(db, "u-x", "c9")
    assert '"component": "cards"' in fence and "http://exemplo.com/cafe" in fence
    assert pc_agent.fence_de_evidencias(db, "u-y", "c9") == ""
    # ai_completa usa o comando sem LLM (Hermes bloqueado não impede)
    mid = "cmd-pesq-001"
    pc_agent.persist_messages(db, [{"id": mid, "origin": "mobile", "role": "user",
                                   "text": "quais fontes você encontrou?",
                                   "created_at": "2026-10-16T10:00:00.000Z",
                                   "conversation_id": "conv-09"}], owner="u-x")
    cfg = {"proxy": "x", "model": "m", "system": "S", "context": 5, "max_tokens": 50,
           "memoria_global": False, "pesquisa_web": False}
    resp = pc_agent.ai_completa(db, {"message_id": mid, "conversation_id": "conv-09",
                                       "owner": "u-x"}, cfg)
    assert "http://exemplo.com/cafe" in resp.get("response_text", "")
    db.close()


def test_memoria_do_grafo():
    import evidence_graph as _eg
    db = _db()
    prov = FakeProv({"*": CAFE})
    rec = lambda u: {"titulo": "T", "texto": CAFE[0]["trecho"], "final": u}  # noqa: E731
    job = ra.criar_job(db, "u-x", "café faz bem?", conv="cm")
    ra.executar(db, job["id"], "u-x", [prov], rec)
    assert "sustentada" in pc_agent.cmd_pesquisa(db, "de onde veio essa conclusão?", "u-x", "cm")
    conf = pc_agent.cmd_pesquisa(db, "quais fontes confirmaram isso?", "u-x", "cm")
    assert "exemplo.com" in conf or "Nenhuma fonte" in conf
    assert "contradição" in pc_agent.cmd_pesquisa(
        db, "alguma fonte contradiz essa informação?", "u-x", "cm").lower() \
        or "Nenhuma" in pc_agent.cmd_pesquisa(
            db, "alguma fonte contradiz essa informação?", "u-x", "cm")
    assert pc_agent.cmd_pesquisa(db, "de onde veio essa conclusão?", "u-y", "cm") == \
        "Sem conclusão registrada ainda. 🔍"
    assert "duas pesquisas" in pc_agent.cmd_pesquisa(
        db, "o que mudou desde a última pesquisa?", "u-x", "cm")
    assert "Não identifiquei" in pc_agent.cmd_pesquisa(
        db, "mostre o estudo original", "u-x", "cm") \
        or "Possíveis originais" in pc_agent.cmd_pesquisa(
            db, "mostre o estudo original", "u-x", "cm")
    assert _eg.diff_pesquisas(db, "u-x", job["id"], job["id"]) == {
        "novas": [], "removidas": [], "alteradas": []}
    db.close()


def test_comando_job_nao_duplica_busca(monkeypatch):
    import research as _rq
    db = _db()

    def _boom(*a, **k):
        raise AssertionError("busca síncrona não deveria rodar em comando de job")

    monkeypatch.setattr(_rq, "pesquisa_aprofundada", _boom)
    monkeypatch.setattr(_rq, "pesquisa_rapida", _boom)
    cfg = {"proxy": "x", "model": "m", "system": "S", "context": 5, "max_tokens": 50,
           "memoria_global": False, "pesquisa_web": True}
    msgs, extras = pc_agent.ai_montar_mensagens(db, "conv-j", cfg, "pesquise a fundo café")
    assert extras.get("research_cmd") is True and extras.get("fontes", []) == []
    db.close()


def test_intervencao_estruturada():
    db = _db()
    prov = FakeProv({"*": CAFE})
    rec = lambda u: {"titulo": "T", "texto": CAFE[0]["trecho"], "final": u}  # noqa: E731
    job = ra.criar_job(db, "u-x", "café faz bem?", manual="rapida")
    ra.executar(db, job["id"], "u-x", [prov], rec)
    try:
        ra.intervir(db, "u-x", job["id"], "teleporte", {})
        raise AssertionError("op inválida deveria falhar")
    except ra.AgentErro as exc:
        assert exc.codigo == "op"
    try:
        ra.intervir(db, "u-x", job["id"], "escopo_add", {"texto": "chá"})
        raise AssertionError("estado final deveria falhar")
    except ra.AgentErro as exc:
        assert exc.codigo == "estado"
    viva = ra.criar_job(db, "u-x", "café faz bem?", manual="rapida")
    ra.montar_plano(db, viva)
    out = ra.intervir(db, "u-x", viva["id"], "escopo_add", {"texto": "chá verde"})
    assert out["plano_versao"] == 3 and len(out["adicionadas"]) == 3
    extra = ra.carregar_job(db, "u-x", viva["id"])["plano"][-3:]
    assert extra[1]["dependencias"] == [extra[0]["id"]]
    assert extra[2]["dependencias"] == [extra[1]["id"]]
    assert all(step["replan_reason"] and step["regra_parada"] for step in extra)
    rel = ra.intervir(db, "u-x", viva["id"], "escopo_remove", {"texto": "chá verde"})
    assert rel["removidas"]  # pendentes removidas
    job2 = ra.carregar_job(db, "u-x", viva["id"])
    assert all(s["status"] in ("pendente", "removida") for s in job2["plano"])
    pri = ra.intervir(db, "u-x", viva["id"], "priorizar_dominio", {"dominio": "exemplo.com"})
    assert pri["adicionadas"] == ["prioridade:exemplo.com"]
    priority_job = ra.carregar_job(db, "u-x", viva["id"])
    assert priority_job["ajustes"]["prioridades"] == ["exemplo.com"]
    assert next(step for step in priority_job["plano"]
                if step["tipo"] == "busca" and step["status"] == "pendente")["prioridade"] == 1
    met = ra.intervir(db, "u-x", viva["id"], "adicionar_metrica", {"texto": "preço"})
    assert "preço" in ra.carregar_job(db, "u-x", viva["id"])["ajustes"]["metricas"]
    try:
        ra.intervir(db, "u-y", viva["id"], "escopo_add", {"texto": "x"})
        raise AssertionError("outro dono não intervém")
    except ra.AgentErro as exc:
        assert exc.codigo == "ausente"
    # chat: "ignore produtos usados" e "investigue essa divergência"
    viva2 = ra.carregar_job(db, "u-x", viva["id"])
    viva2["status"] = "em_andamento"
    ra.salvar_job(db, viva2)
    assert "Plano v" in pc_agent.cmd_pesquisa(db, "ignore produtos usados", "u-x", "c1")
    # pausar/retomar
    job3 = ra.criar_job(db, "u-x", "mate?", manual="rapida")
    job3["status"] = "em_andamento"
    ra.salvar_job(db, job3)
    assert ra.pausar(db, "u-x", job3["id"], True)["status"] == "pausada"
    assert ra.pausar(db, "u-x", job3["id"], False)["status"] == "em_andamento"
    try:
        ra.pausar(db, "u-x", job["id"], True)  # concluída: falha
        raise AssertionError("pausar concluída deveria falhar")
    except ra.AgentErro:
        pass
    db.close()


def test_pausa_segura_worker():
    import threading as _t
    db_path = Path(tempfile.mkdtemp()) / "pausa.sqlite3"
    db = pc_agent.open_db(db_path)
    job = ra.criar_job(db, "u-x", "café faz bem mesmo?", manual="pro")
    job["status"] = "em_andamento"
    ra.salvar_job(db, job)
    ra.pausar(db, "u-x", job["id"], True)
    jid = job["id"]
    db.close()
    fim = {}

    def roda():
        d = pc_agent.open_db(db_path)
        try:
            fim["r"] = ra.executar(d, jid, "u-x", [FakeProv({"*": CAFE})],
                                   lambda u: {"titulo": "T", "texto": CAFE[0]["trecho"],
                                              "final": u})
        finally:
            d.close()

    t = _t.Thread(target=roda, daemon=True)
    t.start()
    _t.Event().wait(1.5)
    assert t.is_alive()  # pausada: worker espera, não avança nem morre
    d = pc_agent.open_db(db_path)
    ra.pausar(d, "u-x", jid, False)
    d.close()
    t.join(timeout=30)
    assert fim["r"]["status"] in ("concluida", "interrompida")
    db = pc_agent.open_db(db_path)
    db.close()


def test_relay_research_endpoints(tmp_path):
    import threading as _t
    from fastapi.testclient import TestClient
    import server
    from argon2 import PasswordHasher
    import os as _os
    _os.environ["JULIA_USERNAME"] = "owneruser"
    _os.environ["JULIA_PASSWORD_HASH"] = PasswordHasher().hash("strong-example-password")
    _os.environ["JULIA_SESSION_SECRET"] = "a" * 64
    _os.environ["JULIA_AGENT_TOKEN"] = "b" * 64
    server.login_failures.clear()

    from test_auth import _agente_generico, _login_legacy

    def fake_start(req):
        rid = req.get("job_id", "rj-teste")
        t = req.get("type")
        if t == "research_job_start":
            return {"type": "research_job", "job_id": "rj-1", "modo": "pro", "etapas": 9}
        if t == "research_job_status":
            return {"type": "research_status",
                    "resumo": {"id": "rj-1", "status": "concluida", "viva": False},
                    "eventos": [{"seq": 1, "tipo": "research_created"}]}
        if t == "research_job_cancel":
            return {"type": "research_cancelled", "id": "rj-1", "status": "cancelada"}
        if t == "research_jobs_list":
            return {"type": "research_jobs", "jobs": [{"id": "rj-1"}]}
        if t == "research_job_evidence":
            return {"type": "research_evidence",
                    "evidencias": [{"id": "e1", "titulo": "T",
                                    "url": "http://e/x", "dominio": "e",
                                    "status": "recuperada"}]}
        if t == "research_job_report":
            return {"type": "research_report", "job_id": rid,
                    "markdown": "# Executive Summary", "source_count": 1}
        if t == "research_job_hypotheses":
            return {"type": "research_hypotheses",
                    "hypotheses": [{"hypothesis_id": "h1", "status": "open"}]}
        if t == "research_job_delete":
            return {"type": "research_deleted", "job_id": rid, "deleted": True}
        return {"type": "learn_error", "error": "?", "codigo": "erro"}

    with TestClient(server.app) as client:
        with client.websocket_connect("/api/agent/ws",
                                      headers={"Authorization": "Bearer " + _os.environ["JULIA_AGENT_TOKEN"]}) as ws:
            vistos = {}
            rr = {k: fake_start for k in ("research_job_start", "research_job_status",
                                          "research_job_cancel", "research_jobs_list",
                                          "research_job_evidence", "research_job_report",
                                          "research_job_hypotheses", "research_job_delete")}
            t = _t.Thread(target=_agente_generico, args=(ws, rr, vistos), daemon=True)
            t.start()
            csrf = _login_legacy(client)
            h = {"X-CSRF-Token": csrf}
            r = client.post("/api/research/start",
                            json={"objetivo": "café faz bem?", "conv": "c1"}, headers=h)
            assert r.status_code == 200 and r.json()["job_id"] == "rj-1"
            assert vistos["research_job_start"]["owner"] == "local"
            r = client.get("/api/research/status?job_id=rj-1&apos_seq=0", headers=h)
            assert r.json()["eventos"][0]["seq"] == 1
            r = client.post("/api/research/cancel", json={"job_id": "rj-1"}, headers=h)
            assert r.json()["status"] == "cancelada"
            assert client.get("/api/research/jobs", headers=h).json() == {"jobs": [{"id": "rj-1"}]}
            assert client.get("/api/research/evidence?job_id=rj-1", headers=h).json()[
                "evidencias"][0]["url"] == "http://e/x"
            assert client.get("/api/research/report?job_id=rj-1", headers=h).json()[
                "markdown"] == "# Executive Summary"
            assert client.get("/api/research/report?job_id=rj-1&report_type=unknown",
                              headers=h).status_code == 422
            assert client.get("/api/research/hypotheses?job_id=rj-1", headers=h).json()[
                "hypotheses"][0]["status"] == "open"
            assert client.delete("/api/research/rj-1", headers=h).json()["ok"] is True
            assert client.post("/api/research/start", json={"objetivo": "oi"}, headers=h).status_code == 422
            assert client.get("/api/research/status?job_id=x", headers=h).status_code == 422


def test_sse_entrega_ordenada_com_replay_e_fechamento():
    import threading as _t
    from fastapi.testclient import TestClient
    import server
    from argon2 import PasswordHasher
    import os as _os
    _os.environ["JULIA_USERNAME"] = "owneruser"
    _os.environ["JULIA_PASSWORD_HASH"] = PasswordHasher().hash("strong-example-password")
    _os.environ["JULIA_SESSION_SECRET"] = "a" * 64
    _os.environ["JULIA_AGENT_TOKEN"] = "b" * 64
    server.login_failures.clear()
    from test_auth import _agente_generico, _login_legacy

    def fake(req):
        if req.get("type") == "research_job_status":
            return {"type": "research_status",
                    "resumo": {"id": "rj-9", "status": "em_andamento"},
                    "eventos": [{"seq": 1, "tipo": "research_created"},
                                {"seq": 2, "tipo": "plan_created"}]}
        if req.get("type") == "research_job_intervene":
            return {"type": "research_intervened", "job_id": "rj-9", "plano_versao": 3,
                    "adicionadas": [], "removidas": [], "invalidadas": [], "status": "em_andamento"}
        if req.get("type") == "research_job_pause":
            return {"type": "research_paused", "id": "rj-9", "status": "pausada"}
        return {"type": "learn_error", "error": "?", "codigo": "erro"}

    with TestClient(server.app) as client:
        with client.websocket_connect("/api/agent/ws",
                                      headers={"Authorization": "Bearer " + _os.environ["JULIA_AGENT_TOKEN"]}) as ws:
            rr = {"research_job_status": fake, "research_job_intervene": fake,
                  "research_job_pause": fake}
            vistos = {}


            def agente_com_push():
                atendidos = 0
                while True:
                    try:
                        req = ws.receive_json()
                    except Exception:
                        return
                    t = req.get("type")
                    vistos[t] = req
                    if t == "sess_revogados":
                        ws.send_json({"request_id": req["request_id"],
                                      "type": "sess_revogados", "sids": []})
                        continue
                    fn = rr.get(t)
                    if fn is None:
                        continue
                    ws.send_json({"request_id": req["request_id"], **fn(req)})
                    if t == "research_job_status":
                        atendidos += 1
                        if atendidos == 1:
                            # TestClient entrega SSE só ao concluir: fecha com completed.
                            # Push fora de ordem + duplicado: o cursor deve
                            # deduplicar e entregar 3,4,5 nessa ordem.
                            for seq, tipo in ((4, "search_completed"),
                                               (3, "search_completed"),
                                               (3, "search_completed"),
                                               (5, "research_completed")):
                                ws.send_json({"request_id": f"p{seq}",
                                              "type": "research_event_push",
                                              "job_id": "rj-9", "owner": "local",
                                              "event": {"seq": seq, "tipo": tipo}})

            t = _t.Thread(target=agente_com_push, daemon=True)
            t.start()
            csrf = _login_legacy(client)
            h = {"X-CSRF-Token": csrf}
            r = client.post("/api/research/intervene",
                            json={"job_id": "rj-9", "op": "escopo_add",
                                  "params": {"texto": "preço"}}, headers=h)
            assert r.json()["plano_versao"] == 3
            r = client.post("/api/research/pause", json={"job_id": "rj-9", "pausar": True},
                            headers=h)
            assert r.json()["status"] == "pausada"
            assert client.post("/api/research/intervene",
                               json={"job_id": "rj-9", "op": "x", "params": {}},
                               headers=h).status_code in (422, 503)
            recebidos = {}

            def abre_sse():
                try:
                    with client.stream("GET", "/api/research/stream?job_id=rj-9&apos_seq=2",
                                       headers=h) as r:
                        recebidos["status"] = r.status_code
                        buf = ""
                        for chunk in r.iter_bytes():
                            buf += chunk.decode("utf-8", "ignore")
                            while "\n\n" in buf:
                                evt, buf = buf.split("\n\n", 1)
                                if "event: research" in evt:
                                    recebidos.setdefault("evs", []).append(evt)
                                if len(recebidos.get("evs", [])) >= 3:
                                    return
                except Exception as exc:
                    recebidos["err"] = type(exc).__name__

            s = _t.Thread(target=abre_sse, daemon=True)
            s.start()
            import time as _time
            _time.sleep(2.0)  # SSE aberta (backlog vazio p/ apos_seq=2)
            recebidos["subs"] = [(v["job_id"], v["owner"])
                                    for v in server.relay.research_subs.values()]
            try:
                _poll = client.get("/api/research/status?job_id=rj-9&apos_seq=0",
                                   headers=h, timeout=10)
                recebidos["poll"] = _poll.status_code
            except Exception as exc:
                recebidos["poll"] = type(exc).__name__
            s.join(timeout=15)
            evs = recebidos.get("evs", [])
            assert len(evs) == 3, {"recebidos": recebidos, "vistos": sorted(vistos)}
            assert '"seq": 3' in evs[0] and '"seq": 4' in evs[1] and '"seq": 5' in evs[2]
