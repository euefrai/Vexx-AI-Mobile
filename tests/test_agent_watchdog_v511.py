"""Watchdog opcional: nunca duplica o agente e exige checkout explicito."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import agent_watchdog as watchdog


def test_agente_vivo_aceita_qualquer_estado_nao_terminal(monkeypatch):
    monkeypatch.setattr(watchdog.agent_runtime, "command",
                        lambda *a, **k: {"state": "STARTING", "pid": 123})
    assert watchdog.agente_vivo("https://exemplo.invalid") is True


def test_agente_vivo_rejeita_stopped(monkeypatch):
    monkeypatch.setattr(watchdog.agent_runtime, "command",
                        lambda *a, **k: {"state": "STOPPED", "pid": 123})
    assert watchdog.agente_vivo("https://exemplo.invalid") is False


def test_agente_vivo_rejeita_canal_que_nao_responde(monkeypatch):
    def falhar(*a, **k):
        raise TimeoutError("sem resposta")
    monkeypatch.setattr(watchdog.agent_runtime, "command", falhar)
    assert watchdog.agente_vivo("https://exemplo.invalid") is False


def test_iniciar_agente_exige_pc_agent(tmp_path):
    outro = tmp_path / "outro.py"
    outro.write_text("print('x')", encoding="utf-8")
    with pytest.raises(ValueError):
        watchdog.iniciar_agente(outro, tmp_path / "logs")
    with pytest.raises(ValueError):
        watchdog.iniciar_agente(tmp_path / "pc_agent.py", tmp_path / "logs")


def test_pythonw_aponta_para_executavel_windows():
    caminho = Path(watchdog._pythonw())
    assert caminho.exists()
    if os.name == "nt":
        assert caminho.name.lower() in ("pythonw.exe", "python.exe")


def test_main_recusa_sem_relay_ou_checkout(monkeypatch):
    monkeypatch.delenv("JULIA_RELAY_URL", raising=False)
    monkeypatch.delenv("VEXX_AGENT_SCRIPT", raising=False)
    assert watchdog.main(["--once"]) == 2
    monkeypatch.setenv("JULIA_RELAY_URL", "https://exemplo.invalid")
    assert watchdog.main(["--once"]) == 2
    monkeypatch.setenv("VEXX_AGENT_SCRIPT", "nao-existe.py")
    assert watchdog.main(["--once"]) == 2


def test_runtime_directory_e_estavel():
    a = watchdog.runtime_directory("https://vexx-ai.onrender.com")
    b = watchdog.runtime_directory("https://vexx-ai.onrender.com/")
    assert a == b
    assert a.name and len(a.name) == 24


def test_main_once_nao_falha_sem_diretorio_previo(monkeypatch, tmp_path):
    script = tmp_path / "pc_agent.py"
    script.write_text("raise SystemExit(0)\n", encoding="utf-8")
    monkeypatch.setenv("JULIA_RELAY_URL", "https://exemplo.invalid")
    monkeypatch.setenv("JULIA_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setattr(watchdog, "agente_vivo", lambda relay: True)
    criados = []

    def privado(path):
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        criados.append(path)
        return path
    monkeypatch.setattr(watchdog.agent_runtime, "private_directory", privado)
    assert watchdog.main(["--once", "--script", str(script)]) == 0
    assert criados and criados[0].name == watchdog.runtime_directory(
        "https://exemplo.invalid").name
