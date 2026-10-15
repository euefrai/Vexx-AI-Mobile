"""V4.2 FASE 3/4: endpoints /api/learn/* — contrato relay, correção servidor, isolamento."""
import os
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import learning
import pc_agent
import server
from argon2 import PasswordHasher
from fastapi.testclient import TestClient


def setup_module():
    os.environ["JULIA_USERNAME"] = "owneruser"
    os.environ["JULIA_PASSWORD_HASH"] = PasswordHasher().hash("strong-example-password")
    os.environ["JULIA_SESSION_SECRET"] = "a" * 64
    os.environ["JULIA_AGENT_TOKEN"] = "b" * 64
    server.login_failures.clear()
    server.revogados["sids"] = set()
    server.revogados["ts"] = 0.0
    server.revogados["suportado"] = True
    server.revogados["falhas"] = 0


QUESTOES = [
    {"id": "q1", "enunciado": "Quanto é 2+2?", "tipo": "multipla",
     "opcoes": ["3", "4", "5"], "gabarito": 1, "explicacao": "Soma básica.",
     "dificuldade": "facil", "assunto": "mat"},
    {"id": "q2", "enunciado": "Python é linguagem de programação?", "tipo": "vf",
     "opcoes": ["Verdadeiro", "Falso"], "gabarito": 0, "explicacao": "Sim.",
     "dificuldade": "facil", "assunto": "info"},
]


def _agente_learn(ws, db_path, vistos, usuarios):
    """Agente fake: learn_* delega às funções reais (cadeia relay→agente→SQLite)."""
    db = pc_agent.open_db(Path(db_path))
    learning.criar_assessment(db, "u-aaa", "Prova de Mat", "mat", QUESTOES,
                             origem="ia", assessment_id="av-mat")
    while True:
        try:
            req = ws.receive_json()
        except Exception:
            db.close()
            return
        tipo = req.get("type")
        vistos[tipo] = req
        rid = req.get("request_id")
        if tipo == "sess_revogados":
            ws.send_json({"request_id": rid, "type": "sess_revogados", "sids": []})
        elif tipo == "auth_login":
            u = usuarios.get(req.get("username"), "u-aaa")
            ws.send_json({"request_id": rid, "type": "auth_ok", "uid": u,
                          "username": req.get("username"), "display": "Nome",
                          "role": "user", "sid": "sid-" + u})
        elif tipo == "learn_get":
            try:
                ws.send_json({"request_id": rid, "type": "learn_assessment",
                              **learning.obter_assessment(db, req.get("owner"), req.get("id", ""))})
            except learning.LearnErro as exc:
                ws.send_json({"request_id": rid, "type": "learn_error",
                              "error": str(exc), "codigo": exc.codigo})
        elif tipo == "learn_attempt":
            try:
                ws.send_json({"request_id": rid, "type": "learn_attempt",
                              **learning.iniciar_tentativa(db, req.get("owner"),
                                                          req.get("assessment_id", ""), "")})
            except learning.LearnErro as exc:
                ws.send_json({"request_id": rid, "type": "learn_error",
                              "error": str(exc), "codigo": exc.codigo})
        elif tipo == "learn_answer":
            try:
                ws.send_json({"request_id": rid, "type": "learn_answer",
                              **learning.responder(db, req.get("owner"), req.get("attempt_id", ""),
                                                  req.get("question_id", ""), req.get("resposta", ""))})
            except learning.LearnErro as exc:
                ws.send_json({"request_id": rid, "type": "learn_error",
                              "error": str(exc), "codigo": exc.codigo})
        elif tipo == "learn_finish":
            try:
                ws.send_json({"request_id": rid, "type": "learn_result",
                              **learning.finalizar_tentativa(db, req.get("owner"),
                                                           req.get("attempt_id", ""))})
            except learning.LearnErro as exc:
                ws.send_json({"request_id": rid, "type": "learn_error",
                              "error": str(exc), "codigo": exc.codigo})
        elif tipo == "learn_avulso":
            ws.send_json({"request_id": rid, "type": "learn_avulso_ok",
                          **learning.historico_avulso(db, req.get("owner"), req.get("titulo", ""),
                                                    req.get("assunto", ""), int(req.get("certas", 0)),
                                                    int(req.get("total", 0)))})
        elif tipo == "learn_stats":
            ws.send_json({"request_id": rid, "type": "learn_stats",
                          "resumo": learning.resumo_progresso(db, req.get("owner")),
                          "por_assunto": learning.desempenho_por_assunto(db, req.get("owner"))})
        elif tipo in ("learn_plan_create", "learn_plan_get", "learn_plan_item",
                      "learn_plan_update", "learn_plans", "learn_cards_create",
                      "learn_cards_due", "learn_cards_review", "learn_recommend",
                      "learn_flag", "learn_mistakes", "learn_lesson_create",
                      "learn_lesson_get", "learn_lessons", "learn_lesson_section",
                      "learn_history"):
            try:
                ws.send_json({"request_id": rid, **_learn_op(db, req)})
            except learning.LearnErro as exc:
                ws.send_json({"request_id": rid, "type": "learn_error",
                              "error": str(exc), "codigo": exc.codigo})


def _learn_op(db, req):
    """Operações plano/cards/adaptativo (espelha o dispatch do pc_agent)."""
    dono, tipo = req.get("owner"), req.get("type")
    if tipo == "learn_plan_create":
        return {"type": "learn_plan", **learning.criar_plano(
            db, dono, req.get("titulo", ""), req.get("objetivo", ""), req.get("assunto", ""),
            req.get("prazo_iso", ""), req.get("min_dia", 30), req.get("itens", []), req.get("id", ""))}
    if tipo == "learn_plan_get":
        return {"type": "learn_plan_full", **learning.obter_plano(db, dono, req.get("id", ""))}
    if tipo == "learn_plan_item":
        return {"type": "learn_plan_progress",
                "progresso": learning.concluir_item(db, dono, req.get("plan_id", ""),
                                                  int(req.get("item_id", 0)),
                                                  str(req.get("feito", "1")) == "1")}
    if tipo == "learn_plan_update":
        return {"type": "learn_plan_full",
                **learning.atualizar_plano(db, dono, req.get("plan_id", ""), req.get("mudancas", {}))}
    if tipo == "learn_plans":
        return {"type": "learn_plans", "planos": learning.listar_planos(db, dono)}
    if tipo == "learn_cards_create":
        return {"type": "learn_cards", **learning.criar_flashcards(db, dono, req.get("cards", []))}
    if tipo == "learn_cards_due":
        return {"type": "learn_cards_due",
                "cards": learning.revisoes_pendentes(db, dono, limite=int(req.get("limite", 50)))}
    if tipo == "learn_cards_review":
        return {"type": "learn_cards_review",
                **learning.revisar_flashcard(db, dono, req.get("flashcard_id", ""),
                                            str(req.get("acertou", "1")) == "1")}
    if tipo == "learn_recommend":
        return {"type": "learn_recommend", **learning.recomendar(db, dono)}
    if tipo == "learn_flag":
        return {"type": "learn_flag_ok",
                **learning.sinalizar_questao(db, dono, req.get("question_id", ""), req.get("motivo", ""))}
    if tipo == "learn_mistakes":
        return {"type": "learn_mistakes",
                "erradas": learning.questoes_erradas(db, dono, int(req.get("limite", 20)))}
    if tipo == "learn_lesson_create":
        return {"type": "learn_lesson",
                **learning.criar_aula(db, dono, req.get("aula", {}), req.get("origem", "ia"),
                                      req.get("id", ""))}
    if tipo == "learn_lesson_get":
        return {"type": "learn_lesson_full", **learning.obter_aula(db, dono, req.get("id", ""))}
    if tipo == "learn_lessons":
        return {"type": "learn_lessons", "aulas": learning.listar_aulas(db, dono)}
    if tipo == "learn_lesson_section":
        return {"type": "learn_lesson_progress",
                **learning.concluir_secao(db, dono, req.get("lesson_id", ""),
                                          int(req.get("ordem", 0)))}
    if tipo == "learn_history":
        return {"type": "learn_history",
                "tentativas": learning.historico_tentativas(db, dono, int(req.get("limite", 50)))}
    raise learning.LearnErro("operação desconhecida", "tipo")


def _login_comum(client, username="ana"):
    r = client.post("/api/login", json={"username": username, "password": "senha-forte-1"})
    assert r.status_code == 200, r.text
    return r.json()["csrf"]


def _sessao(tmp_path, usuarios=None):
    client = TestClient(server.app)
    ws_ctx = client.websocket_connect("/api/agent/ws",
                                      headers={"Authorization": "Bearer " + os.environ["JULIA_AGENT_TOKEN"]})
    return client, ws_ctx, {}


def test_fluxo_prova_completo(tmp_path):
    with TestClient(server.app) as client:
        with client.websocket_connect("/api/agent/ws",
                                      headers={"Authorization": "Bearer " + os.environ["JULIA_AGENT_TOKEN"]}) as ws:
            vistos = {}
            t = threading.Thread(target=_agente_learn,
                                 args=(ws, tmp_path / "learnapi.sqlite3", vistos, {"ana": "u-aaa"}),
                                 daemon=True)
            t.start()
            csrf = _login_comum(client)
            h = {"X-CSRF-Token": csrf}
            r = client.get("/api/learn/assessments/av-mat", headers=h)
            assert r.status_code == 200, r.text
            prova = r.json()
            assert [q["id"] for q in prova["questions"]] == ["q1", "q2"]
            assert all("gabarito" not in q for q in prova["questions"])  # sem vazar gabarito
            assert vistos["learn_get"]["owner"] == "u-aaa"
            r = client.post("/api/learn/attempts", json={"assessment_id": "av-mat"}, headers=h)
            assert r.status_code == 200, r.text
            att = r.json()["id"]
            r = client.post("/api/learn/answer",
                            json={"attempt_id": att, "question_id": "q1", "resposta": "1"}, headers=h)
            assert r.json() == {"correta": True}
            r = client.post("/api/learn/answer",
                            json={"attempt_id": att, "question_id": "q2", "resposta": "1"}, headers=h)
            assert r.json() == {"correta": False}
            r = client.post("/api/learn/finish", json={"attempt_id": att}, headers=h)
            fim = r.json()
            assert fim["certas"] == 1 and fim["total"] == 2 and fim["nota"] == 0.5
            assert len(fim["erradas"]) == 1 and fim["erradas"][0]["question_id"] == "q2"
            r = client.get("/api/learn/stats", headers=h)
            est = r.json()
            assert est["resumo"]["concluidas"] == 1 and est["resumo"]["acertos"] == 1
            perf = {p["assunto"]: p for p in est["por_assunto"]}
            assert perf["mat"]["taxa"] == 1.0 and perf["info"]["taxa"] == 0.0


def test_isolamento_entre_usuarios(tmp_path):
    with TestClient(server.app) as client:
        with client.websocket_connect("/api/agent/ws",
                                      headers={"Authorization": "Bearer " + os.environ["JULIA_AGENT_TOKEN"]}) as ws:
            vistos = {}
            t = threading.Thread(target=_agente_learn,
                                 args=(ws, tmp_path / "learniso.sqlite3", vistos,
                                       {"ana": "u-aaa", "beto": "u-bbb"}), daemon=True)
            t.start()
            csrf_b = _login_comum(client, "beto")
            h = {"X-CSRF-Token": csrf_b}
            assert vistos["auth_login"]["username"] == "beto"
            r = client.get("/api/learn/assessments/av-mat", headers=h)
            assert r.status_code == 404  # prova é de outro dono
            r = client.get("/api/learn/stats", headers=h)
            assert r.json() == {"resumo": {"avaliacoes": 0, "concluidas": 0, "acertos": 0,
                                           "respostas": 0, "itens_plano": 0, "itens_feitos": 0,
                                           "revisoes_pendentes": 0}, "por_assunto": []}


def test_validacao_e_auth(tmp_path):
    with TestClient(server.app) as client:
        assert client.get("/api/learn/stats").status_code == 401
        assert client.get("/api/learn/assessments/av-mat").status_code == 401
        with client.websocket_connect("/api/agent/ws",
                                      headers={"Authorization": "Bearer " + os.environ["JULIA_AGENT_TOKEN"]}) as ws:
            vistos = {}
            t = threading.Thread(target=_agente_learn,
                                 args=(ws, tmp_path / "learnval.sqlite3", vistos, {"ana": "u-aaa"}),
                                 daemon=True)
            t.start()
            csrf = _login_comum(client)
            h = {"X-CSRF-Token": csrf}
            assert client.post("/api/learn/attempts", json={"assessment_id": "??"},
                               headers=h).status_code == 422
            assert client.post("/api/learn/answer",
                               json={"attempt_id": "x", "question_id": "y"},
                               headers=h).status_code == 422
            r = client.get("/api/learn/assessments/nope", headers=h)
            assert r.status_code == 404
            r = client.post("/api/learn/avulso",
                            json={"titulo": "Quiz", "assunto": "mat", "certas": 3, "total": 4},
                            headers=h)
            assert r.json()["ok"] is True
            assert vistos["learn_avulso"]["owner"] == "u-aaa"
            assert client.get("/api/learn/stats", headers=h).json()["resumo"]["concluidas"] == 1


def test_conta_bloqueada_vira_403():
    with TestClient(server.app) as client:
        with client.websocket_connect("/api/agent/ws",
                                      headers={"Authorization": "Bearer " + os.environ["JULIA_AGENT_TOKEN"]}) as ws:
            from test_auth import _agente_generico, _login_legacy
            respostas = {
                "learn_stats": lambda r: {"type": "learn_error",
                                          "error": "Conta indisponível.", "codigo": "bloqueada"},
            }
            vistos = {}
            t = threading.Thread(target=_agente_generico, args=(ws, respostas, vistos), daemon=True)
            t.start()
            csrf = _login_legacy(client)
            r = client.get("/api/learn/stats", headers={"X-CSRF-Token": csrf})
            assert r.status_code == 403


def test_planos_api(tmp_path):
    with TestClient(server.app) as client:
        with client.websocket_connect("/api/agent/ws",
                                      headers={"Authorization": "Bearer " + os.environ["JULIA_AGENT_TOKEN"]}) as ws:
            vistos = {}
            t = threading.Thread(target=_agente_learn,
                                 args=(ws, tmp_path / "learnplanapi.sqlite3", vistos, {"ana": "u-aaa"}),
                                 daemon=True)
            t.start()
            csrf = _login_comum(client)
            h = {"X-CSRF-Token": csrf}
            corpo = {"titulo": "Mat até nov", "objetivo": "Passar", "assunto": "mat",
                     "prazo_iso": "2026-11-30", "min_dia": 30,
                     "itens": [{"titulo": "Frações"}, {"titulo": "Quiz 1", "tipo": "quiz"}]}
            r = client.post("/api/learn/plans", json=corpo, headers=h)
            assert r.status_code == 200, r.text
            pid = r.json()["id"]
            assert vistos["learn_plan_create"]["owner"] == "u-aaa"
            r = client.get(f"/api/learn/plans/{pid}", headers=h)
            plano = r.json()
            assert plano["progresso"] == {"feitos": 0, "total": 2, "taxa": 0.0}
            iid = plano["itens"][0]["id"]
            r = client.post("/api/learn/plans/item",
                            json={"plan_id": pid, "item_id": iid, "feito": True}, headers=h)
            assert r.json()["progresso"] == {"feitos": 1, "total": 2, "taxa": 0.5}
            r = client.post("/api/learn/plans/update",
                            json={"plan_id": pid, "mudancas": {"min_dia": 45, "itens": [
                                {"titulo": "Frações"}, {"titulo": "Geometria"}]}}, headers=h)
            assert r.json()["progresso"] == {"feitos": 1, "total": 2, "taxa": 0.5}
            assert client.get("/api/learn/plans", headers=h).json()["planos"][0]["id"] == pid
            assert client.post("/api/learn/plans", json={"titulo": "X", "itens": []},
                               headers=h).status_code == 422


def test_cards_recommend_flag_api(tmp_path):
    with TestClient(server.app) as client:
        with client.websocket_connect("/api/agent/ws",
                                      headers={"Authorization": "Bearer " + os.environ["JULIA_AGENT_TOKEN"]}) as ws:
            vistos = {}
            t = threading.Thread(target=_agente_learn,
                                 args=(ws, tmp_path / "learncardsapi.sqlite3", vistos, {"ana": "u-aaa"}),
                                 daemon=True)
            t.start()
            csrf = _login_comum(client)
            h = {"X-CSRF-Token": csrf}
            r = client.get("/api/learn/recommend", headers=h)
            assert r.json() == {"recomendacoes": [], "motivo": "sem_dados",
                                "aviso": "Ainda não há respostas suficientes para recomendar."}
            r = client.post("/api/learn/cards",
                            json={"cards": [{"frente": "2+2?", "verso": "4", "assunto": "mat"}]},
                            headers=h)
            fid = r.json()["ids"][0]
            assert client.get("/api/learn/cards/due", headers=h).json()["cards"][0]["id"] == fid
            r = client.post("/api/learn/cards/review",
                            json={"flashcard_id": fid, "acertou": True}, headers=h)
            assert r.json()["intervalo_d"] == 1 and r.json()["proxima_iso"] != ""
            rec = client.get("/api/learn/recommend", headers=h).json()
            assert rec["motivo"] == "sem_dados"  # 1 flip de card não inventa dificuldade
            att = client.post("/api/learn/attempts", json={"assessment_id": "av-mat"},
                              headers=h).json()["id"]
            client.post("/api/learn/answer",
                        json={"attempt_id": att, "question_id": "q1", "resposta": "1"}, headers=h)
            client.post("/api/learn/answer",
                        json={"attempt_id": att, "question_id": "q2", "resposta": "1"}, headers=h)
            client.post("/api/learn/finish", json={"attempt_id": att}, headers=h)
            erradas = client.get("/api/learn/mistakes", headers=h).json()["erradas"]
            assert len(erradas) == 1 and erradas[0]["question_id"] == "q2"
            rec = client.get("/api/learn/recommend", headers=h).json()
            assert rec["motivo"] == "dados_reais"
            assert rec["recomendacoes"][0]["tipo"] in ("refazer_erradas", "revisar")
            r = client.post("/api/learn/flag",
                            json={"question_id": "q1", "motivo": "gabarito parece trocado"}, headers=h)
            assert r.json() == {"ok": True, "question_id": "q1"}
            assert client.post("/api/learn/flag", json={"question_id": "q1", "motivo": "x"},
                               headers=h).status_code == 422


def test_aulas_e_historico_api(tmp_path):
    with TestClient(server.app) as client:
        with client.websocket_connect("/api/agent/ws",
                                      headers={"Authorization": "Bearer " + os.environ["JULIA_AGENT_TOKEN"]}) as ws:
            vistos = {}
            t = threading.Thread(target=_agente_learn,
                                 args=(ws, tmp_path / "learnaulaapi.sqlite3", vistos, {"ana": "u-aaa"}),
                                 daemon=True)
            t.start()
            csrf = _login_comum(client)
            h = {"X-CSRF-Token": csrf}
            aula = {"assunto": "OOP", "objetivo": "Classes", "nivel": "basico",
                    "secoes": [{"titulo": "Classes",
                                "explicacao": "Uma classe é o molde de objetos em Python."}],
                    "resumo": "Classe molda."}
            r = client.post("/api/learn/lessons", json={"aula": aula}, headers=h)
            assert r.status_code == 200, r.text
            lid = r.json()["id"]
            assert vistos["learn_lesson_create"]["owner"] == "u-aaa"
            r = client.get(f"/api/learn/lessons/{lid}", headers=h)
            assert r.json()["progresso"] == {"feitas": 0, "total": 1, "taxa": 0.0}
            r = client.post("/api/learn/lessons/section",
                            json={"lesson_id": lid, "ordem": 0}, headers=h)
            assert r.json() == {"estado": "concluida",
                                "progresso": {"feitas": 1, "total": 1, "taxa": 1.0}}
            assert client.get("/api/learn/lessons", headers=h).json()["aulas"][0]["id"] == lid
            assert client.get("/api/learn/history", headers=h).json() == {"tentativas": []}
            att = client.post("/api/learn/attempts", json={"assessment_id": "av-mat"},
                              headers=h).json()["id"]
            client.post("/api/learn/answer",
                        json={"attempt_id": att, "question_id": "q1", "resposta": "1"}, headers=h)
            client.post("/api/learn/answer",
                        json={"attempt_id": att, "question_id": "q2", "resposta": "0"}, headers=h)
            client.post("/api/learn/finish", json={"attempt_id": att}, headers=h)
            hist = client.get("/api/learn/history", headers=h).json()["tentativas"]
            assert len(hist) == 1 and hist[0]["nota"] == 1.0 and hist[0]["total"] == 2
            assert client.post("/api/learn/lessons", json={"aula": {"assunto": "x"}},
                               headers=h).status_code in (503, 422)


def test_resposta_idempotente_ultima_vale(tmp_path):
    """Reenvio (fila offline) não duplica: mesma (attempt, questão) = 1 linha."""
    import sqlite3 as _sq
    db_path = tmp_path / "learnidem.sqlite3"
    with TestClient(server.app) as client:
        with client.websocket_connect("/api/agent/ws",
                                      headers={"Authorization": "Bearer " + os.environ["JULIA_AGENT_TOKEN"]}) as ws:
            vistos = {}
            t = threading.Thread(target=_agente_learn,
                                 args=(ws, db_path, vistos, {"ana": "u-aaa"}),
                                 daemon=True)
            t.start()
            csrf = _login_comum(client)
            h = {"X-CSRF-Token": csrf}
            att = client.post("/api/learn/attempts", json={"assessment_id": "av-mat"},
                              headers=h).json()["id"]
            assert client.post("/api/learn/answer",
                               json={"attempt_id": att, "question_id": "q1", "resposta": "0"},
                               headers=h).json() == {"correta": False}
            assert client.post("/api/learn/answer",
                               json={"attempt_id": att, "question_id": "q1", "resposta": "1"},
                               headers=h).json() == {"correta": True}
    con = _sq.connect(db_path)
    n = con.execute("SELECT COUNT(*) FROM answers WHERE attempt_id=? AND question_id='q1'",
                    (att,)).fetchone()[0]
    con.close()
    assert n == 1  # reenvio substitui, nunca duplica
