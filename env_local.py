"""Carrega um arquivo `.env` local (somente PC) para os processos do agente.

Regras de ouro (V5.4.2):
- NUNCA imprime nem registra valores — só conta quantas variáveis entraram.
- NUNCA sobrescreve variável de ambiente já definida com valor (o sistema
  manda; o `.env` só preenche o que estiver vazio/ausente).
- Expande %VAR% (ex.: %USERPROFILE%) e aceita valor entre aspas.
- Sem `.env` no projeto, é um no-op silencioso.
"""
import os
from pathlib import Path


def carregar_env_local(raiz: Path | None = None) -> int:
    """Preenche os.environ a partir de `<raiz>/.env`. Retorna quantos entraram."""
    base = Path(raiz) if raiz is not None else Path(__file__).resolve().parent
    caminho = base / ".env"
    if not caminho.is_file():
        return 0
    try:
        linhas = caminho.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return 0
    entradas = 0
    for linha in linhas:
        s = linha.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        chave, valor = s.split("=", 1)
        chave = chave.strip()
        valor = valor.strip().strip('"').strip("'")
        if not chave or not valor:
            continue
        try:
            valor = os.path.expandvars(valor)
        except Exception:
            pass
        if not os.environ.get(chave, ""):
            os.environ[chave] = valor
            entradas += 1
    return entradas
