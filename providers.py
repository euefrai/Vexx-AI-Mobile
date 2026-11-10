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
import hashlib
from concurrent.futures import ThreadPoolExecutor
import logging
import os
import re
import time
import threading
import urllib.error
import urllib.request

import env_local
import hermes_bridge
import tool_protocol
from hermes_bridge import BridgeErro

log = logging.getLogger("JULIA-providers")

_CATALOGS = {}
_CATALOG_LOCK = threading.Lock()
CATALOG_TTL = 300


def supports_chat(model_id, metadata=None):
    """Declared capability first; conservative exclusion when metadata is absent."""
    if model_id in ("vexx-qwen-2.5-3b", "qwen2.5-3b-instruct", "qwen2.5-1.5b-instruct"):
        return True
    meta = metadata if isinstance(metadata, dict) else {}
    capabilities = meta.get('capabilities')
    if isinstance(capabilities, dict):
        for key in ('chat', 'text_generation'):
            if type(capabilities.get(key)) is bool:
                return capabilities[key]
    methods = meta.get('supportedGenerationMethods')
    if isinstance(methods, list) and methods:
        return any(m in ('generateContent', 'streamGenerateContent', 'chat', 'completions') for m in methods)
    outputs = meta.get('output_modalities')
    if isinstance(outputs, list) and outputs:
        return 'text' in [str(v).lower() for v in outputs]
    kind = str(meta.get('type') or '').lower()
    if kind in ('embedding', 'rerank', 'audio', 'image', 'speech'):
        return False
    return not re.search(r'(?:^|[/_.:-])(?:embeddings?|rerank\w*|whisper\w*|tts|'
                         r'transcrib\w*|speech|audio|realtime|live|lyria\w*|aqa|'
                         r'sentence-transformers|gte|image)(?:$|[/_.:-])', str(model_id).lower())


def _catalog_key(provider, proxy=''):
    # Configuration changes invalidate cached availability without retaining keys.
    credential = chave(provider) if provider != 'hermes' else ''
    return provider, hashlib.sha256((proxy + '\0' + credential).encode()).digest()


def _remember_catalog(provider, ids, proxy=''):
    with _CATALOG_LOCK:
        # At most one current configuration per provider; no bodies or prompts.
        _CATALOGS[provider] = (_catalog_key(provider, proxy), time.monotonic(), frozenset(ids))


def selection_error(model, proxy=''):
    """No network on the message path; reject only known unavailable selections."""
    if model in ("vexx-qwen-2.5-3b", "vexx/vexx-qwen-2.5-3b", "qwen2.5-3b-instruct",
                 "qwen2.5-1.5b-instruct", "qwen_local/qwen2.5-1.5b-instruct",
                 "local/qwen2.5-1.5b-instruct"):
        return None
    provider, mid = dividir(model)
    unavailable = not supports_chat(mid)
    with _CATALOG_LOCK:
        row = _CATALOGS.get(provider)
        if row and row[0] == _catalog_key(provider, proxy if provider == 'hermes' else '') \
                and time.monotonic() - row[1] < CATALOG_TTL:
            # The accepted catalog already applied declared capabilities. A
            # text-capable multimodal model may legitimately contain "audio".
            unavailable = mid not in row[2]
    if unavailable:
        return {'codigo': 'modelo_indisponivel', 'error':
                'O modelo selecionado não está disponível para chat. Abra Provedores de IA e escolha outro modelo.'}
    return None


def cached_default(proxy, fallback):
    """Resolve an implicit default from a fresh free catalog without new I/O."""
    with _CATALOG_LOCK:
        row = _CATALOGS.get('hermes')
        if (row and row[0] == _catalog_key('hermes', proxy)
                and time.monotonic() - row[1] < CATALOG_TTL and fallback not in row[2]):
            return next(iter(sorted(i for i in row[2] if i.endswith(':free'))), fallback)
    return fallback

PROVIDERS = {
    "vexx": {
        "label": "⚡ VEXX Qwen 2.5 3B (Modelo Principal VEXX AI)",
        "key_env": None, "api": "vexx_qwen",
        "modelos": ["vexx-qwen-2.5-3b"],
    },
    "qwen_local": {
        "label": "🖥️ Qwen 2.5 (Local PC)",
        "key_env": None,
        "base": "http://127.0.0.1:8008/v1",
        "hosts": ("127.0.0.1", "localhost"),
        "api": "openai",
        "modelos": ["qwen2.5-vl-7b-instruct", "qwen2.5-1.5b-instruct", "qwen2.5-3b-instruct"],
        "api_key": "sk-local",
    },
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
    if nome == "qwen_local":
        return "sk-local"
    d = definicao(nome)
    if not d or not d.get("key_env"):
        return ""
    val = (os.environ.get(d["key_env"], "") or "").strip()
    if not val:
        try:
            import env_local
            val = (env_local.valores_do_arquivo().get(d["key_env"], "") or "").strip()
            if val:
                os.environ[d["key_env"]] = val
        except Exception:
            pass
    return val


def chave_origem(nome: str) -> str:
    """Onde a chave está definida: 'arquivo' (.env local, salva pelo app),
    'sistema' (variável do PC) ou '' (sem chave). Nunca expõe o valor."""
    if nome == "qwen_local":
        return "local_pc"
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
    """Provedores utilizáveis agora: qwen_local, vexx e hermes sempre + quem tem chave."""
    out = ["qwen_local", "vexx", "hermes"]
    for nome, d in PROVIDERS.items():
        if nome not in ("qwen_local", "vexx", "hermes") and chave(nome):
            out.append(nome)
    return out


def dividir(modelo: str) -> tuple:
    """'gemini/gemini-2.0-flash' → ('gemini', 'gemini-2.0-flash').
    Sem prefixo conhecido → ('hermes', modelo) (legado)."""
    texto = str(modelo or "").strip()
    if texto in ("qwen2.5-vl-7b-instruct", "qwen2.5-vl-7b", "qwen2.5-1.5b-instruct", "qwen_local/qwen2.5-1.5b-instruct", "local/qwen2.5-1.5b-instruct") or texto.startswith(("qwen_local/", "local/")):
        resto = texto.split("/", 1)[1] if "/" in texto else texto
        return "qwen_local", resto or "qwen2.5-vl-7b-instruct"
    if texto in ("vexx-qwen-2.5-3b", "vexx/vexx-qwen-2.5-3b", "qwen2.5-3b-instruct", "qwen_local/qwen2.5-3b-instruct") or texto.startswith("vexx/"):
        return "vexx", "vexx-qwen-2.5-3b"
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
    metadata = getattr(ids, 'metadata', {})
    filtered = sorted({i for i in ids if isinstance(i, str) and i
                       and supports_chat(i, metadata.get(i))}, key=lambda mid: (not mid.endswith(':free'), mid))
    _remember_catalog(nome, filtered)
    return hermes_bridge.ModelCatalog([{'id': i, **metadata.get(i, {})} for i in filtered[:200]]), ''


def listar_tudo(proxy_cfg: str = "") -> dict:
    """Catálogo p/ o seletor: models, default, providers (SEM chaves)."""
    # Independent network requests share a bounded pool: serial discovery could
    # exceed the relay's 30-second deadline before reaching the saved provider.
    def descobrir(nome, d):
        if nome == "hermes":
            try:
                ids = hermes_bridge.listar_modelos(proxy_cfg or hermes_bridge.DEFAULT_PROXY_URL)
                metadata = getattr(ids, 'metadata', {})
                filtered = sorted({i for i in ids if isinstance(i, str) and i
                    and supports_chat(i, metadata.get(i))}, key=lambda mid: (not mid.endswith(':free'), mid))
                _remember_catalog(nome, filtered, proxy_cfg or hermes_bridge.DEFAULT_PROXY_URL)
                return hermes_bridge.ModelCatalog([{'id': i, **metadata.get(i, {})} for i in filtered[:500]]), ''
            except BridgeErro as exc:
                log.warning("hermes listar falhou (%s)", exc.codigo)
                return [], exc.codigo
        if chave(nome) and d["api"] == "openai":
            return _modelos_vivos_openai(nome, d)
        return None, ""

    with ThreadPoolExecutor(max_workers=len(PROVIDERS)) as pool:
        pending = {nome: pool.submit(descobrir, nome, d) for nome, d in PROVIDERS.items()}
        discoveries = {nome: task.result() for nome, task in pending.items()}
    vexx_item = {
        "id": "vexx-qwen-2.5-3b",
        "provider": "vexx",
        "label": "⚡ VEXX Qwen 2.5 3B (Modelo 3)",
        "free": True,
    }
    local_item = {
        "id": "qwen2.5-1.5b-instruct",
        "provider": "qwen_local",
        "label": "🖥️ Qwen 2.5 1.5B Instruct (Modelo 1.5 - Local PC)",
        "free": True,
    }
    vexx_provider = {
        "id": "vexx",
        "label": "⚡ VEXX Qwen 2.5 3B (Modelo 3)",
        "configured": True,
        "source": "hf_space"
    }
    local_provider = {
        "id": "qwen_local",
        "label": "🖥️ Qwen 2.5 1.5B (Modelo 1.5 - Local PC)",
        "configured": True,
        "source": "local_pc"
    }
    itens = [
        vexx_item,
        local_item
    ]
    provs = [
        vexx_provider,
        local_provider
    ]
    for nome, d in PROVIDERS.items():
        if nome in ("qwen_local", "vexx"):
            continue
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
        for mid in (vivos if vivos is not None else d["modelos"]):
            if not supports_chat(mid, getattr(vivos, 'metadata', {}).get(mid)):
                continue
            itens.append({"id": mid if nome == "hermes" else f"{nome}/{mid}",
                          "provider": nome, "label": d["label"],
                          "free": mid.endswith(":free"),
                          **({"needs_key": True} if not conf else {}),
                          **({"curated": True} if not vivos else {}),
                          **({"auth_error": True} if auth_ruim else {})})
    # Up to 500 proxy models + 200 per external provider. Do not silently cut
    # off the providers at the end of the registry after only 500 total IDs.
    default = "vexx-qwen-2.5-3b"
    return {"models": [i["id"] for i in itens], "items": itens,
            "default": default, "providers": provs}


# ── Chamadas ──────────────────────────────────────────────────────────

def _podar_contexto_local(messages: list, max_chars: int = 6000) -> list:
    """Para modelos locais (Qwen 1.5B com contexto de 2048/4096), preserva a
    instrução de sistema e mantém apenas as mensagens mais recentes para evitar
    estouro de contexto e garantir TTFT sub-segundo."""
    if not messages:
        return []
    sistema = [m for m in messages if isinstance(m, dict) and m.get("role") == "system"][:1]
    historico = [m for m in messages if isinstance(m, dict) and m.get("role") != "system"]
    total = sum(len(str(m.get("content", ""))) for m in sistema)
    podado = []
    for m in reversed(historico):
        tamanho = len(str(m.get("content", "")))
        if total + tamanho > max_chars and podado:
            break
        podado.append(m)
        total += tamanho
    podado.reverse()
    return sistema + podado


def _para_openai(messages: list) -> list:
    # Do not cut JSON evidence or instructions mid-message. Bound the request
    # explicitly, before transport, so oversized input fails without corruption.
    result, total = [], 0
    for m in messages:
        if not isinstance(m, dict):
            continue
        content = str(m.get("content", ""))
        total += len(content)
        if len(content) > 64000 or total > 128000 or len(result) >= 64:
            raise BridgeErro("Contexto excede o limite de envio ao provedor.", "pedido")
        result.append({"role": m.get("role", "user"), "content": content})
    return result


def _para_anthropic(messages: list) -> tuple:
    sistema, resto = "", []
    for m in _para_openai(messages):
        if m.get("role") == "system" and not sistema:
            sistema = m["content"]
        elif m.get("role") in ("user", "assistant"):
            resto.append(m)
    if not resto:
        raise BridgeErro("Sem mensagem de usuário.", "pedido")
    return sistema, resto


def chat_complete(prov: str, model_id: str, messages: list,
                  timeout: float = 60.0, max_tokens: int = 2000,
                  proxy: str = "") -> dict:
    d = definicao(prov)
    if d is None:
        raise BridgeErro(f"Provedor '{prov}' desconhecido.", "provedor")
    if prov == "qwen_local":
        messages = _podar_contexto_local(messages, max_chars=6000)
    if prov == "vexx" or model_id in ("vexx-qwen-2.5-3b", "qwen2.5-3b-instruct"):
        import qwen_llm_service
        inicio = time.monotonic()
        res = qwen_llm_service.gerar_resposta_qwen(messages, max_tokens=max_tokens, timeout=timeout)
        texto = (res.get("resposta") or "").strip()
        if not texto:
            raise BridgeErro("Qwen Space em hibernação ou indisponível.", "indisponivel")
        return {
            "texto": texto[:hermes_bridge.MAX_TEXTO],
            "truncada": len(texto) > hermes_bridge.MAX_TEXTO,
            "latencia_s": round(time.monotonic() - inicio, 2),
            "tool_calls": res.get("tool_calls", []),
            "queries_pesquisa": res.get("queries_pesquisa", [])
        }
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
    if prov == "qwen_local":
        try:
            return _chamar(hermes_bridge.chat_complete, prov, model_id,
                           d["base"], model_id, _para_openai(messages),
                           timeout=min(timeout, 3.0), max_tokens=max_tokens,
                           api_key=key, hosts=d["hosts"])
        except BridgeErro as exc:
            log.warning("Qwen local 1.5B (porta 8008) indisponível (%s). Alternando para VEXX Qwen 2.5 3B...", exc)
            return chat_complete("vexx", "vexx-qwen-2.5-3b", messages, timeout=timeout, max_tokens=max_tokens, proxy=proxy)
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
    if prov == "qwen_local":
        messages = _podar_contexto_local(messages, max_chars=6000)
    if prov == "vexx" or model_id in ("vexx-qwen-2.5-3b", "qwen2.5-3b-instruct"):
        import qwen_llm_service
        inicio = time.monotonic()
        res = qwen_llm_service.gerar_resposta_qwen(messages, max_tokens=max_tokens, timeout=timeout)
        texto = (res.get("resposta") or "").strip()
        if not texto:
            raise BridgeErro("Qwen Space em hibernação ou indisponível.", "indisponivel")
        chunks = 1
        if callable(on_delta):
            palavras = re.findall(r'\S+|\s+', texto)
            seq = 0
            for pedaco in palavras:
                seq += 1
                try:
                    on_delta(seq, pedaco)
                except TypeError:
                    on_delta(pedaco)
                if len(palavras) > 1 and len(pedaco.strip()) > 0:
                    time.sleep(0.010)
            chunks = seq
        return {
            "texto": texto[:hermes_bridge.MAX_TEXTO],
            "truncada": len(texto) > hermes_bridge.MAX_TEXTO,
            "latencia_s": round(time.monotonic() - inicio, 2),
            "chunks": chunks
        }
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
    if prov == "qwen_local":
        try:
            return _chamar(hermes_bridge.chat_stream, prov, model_id,
                           d["base"], model_id, _para_openai(messages), on_delta,
                           deve_parar, timeout=min(timeout, 3.0), max_tokens=max_tokens,
                           api_key=key, hosts=d["hosts"])
        except BridgeErro as exc:
            log.warning("Qwen local 1.5B (porta 8008) indisponível (%s). Alternando para VEXX Qwen 2.5 3B...", exc)
            return chat_stream("vexx", "vexx-qwen-2.5-3b", messages, on_delta,
                               deve_parar, timeout=timeout, max_tokens=max_tokens, proxy=proxy)
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
            time.sleep(0.3)
        inicio = time.monotonic()
        try:
            prov, mid = dividir(modelo)
            res = chat_complete(prov, mid, messages,
                                timeout=timeout_por_tentativa, max_tokens=max_tokens,
                                proxy=proxy)
            res["model_usado"] = modelo
            res["fallback_usado"] = (i > 0)
            res["tentativas"] = tentativas
            return res
        except BridgeErro as exc:
            tentativas.append({"model": modelo, "codigo": exc.codigo,
                               "latencia_s": round(time.monotonic() - inicio, 2)})
            try:
                from pc_modules.db_core import registrar_cooldown_modelo
                registrar_cooldown_modelo(modelo, 180.0)
            except Exception:
                pass
            log.warning("MODEL_FAILOVER modelo=%s falhou com codigo=%s. Tentando próximo modelo...",
                        modelo, exc.codigo)
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
                codigos = {t.get("codigo") for t in tentativas if t.get("codigo")}
                codigo_final = exc.codigo if len(codigos) == 1 else "todos_falharam"
                raise BridgeErro(
                    f"Nenhum modelo respondeu ({len(fila)} tentativas; "
                    f"último: {exc.codigo}).", codigo_final, exc.detalhe) from None
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
            time.sleep(0.3)
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
            res["fallback_usado"] = (i > 0)
            res["tentativas"] = tentativas
            return res
        except BridgeErro as exc:
            tentativas.append({"model": modelo, "codigo": exc.codigo,
                               "latencia_s": round(time.monotonic() - inicio, 2)})
            if n_deltas[0] > 0:
                raise
            try:
                from pc_modules.db_core import registrar_cooldown_modelo
                registrar_cooldown_modelo(modelo, 180.0)
            except Exception:
                pass
            log.warning("MODEL_FAILOVER stream modelo=%s falhou com codigo=%s. Tentando próximo da fila...",
                        modelo, exc.codigo)
            if exc.codigo in ("auth", "sem_chave"):
                restantes = fila[i + 1:]
                if not any(dividir(r)[0] != dividir(modelo)[0] for r in restantes):
                    raise
                continue
            if len(fila) == 1:
                raise
            if i == len(fila) - 1:
                codigos = {t.get("codigo") for t in tentativas if t.get("codigo")}
                codigo_final = exc.codigo if len(codigos) == 1 else "todos_falharam"
                raise BridgeErro(
                    f"Nenhum modelo respondeu ({len(fila)} tentativas; "
                    f"último: {exc.codigo}).", codigo_final, exc.detalhe) from None
    raise BridgeErro("Nenhum modelo respondeu.", "todos_falharam")

def testar_latencia_ai(model_id: str = "qwen2.5-1.5b-instruct") -> dict:
    """Executa medição de latência do modelo local (TTFT, completion e tokens/s)."""
    endpoint_url = "http://127.0.0.1:8008/v1/models"
    req_check = urllib.request.Request(endpoint_url, headers={"Authorization": "Bearer sk-local"})
    try:
        with urllib.request.urlopen(req_check, timeout=1.5) as r:
            if r.status != 200:
                return {"status": "erro", "local_online": False, "mensagem": f"HTTP {r.status} na porta 8008"}
    except Exception as exc:
        return {
            "status": "erro",
            "local_online": False,
            "mensagem": f"Servidor local na porta 8008 inacessível: {exc}"
        }

    prompt_teste = [{"role": "user", "content": "Diga olá em uma frase curta."}]
    primeiro_delta = [None]
    t0 = time.perf_counter()

    def _on_delta(seq, txt):
        if primeiro_delta[0] is None:
            primeiro_delta[0] = time.perf_counter()

    try:
        res_stream = chat_stream("qwen_local", model_id, prompt_teste, _on_delta, max_tokens=25, timeout=10.0)
        t_fim = time.perf_counter()
        ttft_ms = round(((primeiro_delta[0] - t0) * 1000), 1) if primeiro_delta[0] else round((t_fim - t0) * 1000, 1)
        duracao_total_ms = round((t_fim - t0) * 1000, 1)
        texto = res_stream.get("texto", "").strip()
        num_palavras = len(texto.split())
        tps = round(num_palavras / (duracao_total_ms / 1000.0), 1) if duracao_total_ms > 0 else 0.0

        return {
            "status": "sucesso",
            "local_online": True,
            "modelo": model_id,
            "ttft_ms": ttft_ms,
            "duracao_ms": duracao_total_ms,
            "tokens_aprox": num_palavras,
            "tokens_per_sec": tps,
            "exemplo": texto,
            "motor": "Local PC (Porta 8008)",
        }
    except Exception as exc:
        return {
            "status": "erro",
            "local_online": True,
            "mensagem": f"Erro durante geração de teste: {exc}"
        }

