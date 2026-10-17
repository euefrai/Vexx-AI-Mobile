"""Carrega um arquivo `.env` local (somente PC) para os processos do agente.

Regras de ouro (V5.4.3):
- NUNCA imprime nem registra valores — só conta quantas variáveis entraram.
- Chave de PROVEDOR salva pelo app no `.env` VENCE a variável de sistema: é
  assim que salvar/trocar/remover uma chave na interface tem efeito real,
  mesmo que exista uma variável antiga (setx) no PC. Todas as demais
  variáveis continuam "sistema manda" (o `.env` só preenche o que falta).
- Expande %VAR% (ex.: %USERPROFILE%) e aceita valor entre aspas.
- Sem `.env` no projeto, é um no-op silencioso.
- `JULIA_ENV_FILE` pode apontar para outro arquivo (usado nos testes/E2E):
  passa a ser o `.env` local para leitura E escrita.
"""
import os
from pathlib import Path

# Variáveis de chave dos provedores externos (ver providers.PROVIDERS; um
# teste garante que este conjunto não sai de sincronia com o registro).
PROVIDER_KEY_ENVS = frozenset({
    "OPENAI_API_KEY", "GEMINI_API_KEY", "ANTHROPIC_API_KEY",
    "DEEPSEEK_API_KEY", "GROQ_API_KEY", "MISTRAL_API_KEY",
    "OPENROUTER_API_KEY",
})


def env_file_path(raiz: Path | None = None) -> Path:
    """Caminho do .env local: `<raiz>/.env`, ou `JULIA_ENV_FILE`, ou repo/.env."""
    if raiz is None:
        override = (os.environ.get("JULIA_ENV_FILE") or "").strip()
        if override:
            return Path(os.path.expandvars(override))
        raiz = Path(__file__).resolve().parent
    return Path(raiz) / ".env"


def _ler_linhas(caminho: Path) -> list:
    try:
        return caminho.read_text(encoding="utf-8", errors="ignore").splitlines(keepends=True)
    except OSError:
        return []


def _e_linha_de(chave: str, linha: str) -> bool:
    s = linha.strip()
    if not s or s.startswith("#") or "=" not in s:
        return False
    return s.split("=", 1)[0].strip() == chave


def _parse_linha(linha: str):
    s = linha.strip()
    if not s or s.startswith("#") or "=" not in s:
        return None
    chave, valor = s.split("=", 1)
    chave = chave.strip()
    valor = valor.strip().strip('"').strip("'")
    if not chave or not valor:
        return None
    try:
        valor = os.path.expandvars(valor)
    except Exception:
        pass
    return chave, valor


def valores_do_arquivo(caminho: Path | None = None) -> dict:
    """Entradas ativas do .env (última ocorrência vence). Nunca logar o dict."""
    c = Path(caminho) if caminho is not None else env_file_path()
    out = {}
    for linha in _ler_linhas(c):
        par = _parse_linha(linha)
        if par:
            out[par[0]] = par[1]
    return out


def carregar_env_local(raiz: Path | None = None) -> int:
    """Preenche os.environ a partir do .env local. Retorna quantos entraram."""
    caminho = env_file_path(raiz)
    if not caminho.is_file():
        return 0
    entradas = 0
    for chave, valor in valores_do_arquivo(caminho).items():
        if chave in PROVIDER_KEY_ENVS:
            # Chave salva pelo app manda: vence variável antiga do sistema.
            if os.environ.get(chave, "") != valor:
                os.environ[chave] = valor
                entradas += 1
        elif not os.environ.get(chave, ""):
            os.environ[chave] = valor
            entradas += 1
    return entradas


def _fim_de_linha(linha: str) -> str:
    if linha.endswith("\r\n"):
        return "\r\n"
    if linha.endswith("\n"):
        return "\n"
    if linha.endswith("\r"):
        return "\r"
    return "\n"


def salvar_chave(chave: str, valor: str) -> Path:
    """Grava/atualiza `CHAVE=valor` no .env local (o valor nunca é logado).

    - Preserva comentários, demais linhas e o tipo de fim de linha.
    - Duplicatas ativas da mesma chave são consolidadas em uma só.
    - Escreve em arquivo temporário e renomeia (nunca deixa o .env pela metade).
    """
    chave = str(chave or "").strip()
    valor = str(valor or "").strip()
    if not chave or "=" in chave or not valor:
        raise ValueError("chave/valor inválidos")
    if "\n" in valor or "\r" in valor:
        raise ValueError("valor não pode ter quebras de linha")
    caminho = env_file_path()
    linhas = _ler_linhas(caminho)
    novas, achou = [], False
    for linha in linhas:
        if _e_linha_de(chave, linha):
            if not achou:
                novas.append(chave + "=" + valor + _fim_de_linha(linha))
                achou = True
            continue
        novas.append(linha)
    if not achou:
        if novas and not novas[-1].endswith(("\n", "\r")):
            novas[-1] += "\n"
        novas.append(chave + "=" + valor + "\n")
    caminho.parent.mkdir(parents=True, exist_ok=True)
    tmp = caminho.with_name(caminho.name + ".tmp")
    tmp.write_text("".join(novas), encoding="utf-8", newline="")
    os.replace(tmp, caminho)
    return caminho


def remover_chave(chave: str) -> Path:
    """Remove todas as linhas ativas com essa chave do .env local (se houver)."""
    chave = str(chave or "").strip()
    caminho = env_file_path()
    linhas = _ler_linhas(caminho)
    novas = [l for l in linhas if not _e_linha_de(chave, l)]
    if novas != linhas:
        tmp = caminho.with_name(caminho.name + ".tmp")
        tmp.write_text("".join(novas), encoding="utf-8", newline="")
        os.replace(tmp, caminho)
    return caminho
