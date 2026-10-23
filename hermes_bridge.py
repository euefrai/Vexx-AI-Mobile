"""Ponte OpenAI-compatible com o Hermes Subscription Proxy (Opção A).

O proxy roda no próprio PC (padrão http://127.0.0.1:8645/v1) e aceita bearer
arbitrário — ele substitui a credencial no upstream. Isso NÃO é autenticação:
por isso a URL é restrita a loopback (proteção contra SSRF) e nenhum token
real (Render/Nous) é enviado ou registrado aqui.
"""
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request

import tool_protocol

log = logging.getLogger(__name__)

DEFAULT_PROXY_URL = "http://127.0.0.1:8645/v1"
DEFAULT_MODEL = "poolside/laguna-s-2.1:free"
LOOPBACK = {"127.0.0.1", "localhost", "::1"}
MAX_TEXTO = 20000


class BridgeErro(ValueError):
    def __init__(self, mensagem, codigo="erro", detalhe=""):
        super().__init__(mensagem)
        self.codigo = codigo
        self.detalhe = detalhe[:200]


def proxy_url(valor: str = "") -> str:
    """Base do proxy, sempre terminando em /v1 (contrato: ...:8645/v1)."""
    url = (valor or DEFAULT_PROXY_URL).strip().rstrip("/")
    try:
        parte = urllib.parse.urlsplit(url)
    except ValueError as exc:
        raise BridgeErro(f"URL do proxy inválida: {exc}.", "url_invalida") from None
    if parte.scheme != "http" or not parte.netloc:
        raise BridgeErro("Proxy local usa http://host:porta.", "url_invalida")
    if (parte.hostname or "").lower() not in LOOPBACK:
        raise BridgeErro("Por segurança, o proxy precisa ser local (127.0.0.1).",
                         "url_bloqueada")
    if parte.username or parte.password:
        raise BridgeErro("URL do proxy não pode conter credenciais.", "url_invalida")
    if not parte.path.rstrip("/").endswith("/v1"):
        raise BridgeErro("URL do proxy deve terminar em /v1.", "url_invalida")
    return url


def _req(url: str, corpo: dict, timeout: float, api_key: str = "",
         extras: dict | None = None):
    # Sem chave (proxy local): bearer arbitrário — o proxy troca pelo real.
    headers = {"Content-Type": "application/json",
               "Authorization": ("Bearer " + api_key) if api_key else "Bearer local"}
    if extras:
        headers.update(extras)
    data = json.dumps(corpo, ensure_ascii=False).encode("utf-8")
    return urllib.request.Request(url, data=data, headers=headers)


def base_publica(url: str, hosts: tuple) -> str:
    """Base HTTPS de provedor direto. Só hosts da allowlist do provedor;
    https obrigatório; sem credenciais, query ou fragmento."""
    base = (url or "").strip().rstrip("/")
    try:
        parte = urllib.parse.urlsplit(base)
    except ValueError as exc:
        raise BridgeErro(f"URL do provedor inválida: {exc}.", "url_invalida") from None
    if parte.scheme != "https" or not parte.hostname:
        raise BridgeErro("Provedor direto exige https://host.", "url_invalida")
    if parte.hostname.lower() not in tuple(h.lower() for h in hosts):
        raise BridgeErro(f"Host '{parte.hostname}' fora da lista do provedor.",
                         "url_bloqueada")
    if parte.username or parte.password or parte.query or parte.fragment:
        raise BridgeErro("URL do provedor não aceita credenciais/parâmetros.",
                         "url_invalida")
    return base


def _base(base: str, api_key: str = "", hosts: tuple = ()) -> str:
    if api_key:
        return base_publica(base, hosts)
    return proxy_url(base)


def _mapear_http(exc: urllib.error.HTTPError, model: str) -> BridgeErro:
    try:
        detalhe = exc.read().decode("utf-8", "ignore")[:200]
    except Exception:
        detalhe = ""
    if exc.code in (401, 403):
        return BridgeErro("Proxy recusou a chamada (401/403). Verifique 'hermes proxy status'.",
                          "auth", detalhe)
    if exc.code in (404, 410):
        return BridgeErro(f"Modelo '{model}' não encontrado no proxy. Liste /v1/models e troque.",
                          "modelo-nao-encontrado", detalhe)
    if exc.code == 402:
        return BridgeErro("Cota da assinatura esgotada (402). Verifique 'hermes proxy status'.",
                          "quota", detalhe)
    if exc.code == 422:
        return BridgeErro("Pedido rejeitado pelo provedor (422: parâmetros ou contexto).",
                          "pedido", detalhe)
    if exc.code == 429:
        return BridgeErro("Provedor com limite excedido (429). Aguarde e tente de novo.",
                          "rate_limit", detalhe)
    if 500 <= exc.code < 600:
        return BridgeErro(f"Provedor falhou (HTTP {exc.code}). Tente de novo.",
                          "provedor", detalhe)
    return BridgeErro(f"Falha HTTP {exc.code}.", "http", detalhe)


def listar_modelos(base: str, timeout: float = 10.0, api_key: str = "",
                   hosts: tuple = ()) -> list:
    url = _base(base, api_key, hosts)
    req = urllib.request.Request(
        url + "/models",
        headers={"Authorization": ("Bearer " + api_key) if api_key else "Bearer local"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            dados = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise _mapear_http(exc, "") from None
    except (OSError, TimeoutError, ValueError) as exc:
        raise BridgeErro(f"Proxy inacessível em {url} ({type(exc).__name__}). "
                         "Rode 'hermes proxy start'.", "indisponivel") from None
    if not isinstance(dados, dict) or not isinstance(dados.get("data"), list):
        raise BridgeErro("Resposta /v1/models em formato inesperado.", "formato")
    ids = [m.get("id") for m in dados["data"]
           if isinstance(m, dict) and isinstance(m.get("id"), str)]
    if not ids:
        raise BridgeErro("Proxy não listou nenhum modelo.", "vazio")
    return ids


def extrair_texto(dados: dict) -> str:
    try:
        return str(dados["choices"][0]["message"]["content"] or "")
    except (KeyError, IndexError, TypeError, AttributeError):
        raise BridgeErro("Resposta do modelo em formato inesperado.", "formato") from None


def extrair_delta(dados: dict) -> str:
    try:
        escolhas = dados.get("choices") or []
        if escolhas and isinstance(escolhas[0], dict):
            delta = escolhas[0].get("delta") or {}
            if isinstance(delta, dict) and delta.get("content"):
                return str(delta["content"])
    except (AttributeError, TypeError, IndexError):
        pass
    return ""


class AcumuladorSSE:
    """Reconstrói deltas de um stream SSE, tolerando eventos fragmentados."""

    def __init__(self):
        import codecs
        self.decoder = codecs.getincrementaldecoder('utf-8')(errors='replace')
        self.resto = ""
        self.seq = 0
        self.concluido = False

    def alimentar(self, bloco: bytes) -> list:
        novos = []
        try:
            self.resto += self.decoder.decode(bloco)
        except Exception:
            return novos
        while "\n" in self.resto:
            linha, self.resto = self.resto.split("\n", 1)
            linha = linha.strip()
            if not linha or linha.startswith(":"):
                continue  # keepalive/comentário
            if not linha.startswith("data:"):
                continue
            carga = linha[5:].strip()
            if carga == "[DONE]":
                self.concluido = True
                continue
            try:
                dados = json.loads(carga)
            except ValueError:
                continue
            trecho = extrair_delta(dados)
            if trecho:
                self.seq += 1
                novos.append((self.seq, trecho))
        return novos


def chat_complete(base: str, model: str, messages: list,
                  timeout: float = 120.0, max_tokens: int = 2000,
                  api_key: str = "", hosts: tuple = ()) -> dict:
    url = _base(base, api_key, hosts)
    inicio = time.monotonic()
    try:
        req = _req(url + "/chat/completions",
                   {"model": model, "messages": messages, "max_tokens": max_tokens},
                   timeout, api_key)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            dados = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise _mapear_http(exc, model) from None
    except (OSError, TimeoutError) as exc:
        raise BridgeErro(f"Falha ao falar com o proxy ({type(exc).__name__}).",
                         "timeout" if isinstance(exc, TimeoutError) or
                         (isinstance(exc, urllib.error.URLError) and isinstance(exc.reason, TimeoutError))
                         else "indisponivel") from None
    except ValueError as exc:
        raise BridgeErro("Resposta do proxy em formato inesperado.", "formato") from None
    texto, erros = tool_protocol.sanitizar_texto(extrair_texto(dados))
    for erro in erros:
        log.warning("TOOL_PROTOCOL %s ferramenta=%s: %s", erro.get("codigo"),
                    erro.get("ferramenta") or "?", erro.get("detalhe") or "")
    if not texto.strip():
        if erros:
            raise BridgeErro("O modelo emitiu apenas uma chamada interna de ferramenta; "
                             "nada foi executado nem exibido.", "protocolo_ferramenta")
        raise BridgeErro("Modelo devolveu resposta vazia.", "vazia")
    return {"texto": texto[:MAX_TEXTO],
            "truncada": len(texto) > MAX_TEXTO,
            "latencia_s": round(time.monotonic() - inicio, 2)}


def chat_stream(base: str, model: str, messages: list, on_delta,
                deve_parar=None, timeout: float = 180.0,
                max_tokens: int = 2000, api_key: str = "",
                hosts: tuple = ()) -> dict:
    """Lê SSE chamando on_delta(seq, trecho). Retorna texto final.

    `deve_parar` é um callable sem args (cancelamento cooperativo).
    """
    url = _base(base, api_key, hosts)
    inicio = time.monotonic()
    req = _req(url + "/chat/completions",
               {"model": model, "messages": messages,
                "max_tokens": max_tokens, "stream": True}, timeout, api_key)
    req.add_header("Accept", "text/event-stream")
    acum = AcumuladorSSE()
    limpo = tool_protocol.Sanitizador()
    partes = []
    seq_envio = [0]
    erros_protocolo: list = []
    sanitizador_fechado = [False]

    def _emitir_seguro(trecho):
        if not trecho:
            return
        seq_envio[0] += 1
        partes.append(trecho)
        on_delta(seq_envio[0], trecho)

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

    inicio_leitura = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            while True:
                if deve_parar is not None and deve_parar():
                    _fechar_sanitizador()
                    return {"texto": "".join(partes)[:MAX_TEXTO],
                            "cancelada": True,
                            "latencia_s": round(time.monotonic() - inicio, 2)}
                if time.monotonic() - inicio_leitura > timeout:
                    raise BridgeErro("Timeout aguardando o modelo.", "timeout")
                try:
                    bloco = r.read1(4096)
                except TimeoutError:
                    continue
                if not bloco:
                    break
                for _seq, trecho in acum.alimentar(bloco):
                    _emitir_seguro(limpo.alimentar(trecho))
    except urllib.error.HTTPError as exc:
        raise _mapear_http(exc, model) from None
    except BridgeErro:
        raise
    except (OSError, TimeoutError) as exc:
        if partes:
            _fechar_sanitizador()
            return {"texto": "".join(partes)[:MAX_TEXTO], "parcial": True,
                    "latencia_s": round(time.monotonic() - inicio, 2)}
        raise BridgeErro(f"Falha ao falar com o proxy ({type(exc).__name__}).",
                         "indisponivel") from None
    _fechar_sanitizador()
    texto = "".join(partes)
    if not texto.strip():
        if erros_protocolo:
            raise BridgeErro("O modelo emitiu apenas uma chamada interna de ferramenta; "
                             "nada foi executado nem exibido.", "protocolo_ferramenta")
        raise BridgeErro("Modelo devolveu resposta vazia.", "vazia")
    return {"texto": texto[:MAX_TEXTO],
            "truncada": len(texto) > MAX_TEXTO,
            "parcial": not acum.concluido,
            "latencia_s": round(time.monotonic() - inicio, 2)}


# ── Fallback inteligente + circuit breaker (V4.3.1 FASE 3) ──────────
# Lista PEQUENA e explícita (nunca varre centenas de modelos). Chamadas LLM
# são só leitura: repetir em outro modelo não duplica ação externa.
MAX_TENTATIVAS_MODELO = 5
_CIRCUITO = {}  # base -> {"falhas": int, "aberto_ate": float}
_CIRCUITO_FALHAS = 4
_CIRCUITO_PAUSA = 120.0


def _circuito_aberto(base: str) -> bool:
    est = _CIRCUITO.get(base)
    if not est:
        return False
    ate = est.get("aberto_ate", 0.0)
    if not ate:
        return False  # nunca abriu: mantém a contagem de falhas
    if time.monotonic() >= ate:
        _CIRCUITO.pop(base, None)
        return False
    return True


def _circuito_registrar(base: str, ok: bool) -> None:
    if ok:
        _CIRCUITO.pop(base, None)
        return
    est = _CIRCUITO.get(base, {"falhas": 0, "aberto_ate": 0.0})
    est["falhas"] += 1
    if est["falhas"] >= _CIRCUITO_FALHAS:
        est["aberto_ate"] = time.monotonic() + _CIRCUITO_PAUSA
    _CIRCUITO[base] = est


def tentar_modelos(base: str, modelos: list, messages: list,
                   timeout_por_tentativa: float = 60.0,
                   max_tokens: int = 2000) -> dict:
    """Tenta modelos em ordem até a primeira resposta não vazia.

    Para em `auth` (credencial vale para todos). Backoff 1s/2s/4s entre
    tentativas (sem martelar). Contexto (messages) idêntico em todas.
    """
    fila = [m for m in (modelos or []) if isinstance(m, str) and m][:MAX_TENTATIVAS_MODELO]
    if not fila:
        raise BridgeErro("Nenhum modelo configurado.", "sem_modelo")
    if _circuito_aberto(base):
        raise BridgeErro("Provedor em pausa após falhas repetidas. Tente em 2 minutos.",
                         "circuito_aberto")
    tentativas = []
    for i, modelo in enumerate(fila):
        if i:
            time.sleep(min(2 ** (i - 1), 4))
        inicio = time.monotonic()
        try:
            res = chat_complete(base, modelo, messages,
                                timeout=timeout_por_tentativa, max_tokens=max_tokens)
            _circuito_registrar(base, True)
            res["model_usado"] = modelo
            res["tentativas"] = tentativas
            return res
        except BridgeErro as exc:
            tentativas.append({"model": modelo, "codigo": exc.codigo,
                               "latencia_s": round(time.monotonic() - inicio, 2)})
            _circuito_registrar(base, False)
            if exc.codigo == "auth":
                raise BridgeErro(str(exc) + " (fallback interrompido: vale para todos).",
                                 "auth", exc.detalhe) from None
            if len(fila) == 1:
                raise  # modelo único: erro original transparente (sem reembalar)
            if i == len(fila) - 1:
                raise BridgeErro(
                    f"Nenhum modelo respondeu ({len(fila)} tentativas; "
                    f"último: {exc.codigo}). " + _conselho_final(tentativas),
                    "todos_falharam", exc.detalhe) from None
    raise BridgeErro("Nenhum modelo respondeu.", "todos_falharam")


def _conselho_final(tentativas: list) -> str:
    codigos = {t.get("codigo") for t in tentativas}
    if "quota" in codigos:
        return "Verifique a cota em 'hermes proxy status'."
    if "rate_limit" in codigos:
        return "Aguarde 1–2 minutos antes de tentar."
    if codigos <= {"modelo-nao-encontrado"}:
        return "Liste /v1/models e ajuste JULIA_AI_MODEL/JULIA_AI_FALLBACKS."
    if "vazia" in codigos:
        return "O provedor respondeu vazio; tente outro modelo ou mais tarde."
    return "Verifique 'hermes proxy status' e a rede."


def chat_stream_fb(base: str, modelos: list, messages: list, on_delta,
                   deve_parar=None, timeout: float = 180.0,
                   max_tokens: int = 2000) -> dict:
    """Stream com fallback SÓ antes do primeiro delta.

    Depois do primeiro trecho, erro propaga (trocar de modelo no meio
    duplicaria/embaralharia a resposta). Mesma reply_id em todas.
    """
    fila = [m for m in (modelos or []) if isinstance(m, str) and m][:MAX_TENTATIVAS_MODELO]
    if not fila:
        raise BridgeErro("Nenhum modelo configurado.", "sem_modelo")
    if _circuito_aberto(base):
        raise BridgeErro("Provedor em pausa após falhas repetidas. Tente em 2 minutos.",
                         "circuito_aberto")
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
            res = chat_stream(base, modelo, messages, _emit, deve_parar,
                              timeout, max_tokens)
            _circuito_registrar(base, True)
            res["model_usado"] = modelo
            res["tentativas"] = tentativas
            return res
        except BridgeErro as exc:
            tentativas.append({"model": modelo, "codigo": exc.codigo,
                               "latencia_s": round(time.monotonic() - inicio, 2)})
            _circuito_registrar(base, False)
            if n_deltas[0] > 0 or exc.codigo == "auth":
                raise  # meio do stream ou auth: sem troca silenciosa
            if len(fila) == 1:
                raise  # modelo único: erro original transparente
            if i == len(fila) - 1:
                raise BridgeErro(
                    f"Nenhum modelo respondeu ({len(fila)} tentativas; "
                    f"último: {exc.codigo}). " + _conselho_final(tentativas),
                    "todos_falharam", exc.detalhe) from None
    raise BridgeErro("Nenhum modelo respondeu.", "todos_falharam")
