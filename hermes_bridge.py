"""Ponte OpenAI-compatible com o Hermes Subscription Proxy (Opção A).

O proxy roda no próprio PC (padrão http://127.0.0.1:8645/v1) e aceita bearer
arbitrário — ele substitui a credencial no upstream. Isso NÃO é autenticação:
por isso a URL é restrita a loopback (proteção contra SSRF) e nenhum token
real (Render/Nous) é enviado ou registrado aqui.
"""
import json
import time
import urllib.error
import urllib.parse
import urllib.request

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


def _req(url: str, corpo: dict, timeout: float):
    # Bearer arbitrário exigido pelo formato; o proxy troca pelo real.
    data = json.dumps(corpo, ensure_ascii=False).encode("utf-8")
    return urllib.request.Request(url, data=data,
                                  headers={"Content-Type": "application/json",
                                           "Authorization": "Bearer local"})


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
    if exc.code == 429:
        return BridgeErro("Provedor com limite excedido (429). Aguarde e tente de novo.",
                          "rate_limit", detalhe)
    if 500 <= exc.code < 600:
        return BridgeErro(f"Provedor falhou (HTTP {exc.code}). Tente de novo.",
                          "provedor", detalhe)
    return BridgeErro(f"Falha HTTP {exc.code}.", "http", detalhe)


def listar_modelos(base: str, timeout: float = 10.0) -> list:
    url = proxy_url(base)
    try:
        with urllib.request.urlopen(url + "/models", timeout=timeout) as r:
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
        self.resto = ""
        self.seq = 0
        self.concluido = False

    def alimentar(self, bloco: bytes) -> list:
        novos = []
        try:
            self.resto += bloco.decode("utf-8", errors="ignore")
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
                  timeout: float = 120.0, max_tokens: int = 2000) -> dict:
    url = proxy_url(base)
    inicio = time.monotonic()
    try:
        req = _req(url + "/chat/completions",
                   {"model": model, "messages": messages, "max_tokens": max_tokens},
                   timeout)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            dados = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise _mapear_http(exc, model) from None
    except (OSError, TimeoutError) as exc:
        raise BridgeErro(f"Falha ao falar com o proxy ({type(exc).__name__}).",
                         "indisponivel") from None
    except ValueError as exc:
        raise BridgeErro("Resposta do proxy em formato inesperado.", "formato") from None
    texto = extrair_texto(dados)
    if not texto.strip():
        raise BridgeErro("Modelo devolveu resposta vazia.", "vazia")
    return {"texto": texto[:MAX_TEXTO],
            "truncada": len(texto) > MAX_TEXTO,
            "latencia_s": round(time.monotonic() - inicio, 2)}


def chat_stream(base: str, model: str, messages: list, on_delta,
                deve_parar=None, timeout: float = 180.0,
                max_tokens: int = 2000) -> dict:
    """Lê SSE chamando on_delta(seq, trecho). Retorna texto final.

    `deve_parar` é um callable sem args (cancelamento cooperativo).
    """
    url = proxy_url(base)
    inicio = time.monotonic()
    req = _req(url + "/chat/completions",
               {"model": model, "messages": messages,
                "max_tokens": max_tokens, "stream": True}, timeout)
    req.add_header("Accept", "text/event-stream")
    acum = AcumuladorSSE()
    partes = []
    inicio_leitura = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            while True:
                if deve_parar is not None and deve_parar():
                    return {"texto": "".join(partes)[:MAX_TEXTO],
                            "cancelada": True,
                            "latencia_s": round(time.monotonic() - inicio, 2)}
                if time.monotonic() - inicio_leitura > timeout:
                    raise BridgeErro("Timeout aguardando o modelo.", "timeout")
                try:
                    bloco = r.read(4096)
                except TimeoutError:
                    continue
                if not bloco:
                    break
                for seq, trecho in acum.alimentar(bloco):
                    partes.append(trecho)
                    on_delta(seq, trecho)
    except urllib.error.HTTPError as exc:
        raise _mapear_http(exc, model) from None
    except BridgeErro:
        raise
    except (OSError, TimeoutError) as exc:
        if partes:
            return {"texto": "".join(partes)[:MAX_TEXTO], "parcial": True,
                    "latencia_s": round(time.monotonic() - inicio, 2)}
        raise BridgeErro(f"Falha ao falar com o proxy ({type(exc).__name__}).",
                         "indisponivel") from None
    texto = "".join(partes)
    if not texto.strip():
        raise BridgeErro("Modelo devolveu resposta vazia.", "vazia")
    return {"texto": texto[:MAX_TEXTO],
            "truncada": len(texto) > MAX_TEXTO,
            "latencia_s": round(time.monotonic() - inicio, 2)}
