"""Free, documented public APIs used as optional discovery providers.

Every adapter here is additive: a missing key, quota error, malformed payload
or timeout becomes a provider error and the existing search fallback continues.
No CAPTCHA, bot-wall or undocumented store endpoint is bypassed.

Keyless providers: OpenAlex, arXiv, GitHub (optional token raises limits),
BrasilAPI (CEP/CNPJ), CoinGecko.  Brave Search is optional and is advertised
only when ``BRAVE_SEARCH_API_KEY`` is configured.
"""
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

UA = "VexxAI/1.0 (+https://vexx-ai.space; research)"
MAX_BYTES = 1024 * 1024
MAX_REDIRECTS = 3
OPENALEX_URL = "https://api.openalex.org/works"
ARXIV_URL = "https://export.arxiv.org/api/query"
GITHUB_SEARCH_URL = "https://api.github.com/search/repositories"
BRASILAPI_CEP_URL = "https://brasilapi.com.br/api/cep/v2/"
BRASILAPI_CNPJ_URL = "https://brasilapi.com.br/api/cnpj/v1/"
COINGECKO_SEARCH_URL = "https://api.coingecko.com/api/v3/search"
COINGECKO_MARKETS_URL = "https://api.coingecko.com/api/v3/coins/markets"
COINGECKO_PRICE_URL = "https://api.coingecko.com/api/v3/simple/price"
BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"


class ErroFonte(ValueError):
    """Provider error with the same honest codes used by search_providers."""

    def __init__(self, mensagem: str, codigo: str = "erro"):
        super().__init__(mensagem)
        self.codigo = codigo


def _research():
    import research  # late import: research imports search_providers lazily
    return research


def _erro(exc: Exception) -> ErroFonte:
    if isinstance(exc, ErroFonte):
        return exc
    http = getattr(exc, "http", getattr(exc, "code", 0))
    codigo = getattr(exc, "codigo", "") or type(exc).__name__
    mapa = {
        "ssrf": "bloqueado", "tipo_bloqueado": "tipo", "redirect": "http",
        "http": "http", "rede": "rede", "tamanho": "tamanho",
        "formato": "formato", "vazio": "vazio", "timeout": "rede",
        "URLError": "rede", "socket.timeout": "rede", "HTTPError": "http",
        "ResearchErro": "erro", "OSError": "rede", "TimeoutError": "rede",
        "ConnectionError": "rede", "rate_limited": "bloqueado",
        "http_401": "bloqueado", "http_403": "bloqueado", "http_429": "bloqueado",
    }
    if http == 429:
        codigo = "bloqueado"
    erro = ErroFonte(str(exc)[:200], mapa.get(codigo, codigo or "erro"))
    if http:
        erro.http = http
    elif codigo == "rate_limited":
        erro.http = 429
    return erro


def _limpar(texto, teto: int = 300) -> str:
    import html as _html
    txt = _html.unescape(re.sub(r"<[^>]+>", " ", str(texto or "")))
    return re.sub(r"\s+", " ", txt).strip()[:teto]


def _http(value) -> str:
    texto = str(value or "").strip()
    return texto[:500] if texto.startswith(("http://", "https://")) else ""


def _resultado(titulo, url, trecho, **meta) -> dict:
    return {"titulo": _limpar(titulo, 220), "url": _http(url),
            "trecho": _limpar(trecho, 500),
            "content_scope": "metadata_only", "full_text_fetched": False,
            "metadata_source": "public_api", "meta": meta}


def _request(url: str, *, timeout: float, headers=None, payload=None,
             method: str = "GET", max_bytes: int = MAX_BYTES):
    """GET/POST bytes with validated URL, revalidated redirects and size cap.

    Uses the same public-address opener as ``research.baixar``. The response is
    returned as ``(raw, content_type)``; no HTML body is ever parsed as JSON.
    """
    core = _research()
    atual = core.url_segura(url)
    body = None
    request_headers = {"User-Agent": UA, "Accept": "application/json"}
    if headers:
        request_headers.update({str(k): str(v) for k, v in headers.items()
                                if str(k).lower() != "user-agent"})
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")
    for _ in range(MAX_REDIRECTS + 1):
        try:
            resposta = core._abrir(
                atual, timeout, user_agent=UA, headers=request_headers,
                data=body, method=method)
        except urllib.error.HTTPError as exc:
            if exc.code in (301, 302, 303, 307, 308):
                destino = exc.headers.get("Location", "")
                if not destino:
                    raise ErroFonte("Redirect sem destino.", "http") from None
                atual = core.url_segura(urllib.parse.urljoin(atual, destino))
                if exc.code in (301, 302, 303):
                    method, body = "GET", None
                    request_headers.pop("Content-Type", None)
                continue
            codigo = "bloqueado" if exc.code in (401, 403, 429) else "http"
            erro = ErroFonte(f"Provedor HTTP {exc.code}.", codigo)
            erro.http = exc.code
            raise erro from None
        except (OSError, TimeoutError, ValueError) as exc:
            raise _erro(exc) from None
        with resposta:
            status = getattr(resposta, "status", 200)
            if status >= 400:
                codigo = "bloqueado" if status in (401, 403, 429) else "http"
                erro = ErroFonte(f"Provedor HTTP {status}.", codigo)
                erro.http = status
                raise erro
            try:
                ctype = (resposta.headers.get_content_type()
                         if hasattr(resposta.headers, "get_content_type")
                         else str(resposta.headers.get("Content-Type", "")).split(";")[0])
            except Exception:
                ctype = ""
            if "json" not in (ctype or "").lower() and "xml" not in (ctype or "").lower() \
                    and not (ctype or "").lower().startswith("text/"):
                raise ErroFonte("Provedor sem JSON/XML.", "tipo")
            try:
                total = int(resposta.headers.get("Content-Length") or 0)
            except (TypeError, ValueError):
                total = 0
            if total > max_bytes:
                raise ErroFonte("Resposta grande demais.", "tamanho")
            raw = resposta.read(max_bytes + 1)
            if len(raw) > max_bytes:
                raise ErroFonte("Resposta grande demais.", "tamanho")
            return raw, ctype
    raise ErroFonte("Redirects demais.", "http")


def _json_request(url: str, *, timeout: float, headers=None, payload=None,
                  method: str = "GET", max_bytes: int = MAX_BYTES):
    raw, _ = _request(url, timeout=timeout, headers=headers, payload=payload,
                      method=method, max_bytes=max_bytes)
    try:
        return json.loads(raw.decode("utf-8", errors="replace"))
    except (ValueError, TypeError):
        raise ErroFonte("JSON inválido.", "formato") from None


def _clamp(valor, minimo: int, maximo: int) -> int:
    try:
        return max(minimo, min(int(valor), maximo))
    except (TypeError, ValueError):
        return minimo


# ── OpenAlex (metadados acadêmicos) ─────────────────────────────────────
def _openalex_provider():
    import academic_research as academic
    return academic.OpenAlexWorksProvider(
        mailto=os.getenv("JULIA_RESEARCH_MAILTO", ""))


def buscar_openalex(consulta: str, limite: int = 6, timeout: float = 8.0) -> list:
    """Reuse the existing OpenAlex normalizer without making it mandatory."""
    try:
        linhas = _openalex_provider().buscar(consulta, limite)
    except Exception as exc:
        raise _erro(exc) from None
    saida = []
    for linha in linhas or []:
        if not isinstance(linha, dict):
            continue
        titulo = linha.get("titulo") or linha.get("title")
        url = _http(linha.get("url"))
        doi = str(linha.get("doi") or "").strip()
        if not url and doi:
            url = "https://doi.org/" + doi.removeprefix("https://doi.org/")
        if not titulo or not url:
            continue
        saida.append({
            "titulo": _limpar(titulo, 220), "url": url,
            "trecho": _limpar(linha.get("trecho") or linha.get("abstract"), 500),
            "doi": doi or None, "authors": linha.get("authors") or [],
            "year": linha.get("year"), "pdf_url": _http(linha.get("pdf_url")) or None,
            "fonte_primaria": True, "metadata_source": "academic_provider",
            "content_scope": "metadata_only", "full_text_fetched": False,
            "meta": {"provider": "openalex",
                     "open_access": bool(linha.get("open_access")),
                     "citation_count": linha.get("citation_count")},
        })
    if not saida:
        raise ErroFonte("OpenAlex sem resultados utilizáveis.", "vazio")
    return saida[:limite]


# ── arXiv (Atom público) ────────────────────────────────────────────────
_ARXIV_NS = {"a": "http://www.w3.org/2005/Atom",
             "arxiv": "http://arxiv.org/schemas/atom"}


def buscar_arxiv(consulta: str, limite: int = 6, timeout: float = 10.0) -> list:
    q = re.sub(r"\s+", " ", str(consulta or "")).strip()[:200]
    if len(q) < 2:
        raise ErroFonte("Consulta vazia.", "vazio")
    url = ARXIV_URL + "?" + urllib.parse.urlencode({
        "search_query": "all:" + q, "start": 0,
        "max_results": _clamp(limite, 1, 20),
        "sortBy": "relevance", "sortOrder": "descending"})
    raw, _ = _request(url, timeout=timeout,
                      headers={"Accept": "application/atom+xml, application/xml;q=0.9"},
                      max_bytes=2 * MAX_BYTES)
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        raise ErroFonte("Resposta arXiv fora do formato Atom.", "formato") from None
    saida = []
    for entrada in root.findall("a:entry", _ARXIV_NS):
        titulo = entrada.findtext("a:title", default="", namespaces=_ARXIV_NS)
        resumo = entrada.findtext("a:summary", default="", namespaces=_ARXIV_NS)
        link = ""
        for item in entrada.findall("a:link", _ARXIV_NS):
            if item.get("rel") == "alternate" and item.get("href"):
                link = item.get("href")
                break
        link = link or entrada.findtext("a:id", default="", namespaces=_ARXIV_NS)
        link = _http(link.replace("http://arxiv.org/abs/", "https://arxiv.org/abs/"))
        if not titulo or not link:
            continue
        publicado = entrada.findtext("a:published", default="", namespaces=_ARXIV_NS)[:10]
        autores = [_limpar(a.findtext("a:name", default="", namespaces=_ARXIV_NS), 160)
                   for a in entrada.findall("a:author", _ARXIV_NS)]
        doi = entrada.findtext("arxiv:doi", default="", namespaces=_ARXIV_NS)
        saida.append({
            "titulo": _limpar(titulo, 220), "url": link,
            "trecho": _limpar(resumo, 500),
            "authors": [a for a in autores if a][:20],
            "year": int(publicado[:4]) if publicado[:4].isdigit() else None,
            "published_at": publicado or None, "doi": doi or None,
            "pdf_url": link.replace("/abs/", "/pdf/") if "/abs/" in link else None,
            "fonte_primaria": True, "metadata_source": "academic_provider",
            "content_scope": "metadata_only", "full_text_fetched": False,
            "meta": {"provider": "arxiv", "repository": "arXiv"},
        })
    if not saida:
        raise ErroFonte("arXiv sem resultados.", "vazio")
    return saida[:limite]


# ── GitHub (busca de repositórios; token opcional) ──────────────────────
def buscar_github(consulta: str, limite: int = 6, timeout: float = 10.0) -> list:
    q = re.sub(r"\s+", " ", str(consulta or "")).strip()[:180]
    if len(q) < 2:
        raise ErroFonte("Consulta vazia.", "vazio")
    headers = {"Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28"}
    token = os.getenv("GITHUB_TOKEN", "").strip()
    if token:
        headers["Authorization"] = "Bearer " + token
    url = GITHUB_SEARCH_URL + "?" + urllib.parse.urlencode({
        "q": q, "sort": "stars", "order": "desc",
        "per_page": _clamp(limite, 1, 20)})
    dados = _json_request(url, timeout=timeout, headers=headers)
    itens = dados.get("items") if isinstance(dados, dict) else None
    if not isinstance(itens, list) or not itens:
        raise ErroFonte("GitHub sem repositórios.", "vazio")
    saida = []
    for item in itens:
        if not isinstance(item, dict):
            continue
        nome = _limpar(item.get("full_name"), 160)
        link = _http(item.get("html_url"))
        if not nome or not link:
            continue
        descricao = _limpar(item.get("description"), 300)
        estrelas = item.get("stargazers_count")
        linguagem = _limpar(item.get("language"), 40)
        trecho = descricao
        if isinstance(estrelas, int):
            trecho += f" — {estrelas} estrelas"
        if linguagem:
            trecho += f" · {linguagem}"
        saida.append({
            "titulo": nome, "url": link, "trecho": trecho.strip(" —·"),
            "metadata_source": "public_api",
            "meta": {"provider": "github", "stars": estrelas,
                     "language": linguagem or None,
                     "updated_at": item.get("updated_at"),
                     "topics": (item.get("topics") or [])[:10],
                     "archived": bool(item.get("archived")),
                     "license": ((item.get("license") or {}).get("spdx_id")
                                 if isinstance(item.get("license"), dict) else None)},
        })
    if not saida:
        raise ErroFonte("GitHub sem resultados utilizáveis.", "vazio")
    return saida[:limite]


# ── BrasilAPI (CEP e CNPJ) ──────────────────────────────────────────────
def _sem_acentos(texto: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFKD", str(texto or "").casefold())
                   if not unicodedata.combining(c))


def detectar_documento(consulta: str):
    """Return ``("cep"|"cnpj"|None, digits)`` from explicit document context."""
    texto = str(consulta or "")
    normalizado = _sem_acentos(texto)
    cep = re.search(r"\b(\d{5})-(\d{3})\b", texto)
    if cep:
        return "cep", cep.group(1) + cep.group(2)
    if re.search(r"\bcep\b", normalizado):
        cep = re.search(r"\b(\d{8})\b", texto)
        if cep:
            return "cep", cep.group(1)
    cnpj = re.search(r"\b(\d{2})\.(\d{3})\.(\d{3})/(\d{4})-(\d{2})\b", texto)
    if cnpj:
        return "cnpj", "".join(cnpj.groups())
    if re.search(r"\bcnpj\b", normalizado):
        cnpj = re.search(r"\b(\d{14})\b", re.sub(r"[.\-/]", "", texto))
        if cnpj:
            return "cnpj", cnpj.group(1)
    return None, ""


def _formatar_cep(digitos: str) -> str:
    return f"{digitos[:5]}-{digitos[5:]}" if len(digitos) == 8 else digitos


def _formatar_cnpj(digitos: str) -> str:
    if len(digitos) != 14:
        return digitos
    return f"{digitos[:2]}.{digitos[2:5]}.{digitos[5:8]}/{digitos[8:12]}-{digitos[12:]}"


def _brasilapi_json(url: str, timeout: float) -> dict:
    try:
        dados = _json_request(url, timeout=timeout)
    except ErroFonte as exc:
        if getattr(exc, "http", 0) == 404:
            raise ErroFonte("Documento não encontrado na BrasilAPI.", "vazio") from None
        raise
    if not isinstance(dados, dict):
        raise ErroFonte("BrasilAPI retornou formato inesperado.", "formato")
    return dados


def buscar_brasilapi(consulta: str, limite: int = 3, timeout: float = 8.0) -> list:
    tipo, digitos = detectar_documento(consulta)
    if tipo == "cep":
        dados = _brasilapi_json(BRASILAPI_CEP_URL + digitos, timeout)
        if not dados.get("cep"):
            raise ErroFonte("BrasilAPI sem dados para o CEP.", "vazio")
        rua = _limpar(dados.get("street"), 160)
        bairro = _limpar(dados.get("neighborhood"), 120)
        cidade = _limpar(dados.get("city"), 120)
        estado = _limpar(dados.get("state"), 40)
        local = ", ".join(x for x in (rua, bairro, cidade) if x)
        if estado:
            local = (local + "/" + estado) if local else estado
        localizacao = dados.get("location") if isinstance(dados.get("location"), dict) else {}
        coordenadas = localizacao.get("coordinates") if isinstance(
            localizacao.get("coordinates"), dict) else {}
        trecho = (f"CEP {_formatar_cep(digitos)} · {digitos} · {local or 'endereço não informado'}")
        if dados.get("timezoneName"):
            trecho += f" · {dados['timezoneName']}"
        return [_resultado(
            f"CEP {_formatar_cep(digitos)} — {rua or local or 'endereço'}",
            BRASILAPI_CEP_URL + digitos, trecho,
            provider="brasilapi", kind="cep", cep=digitos,
            city=cidade, state=estado, neighborhood=bairro, street=rua,
            ibge=dados.get("ibge"), coordinates=coordenadas,
            timezone=dados.get("timezoneName"))][:max(1, int(limite))]
    if tipo == "cnpj":
        dados = _brasilapi_json(BRASILAPI_CNPJ_URL + digitos, timeout)
        razao = _limpar(dados.get("razao_social"), 180)
        if not razao:
            raise ErroFonte("BrasilAPI sem razão social para o CNPJ.", "vazio")
        fantasia = _limpar(dados.get("nome_fantasia"), 160)
        municipio = _limpar(dados.get("municipio"), 120)
        uf = _limpar(dados.get("uf"), 40)
        cnae = _limpar(dados.get("cnae_fiscal_descricao"), 200)
        situacao = _limpar(dados.get("descricao_situacao_cadastral"), 80)
        abertura = _limpar(dados.get("data_inicio_atividade"), 20)
        partes = [x for x in (fantasia, cnae, situacao) if x]
        if municipio:
            partes.append(municipio + ("/" + uf if uf else ""))
        trecho = f"CNPJ {_formatar_cnpj(digitos)} · {digitos}"
        if partes:
            trecho += " · " + " · ".join(partes)
        if abertura:
            trecho += f" · início {abertura}"
        return [_resultado(
            f"{razao} — CNPJ {_formatar_cnpj(digitos)}",
            BRASILAPI_CNPJ_URL + digitos, trecho,
            provider="brasilapi", kind="cnpj", cnpj=digitos,
            razao_social=razao, nome_fantasia=fantasia, cnae=cnae,
            situacao=situacao, municipio=municipio, uf=uf,
            data_inicio_atividade=abertura)][:max(1, int(limite))]
    raise ErroFonte("Consulta sem CEP ou CNPJ identificável.", "vazio")


# ── CoinGecko (dados públicos de criptoativos) ─────────────────────────
_RX_CRIPTO = re.compile(
    r"\b(bitcoin|btc|ethereum|ether|eth|solana|cardano|dogecoin|doge|xrp|"
    r"ripple|bnb|binance|criptomoedas?|cripto|criptoativos?|stablecoins?|"
    r"tether|usdt|usdc|moedas? digitais?)\b", re.I)
_GENERICOS_CRIPTO = {
    "preco", "precos", "cotacao", "cotacoes", "valor", "valores", "hoje",
    "agora", "atual", "quanto", "custa", "custam", "qual", "quais", "que",
    "como", "onde", "quando", "esta", "estao", "e", "eh",
    "a", "o", "de", "do", "da", "dos", "das", "em", "para", "por", "sobre",
    "cripto", "criptomoeda", "criptomoedas", "criptoativo", "criptoativos",
    "moeda", "moedas", "digital", "digitais", "mercado", "ranking",
}


def detectar_cripto(consulta: str) -> bool:
    return bool(_RX_CRIPTO.search(_sem_acentos(consulta)))


def _consulta_cripto(consulta: str) -> str:
    termos = [t for t in re.findall(r"[a-z0-9-]+", _sem_acentos(consulta))
              if t not in _GENERICOS_CRIPTO]
    return " ".join(termos)[:80]


def _brl(valor) -> str:
    try:
        return "R$ " + f"{float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (TypeError, ValueError):
        return ""


def _usd(valor) -> str:
    try:
        return "US$ " + f"{float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (TypeError, ValueError):
        return ""


def buscar_coingecko(consulta: str, limite: int = 6, timeout: float = 10.0) -> list:
    limite = _clamp(limite, 1, 10)
    termo = _consulta_cripto(consulta)
    moedas = []
    if termo:
        busca = _json_request(
            COINGECKO_SEARCH_URL + "?" + urllib.parse.urlencode({"query": termo}),
            timeout=timeout)
        candidatos = busca.get("coins") if isinstance(busca, dict) else None
        termos = [t for t in re.findall(r"[a-z0-9-]+", termo) if len(t) >= 2]
        for moeda in (candidatos or []):
            if not isinstance(moeda, dict):
                continue
            if moeda.get("market_cap_rank") is None:
                continue
            alvo = " ".join(str(moeda.get(k) or "").casefold()
                            for k in ("id", "name", "symbol"))
            if termos and not any(t in alvo for t in termos):
                continue
            moedas.append({"id": moeda.get("id"), "name": moeda.get("name"),
                           "symbol": moeda.get("symbol"),
                           "market_cap_rank": moeda.get("market_cap_rank")})
    if not moedas and not termo:
        mercados = _json_request(
            COINGECKO_MARKETS_URL + "?" + urllib.parse.urlencode({
                "vs_currency": "brl", "order": "market_cap_desc",
                "per_page": limite, "page": 1, "sparkline": "false",
                "price_change_percentage": "24h"}),
            timeout=timeout)
        if not isinstance(mercados, list):
            raise ErroFonte("CoinGecko retornou formato inesperado.", "formato")
        moedas = [{"id": m.get("id"), "name": m.get("name"),
                   "symbol": m.get("symbol"),
                   "market_cap_rank": m.get("market_cap_rank")}
                  for m in mercados if isinstance(m, dict) and m.get("id")]
    ids = [m["id"] for m in moedas[:limite] if m.get("id")]
    if not ids:
        raise ErroFonte("CoinGecko sem moedas correspondentes.", "vazio")
    precos = _json_request(
        COINGECKO_PRICE_URL + "?" + urllib.parse.urlencode({
            "ids": ",".join(ids), "vs_currencies": "brl,usd",
            "include_24hr_change": "true", "include_last_updated_at": "true"}),
        timeout=timeout)
    if not isinstance(precos, dict):
        raise ErroFonte("CoinGecko retornou preços em formato inesperado.", "formato")
    saida = []
    for moeda in moedas:
        preco = precos.get(moeda.get("id")) if isinstance(precos, dict) else None
        if not isinstance(preco, dict):
            continue
        brl, usd = preco.get("brl"), preco.get("usd")
        if brl is None and usd is None:
            continue
        nome = _limpar(moeda.get("name"), 100)
        simbolo = str(moeda.get("symbol") or "").upper()[:12]
        partes = []
        if usd is not None:
            partes.append(_usd(usd))
        variacao = preco.get("brl_24h_change")
        if isinstance(variacao, (int, float)):
            partes.append(f"24h {variacao:+.2f}%")
        if moeda.get("market_cap_rank"):
            partes.append(f"ranking #{moeda['market_cap_rank']}")
        titulo = f"{nome} ({simbolo})"
        if brl is not None:
            titulo += f" — {_brl(brl)}"
        saida.append({
            "titulo": titulo[:220],
            "url": f"https://www.coingecko.com/en/coins/{moeda['id']}",
            "trecho": " · ".join(partes) or "Cotação pública CoinGecko",
            "content_scope": "metadata_only", "full_text_fetched": False,
            "metadata_source": "public_api",
            "meta": {"provider": "coingecko", "id": moeda["id"],
                     "symbol": simbolo, "price_brl": brl, "price_usd": usd,
                     "change_24h_pct": variacao,
                     "market_cap_rank": moeda.get("market_cap_rank"),
                     "last_updated_at": preco.get("last_updated_at"),
                     "disclaimer": "Dados de mercado; não é recomendação de investimento."},
        })
    if not saida:
        raise ErroFonte("CoinGecko sem cotações utilizáveis.", "vazio")
    return saida[:limite]


# ── Brave Search (opcional; chave própria) ─────────────────────────────
def buscar_brave(consulta: str, limite: int = 8, timeout: float = 10.0) -> list:
    chave = os.getenv("BRAVE_SEARCH_API_KEY", "").strip()
    if not chave:
        raise ErroFonte("Brave Search sem BRAVE_SEARCH_API_KEY configurada.", "indisponivel")
    q = re.sub(r"\s+", " ", str(consulta or "")).strip()[:200]
    if len(q) < 2:
        raise ErroFonte("Consulta vazia.", "vazio")
    params = {"q": q, "count": _clamp(limite, 1, 20), "country": "br",
              "search_lang": "pt", "safesearch": "moderate",
              "text_decorations": "false", "spellcheck": "false"}
    if re.search(r"\b(noticias?|hoje|ontem|ultimas?|recentes?)\b", _sem_acentos(q)):
        params["freshness"] = "pw"
    dados = _json_request(
        BRAVE_SEARCH_URL + "?" + urllib.parse.urlencode(params),
        timeout=timeout,
        headers={"X-Subscription-Token": chave, "Accept": "application/json"})
    web = dados.get("web") if isinstance(dados, dict) else None
    itens = web.get("results") if isinstance(web, dict) else None
    if not isinstance(itens, list) or not itens:
        raise ErroFonte("Brave Search sem resultados.", "vazio")
    saida = []
    for item in itens:
        if not isinstance(item, dict):
            continue
        titulo = _limpar(item.get("title"), 220)
        link = _http(item.get("url"))
        if not titulo or not link:
            continue
        trecho = _limpar(item.get("description"), 500)
        idade = _limpar(item.get("age"), 60)
        if idade:
            trecho = (trecho + f" · {idade}").strip(" ·")
        saida.append({
            "titulo": titulo, "url": link, "trecho": trecho,
            "meta": {"provider": "brave", "age": idade or None,
                     "hostname": _limpar((item.get("meta_url") or {}).get("hostname")
                                          if isinstance(item.get("meta_url"), dict) else "", 160),
                     "language": item.get("language")},
        })
    if not saida:
        raise ErroFonte("Brave Search sem resultados utilizáveis.", "vazio")
    return saida[:limite]
