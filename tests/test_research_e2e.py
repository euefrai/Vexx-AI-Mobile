"""E2E real V4.7 §18: relay + agente de verdade, busca DDG real, eventos via HTTP.

Sem mocks: processos reais, rede real (DDG), SQLite temporário. LLM não é
usada (pipeline determinístico); inferência real segue BLOQUEADA.
Marcador `e2e_real`; pula sem uvicorn.
"""
import json
import os
import shutil
import sys
import time
import urllib.request
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from e2e_processes import LoggedProcess, available_loopback_port

pytestmark = pytest.mark.e2e_real


def setup_module():
    from argon2 import PasswordHasher
    os.environ["JULIA_USERNAME"] = "efrai"
    os.environ["JULIA_PASSWORD_HASH"] = PasswordHasher().hash("strong-example-password")
    os.environ["JULIA_SESSION_SECRET"] = "a" * 64
    os.environ["JULIA_AGENT_TOKEN"] = "b" * 64


def _call(porta, path, data=None, csrf=None, timeout=60):
    req = urllib.request.Request(
        f"http://127.0.0.1:{porta}" + path,
        data=json.dumps(data).encode() if data is not None else None,
        headers={"Content-Type": "application/json"})
    if csrf:
        req.add_header("X-CSRF-Token", csrf)
    import http.cookiejar
    global _cj, _opener
    try:
        _cj
    except NameError:
        _cj = http.cookiejar.CookieJar()
        _opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(_cj))
    with _opener.open(req, timeout=timeout) as r:
        return json.loads(r.read().decode() or "{}")


def _esperar(url, cond, timeout, nome):
    inicio = time.monotonic()
    ultimo = None
    while time.monotonic() - inicio < timeout:
        try:
            with urllib.request.urlopen(url, timeout=3) as r:
                if cond(json.loads(r.read().decode() or "{}")):
                    return
                ultimo = "sem pronto"
        except Exception as exc:
            ultimo = exc
        time.sleep(0.5)
    raise AssertionError(f"{nome} não pronto ({ultimo})")


def test_e2e_pesquisa_com_eventos_reais(tmp_path):
    if shutil.which(sys.executable) is None:
        pytest.skip("interpretador indisponível")
    import importlib.util
    if importlib.util.find_spec("uvicorn") is None:
        pytest.skip("uvicorn ausente: e2e exige relay real")
    porta = available_loopback_port()
    env = dict(os.environ)
    env["JULIA_USERNAME"] = "efrai"
    env["JULIA_PASSWORD_HASH"] = os.environ["JULIA_PASSWORD_HASH"]
    env["JULIA_SESSION_SECRET"] = "a" * 64
    env["JULIA_AGENT_TOKEN"] = "b" * 64
    env["JULIA_RELAY_URL"] = f"http://127.0.0.1:{porta}"
    env["JULIA_SQLITE_PATH"] = str(tmp_path / "e2e.sqlite3")
    env["HERMES_PROXY_URL"] = "http://127.0.0.1:9/v1"
    # This integration explicitly tests deterministic research, not inference.
    # Keep local developer model configuration out of the child PC Agent.
    env['VEXX_RESEARCH_SYNTHESIS'] = '0'
    raiz = str(Path(__file__).resolve().parents[1])
    relay_log = tmp_path / "relay.log"
    agent_log = tmp_path / "agent.log"
    with LoggedProcess(
        [sys.executable, "-m", "uvicorn", "server:app",
         "--host", "127.0.0.1", "--port", str(porta)],
        relay_log, cwd=raiz, env=env,
    ):
        _esperar(
            f"http://127.0.0.1:{porta}/api/diag",
            lambda c: True, 30.0, "relay",
        )
        with LoggedProcess(
            [sys.executable, "pc_agent.py"],
            agent_log, cwd=raiz, env=env,
        ):
            _esperar(
                f"http://127.0.0.1:{porta}/api/diag",
                lambda c: c.get("pc_online") is True, 30.0, "agente",
            )
            sess = _call(
                porta, "/api/login",
                {"username": "efrai", "password": "strong-example-password"},
            )
            csrf = sess["csrf"]

            def call(path, data=None, csrf_=None):
                return _call(porta, path, data, csrf_ or csrf)

            inicio = time.monotonic()
            r = call("/api/research/start", {"objetivo": "fotossíntese plantas",
                                             "conv": "e2e-1", "modo": "rapida"})
            job = r["job_id"]
            assert r["modo"] == "rapida"
            resumo, eventos = {}, []
            prazo = time.monotonic() + 30
            while time.monotonic() < prazo:
                st = call(f"/api/research/status?job_id={job}&apos_seq=0")
                resumo = st["resumo"]
                for ev in st["eventos"]:
                    if ev["seq"] not in {e["seq"] for e in eventos}:
                        eventos.append(ev)
                tipos = {e["tipo"] for e in eventos}
                if (resumo["status"] in ("concluida", "falhou", "interrompida")
                        and "research_completed" in tipos):
                    break
                time.sleep(0.2)
            dur = time.monotonic() - inicio
            assert resumo["status"] == "concluida", resumo
            tipos = {e["tipo"] for e in eventos}
            for t in ("research_created", "plan_created", "step_started",
                      "search_completed", "research_completed"):
                assert t in tipos, tipos
            seqs = [e["seq"] for e in eventos]
            assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs)
            ev = call(f"/api/research/evidence?job_id={job}")
            assert len(ev["evidencias"]) >= 1, ev
            assert all(e["url"].startswith("http") for e in ev["evidencias"])
            print(f"\nE2E research: {len(eventos)} eventos, "
                  f"{len(ev['evidencias'])} evidências em {dur:.0f}s")
