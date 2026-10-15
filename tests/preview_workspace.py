"""Disposable local UI/RPC environment. Never reads the user's database or secrets.

Run: python tests/preview_workspace.py
Open http://127.0.0.1:8770 and sign in as preview / preview-only-2026.
Ctrl+C stops both children and removes the temporary SQLite database.
"""
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    from argon2 import PasswordHasher
    with tempfile.TemporaryDirectory(prefix="vexx-ui-check-") as directory:
        env = dict(os.environ, JULIA_USERNAME="preview",
                   JULIA_PASSWORD_HASH=PasswordHasher().hash("preview-only-2026"),
                   JULIA_AGENT_TOKEN=secrets.token_hex(32), JULIA_SESSION_SECRET=secrets.token_hex(32),
                   JULIA_SQLITE_PATH=str(Path(directory) / "preview.sqlite3"),
                   JULIA_RELAY_URL="http://127.0.0.1:8770", JULIA_ENV="development",
                   JULIA_REMOTE="0", HERMES_PROXY_URL="http://127.0.0.1:9/v1")
        import pc_agent
        db = pc_agent.open_db(Path(env["JULIA_SQLITE_PATH"]))
        pc_agent.persist_messages(db, [
            dict(id="preview-message-001", conversation_id="preview-week-plan", origin="mobile", role="user",
                 text="Me ajuda a organizar a semana? Quero estudar e avançar no meu projeto, sem sobrecarregar os dias.",
                 created_at="2026-10-15T12:00:00.000Z"),
            dict(id="preview-message-001-r1", conversation_id="preview-week-plan", origin="mobile", role="assistant",
                 text="Vamos começar com um plano simples e espaço para imprevistos.\n\n### Uma prioridade por dia\n\nReserve um bloco de foco para o projeto e outro, mais curto, para estudar.\n\n| Dias | Atividade |\n|---|---|\n| Seg, qua e sex | Avançar no projeto por 60 minutos |\n| Ter e qui | Estudar e praticar por 30 minutos |\n\nNa sexta, separe 15 minutos para revisar o que funcionou.\n\nQual período do dia costuma ser mais tranquilo para você?",
                 created_at="2026-10-15T12:00:02.000Z")])
        db.close()
        children = []
        try:
            children.append(subprocess.Popen([sys.executable, "-m", "uvicorn", "server:app", "--host", "127.0.0.1", "--port", "8770", "--log-level", "warning"], cwd=ROOT, env=env))
            children.append(subprocess.Popen([sys.executable, "pc_agent.py"], cwd=ROOT, env=env))
            print("Disposable preview: http://127.0.0.1:8770 (preview / preview-only-2026)", flush=True)
            while all(p.poll() is None for p in children):
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            for child in children:
                if child.poll() is None:
                    child.terminate()
            for child in children:
                child.wait(timeout=15)


if __name__ == "__main__":
    main()
