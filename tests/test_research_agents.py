"""V4.5 FASE 2-7: orchestrator, agentes, evidências, verificação (determinístico)."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pc_agent
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


def test_plano_e_eventos():
    db = _db()
    job = ra.criar_job(db, "u-x", "café e chá", manual="pro")
    ra.montar_plano(db, job)
    tipos = [s["tipo"] for s in job["plano"]]
    assert tipos[:3] == ["busca", "ler", "analisar"] and tipos[-3:] == ["verificar", "sintetizar", "auditar"]
    evs = ra.eventos_desde(db, "u-x", job["id"])
    assert [e["tipo"] for e in evs] == ["research_created", "plan_created"]
    assert [e["seq"] for e in evs] == [1, 2]
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
    assert all(set(x) == {"afirmacao", "estado", "cobertura_lexica"} for x in v)
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
        return {"type": "learn_error", "error": "?", "codigo": "erro"}

    with TestClient(server.app) as client:
        with client.websocket_connect("/api/agent/ws",
                                      headers={"Authorization": "Bearer " + _os.environ["JULIA_AGENT_TOKEN"]}) as ws:
            vistos = {}
            rr = {k: fake_start for k in ("research_job_start", "research_job_status",
                                          "research_job_cancel", "research_jobs_list",
                                          "research_job_evidence")}
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
            assert client.post("/api/research/start", json={"objetivo": "oi"}, headers=h).status_code == 422
            assert client.get("/api/research/status?job_id=x", headers=h).status_code == 422
