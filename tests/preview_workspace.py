"""Disposable local UI/RPC environment. Never reads the user's database or secrets.

Run: python tests/preview_workspace.py
Open http://127.0.0.1:8770 and sign in as preview / preview-only-2026.
Ctrl+C stops both children and removes the temporary SQLite database.
"""
import os
import json
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
        if os.environ.get('VEXX_UI_FIXTURES') == '1':
            # Explicitly synthetic UI fixtures, only in this disposable database.
            fixture = {'version':'JULIA-ui-message/v1', 'blocks':[
                {'type':'ui', 'component':'quiz', 'props':{'title':'Quiz de teste', 'questions':[
                    {'q':'Quanto é 2 + 2?', 'options':['3','4'], 'answer':1, 'explain':'Exemplo de teste.'}]}},
                {'type':'ui', 'component':'evidencegraph', 'props':{'title':'Grafo de teste — dados fictícios',
                    'nodes':[{'id':'c1','kind':'claim','label':'Afirmação de teste'},
                             {'id':'e1','kind':'evidence','label':'Evidência de teste'},
                             {'id':'s1','kind':'source','label':'Fonte de teste'}],
                    'edges':[{'from':'e1','to':'c1','label':'SUPPORTS'},
                             {'from':'s1','to':'e1','label':'SUPPORTS'}]}}
            ]}
            pc_agent.persist_messages(db, [dict(id='preview-ui-001-r1', conversation_id='preview-ui-tests',
                origin='mobile', role='assistant', created_at='2026-10-15T12:01:00.000Z',
                text='## Componentes de demonstração\n\nDados fictícios para validar a interface.\n\n'
                     '| Campo | Valor | Nota |\n|---|---|---|\n| A | | Célula vazia preservada |\n\n'
                     '```jdui\n' + json.dumps(fixture, ensure_ascii=False) + '\n```')])
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
