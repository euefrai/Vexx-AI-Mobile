"""V5.8 security hardening: limites, CSRF central, throttle e cancelamento."""
import os
import sqlite3
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import julia_auth as ja
import pc_agent
import research
import research_agents as ra
import server
from rate_limit import RateLimiter, client_ip


def setup_module():
    os.environ["JULIA_USERNAME"] = "efrai"
    os.environ["JULIA_PASSWORD_HASH"] = PasswordHasher().hash("strong-example-password")
    os.environ["JULIA_SESSION_SECRET"] = "c" * 64
    os.environ["JULIA_AGENT_TOKEN"] = "d" * 64


def _db(nome="hardening.sqlite3"):
    return pc_agent.open_db(Path(tempfile.mkdtemp()) / nome)


def _login(client):
    r = client.post("/api/login",
                    json={"username": "efrai", "password": "strong-example-password"})
    assert r.status_code == 200, r.text
    return r.json()["csrf"]


def test_rate_limiter_bounded_e_retry_after():
    lim = RateLimiter(max_chaves=64)
    for i in range(600):
        assert lim.hit(f"chave-{i}", 1, 60) == 0
    assert len(lim) <= 64
    assert lim.hit("rajada", 2, 60) == 0
    assert lim.hit("rajada", 2, 60) == 0
    espera = lim.hit("rajada", 2, 60)
    assert espera >= 1


def test_client_ip_ignora_cabecalho_sem_proxy_confiavel(monkeypatch):
    req = SimpleNamespace(headers={"cf-connecting-ip": "203.0.113.9",
                                   "x-forwarded-for": "198.51.100.7"},
                          client=SimpleNamespace(host="127.0.0.1"))
    monkeypatch.delenv("JULIA_TRUST_PROXY", raising=False)
    assert client_ip(req) == "127.0.0.1"
    monkeypatch.setenv("JULIA_TRUST_PROXY", "1")
    assert client_ip(req) == "203.0.113.9"


def test_login_burst_429_com_retry_after(monkeypatch):
    monkeypatch.setenv("JULIA_RATE_LOGIN_IP", "2")
    monkeypatch.setenv("JULIA_RATE_LOGIN_GLOBAL", "100")
    server.rate_limiter.clear()
    with TestClient(server.app) as client:
        codigos = [client.post("/api/login",
                                json={"username": "conta-comum", "password": "x"}).status_code
                   for _ in range(3)]
    assert codigos == [503, 503, 429], codigos
    with TestClient(server.app) as client:
        r = client.post("/api/login", json={"username": "conta-comum", "password": "x"})
    assert r.status_code == 429
    assert int(r.headers["Retry-After"]) >= 1


def test_corpo_json_grande_rejeitado_antes_da_autenticacao():
    with TestClient(server.app) as client:
        r = client.post("/api/sync", content=b"x" * (server.API_BODY_MAX_BYTES + 1),
                        headers={"Content-Type": "application/json"})
    assert r.status_code == 413
    assert "limite" in r.json()["detail"].lower()


@pytest.mark.parametrize("caminho,payload", [
    ("/api/admin/users/create",
     {"display": "Nova", "username": "nova", "password": "senha-forte-1", "role": "user"}),
    ("/api/admin/users/role", {"uid": "u-1", "role": "user"}),
    ("/api/admin/users/status", {"uid": "u-1", "status": "ativo"}),
    ("/api/admin/users/sessions", {"uid": "u-1"}),
    ("/api/admin/users/delete", {"uid": "u-1"}),
    ("/api/admin/users/limits", {"uid": "u-1", "max_ai_hora": 1}),
    ("/api/admin/quality/run", None),
    ("/api/admin/invites/create", {"max_usos": 1, "dias": 7}),
    ("/api/admin/invites/revoke", {"id": 1, "aprovar": False}),
    ("/api/admin/regs/decide", {"id": 1, "aprovar": True}),
    ("/api/admin/config", {"modo": "fechado", "exigir_aprovacao": True}),
])
def test_admin_post_exige_csrf(caminho, payload):
    with TestClient(server.app) as client:
        _login(client)
        r = client.post(caminho, json=payload) if payload is not None else client.post(caminho)
    assert r.status_code == 403, (caminho, r.status_code, r.text)


def test_admin_post_com_csrf_nao_e_bloqueado_pelo_csrf():
    with TestClient(server.app) as client:
        csrf = _login(client)
        r = client.post("/api/admin/invites/create",
                        json={"max_usos": 1, "dias": 7},
                        headers={"X-CSRF-Token": csrf})
    assert r.status_code == 503  # PC offline: passou CSRF/admin, parou no relay


def test_params_de_intervencao_limitados():
    server.ResearchInterveneIn(job_id="rj-1", op="escopo_add",
                               params={"texto": "preço", "indice": 1})
    with pytest.raises(ValidationError):
        server.ResearchInterveneIn(job_id="rj-1", op="escopo_add",
                                   params={"texto": {"aninhado": "x"}})
    with pytest.raises(ValidationError):
        server.ResearchInterveneIn(job_id="rj-1", op="escopo_add",
                                   params={f"k{i}": i for i in range(11)})


def test_throttle_login_persistente_e_generico(monkeypatch):
    monkeypatch.setenv("JULIA_LOGIN_MAX_FALHAS", "3")
    monkeypatch.setenv("JULIA_LOGIN_JANELA_S", "300")
    path = Path(tempfile.mkdtemp()) / "auth.sqlite3"
    db = pc_agent.open_db(path)
    ja.criar_usuario(db, "ana", "Ana", "senha-forte-1")
    codigos = []
    for _ in range(4):
        with pytest.raises(ja.AuthErro) as erro:
            ja.login_conta(db, "ana", "errada")
        codigos.append(erro.value.codigo)
    assert codigos == ["credenciais", "credenciais", "credenciais", "rate"]
    assert erro.value.retry_after >= 1
    db.close()

    # Reinício do processo não zera o throttle.
    db = pc_agent.open_db(path)
    with pytest.raises(ja.AuthErro) as erro:
        ja.login_conta(db, "ana", "senha-forte-1")
    assert erro.value.codigo == "rate"
    db.close()


def test_sucesso_limpa_historico_de_falhas(monkeypatch):
    monkeypatch.setenv("JULIA_LOGIN_MAX_FALHAS", "5")
    db = _db("reset.sqlite3")
    try:
        ja.criar_usuario(db, "bia", "Bia", "senha-forte-1")
        for _ in range(2):
            with pytest.raises(ja.AuthErro):
                ja.login_conta(db, "bia", "errada")
        assert ja.login_conta(db, "bia", "senha-forte-1")["uid"].startswith("u-")
        assert db.execute("SELECT COUNT(*) FROM login_attempts").fetchone()[0] == 0
    finally:
        db.close()


def test_login_concorrente_respeita_teto_atomico(monkeypatch):
    monkeypatch.setenv("JULIA_LOGIN_MAX_FALHAS", "3")
    monkeypatch.setenv("JULIA_LOGIN_JANELA_S", "300")
    path = Path(tempfile.mkdtemp()) / "concorrente.sqlite3"
    db = pc_agent.open_db(path)
    ja.criar_usuario(db, "carla", "Carla", "senha-forte-1")
    db.close()

    barreira = threading.Barrier(8)
    codigos = []

    def tentar():
        conexao = sqlite3.connect(path)
        conexao.execute("PRAGMA busy_timeout=5000")
        barreira.wait(timeout=10)
        try:
            ja.login_conta(conexao, "carla", "errada")
            return "ok"
        except ja.AuthErro as exc:
            return exc.codigo
        finally:
            conexao.close()

    with ThreadPoolExecutor(max_workers=8) as pool:
        codigos = list(pool.map(lambda _: tentar(), range(8)))
    assert codigos.count("credenciais") == 3, codigos
    assert codigos.count("rate") == 5, codigos


def test_busca_cancela_antes_do_proximo_provedor():
    class Prov:
        nome = "p1"

        def __init__(self, evento):
            self.evento = evento
            self.chamadas = []

        def buscar(self, consulta, limite=6):
            self.chamadas.append(consulta)
            self.evento.set()
            return []

    evento = threading.Event()
    p1 = Prov(evento)
    p2 = Prov(evento)
    achados, info = ra.buscar_com_fallback([p1, p2], "tema", deve_parar=evento.is_set)
    assert achados == [] and info["cancelado"] is True
    assert len(p1.chamadas) == 1 and p2.chamadas == []


def test_agente_busca_nao_inicia_segunda_consulta_apos_cancelar():
    db = _db("cancelabusca.sqlite3")
    try:
        job = ra.criar_job(db, "u-cancel", "café e saúde", manual="pro")
        ra.montar_plano(db, job)
        etapa = next(s for s in job["plano"] if s["tipo"] == "busca")

        class Prov:
            nome = "p1"

            def __init__(self):
                self.chamadas = []

            def buscar(self, consulta, limite=6):
                self.chamadas.append(consulta)
                evento.set()
                return []

        evento = threading.Event()
        prov = Prov()
        achados = ra.agente_busca(db, job, etapa, [prov], vistas=set(),
                                  deve_parar=evento.is_set)
        assert achados == []
        assert len(prov.chamadas) == 1
    finally:
        db.close()


def test_agente_analista_respeita_prazo_sem_baixar():
    db = _db("cancelaler.sqlite3")
    try:
        job = ra.criar_job(db, "u-prazo", "café e saúde", manual="pro")
        ra.montar_plano(db, job)
        etapa = next(s for s in job["plano"] if s["tipo"] == "ler")
        chamadas = []

        def recuperar(url):
            chamadas.append(url)
            return {"titulo": "x", "texto": "x"}

        evidencias = ra.agente_analista(
            db, job, etapa,
            [{"id": "f1", "titulo": "x", "url": "https://example.com/x",
              "trecho": "x", "dominio": "example.com"}],
            recuperar_fn=recuperar, prazo=time.monotonic() - 1)
        assert evidencias == [] and chamadas == []
    finally:
        db.close()


def test_salvar_job_preserva_cancelamento_e_pausa_concorrentes():
    db = _db("status.sqlite3")
    try:
        job = ra.criar_job(db, "u-status", "café e saúde", manual="pro")
        job["status"] = "em_andamento"
        ra.salvar_job(db, job)
        antigo = ra.carregar_job(db, "u-status", job["id"])
        ra.cancelar(db, "u-status", job["id"])
        ra.salvar_job(db, antigo)
        assert ra.carregar_job(db, "u-status", job["id"])["status"] == "cancelada"

        outro = ra.criar_job(db, "u-status", "chá e saúde", manual="pro")
        outro["status"] = "em_andamento"
        ra.salvar_job(db, outro)
        antigo = ra.carregar_job(db, "u-status", outro["id"])
        ra.pausar(db, "u-status", outro["id"], True)
        ra.salvar_job(db, antigo)
        assert ra.carregar_job(db, "u-status", outro["id"])["status"] == "pausada"
    finally:
        db.close()


def test_retomada_manual_vence_cancelamento(monkeypatch):
    db = _db("retomada.sqlite3")
    disparados = []
    try:
        job = ra.criar_job(db, "u-retoma", "café e saúde", manual="pro")
        job["status"] = "em_andamento"
        ra.salvar_job(db, job)
        ra.cancelar(db, "u-retoma", job["id"])
        monkeypatch.setattr(pc_agent, "iniciar_job_bg",
                            lambda *a, **k: disparados.append(a[1]) or True)
        texto = pc_agent.cmd_pesquisa(db, "continue aquela pesquisa", "u-retoma", "c1")
        assert "retomada" in texto
        assert disparados == [job["id"]]
        assert ra.carregar_job(db, "u-retoma", job["id"])["status"] == "em_andamento"

        falho = ra.criar_job(db, "u-retoma2", "chá e saúde", manual="pro")
        falho["status"] = "em_andamento"
        ra.salvar_job(db, falho)
        ra.cancelar(db, "u-retoma2", falho["id"])
        monkeypatch.setattr(pc_agent, "iniciar_job_bg", lambda *a, **k: False)
        texto = pc_agent.cmd_pesquisa(db, "continue aquela pesquisa", "u-retoma2", "c1")
        assert "outra pesquisa" in texto
        assert ra.carregar_job(db, "u-retoma2", falho["id"])["status"] == "interrompida"
    finally:
        db.close()


def test_recover_interrupted_research_marca_orfaos():
    db = _db("orfaos.sqlite3")
    try:
        job = ra.criar_job(db, "u-orfao", "café e saúde", manual="pro")
        job["status"] = "em_andamento"
        ra.salvar_job(db, job)
        pronto = ra.criar_job(db, "u-orfao", "chá e saúde", manual="pro")
        pronto["status"] = "concluida"
        ra.salvar_job(db, pronto)

        assert pc_agent.recover_interrupted_research(db) == 1
        recuperado = ra.carregar_job(db, "u-orfao", job["id"])
        assert recuperado["status"] == "interrompida"
        assert any("reiniciado" in p.lower() for p in recuperado["pendencias"])
        assert ra.carregar_job(db, "u-orfao", pronto["id"])["status"] == "concluida"
        eventos = ra.eventos_desde(db, "u-orfao", job["id"])
        assert any(e["tipo"] == "research_cancelled" for e in eventos)
    finally:
        db.close()
