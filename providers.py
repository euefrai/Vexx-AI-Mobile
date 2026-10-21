"""Provedores de LLM — Hermes proxy local + diretos com API key.

PC-SIDE ONLY: chaves lidas SÓ de variáveis de ambiente do PC. NUNCA vão
ao relay, ao frontend, aos logs ou a mensagens de erro (erros carregam
só o nome do provedor e o código HTTP).

Modelos: "provedor/modelo" (ex.: "gemini/gemini-2.0-flash"). IDs sem
prefixo continuam no Hermes (legado). Listas `modelos` abaixo são ponto
de partida honesto: com chave, tentamos `/models` ao vivo primeiro e só
caímos na curadoria se a listagem falhar (Anthropic não tem listagem —
use os IDs do console).
"""
import json
from concurrent.futures import ThreadPoolExecutor
import logging
import os
import re
import time
import urllib.error
import urllib.request

import env_local
import hermes_bridge
import tool_protocol
from hermes_bridge import BridgeErro

log = logging.getLogger("JULIA-providers")

PROVIDERS = {
    "hermes": {
        "label": "Hermes (proxy local)", "key_env": None, "api": "openai",
        "modelos": [],
    },
    "openai": {
        "label": "OpenAI", "key_env": "OPENAI_API_KEY",
        "base": "https://api.openai.com/v1", "hosts": ("api.openai.com",),
        "api": "openai",
        "modelos": ["gpt-4o-mini", "gpt-4o", "o4-mini"],
    },
    "gemini": {
        "label": "Google Gemini", "key_env": "GEMINI_API_KEY",
        "base": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "hosts": ("generativelanguage.googleapis.com",),
        "api": "openai",
        "modelos": ["gemini-2.0-flash", "gemini-2.5-flash", "gemini-2.0-flash-lite"],
    },
    "anthropic": {
        "label": "Anthropic", "key_env": "ANTHROPIC_API_KEY",
        "base": "https://api.anthropic.com/v1", "hosts": ("api.anthropic.com",),
        "api": "anthropic",
        "modelos": ["claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022"],
    },
    "deepseek": {
        "label": "DeepSeek", "key_env": "DEEPSEEK_API_KEY",
        "base": "https://api.deepseek.com/v1", "hosts": ("api.deepseek.com",),
        "api": "openai",
        "modelos": ["deepseek-chat", "deepseek-reasoner"],
    },
    "groq": {
        "label": "Groq", "key_env": "GROQ_API_KEY",
        "base": "https://api.groq.com/openai/v1", "hosts": ("api.groq.com",),
        "api": "openai",
        "modelos": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"],
    },
    "mistral": {
        "label": "Mistral", "key_env": "MISTRAL_API_KEY",
        "base": "https://api.mistral.ai/v1", "hosts": ("api.mistral.ai",),
        "api": "openai",
        "modelos": ["mistral-large-latest", "mistral-small-latest"],
    },
    "openrouter": {
        "label": "OpenRouter", "key_env": "OPENROUTER_API_KEY",
        "base": "https://openrouter.ai/api/v1", "hosts": ("openrouter.ai",),
        "api": "openai",
        "modelos": ["openai/gpt-4o-mini", "anthropic/claude-3-5-sonnet",
                    "google/gemini-2.0-flash", "deepseek/deepseek-chat"],
    },
}

ANTHROPIC_VERSION = "2023-06-01"

# Variáveis de ambiente das chaves (espelho de env_local.PROVIDER_KEY_ENVS;
# um teste garante que os dois conjuntos são idênticos).
PROVIDER_KEY_ENVS = frozenset(
    d["key_env"] for d in PROVIDERS.values() if d.get("key_env"))

# Erros de chamada DIRETA recebem a cara do provedor: nada de mensagem de
# "hermes proxy" quando o problema é a chave do OpenAI/Gemini/etc. Nenhum
# fragmento de chave aparece em mensagem ou detalhe.
_FRAGMENTO_CHAVE = re.compile(r"(?:sk|key|api)[-_][A-Za-z0-9_\-]{8,}")


def _limpar_detalhe(texto: str) -> str:
    return _FRAGMENTO_CHAVE.sub("***", str(texto or ""))[:200]


def _remapear(exc: BridgeErro, nome: str, model: str) -> BridgeErro:
    d = definicao(nome)
    if d is None or nome == "hermes":
        return exc
    env = d.get("key_env") or ""
    codigo = exc.codigo
    if codigo == "auth":
        msg = (f"{d['label']} recusou a chave (HTTP 401/403). "
               f"Atualize {env} no PC e reinicie o agente.")
    elif codigo == "modelo-nao-encontrado":
        msg = f"Modelo '{model}' não encontrado em {d['label']}."
    elif codigo == "quota":
        msg = f"{d['label']} sem cota/saldo (HTTP 402)."
    elif codigo == "rate_limit":
        msg = f"{d['label']} com limite excedido (HTTP 429). Aguarde 1–2 minutos."
    elif codigo == "pedido":
        msg = f"{d['label']} recusou o pedido (HTTP 422)."
    elif codigo == "provedor":
        msg = f"{d['label']} falhou no provedor. Tente de novo."
    elif codigo in ("indisponivel", "timeout"):
        msg = f"Sem resposta de {d['label']} (rede). Verifique a conexão do PC."
    elif codigo == "http":
        msg = f"Falha HTTP ao falar com {d['label']}."
    else:
        return exc
    return BridgeErro(msg, codigo, _limpar_detalhe(exc.detalhe))


def _chamar(fn, prov: str, model_id: str, *args, **kwargs):
    """Chamada direta + erro remapeado (mantém código/cancelamento originais)."""
    try:
        return fn(*args, **kwargs)
    except BridgeErro as exc:
        raise _remapear(exc, prov, model_id) from None


def definicao(nome: str) -> dict | None:
    return PROVIDERS.get(str(nome or "").lower())


def chave(nome: str) -> str:
    """API key do provedor ("" se ausente). Nunca logar o valor."""
    d = definicao(nome)
    if not d or not d.get("key_env"):
        return ""
    return (os.environ.get(d["key_env"], "") or "").strip()


def chave_origem(nome: str) -> str:
    """Onde a chave está definida: 'arquivo' (.env local, salva pelo app),
    'sistema' (variável do PC) ou '' (sem chave). Nunca expõe o valor."""
    d = definicao(nome)
    if not d or not d.get("key_env"):
        return ""
    atual = chave(nome)
    if not atual:
        return ""
    try:
        if env_local.valores_do_arquivo().get(d["key_env"]) == atual:
            return "arquivo"
    except Exception:
        pass
    return "sistema"


def configurados() -> list:
    """Provedores utilizáveis agora: hermes sempre + quem tem chave."""
    out = ["hermes"]
    for nome, d in PROVIDERS.items():
        if nome != "hermes" and chave(nome):
            out.append(nome)
    return out


def dividir(modelo: str) -> tuple:
    """'gemini/gemini-2.0-flash' → ('gemini', 'gemini-2.0-flash').
    Sem prefixo conhecido → ('hermes', modelo) (legado)."""
    texto = str(modelo or "")
    if "/" in texto:
        prov, resto = texto.split("/", 1)
        if prov.lower() in PROVIDERS and resto:
            return prov.lower(), resto
    return "hermes", texto


def _modelos_vivos_openai(nome: str, d: dict, timeout: float = 8.0) -> tuple:
    """(ids|None, codigo_de_erro). 'auth' significa chave recusada — o
    seletor desabilita o provedor em vez de deixar escolher o que não roda."""
    try:
        ids = hermes_bridge.listar_modelos(d["base"], timeout=timeout,
                                           api_key=chave(nome), hosts=d["hosts"])
    except BridgeErro as exc:
        log.warning("provedor %s: listagem falhou (%s)", nome, exc.codigo)
        return None, exc.codigo
    return (sorted({i for i in ids if isinstance(i, str) and i}, key=lambda mid: (not mid.endswith(":free"), mid))[:200] or None), ""


def listar_tudo(proxy_cfg: str = "") -> dict:
    """Catálogo p/ o seletor: models, default, providers (SEM chaves)."""
    # Independent network requests share a bounded pool: serial discovery could
    # exceed the relay's 30-second deadline before reaching the saved provider.
    def descobrir(nome, d):
        if nome == "hermes":
            try:
                ids = hermes_bridge.listar_modelos(proxy_cfg or hermes_bridge.DEFAULT_PROXY_URL)
                return sorted(set(ids), key=lambda mid: (not mid.endswith(":free"), mid))[:500], ""
            except BridgeErro as exc:
                log.warning("hermes listar falhou (%s)", exc.codigo)
                return [], exc.codigo
        if chave(nome) and d["api"] == "openai":
            return _modelos_vivos_openai(nome, d)
        return None, ""

    with ThreadPoolExecutor(max_workers=len(PROVIDERS)) as pool:
        pending = {nome: pool.submit(descobrir, nome, d) for nome, d in PROVIDERS.items()}
        discoveries = {nome: task.result() for nome, task in pending.items()}
    itens, provs = [], []
    for nome, d in PROVIDERS.items():
        conf = True if nome == "hermes" else bool(chave(nome))
        prov = {"id": nome, "label": d["label"], "configured": conf}
        origem = chave_origem(nome) if conf else ""
        if origem:
            prov["source"] = origem
        vivos, erro = discoveries[nome]
        auth_ruim = erro in ("auth", "sem_chave")
        if auth_ruim:
            prov["auth_error"] = True
        provs.append(prov)
        for mid in (vivos if vivos else d["modelos"]):
            itens.append({"id": mid if nome == "hermes" else f"{nome}/{mid}",
                          "provider": nome, "label": d["label"],
                          "free": mid.endswith(":free"),
                          **({"needs_key": True} if not conf else {}),
                          **({"curated": True} if not vivos else {}),
                          **({"auth_error": True} if auth_ruim else {})})
    # Up to 500 proxy models + 200 per external provider. Do not silently cut
    # off the providers at the end of the registry after only 500 total IDs.
    return {"models": [i["id"] for i in itens], "items": itens,
            "default": hermes_bridge.DEFAULT_MODEL, "providers": provs}


# ── Chamadas ──────────────────────────────────────────────────────────

def _para_openai(messages: list) -> list:
    return [{"role": m.get("role", "user"), "content": str(m.get("content", ""))[:12000]}
            for m in messages if isinstance(m, dict)]


def _para_anthropic(messages: list) -> tuple:
    sistema, resto = "", []
    for m in messages:
        if not isinstance(m, dict):
            continue
        if m.get("role") == "system" and not sistema:
            sistema = str(m.get("content", ""))[:12000]
        elif m.get("role") in ("user", "assistant"):
            resto.append({"role": m["role"], "content": str(m.get("content", ""))[:12000]})
    if not resto:
        raise BridgeErro("Sem mensagem de usuário.", "pedido")
    return sistema, resto


def chat_complete(prov: str, model_id: str, messages: list,
                  timeout: float = 60.0, max_tokens: int = 2000,
                  proxy: str = "") -> dict:
    d = definicao(prov)
    if d is None:
        raise BridgeErro(f"Provedor '{prov}' desconhecido.", "provedor")
    if prov == "hermes":
        return hermes_bridge.chat_complete(
            proxy or hermes_bridge.DEFAULT_PROXY_URL, model_id, messages,
            timeout=timeout, max_tokens=max_tokens)
    key = chave(prov)
    if not key:
        raise BridgeErro(f"Provedor {d['label']} sem chave ({d['key_env']}).",
                         "sem_chave")
    if d["api"] == "anthropic":
        return _anthropic_complete(d, key, model_id, messages, timeout, max_tokens)
    return _chamar(hermes_bridge.chat_complete, prov, model_id,
                   d["base"], model_id, _para_openai(messages),
                   timeout=timeout, max_tokens=max_tokens,
                   api_key=key, hosts=d["hosts"])


def _anthropic_complete(d: dict, key: str, model_id: str, messages: list,
                        timeout: float, max_tokens: int) -> dict:
    sistema, resto = _para_anthropic(messages)
    corpo = {"model": model_id, "max_tokens": max(1, min(int(max_tokens or 1024), 8192)),
             "messages": resto}
    if sistema:
        corpo["system"] = sistema
    url = hermes_bridge.base_publica(d["base"], d["hosts"]) + "/messages"
    req = urllib.request.Request(
        url, data=json.dumps(corpo).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-api-key": key,
                 "anthropic-version": ANTHROPIC_VERSION})
    inicio = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            dados = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise _mapear_anthropic(exc, model_id) from None
    except (OSError, TimeoutError, ValueError) as exc:
        raise BridgeErro(f"Falha ao falar com Anthropic ({type(exc).__name__}).",
                         "indisponivel") from None
    texto, erros = tool_protocol.sanitizar_texto(_extrair_anthropic(dados))
    for erro in erros:
        log.warning("TOOL_PROTOCOL %s ferramenta=%s: %s", erro.get("codigo"),
                    erro.get("ferramenta") or "?", erro.get("detalhe") or "")
    if not texto.strip():
        if erros:
            raise BridgeErro("O modelo emitiu apenas uma chamada interna de ferramenta; "
                             "nada foi executado nem exibido.", "protocolo_ferramenta")
        raise BridgeErro("Modelo devolveu resposta vazia.", "vazia")
    return {"texto": texto[:hermes_bridge.MAX_TEXTO],
            "truncada": len(texto) > hermes_bridge.MAX_TEXTO,
            "latencia_s": round(time.monotonic() - inicio, 2)}


def _mapear_anthropic(exc: urllib.error.HTTPError, model: str) -> BridgeErro:
    try:
        detalhe = exc.read().decode("utf-8", "ignore")[:200]
    except Exception:
        detalhe = ""
    if exc.code in (401, 403):
        return BridgeErro("Anthropic recusou a chave (HTTP 401/403). "
                          "Atualize ANTHROPIC_API_KEY no PC e reinicie o agente.",
                          "auth", _limpar_detalhe(detalhe))
    if exc.code == 404:
        return BridgeErro(f"Modelo '{model}' não encontrado na Anthropic.", "modelo-nao-encontrado", _limpar_detalhe(detalhe))
    if exc.code == 429:
        return BridgeErro("Anthropic com limite excedido (429). Aguarde 1–2 minutos.", "rate_limit", _limpar_detalhe(detalhe))
    if 500 <= exc.code < 600:
        return BridgeErro(f"Anthropic falhou (HTTP {exc.code}). Tente de novo.", "provedor", _limpar_detalhe(detalhe))
    return BridgeErro(f"Falha HTTP {exc.code} na Anthropic.", "http", _limpar_detalhe(detalhe))


def _extrair_anthropic(dados: dict) -> str:
    try:
        for bloco in dados.get("content", []) or []:
            if isinstance(bloco, dict) and bloco.get("type") == "text":
                return str(bloco.get("text", "") or "")
    except (AttributeError, TypeError):
        pass
    raise BridgeErro("Resposta Anthropic em formato inesperado.", "formato")


def chat_stream(prov: str, model_id: str, messages: list, on_delta,
                deve_parar=None, timeout: float = 180.0,
                max_tokens: int = 2000, proxy: str = "") -> dict:
    d = definicao(prov)
    if d is None:
        raise BridgeErro(f"Provedor '{prov}' desconhecido.", "provedor")
    if prov == "hermes":
        return hermes_bridge.chat_stream(
            proxy or hermes_bridge.DEFAULT_PROXY_URL, model_id, messages, on_delta,
            deve_parar, timeout, max_tokens)
    key = chave(prov)
    if not key:
        raise BridgeErro(f"Provedor {d['label']} sem chave ({d['key_env']}).",
                         "sem_chave")
    if d["api"] == "anthropic":
        return _anthropic_stream(d, key, model_id, messages, on_delta,
                                 deve_parar, timeout, max_tokens)
    return _chamar(hermes_bridge.chat_stream, prov, model_id,
                   d["base"], model_id, _para_openai(messages), on_delta,
                   deve_parar, timeout, max_tokens,
                   api_key=key, hosts=d["hosts"])


def _anthropic_stream(d: dict, key: str, model_id: str, messages: list, on_delta,
                      deve_parar, timeout: float, max_tokens: int) -> dict:
    sistema, resto = _para_anthropic(messages)
    corpo = {"model": model_id, "max_tokens": max(1, min(int(max_tokens or 1024), 8192)),
             "messages": resto, "stream": True}
    if sistema:
        corpo["system"] = sistema
    url = hermes_bridge.base_publica(d["base"], d["hosts"]) + "/messages"
    req = urllib.request.Request(
        url, data=json.dumps(corpo).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-api-key": key,
                 "anthropic-version": ANTHROPIC_VERSION,
                 "Accept": "text/event-stream"})
    inicio, partes, seq = time.monotonic(), [], [0]
    limpo = tool_protocol.Sanitizador()
    buf = ""
    erros_protocolo: list = []
    sanitizador_fechado = [False]

    def _emitir_seguro(txt):
        if not txt:
            return
        seq[0] += 1
        partes.append(txt)
        on_delta(seq[0], txt)

    def _fechar_sanitizador():
        if sanitizador_fechado[0]:
            return list(erros_protocolo)
        sanitizador_fechado[0] = True
        resto, erros = limpo.finalizar()
        erros_protocolo.extend(erros)
        for erro in erros:
            log.warning("TOOL_PROTOCOL %s ferramenta=%s: %s", erro.get("codigo"),
                        erro.get("ferramenta") or "?", erro.get("detalhe") or "")
        _emitir_seguro(resto)
        return list(erros_protocolo)

    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            while True:
                if deve_parar is not None and deve_parar():
                    _fechar_sanitizador()
                    return {"texto": "".join(partes)[:hermes_bridge.MAX_TEXTO],
                            "cancelada": True,
                            "latencia_s": round(time.monotonic() - inicio, 2)}
                if time.monotonic() - inicio > timeout:
                    raise BridgeErro("Timeout aguardando o modelo.", "timeout")
                try:
                    bloco = r.read1(4096)
                except TimeoutError:
                    continue
                if not bloco:
                    break
                buf += bloco.decode("utf-8", errors="ignore")
                while "\n" in buf:
                    linha, buf = buf.split("\n", 1)
                    linha = linha.strip()
                    if not linha.startswith("data:"):
                        continue
                    try:
                        ev = json.loads(linha[5:].strip())
                    except ValueError:
                        continue
                    if isinstance(ev, dict) and ev.get("type") == "content_block_delta":
                        txt = ((ev.get("delta") or {}).get("text")) or ""
                        if txt:
                            _emitir_seguro(limpo.alimentar(txt))
    except urllib.error.HTTPError as exc:
        raise _mapear_anthropic(exc, model_id) from None
    except BridgeErro:
        raise
    except (OSError, TimeoutError) as exc:
        if partes:
            _fechar_sanitizador()
            return {"texto": "".join(partes)[:hermes_bridge.MAX_TEXTO], "parcial": True,
                    "latencia_s": round(time.monotonic() - inicio, 2)}
        raise BridgeErro(f"Falha ao falar com Anthropic ({type(exc).__name__}).",
                         "indisponivel") from None
    _fechar_sanitizador()
    texto = "".join(partes)
    if not texto.strip():
        if erros_protocolo:
            raise BridgeErro("O modelo emitiu apenas uma chamada interna de ferramenta; "
                             "nada foi executado nem exibido.", "protocolo_ferramenta")
        raise BridgeErro("Modelo devolveu resposta vazia.", "vazia")
    return {"texto": texto[:hermes_bridge.MAX_TEXTO],
            "truncada": len(texto) > hermes_bridge.MAX_TEXTO,
            "latencia_s": round(time.monotonic() - inicio, 2)}


# ── Fallback entre modelos/provedores (mesma semântica do bridge) ─────

def tentar_modelos(modelos: list, messages: list, timeout_por_tentativa: float = 60.0,
                   max_tokens: int = 2000, proxy: str = "") -> dict:
    fila = [m for m in (modelos or []) if isinstance(m, str) and m][:5]
    if not fila:
        raise BridgeErro("Nenhum modelo configurado.", "sem_modelo")
    tentativas = []
    for i, modelo in enumerate(fila):
        if i:
            time.sleep(min(2 ** (i - 1), 4))
        inicio = time.monotonic()
        try:
            prov, mid = dividir(modelo)
            res = chat_complete(prov, mid, messages,
                                timeout=timeout_por_tentativa, max_tokens=max_tokens,
                                proxy=proxy)
            res["model_usado"] = modelo
            res["tentativas"] = tentativas
            return res
        except BridgeErro as exc:
            tentativas.append({"model": modelo, "codigo": exc.codigo,
                               "latencia_s": round(time.monotonic() - inicio, 2)})
            if exc.codigo in ("auth", "sem_chave"):
                # Credencial vale para todos os modelos do MESMO provedor.
                # Se ainda há candidato de OUTRO provedor, seguimos a fila.
                restantes = fila[i + 1:]
                if not any(dividir(r)[0] != dividir(modelo)[0] for r in restantes):
                    raise BridgeErro(str(exc) + " (fallback interrompido).",
                                     "auth", exc.detalhe) from None
                continue
            if len(fila) == 1:
                raise
            if i == len(fila) - 1:
                raise BridgeErro(
                    f"Nenhum modelo respondeu ({len(fila)} tentativas; "
                    f"último: {exc.codigo}).", "todos_falharam", exc.detalhe) from None
    raise BridgeErro("Nenhum modelo respondeu.", "todos_falharam")


def chat_stream_fb(modelos: list, messages: list, on_delta,
                   deve_parar=None, timeout: float = 180.0,
                   max_tokens: int = 2000, proxy: str = "") -> dict:
    fila = [m for m in (modelos or []) if isinstance(m, str) and m][:5]
    if not fila:
        raise BridgeErro("Nenhum modelo configurado.", "sem_modelo")
    tentativas = []
    for i, modelo in enumerate(fila):
        if i:
            time.sleep(min(2 ** (i - 1), 4))
        inicio = time.monotonic()
        n_deltas = [0]

        def _emit(seq, trecho, _n=n_deltas):
            _n[0] += 1
            return on_delta(seq, trecho)

        try:
            prov, mid = dividir(modelo)
            res = chat_stream(prov, mid, messages, _emit, deve_parar,
                              timeout, max_tokens, proxy=proxy)
            res["model_usado"] = modelo
            res["tentativas"] = tentativas
            return res
        except BridgeErro as exc:
            tentativas.append({"model": modelo, "codigo": exc.codigo,
                               "latencia_s": round(time.monotonic() - inicio, 2)})
            if n_deltas[0] > 0:
                raise
            if exc.codigo in ("auth", "sem_chave"):
                restantes = fila[i + 1:]
                if not any(dividir(r)[0] != dividir(modelo)[0] for r in restantes):
                    raise
                continue
            if len(fila) == 1:
                raise
            if i == len(fila) - 1:
                raise BridgeErro(
                    f"Nenhum modelo respondeu ({len(fila)} tentativas; "
                    f"último: {exc.codigo}).", "todos_falharam", exc.detalhe) from None
    raise BridgeErro("Nenhum modelo respondeu.", "todos_falharam")
