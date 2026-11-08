"""Watchdog opcional do agente do PC.

Nao altera inicializacao do Windows e nao adivinha qual checkout deve rodar:
o operador precisa definir VEXX_AGENT_SCRIPT (caminho explicito do pc_agent.py),
JULIA_RELAY_URL e JULIA_AGENT_TOKEN (o mesmo token do relay). O processo usa o
mesmo lock do agent_runtime, entao uma tentativa duplicada nunca cria duas
instancias consumindo o mesmo relay.

Uso:
    python agent_watchdog.py --once
    python agent_watchdog.py --interval 30
"""
from __future__ import annotations

import argparse
import logging
import logging.handlers
import os
from pathlib import Path
import subprocess
import sys
import time

import agent_runtime

log = logging.getLogger("vexx.watchdog")


def runtime_directory(relay_url: str) -> Path:
    return Path.home() / ".julia-mobile" / "runtime" / agent_runtime.identity(
        relay_url, "production")


def agente_vivo(relay_url: str) -> bool:
    """True apenas quando o canal local autenticado confirma o processo."""
    try:
        estado = agent_runtime.command(runtime_directory(relay_url),
                                       "status", timeout=5)
    except Exception:
        return False
    return estado.get("state") != "STOPPED" and bool(estado.get("pid"))


def _pythonw() -> str:
    if os.name == "nt":
        candidato = Path(sys.executable).with_name("pythonw.exe")
        if candidato.exists():
            return str(candidato)
    return sys.executable


def iniciar_agente(script: Path, log_dir: Path) -> subprocess.Popen:
    """Inicia o checkout informado, destacado, com log persistente."""
    script = script.resolve()
    if not script.is_file() or script.name != "pc_agent.py":
        raise ValueError("VEXX_AGENT_SCRIPT deve apontar para pc_agent.py")
    log_dir.mkdir(parents=True, exist_ok=True)
    destino = log_dir / "watchdog-child.log"
    kwargs = {
        "cwd": str(script.parent),
        "env": os.environ.copy(),
        "stdin": subprocess.DEVNULL,
        "stderr": subprocess.STDOUT,
    }
    if os.name == "nt":
        kwargs["creationflags"] = (subprocess.CREATE_NO_WINDOW
                                   | subprocess.DETACHED_PROCESS)
    else:
        kwargs["start_new_session"] = True
    saida = destino.open("ab")
    try:
        kwargs["stdout"] = saida
        return subprocess.Popen(
            [_pythonw(), str(Path(agent_runtime.__file__).resolve()),
             "--script", str(script)], **kwargs)
    finally:
        saida.close()


def configurar_log(log_dir: Path) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    if any(getattr(h, "baseFilename", "").endswith("watchdog.log")
           for h in logging.getLogger().handlers):
        return
    handler = logging.handlers.RotatingFileHandler(
        log_dir / "watchdog.log", maxBytes=2_000_000, backupCount=2,
        encoding="utf-8")
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.getLogger().addHandler(handler)
    logging.getLogger().setLevel(logging.INFO)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Watchdog do agente Vexx")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval", type=int, default=30)
    parser.add_argument("--script", default=os.environ.get("VEXX_AGENT_SCRIPT", ""))
    args = parser.parse_args(argv)
    relay_url = os.environ.get("JULIA_RELAY_URL", "").strip()
    if not relay_url:
        print("Defina JULIA_RELAY_URL.", file=sys.stderr)
        return 2
    if not args.script or not Path(args.script).is_file():
        print("Defina VEXX_AGENT_SCRIPT com o pc_agent.py do checkout publicado.",
              file=sys.stderr)
        return 2

    log_dir = Path(os.environ.get(
        "JULIA_LOG_DIR", str(Path.home() / ".julia-mobile" / "logs")))
    configurar_log(log_dir)
    runtime_dir = agent_runtime.private_directory(runtime_directory(relay_url))
    lock = agent_runtime.InstanceLock(runtime_dir / "watchdog.lock")
    try:
        lock.acquire()
    except RuntimeError:
        log.warning("Outro watchdog ja esta ativo; saindo.")
        return 0
    try:
        while True:
            if not agente_vivo(relay_url):
                log.error("Agente nao respondeu ao canal local; reiniciando %s.",
                          args.script)
                try:
                    iniciar_agente(Path(args.script), log_dir)
                except (OSError, ValueError) as exc:
                    log.error("Falha ao reiniciar o agente: %s", exc)
            if args.once:
                return 0
            time.sleep(max(5, args.interval))
    finally:
        lock.close()


if __name__ == "__main__":
    raise SystemExit(main())
