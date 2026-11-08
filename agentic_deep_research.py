"""VEXX-AI Agentic Deep Research & Commercial Comparison Engine.

Implementa o padrão "Agentic Loop" (Loop Agêntico de Auto-Correção) com:
1. Search Routing Multi-Provedor (Tavily, Exa.ai, Serper, DuckDuckGo e fallback
   nativo VEXX) + decomposição de perguntas complexas em 2 a 3 queries paralelas.
2. Web Scraping Resiliente em cascata (Jina Reader API `https://r.jina.ai/`,
   Firecrawl API, Playwright Stealth opcional e extrator determinístico VEXX)
   convertendo páginas para Markdown limpo pronto para LLMs.
3. Loop de Repetição & Auto-Correção (até 3 tentativas) que analisa falhas de
   busca/extração, reformula os parâmetros da query e tenta novamente antes de
   reportar erro ao webhook.
4. Habilidades principais:
   - `search_and_compare_products(query)`
   - `deep_investigate_topic(query)`
   - `handle_webhook_response(data)`
"""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import hmac
import json
import logging
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any, Callable

import research
import web_extract

logger = logging.getLogger("JULIA-agentic-research")
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] [%(name)s] %(message)s")
    )
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)


# ── Prompts Injetados do Agente ─────────────────────────────────────────────

AGENTIC_SYSTEM_PROMPT = """Você é o Agente Especialista de Pesquisa Profunda e Inteligência Comercial do VEXX-AI.
Sua missão é investigar tópicos complexos e comparar produtos comerciais com precisão factual absoluta.

REGRAS INEGOCIÁVEIS:
1. Baseie-se EXCLUSIVAMENTE nas evidências em Markdown extraídas das fontes abertas.
2. Nunca invente preços, links, tamanhos, cores, estoques ou estatísticas.
3. Ao comparar produtos, estruture: Nome do Produto, Loja/Domínio, Preço (R$), Tamanhos, Cores, Estilo/Modelo e Link Direto.
4. Ao investigar um tópico profundo, cruze dados de pelo menos 3 fontes independentes, destacando:
   - Consensos verificados entre as fontes;
   - Divergências ou variações de mercado;
   - Tendências, métricas e previsões fundamentadas;
   - Citações numeradas [1], [2], [3] apontando para as URLs originais.
"""

QUERY_DECOMPOSITION_PROMPT = """Divida a solicitação abaixo em 2 ou 3 queries de busca complementares e altamente específicas.
Retorne APENAS um array JSON de strings (ex: ["query 1", "query 2", "query 3"]).
Modo: {mode}
Solicitação: {query}
"""

QUERY_SELF_CORRECTION_PROMPT = """A tentativa {attempt} de pesquisa para "{original_query}" (usando as sub-queries {previous_queries}) falhou ou trouxe evidências insuficientes.
Diagnóstico da falha: {failure_reason}
Gere 3 NOVAS queries reformuladas, mais amplas ou com termos alternativos/sinônimos que contornem o problema.
Retorne APENAS um array JSON de 3 strings.
"""


# ── Utilitários de Rede, Segurança e Normalização ───────────────────────────

_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

_STOPWORDS_PT = {
    "o", "a", "os", "as", "um", "uma", "de", "do", "da", "dos", "das", "em",
    "no", "na", "nos", "nas", "por", "para", "com", "sem", "que", "qual",
    "quais", "como", "onde", "quando", "porque", "sobre", "entre", "mais",
    "menos", "melhor", "melhores", "comparar", "compare", "pesquise", "busque",
    "procure", "me", "mostre", "quero", "preciso",
}

_CORES_CONHECIDAS = (
    "preto", "preta", "branco", "branca", "azul", "vermelho", "vermelha",
    "verde", "amarelo", "amarela", "cinza", "prata", "dourado", "dourada",
    "rosa", "roxo", "roxa", "bege", "marrom", "laranja", "vinho", "grafite",
    "titânio", "titanio", "creme", "off-white", "navy", "black", "white",
    "blue", "red", "green", "silver", "gold", "pink", "purple", "grey", "gray",
)

_TAMANHOS_TOKEN_RE = re.compile(
    r"\b(?:PP|P|M|G|GG|XG|XGG|EG|EGG|XS|S|L|XL|XXL|2XL|3XL|"
    r"3[3-9]|4[0-8]|"
    r"\d{2,3}\s?(?:GB|TB|ml|ML|g|kg|cm|mm|pol|polegadas))\b"
)

_ESTILOS_CONHECIDOS = (
    "casual", "esportivo", "running", "corrida", "treino", "social", "slim",
    "regular", "oversized", "retrô", "retro", "clássico", "classico", "pro",
    "max", "ultra", "plus", "lite", "mini", "gamer", "wireless", "bluetooth",
    " Dobrável", "compacto", "premium", "básico", "basico",
)

_PRECO_BR_RE = re.compile(
    r"(?:R\$|\bBRL\s*)\s*(\d{1,3}(?:\.\d{3})*(?:,\d{2})|\d+(?:,\d{2})?)",
    re.IGNORECASE,
)
_PRECO_US_RE = re.compile(
    r"(?:US\$|\bUSD\s*|\$)\s*(\d{1,3}(?:,\d{3})*(?:\.\d{2})|\d+(?:\.\d{2}))",
    re.IGNORECASE,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _domain_of(url: str) -> str:
    try:
        host = urllib.parse.urlsplit(url).hostname or ""
        return re.sub(r"^www\.", "", host.lower())
    except Exception:
        return ""


def _http_json_post(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    timeout: float = 12.0,
) -> dict[str, Any]:
    research.url_segura(url)
    raw_body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req_headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": _BROWSER_UA,
        **headers,
    }
    req = urllib.request.Request(url, data=raw_body, headers=req_headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read(2 * 1024 * 1024)
        return json.loads(data.decode("utf-8", errors="replace"))


def _http_get_text(
    url: str,
    headers: dict[str, str] | None = None,
    timeout: float = 15.0,
    max_bytes: int = 2 * 1024 * 1024,
) -> tuple[int, str, str]:
    """Retorna (status_code, final_url, text) validando SSRF."""
    research.url_segura(url)
    req_headers = {
        "User-Agent": _BROWSER_UA,
        "Accept": "text/markdown,text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        **(headers or {}),
    }
    req = urllib.request.Request(url, headers=req_headers, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        status = getattr(resp, "status", 200) or 200
        final_url = resp.geturl() or url
        research.url_segura(final_url)
        raw = resp.read(max_bytes)
        charset = resp.headers.get_content_charset() or "utf-8"
        try:
            text = raw.decode(charset, errors="replace")
        except LookupError:
            text = raw.decode("utf-8", errors="replace")
        return status, final_url, text


# ── 1. ROTEAMENTO DE BUSCAS & DECOMPOSIÇÃO DE QUERIES ───────────────────────

def decompose_complex_query(
    query: str,
    mode: str = "general",
    max_queries: int = 3,
    attempt: int = 1,
    failure_reason: str = "",
    previous_queries: list[str] | None = None,
    llm_fn: Callable[[str], str] | None = None,
) -> list[str]:
    """Divide uma pergunta complexa em 2 ou 3 queries simultâneas.

    Em tentativas > 1 (auto-correção), modifica os parâmetros da query para
    ampliar cobertura, remover restrições que falharam e explorar facetas
    complementares.
    """
    base = re.sub(r"\s+", " ", (query or "").strip())
    if not base:
        return []

    max_queries = max(2, min(int(max_queries or 3), 3))

    effective_llm = llm_fn
    if effective_llm is None:
        try:
            import qwen_llm_service
            def _qwen_decompose_wrapper(p: str) -> str:
                r = qwen_llm_service.gerar_resposta_qwen(p, temperatura=0.2, max_tokens=256)
                return str(r.get("resposta") or "")
            effective_llm = _qwen_decompose_wrapper
        except Exception:
            effective_llm = None

    # Se houver função LLM injetada ou modelo Qwen VEXX disponível
    if callable(effective_llm):
        try:
            prompt = (
                QUERY_SELF_CORRECTION_PROMPT.format(
                    attempt=attempt,
                    original_query=base,
                    previous_queries=json.dumps(previous_queries or [base], ensure_ascii=False),
                    failure_reason=failure_reason or " resultados insuficientes",
                )
                if attempt > 1
                else QUERY_DECOMPOSITION_PROMPT.format(mode=mode, query=base)
            )
            raw_resp = effective_llm(prompt) or ""
            match = re.search(r"\[[\s\S]*?\]", raw_resp)
            if match:
                parsed = json.loads(match.group(0))
                cleaned = [
                    str(q).strip()
                    for q in parsed
                    if isinstance(q, str) and len(str(q).strip()) >= 3
                ]
                if len(cleaned) >= 2:
                    logger.info(
                        "Tentativa %d: LLM gerou %d sub-queries: %s",
                        attempt, len(cleaned[:max_queries]), cleaned[:max_queries],
                    )
                    return cleaned[:max_queries]
        except Exception as exc:
            logger.warning(
                "Tentativa %d: Fallback determinístico na decomposição de query (%s)",
                attempt, exc,
            )

    # Decomposição e auto-correção determinística de alta resiliência
    tokens = [
        t for t in re.findall(r"[\wÀ-ÿ-]+", base.lower())
        if len(t) > 2 and t not in _STOPWORDS_PT
    ]
    nucleo = " ".join(tokens[:6]) if tokens else base
    ano_atual = datetime.now(timezone.utc).year

    if mode == "product":
        if attempt == 1:
            queries = [
                f"{base} preço comprar especificações",
                f"{nucleo} ficha técnica tamanhos cores modelos",
                f"{nucleo} ofertas lojas comparativo preço",
            ]
        elif attempt == 2:
            queries = [
                f"{nucleo} menor preço R$ loja oficial",
                f"{nucleo} review características cores tamanhos",
                f"comprar {nucleo} Brasil oferta",
            ]
        else:
            # Tentativa 3: relaxa para os termos mais essenciais do produto
            curto = " ".join(tokens[:4]) if tokens else base
            queries = [
                f"{curto} preço",
                f"{curto} especificações",
                f"{curto} lojas",
            ]
    else:
        # Particiona perguntas compostas (ex: "X e Y", "X vs Y", cláusulas com vírgula)
        partes = [
            p.strip()
            for p in re.split(r"\b(?:vs\.?|versus|comparado com|e também|além de)\b|[,;?]", base, flags=re.I)
            if len(p.strip()) >= 4
        ]
        if attempt == 1:
            if len(partes) >= 2:
                queries = [
                    partes[0],
                    partes[1],
                    f"{nucleo} dados análise {ano_atual}",
                ]
            else:
                queries = [
                    base,
                    f"{nucleo} dados estatísticas relatório {ano_atual}",
                    f"{nucleo} análise mercado tendências perspectivas",
                ]
        elif attempt == 2:
            queries = [
                f"{nucleo} panorama completo dados oficiais",
                f"{nucleo} estudo comparativo indicadores",
                f"{ ' '.join(tokens[:4]) if tokens else base } guia técnico",
            ]
        else:
            curto = " ".join(tokens[:3]) if tokens else base
            queries = [
                curto,
                f"{curto} resumo dados",
                f"{curto} informações principais",
            ]

    # Deduplica preservando a ordem e garantindo pelo menos 2 queries distintas
    unicas: list[str] = []
    for q in queries:
        q_norm = re.sub(r"\s+", " ", q).strip()
        if q_norm and q_norm.lower() not in {u.lower() for u in unicas}:
            unicas.append(q_norm)
    if len(unicas) == 1:
        unicas.append(f"{unicas[0]} detalhes")
    return unicas[:max_queries]


def _search_tavily(query: str, max_results: int = 6, timeout: float = 12.0) -> list[dict[str, Any]]:
    api_key = os.environ.get("TAVILY_API_KEY", "").strip()
    if not api_key:
        return []
    payload = {
        "api_key": api_key,
        "query": query,
        "search_depth": "advanced",
        "include_answer": False,
        "include_raw_content": False,
        "max_results": max_results,
    }
    resp = _http_json_post("https://api.tavily.com/search", payload, {}, timeout=timeout)
    out = []
    for item in resp.get("results", []) or []:
        if not isinstance(item, dict) or not item.get("url"):
            continue
        out.append({
            "title": str(item.get("title") or "").strip(),
            "url": str(item.get("url") or "").strip(),
            "snippet": str(item.get("content") or item.get("snippet") or "").strip(),
            "provider": "tavily",
            "score": float(item.get("score") or 0.8),
        })
    return out


def _search_exa(query: str, max_results: int = 6, timeout: float = 12.0) -> list[dict[str, Any]]:
    api_key = os.environ.get("EXA_API_KEY", "").strip()
    if not api_key:
        return []
    payload = {
        "query": query,
        "numResults": max_results,
        "useAutoprompt": True,
        "contents": {"text": {"maxCharacters": 1200}},
    }
    resp = _http_json_post(
        "https://api.exa.ai/search",
        payload,
        {"x-api-key": api_key, "Authorization": f"Bearer {api_key}"},
        timeout=timeout,
    )
    out = []
    for item in resp.get("results", []) or []:
        if not isinstance(item, dict) or not item.get("url"):
            continue
        out.append({
            "title": str(item.get("title") or "").strip(),
            "url": str(item.get("url") or "").strip(),
            "snippet": str(item.get("text") or item.get("snippet") or "").strip()[:800],
            "provider": "exa",
            "score": float(item.get("score") or 0.8),
        })
    return out


def _search_serper(query: str, max_results: int = 6, timeout: float = 12.0) -> list[dict[str, Any]]:
    api_key = os.environ.get("SERPER_API_KEY", "").strip()
    if not api_key:
        return []
    payload = {"q": query, "gl": "br", "hl": "pt-br", "num": max_results}
    resp = _http_json_post(
        "https://google.serper.dev/search",
        payload,
        {"X-API-KEY": api_key},
        timeout=timeout,
    )
    out = []
    for item in resp.get("organic", []) or []:
        if not isinstance(item, dict) or not item.get("link"):
            continue
        attrs = item.get("attributes") if isinstance(item.get("attributes"), dict) else {}
        attr_txt = "; ".join(f"{k}: {v}" for k, v in attrs.items()) if attrs else ""
        price_txt = str(item.get("price") or item.get("currency") or "").strip()
        snippet = " | ".join(p for p in (str(item.get("snippet") or "").strip(), price_txt, attr_txt) if p)
        out.append({
            "title": str(item.get("title") or "").strip(),
            "url": str(item.get("link") or "").strip(),
            "snippet": snippet,
            "provider": "serper",
            "score": 0.85,
        })
    return out


def _search_duckduckgo(query: str, max_results: int = 6, timeout: float = 12.0) -> list[dict[str, Any]]:
    """Usa `duckduckgo_search` (DDGS) se instalado e faz fallback para os provedores VEXX."""
    out: list[dict[str, Any]] = []
    try:
        from duckduckgo_search import DDGS  # type: ignore

        with DDGS(timeout=int(timeout)) as ddgs:
            for item in ddgs.text(query, region="br-pt", max_results=max_results) or []:
                if not isinstance(item, dict):
                    continue
                url = str(item.get("href") or item.get("url") or "").strip()
                if not url:
                    continue
                out.append({
                    "title": str(item.get("title") or "").strip(),
                    "url": url,
                    "snippet": str(item.get("body") or item.get("snippet") or "").strip(),
                    "provider": "duckduckgo_search",
                    "score": 0.75,
                })
        if out:
            return out
    except Exception:
        pass

    # Fallback para o motor multi-provedor nativo do VEXX-AI (`search_providers`)
    import search_providers

    for prov in ("ddg-html", "ddg-lite", "ddg", "wikipedia-pt", "wikipedia-en"):
        try:
            achados = search_providers.buscar(prov, query, max_resultados=max_results, timeout=timeout)
            for a in achados or []:
                url = str(a.get("url") or "").strip()
                if not url:
                    continue
                out.append({
                    "title": str(a.get("titulo") or a.get("title") or "").strip(),
                    "url": url,
                    "snippet": str(a.get("trecho") or a.get("snippet") or "").strip(),
                    "provider": prov,
                    "score": 0.7,
                })
            if len(out) >= max_results:
                break
        except Exception:
            continue
    return out[:max_results]


def route_search_query(
    query: str,
    max_results: int = 6,
    timeout: float = 12.0,
    preferred_providers: tuple[str, ...] = ("tavily", "exa", "serper", "duckduckgo"),
) -> list[dict[str, Any]]:
    """Roteia uma query pelos provedores de busca otimizados para LLMs com fallback automático."""
    dispatch = {
        "tavily": _search_tavily,
        "exa": _search_exa,
        "serper": _search_serper,
        "duckduckgo": _search_duckduckgo,
    }
    collected: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    for prov in preferred_providers:
        fn = dispatch.get(prov)
        if not fn:
            continue
        try:
            items = fn(query, max_results=max_results, timeout=timeout)
            if items:
                logger.info(
                    "SearchRouter: provedor '%s' retornou %d resultados para '%s'",
                    prov, len(items), query,
                )
            for item in items:
                u = str(item.get("url") or "").strip()
                if not u or u in seen_urls:
                    continue
                seen_urls.add(u)
                collected.append(item)
            if len(collected) >= max_results:
                break
        except Exception as exc:
            logger.warning(
                "SearchRouter: falha no provedor '%s' para '%s': %s",
                prov, query, exc,
            )
            continue

    return collected[:max_results]


def execute_parallel_searches(
    queries: list[str],
    max_results_per_query: int = 6,
    timeout: float = 12.0,
) -> list[dict[str, Any]]:
    """Executa 2 ou 3 sub-queries simultaneamente e deduplica por URL canônica."""
    if not queries:
        return []
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()

    with ThreadPoolExecutor(max_workers=min(len(queries), 4)) as pool:
        future_map = {
            pool.submit(route_search_query, q, max_results_per_query, timeout): q
            for q in queries
        }
        for fut in as_completed(future_map):
            sub_q = future_map[fut]
            try:
                results = fut.result() or []
                for item in results:
                    url = str(item.get("url") or "").strip()
                    if not url or url in seen:
                        continue
                    seen.add(url)
                    enriched = dict(item)
                    enriched.setdefault("matched_query", sub_q)
                    merged.append(enriched)
            except Exception as exc:
                logger.warning("Busca paralela falhou para sub-query '%s': %s", sub_q, exc)

    return merged


# ── 2. WEB SCRAPING RESILIENTE (MARKDOWN PARA LLMs) ─────────────────────────

def _html_to_clean_markdown(html_text: str, url: str = "") -> tuple[str, dict[str, Any]]:
    """Converte HTML bruto em Markdown limpo usando `web_extract` + estruturação."""
    extracted = web_extract.extrair_artigo(html_text, url=url)
    title = str(extracted.get("titulo") or "").strip()
    author = str(extracted.get("autor") or "").strip()
    published = str(extracted.get("publicado_em") or "").strip()
    body = str(extracted.get("texto") or "").strip()
    jsonld = extracted.get("jsonld") if isinstance(extracted.get("jsonld"), list) else []
    og = extracted.get("og") if isinstance(extracted.get("og"), dict) else {}

    md_parts: list[str] = []
    if title:
        md_parts.append(f"# {title}")
    meta_bits = []
    if url:
        meta_bits.append(f"Fonte: {url}")
    if author:
        meta_bits.append(f"Autor: {author}")
    if published:
        meta_bits.append(f"Data: {published}")
    if meta_bits:
        md_parts.append(" | ".join(meta_bits))
    if og.get("description") and og["description"] not in body:
        md_parts.append(f"> {og['description']}")
    if body:
        md_parts.append(body)
    if jsonld:
        try:
            resumo_ld = json.dumps(jsonld[:3], ensure_ascii=False)[:2000]
            md_parts.append(f"### Dados Estruturados (JSON-LD)\n```json\n{resumo_ld}\n```")
        except Exception:
            pass
    return "\n\n".join(md_parts).strip(), extracted


def _scrape_via_jina_reader(url: str, timeout: float = 15.0) -> str:
    """Usa Jina Reader API (`https://r.jina.ai/<url>`) para contornar JS/anti-bot e obter Markdown."""
    research.url_segura(url)
    jina_url = f"https://r.jina.ai/{url}"
    headers = {
        "Accept": "text/markdown",
        "X-Return-Format": "markdown",
        "X-No-Cache": "false",
    }
    jina_key = os.environ.get("JINA_API_KEY", "").strip()
    if jina_key:
        headers["Authorization"] = f"Bearer {jina_key}"

    status, _, text = _http_get_text(jina_url, headers=headers, timeout=timeout)
    if status >= 400 or not text or len(text.strip()) < 80:
        raise ValueError(f"Jina Reader retornou status={status} len={len(text or '')}")
    return text.strip()[:12000]


def _scrape_via_firecrawl(url: str, timeout: float = 18.0) -> str:
    """Usa Firecrawl API (`https://api.firecrawl.dev/v1/scrape`) se `FIRECRAWL_API_KEY` existir."""
    api_key = os.environ.get("FIRECRAWL_API_KEY", "").strip()
    if not api_key:
        raise ValueError("FIRECRAWL_API_KEY não configurada")
    research.url_segura(url)
    resp = _http_json_post(
        "https://api.firecrawl.dev/v1/scrape",
        {"url": url, "formats": ["markdown"], "onlyMainContent": True},
        {"Authorization": f"Bearer {api_key}"},
        timeout=timeout,
    )
    data = resp.get("data") if isinstance(resp.get("data"), dict) else {}
    md = str(data.get("markdown") or data.get("content") or "").strip()
    if len(md) < 80:
        raise ValueError("Firecrawl retornou markdown vazio/curto")
    return md[:12000]


def _scrape_via_playwright_stealth(url: str, timeout: float = 18.0) -> tuple[str, dict[str, Any]]:
    """Fallback opcional com Playwright Headless + Stealth para páginas SPAs pesadas em JS."""
    research.url_segura(url)
    from playwright.sync_api import sync_playwright  # type: ignore

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        try:
            context = browser.new_context(
                user_agent=_BROWSER_UA,
                locale="pt-BR",
                viewport={"width": 1366, "height": 768},
            )
            page = context.new_page()
            page.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
            )
            page.goto(url, wait_until="domcontentloaded", timeout=int(timeout * 1000))
            page.wait_for_timeout(800)
            html_content = page.content()
            return _html_to_clean_markdown(html_content, url=url)
        finally:
            browser.close()


def scrape_url_markdown(
    url: str,
    fallback_snippet: str = "",
    fallback_title: str = "",
    timeout: float = 15.0,
) -> dict[str, Any]:
    """Extrai o conteúdo de uma URL em Markdown limpo usando cascata resiliente anti-403/JS.

    Ordem da cascata:
    1. Extração direta rápida (`_http_get_text` + `web_extract` com JSON-LD/OG preservados);
    2. Jina Reader API (`https://r.jina.ai/<url>`) se a página exigir JS ou retornar 403/429;
    3. Firecrawl API (quando `FIRECRAWL_API_KEY` configurada);
    4. Playwright Headless Stealth (quando instalado localmente);
    5. Fallback seguro com snippet da busca (nunca trava o pipeline).
    """
    started = time.monotonic()
    try:
        research.url_segura(url)
    except Exception as exc:
        logger.warning("Scraper bloqueou URL insegura '%s': %s", url, exc)
        return {
            "url": url,
            "domain": _domain_of(url),
            "title": fallback_title,
            "markdown": "",
            "method": "blocked_ssrf",
            "ok": False,
            "error": str(exc),
            "structured": {},
            "elapsed_ms": int((time.monotonic() - started) * 1000),
        }

    errors: list[str] = []

    # Camada 1: Download HTTP direto + Extrator determinístico (preserva JSON-LD de e-commerce)
    try:
        status, final_url, html_text = _http_get_text(url, timeout=min(timeout, 10.0))
        if 200 <= status < 400 and html_text:
            md, structured = _html_to_clean_markdown(html_text, url=final_url)
            if len(md) >= 160 or structured.get("jsonld"):
                logger.info(
                    "Scraper [direct_html] extraiu %d chars de %s",
                    len(md), final_url,
                )
                return {
                    "url": final_url,
                    "domain": _domain_of(final_url),
                    "title": str(structured.get("titulo") or fallback_title).strip(),
                    "markdown": md[:12000],
                    "method": "direct_html",
                    "ok": True,
                    "error": "",
                    "structured": structured,
                    "elapsed_ms": int((time.monotonic() - started) * 1000),
                }
            errors.append(f"direct_html_curto({len(md)}c)")
    except Exception as exc:
        errors.append(f"direct_html({type(exc).__name__}: {exc})")
        logger.info("Scraper: falha no acesso direto a %s (%s); acionando Jina Reader...", url, exc)

    # Camada 2: Jina Reader API (renderiza JS e contorna 403 comuns, retornando Markdown)
    if os.environ.get("JULIA_DISABLE_JINA_READER", "0") != "1":
        try:
            md_jina = _scrape_via_jina_reader(url, timeout=timeout)
            logger.info("Scraper [jina_reader] extraiu %d chars de %s", len(md_jina), url)
            return {
                "url": url,
                "domain": _domain_of(url),
                "title": fallback_title or _extract_md_title(md_jina),
                "markdown": md_jina,
                "method": "jina_reader",
                "ok": True,
                "error": "",
                "structured": {},
                "elapsed_ms": int((time.monotonic() - started) * 1000),
            }
        except Exception as exc:
            errors.append(f"jina_reader({type(exc).__name__}: {exc})")

    # Camada 3: Firecrawl API (se configurada)
    if os.environ.get("FIRECRAWL_API_KEY", "").strip():
        try:
            md_fc = _scrape_via_firecrawl(url, timeout=timeout)
            logger.info("Scraper [firecrawl] extraiu %d chars de %s", len(md_fc), url)
            return {
                "url": url,
                "domain": _domain_of(url),
                "title": fallback_title or _extract_md_title(md_fc),
                "markdown": md_fc,
                "method": "firecrawl",
                "ok": True,
                "error": "",
                "structured": {},
                "elapsed_ms": int((time.monotonic() - started) * 1000),
            }
        except Exception as exc:
            errors.append(f"firecrawl({type(exc).__name__}: {exc})")

    # Camada 4: Playwright Stealth (se habilitado/instalado)
    if os.environ.get("JULIA_ENABLE_PLAYWRIGHT_STEALTH", "0") == "1":
        try:
            md_pw, structured_pw = _scrape_via_playwright_stealth(url, timeout=timeout)
            if len(md_pw) >= 120:
                logger.info("Scraper [playwright_stealth] extraiu %d chars de %s", len(md_pw), url)
                return {
                    "url": url,
                    "domain": _domain_of(url),
                    "title": str(structured_pw.get("titulo") or fallback_title).strip(),
                    "markdown": md_pw[:12000],
                    "method": "playwright_stealth",
                    "ok": True,
                    "error": "",
                    "structured": structured_pw,
                    "elapsed_ms": int((time.monotonic() - started) * 1000),
                }
        except Exception as exc:
            errors.append(f"playwright_stealth({type(exc).__name__}: {exc})")

    # Camada 5: Fallback de Snippet (caso a página bloqueie todos os extratores)
    if fallback_snippet and len(fallback_snippet.strip()) >= 40:
        md_fallback = f"# {fallback_title or _domain_of(url)}\nFonte: {url}\n\n{fallback_snippet.strip()}"
        logger.warning(
            "Scraper: usando snippet fallback para %s após falhas (%s)",
            url, "; ".join(errors),
        )
        return {
            "url": url,
            "domain": _domain_of(url),
            "title": fallback_title or _domain_of(url),
            "markdown": md_fallback,
            "method": "snippet_fallback",
            "ok": True,
            "degraded": True,
            "error": "; ".join(errors),
            "structured": {},
            "elapsed_ms": int((time.monotonic() - started) * 1000),
        }

    return {
        "url": url,
        "domain": _domain_of(url),
        "title": fallback_title,
        "markdown": "",
        "method": "failed",
        "ok": False,
        "error": "; ".join(errors) or "extracao_vazia",
        "structured": {},
        "elapsed_ms": int((time.monotonic() - started) * 1000),
    }


def _extract_md_title(md: str) -> str:
    for line in (md or "").splitlines():
        s = line.strip()
        if s.startswith("#"):
            return s.lstrip("#").strip()[:160]
        if s.lower().startswith("title:"):
            return s.split(":", 1)[1].strip()[:160]
    return ""


# ── 3. EXTRAÇÃO DE ATRIBUTOS COMERCIAIS (PREÇO, TAMANHOS, CORES, ESTILOS) ───

def _parse_price_value(raw_num: str, is_br: bool = True) -> float | None:
    try:
        cleaned = raw_num.strip()
        if is_br:
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
        val = float(cleaned)
        return val if val > 0 else None
    except Exception:
        return None


def extract_commercial_attributes(
    markdown_text: str,
    title: str = "",
    url: str = "",
    structured: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Extrai preço, tamanhos, cores, estilos, moeda e disponibilidade do Markdown + JSON-LD."""
    combined = f"{title}\n{markdown_text or ''}"
    lower = combined.lower()
    structured = structured or {}

    price_value: float | None = None
    currency = "BRL"
    availability = "Disponível"
    brand = ""
    sizes: list[str] = []
    colors: list[str] = []
    styles: list[str] = []

    # 1. Tenta extrair de JSON-LD Product/Offer quando disponível
    for node in structured.get("jsonld", []) or []:
        if not isinstance(node, dict):
            continue
        tipo = str(node.get("@type") or "").lower()
        if "product" in tipo:
            if not brand:
                b = node.get("brand")
                brand = str(b.get("name") if isinstance(b, dict) else b or "").strip()
            if node.get("color"):
                c_val = str(node["color"]).strip()
                if c_val and c_val not in colors:
                    colors.append(c_val)
            if node.get("size"):
                s_val = str(node["size"]).strip()
                if s_val and s_val not in sizes:
                    sizes.append(s_val)
            offers = node.get("offers")
            offer_list = offers if isinstance(offers, list) else ([offers] if isinstance(offers, dict) else [])
            for off in offer_list:
                if not isinstance(off, dict):
                    continue
                p_raw = off.get("price") or off.get("lowPrice")
                if p_raw is not None and price_value is None:
                    try:
                        price_value = float(str(p_raw).replace(",", "."))
                        currency = str(off.get("priceCurrency") or "BRL").upper()
                    except Exception:
                        pass
                avail = str(off.get("availability") or "").lower()
                if "outofstock" in avail or "esgotado" in avail:
                    availability = "Esgotado"

    # 2. Extração de Preço no Markdown (R$ / BRL ou USD)
    if price_value is None:
        br_matches = [
            _parse_price_value(m.group(1), is_br=True)
            for m in _PRECO_BR_RE.finditer(combined)
        ]
        br_valid = [v for v in br_matches if v is not None and v >= 1.0]
        if br_valid:
            price_value = min(br_valid)
            currency = "BRL"
        else:
            us_matches = [
                _parse_price_value(m.group(1), is_br=False)
                for m in _PRECO_US_RE.finditer(combined)
            ]
            us_valid = [v for v in us_matches if v is not None and v >= 1.0]
            if us_valid:
                price_value = min(us_valid)
                currency = "USD"

    # 3. Extração de Cores
    for cor in _CORES_CONHECIDAS:
        if re.search(rf"\b{re.escape(cor)}\b", lower):
            norm_cor = cor.capitalize()
            if norm_cor not in colors:
                colors.append(norm_cor)

    # 4. Extração de Tamanhos / Capacidades
    for m in _TAMANHOS_TOKEN_RE.finditer(combined):
        tok = m.group(0).strip()
        if tok and tok not in sizes:
            sizes.append(tok)

    # 5. Extração de Estilos / Variantes
    for est in _ESTILOS_CONHECIDOS:
        est_clean = est.strip()
        if re.search(rf"\b{re.escape(est_clean.lower())}\b", lower):
            norm_est = est_clean.capitalize()
            if norm_est not in styles:
                styles.append(norm_est)

    if any(p in lower for p in ("esgotado", "indisponível", "indisponivel", "sem estoque", "out of stock")):
        availability = "Indisponível"

    formatted_price = (
        f"R$ {price_value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        if (price_value is not None and currency == "BRL")
        else (f"US$ {price_value:,.2f}" if price_value is not None else "Preço sob consulta")
    )

    return {
        "product_name": (title or _domain_of(url) or "Produto").strip()[:140],
        "store": _domain_of(url) or "loja-web",
        "url": url,
        "price": price_value,
        "currency": currency,
        "formatted_price": formatted_price,
        "sizes": sizes[:8] or ["Único / Padrão"],
        "colors": colors[:8] or ["Padrão"],
        "styles": styles[:6] or ["Padrão"],
        "brand": brand,
        "availability": availability,
    }


def _format_products_markdown_table(products: list[dict[str, Any]]) -> str:
    if not products:
        return "_Nenhum produto com dados suficientes foi encontrado._"
    header = (
        "| Produto | Loja | Preço | Tamanhos | Cores | Estilo | Disponibilidade | Link |\n"
        "|---|---|---|---|---|---|---|---|"
    )
    rows = []
    for idx, p in enumerate(products, 1):
        nome = str(p.get("product_name") or "Produto").replace("|", "/")[:65]
        loja = str(p.get("store") or "-").replace("|", "/")
        preco = str(p.get("formatted_price") or "Sob consulta")
        tamanhos = ", ".join(p.get("sizes") or ["Padrão"])[:40]
        cores = ", ".join(p.get("colors") or ["Padrão"])[:40]
        estilos = ", ".join(p.get("styles") or ["Padrão"])[:40]
        disp = str(p.get("availability") or "Disponível")
        url = str(p.get("url") or "")
        link_md = f"[Ver [{idx}]]({url})" if url else "-"
        rows.append(f"| {nome} | {loja} | **{preco}** | {tamanhos} | {cores} | {estilos} | {disp} | {link_md} |")
    return header + "\n" + "\n".join(rows)


# ── 4. FUNÇÕES PRINCIPAIS EXIGIDAS PELO VEXX-AI ─────────────────────────────

def search_and_compare_products(
    query: str,
    max_retries: int = 3,
    max_sites: int = 5,
    timeout: float = 15.0,
    llm_fn: Callable[[str], str] | None = None,
    image: str | None = None,
) -> dict[str, Any]:
    """Busca o mesmo produto em diferentes sites, extrai preços, tamanhos, estilos
    e cores, e formata o retorno em JSON + tabela Markdown estruturada.

    Implementa o Loop Agêntico de Auto-Correção com até `max_retries` tentativas.
    """
    clean_query = (query or "").strip()
    if not clean_query:
        raise ValueError("A query de busca de produtos não pode ser vazia.")

    max_retries = max(1, min(int(max_retries or 3), 3))
    visual_ctx: dict[str, Any] | None = None
    if image and isinstance(image, str) and image.strip():
        try:
            import vision_service
            res_v = vision_service.analisar_imagem(image.strip())
            if res_v and res_v.get("status") == "sucesso":
                visual_ctx = res_v
        except Exception as exc:
            logger.warning("Falha ao analisar imagem comercial: %s", exc)
    attempts_log: list[dict[str, Any]] = []
    extracted_products: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    previous_queries: list[str] = []
    failure_reason = ""

    for attempt in range(1, max_retries + 1):
        sub_queries = decompose_complex_query(
            clean_query,
            mode="product",
            max_queries=3,
            attempt=attempt,
            failure_reason=failure_reason,
            previous_queries=previous_queries,
            llm_fn=llm_fn,
        )
        if attempt == 1 and visual_ctx and visual_ctx.get("tags_busca"):
            v_query = f"{clean_query} {visual_ctx['tags_busca']}".strip()[:100]
            if v_query not in sub_queries and len(sub_queries) < 4:
                sub_queries.append(v_query)
        previous_queries.extend(sub_queries)

        if attempt == 1:
            logger.info(
                "Tentativa 1: Iniciando busca comercial paralela para '%s' com sub-queries=%s",
                clean_query, sub_queries,
            )
        else:
            logger.info(
                "Tentativa %d: Modificando query para %s (motivo anterior: %s)",
                attempt, sub_queries, failure_reason,
            )

        candidates = execute_parallel_searches(sub_queries, max_results_per_query=5, timeout=timeout)
        new_candidates = [c for c in candidates if c.get("url") and c["url"] not in seen_urls]

        if not new_candidates:
            failure_reason = "buscador retornou zero candidatos inéditos"
            attempts_log.append({
                "attempt": attempt,
                "queries": sub_queries,
                "candidates_found": 0,
                "scraped_ok": 0,
                "reason": failure_reason,
            })
            continue

        batch = new_candidates[: max(max_sites, 4)]
        scraped_count = 0

        with ThreadPoolExecutor(max_workers=min(len(batch), 4)) as pool:
            futs = {
                pool.submit(
                    scrape_url_markdown,
                    c["url"],
                    fallback_snippet=c.get("snippet", ""),
                    fallback_title=c.get("title", ""),
                    timeout=timeout,
                ): c
                for c in batch
            }
            for fut in as_completed(futs):
                cand = futs[fut]
                seen_urls.add(cand["url"])
                try:
                    scraped = fut.result()
                    if not scraped.get("ok") or not scraped.get("markdown"):
                        continue
                    scraped_count += 1
                    item = extract_commercial_attributes(
                        scraped["markdown"],
                        title=scraped.get("title") or cand.get("title", ""),
                        url=scraped["url"],
                        structured=scraped.get("structured"),
                    )
                    item["scrape_method"] = scraped.get("method", "unknown")
                    item["snippet"] = cand.get("snippet", "")[:280]
                    extracted_products.append(item)
                except Exception as exc:
                    logger.warning("Erro ao extrair produto de %s: %s", cand.get("url"), exc)

        attempts_log.append({
            "attempt": attempt,
            "queries": sub_queries,
            "candidates_found": len(new_candidates),
            "scraped_ok": scraped_count,
            "products_accumulated": len(extracted_products),
        })

        # Critério de sucesso do Loop Agêntico: pelo menos 2 produtos extraídos (ou 1 com preço confirmado)
        with_price = [p for p in extracted_products if p.get("price") is not None]
        if len(extracted_products) >= 2 and (with_price or attempt >= 2):
            logger.info(
                "Loop Agêntico (Produtos) convergiu na tentativa %d com %d ofertas (%d com preço).",
                attempt, len(extracted_products), len(with_price),
            )
            break
        failure_reason = (
            f"apenas {len(extracted_products)} produto(s) extraído(s) e "
            f"{len(with_price)} com preço explícito"
        )

    # Ordena produtos: primeiro os que têm preço confirmado (do menor para o maior)
    extracted_products.sort(
        key=lambda p: (0 if p.get("price") is not None else 1, p.get("price") or float("inf"))
    )
    final_products = extracted_products[:max_sites]

    priced = [p for p in final_products if p.get("price") is not None]
    best_offer = priced[0] if priced else (final_products[0] if final_products else None)
    price_stats = {
        "min_price": min(p["price"] for p in priced) if priced else None,
        "max_price": max(p["price"] for p in priced) if priced else None,
        "average_price": round(sum(p["price"] for p in priced) / len(priced), 2) if priced else None,
        "offers_with_price": len(priced),
        "total_offers": len(final_products),
    }

    markdown_table = _format_products_markdown_table(final_products)

    # Síntese executiva (com LLM se fornecido, ou determinística)
    synthesis = _synthesize_product_comparison(clean_query, final_products, price_stats, llm_fn=llm_fn)

    return {
        "ok": len(final_products) > 0,
        "mode": "product_comparison",
        "query": clean_query,
        "attempts_used": len(attempts_log),
        "attempts_log": attempts_log,
        "products": final_products,
        "best_offer": best_offer,
        "price_summary": price_stats,
        "markdown_table": markdown_table,
        "analysis": synthesis,
        "generated_at": _now_iso(),
    }


def _synthesize_product_comparison(
    query: str,
    products: list[dict[str, Any]],
    price_stats: dict[str, Any],
    llm_fn: Callable[[str], str] | None = None,
    visual_context: dict[str, Any] | None = None,
) -> str:
    if not products:
        return (
            f"Não foi possível confirmar ofertas estruturadas para '{query}' após "
            "as tentativas de auto-correção."
        )
    if callable(llm_fn):
        try:
            prompt = (
                f"{AGENTIC_SYSTEM_PROMPT}\n\n"
                f"Compare os produtos abaixo encontrados para '{query}':\n"
                f"{json.dumps(products, ensure_ascii=False, indent=2)}\n\n"
                "Escreva um resumo executivo direto destacando o melhor custo-benefício, "
                "variação de preços, disponibilidade de cores/tamanhos e recomendação."
            )
            ans = (effective_llm(prompt) or "").strip()
            if len(ans) >= 40:
                return ans
        except Exception as exc:
            logger.warning("Fallback determinístico na síntese comercial: %s", exc)

    lojas = ", ".join(sorted({p["store"] for p in products if p.get("store")}))
    todas_cores = sorted({c for p in products for c in (p.get("colors") or []) if c != "Padrão"})
    todos_tamanhos = sorted({s for p in products for s in (p.get("sizes") or []) if s != "Único / Padrão"})

    partes = [
        f"Comparativo comercial concluído para **{query}** cruzando **{len(products)} fonte(s)** ({lojas})."
    ]
    if price_stats.get("min_price") is not None:
        melhor = products[0]
        partes.append(
            f"O menor preço identificado foi **{melhor['formatted_price']}** na loja "
            f"**{melhor['store']}** ({melhor['product_name']})."
        )
        if price_stats["max_price"] != price_stats["min_price"]:
            partes.append(
                f"A faixa de preços varia de R$ {price_stats['min_price']:,.2f} a "
                f"R$ {price_stats['max_price']:,.2f} (média de R$ {price_stats['average_price']:,.2f})."
            )
    if todos_tamanhos:
        partes.append(f"Tamanhos/capacidades identificados: {', '.join(todos_tamanhos[:10])}.")
    if todas_cores:
        partes.append(f"Cores disponíveis encontradas: {', '.join(todas_cores[:10])}.")
    return " ".join(partes)


def deep_investigate_topic(
    query: str,
    min_deep_links: int = 3,
    max_retries: int = 3,
    timeout: float = 15.0,
    llm_fn: Callable[[str], str] | None = None,
    image: str | None = None,
) -> dict[str, Any]:
    """Acessa pelo menos `min_deep_links` (padrão 3) links profundos da pesquisa,
    lê o conteúdo interno em Markdown e cruza os dados (previsões, análise de
    mercado, tendências e verificação cruzada).

    Implementa o Loop Agêntico de Auto-Correção com até `max_retries` tentativas.
    """
    clean_query = (query or "").strip()
    if not clean_query:
        raise ValueError("A query de investigação profunda não pode ser vazia.")

    min_deep_links = max(3, int(min_deep_links or 3))
    max_retries = max(1, min(int(max_retries or 3), 3))

    visual_ctx: dict[str, Any] | None = None
    if image and isinstance(image, str) and image.strip():
        try:
            import vision_service
            res_v = vision_service.analisar_imagem(image.strip())
            if res_v and res_v.get("status") == "sucesso":
                visual_ctx = res_v
                v_tags = res_v.get("tags_busca", "")
                if v_tags:
                    logger.info("Deep Research enriquecida com tags visuais (YOLOv8): %s", v_tags)
        except Exception as exc:
            logger.warning("Falha ao analisar imagem visual no Deep Research: %s", exc)

    attempts_log: list[dict[str, Any]] = []
    deep_sources: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    previous_queries: list[str] = []
    failure_reason = ""

    for attempt in range(1, max_retries + 1):
        sub_queries = decompose_complex_query(
            clean_query,
            mode="deep_research",
            max_queries=3,
            attempt=attempt,
            failure_reason=failure_reason,
            previous_queries=previous_queries,
            llm_fn=llm_fn,
        )
        previous_queries.extend(sub_queries)

        if attempt == 1:
            logger.info(
                "Tentativa 1: Iniciando Deep Research para '%s' com sub-queries=%s",
                clean_query, sub_queries,
            )
        else:
            logger.info(
                "Tentativa %d: Modificando query para %s (motivo: %s)",
                attempt, sub_queries, failure_reason,
            )

        candidates = execute_parallel_searches(sub_queries, max_results_per_query=6, timeout=timeout)
        fresh_candidates = [c for c in candidates if c.get("url") and c["url"] not in seen_urls]

        if not fresh_candidates:
            failure_reason = "nenhum link inédito retornado pelos buscadores"
            attempts_log.append({
                "attempt": attempt,
                "queries": sub_queries,
                "candidates_found": 0,
                "deep_links_scraped": len(deep_sources),
                "reason": failure_reason,
            })
            continue

        # Seleciona lote de candidatos garantindo diversidade de domínios
        ordered_batch = _prioritize_diverse_domains(fresh_candidates, limit=max(min_deep_links * 2, 6))

        with ThreadPoolExecutor(max_workers=min(len(ordered_batch), 4)) as pool:
            futs = {
                pool.submit(
                    scrape_url_markdown,
                    cand["url"],
                    fallback_snippet=cand.get("snippet", ""),
                    fallback_title=cand.get("title", ""),
                    timeout=timeout,
                ): cand
                for cand in ordered_batch
            }
            for fut in as_completed(futs):
                cand = futs[fut]
                seen_urls.add(cand["url"])
                try:
                    scraped = fut.result()
                    if not scraped.get("ok") or len(scraped.get("markdown", "")) < 80:
                        continue
                    deep_sources.append({
                        "index": len(deep_sources) + 1,
                        "title": scraped.get("title") or cand.get("title") or _domain_of(scraped["url"]),
                        "url": scraped["url"],
                        "domain": scraped.get("domain") or _domain_of(scraped["url"]),
                        "provider": cand.get("provider", "web"),
                        "matched_query": cand.get("matched_query", clean_query),
                        "scrape_method": scraped.get("method", "direct_html"),
                        "markdown": scraped["markdown"],
                        "key_facts": _extract_key_facts_from_markdown(scraped["markdown"]),
                    })
                except Exception as exc:
                    logger.warning("Falha ao ler link profundo %s: %s", cand.get("url"), exc)

        attempts_log.append({
            "attempt": attempt,
            "queries": sub_queries,
            "candidates_found": len(fresh_candidates),
            "deep_links_scraped": len(deep_sources),
        })

        if len(deep_sources) >= min_deep_links:
            logger.info(
                "Loop Agêntico (Deep Research) atingiu %d links profundos na tentativa %d.",
                len(deep_sources), attempt,
            )
            break

        failure_reason = (
            f"apenas {len(deep_sources)}/{min_deep_links} links profundos extraídos com sucesso"
        )

    # Renumera índices das fontes profundas
    for idx, src in enumerate(deep_sources, 1):
        src["index"] = idx

    cross_analysis = _cross_reference_sources(clean_query, deep_sources)
    report_markdown = _synthesize_deep_report(
        clean_query, deep_sources, cross_analysis, llm_fn=llm_fn, visual_context=visual_ctx
    )

    return {
        "ok": len(deep_sources) > 0,
        "met_min_deep_links": len(deep_sources) >= min_deep_links,
        "mode": "deep_investigation",
        "query": clean_query,
        "attempts_used": len(attempts_log),
        "attempts_log": attempts_log,
        "sources_count": len(deep_sources),
        "sources": deep_sources,
        "cross_reference": cross_analysis,
        "report_markdown": report_markdown,
        "visual_context": visual_ctx,
        "generated_at": _now_iso(),
    }


def _prioritize_diverse_domains(
    candidates: list[dict[str, Any]],
    limit: int = 6,
) -> list[dict[str, Any]]:
    """Prioriza links de domínios distintos para enriquecer o cruzamento de dados."""
    primary: list[dict[str, Any]] = []
    secondary: list[dict[str, Any]] = []
    seen_domains: set[str] = set()
    for c in candidates:
        dom = _domain_of(c.get("url", ""))
        if dom and dom not in seen_domains:
            seen_domains.add(dom)
            primary.append(c)
        else:
            secondary.append(c)
    return (primary + secondary)[:limit]


def _extract_key_facts_from_markdown(markdown: str, max_facts: int = 5) -> list[str]:
    """Extrai sentenças densas em dados (números, percentuais, anos, moedas) do Markdown."""
    facts: list[str] = []
    for raw_line in (markdown or "").splitlines():
        line = re.sub(r"^[\s#*>-]+", "", raw_line).strip()
        if len(line) < 45 or len(line) > 320:
            continue
        if re.search(r"(\d+(?:[.,]\d+)?\s*%|\b202[3-9]\b|R\$|\$|milh|bilh|crescimento|queda|tendência|mercado)", line, re.I):
            facts.append(line)
            if len(facts) >= max_facts:
                break
    if not facts:
        for raw_line in (markdown or "").splitlines():
            line = re.sub(r"^[\s#*>-]+", "", raw_line).strip()
            if 60 <= len(line) <= 280 and not line.startswith("Fonte:"):
                facts.append(line)
                if len(facts) >= max_facts:
                    break
    return facts


def _cross_reference_sources(query: str, sources: list[dict[str, Any]]) -> dict[str, Any]:
    """Cruza os fatos extraídos das fontes profundas para identificar consensos, métricas e domínios."""
    domains = [s["domain"] for s in sources if s.get("domain")]
    unique_domains = list(dict.fromkeys(domains))
    quantitative_mentions: list[dict[str, Any]] = []

    for src in sources:
        for fact in src.get("key_facts", []):
            nums = re.findall(r"\d+(?:[.,]\d+)?(?:\s*%|\s*bilh\w+|\s*milh\w+)?", fact, flags=re.I)
            if nums:
                quantitative_mentions.append({
                    "source_index": src["index"],
                    "domain": src["domain"],
                    "url": src["url"],
                    "numbers": nums[:4],
                    "statement": fact,
                })

    confidence = (
        "alta" if len(unique_domains) >= 3 else ("media" if len(unique_domains) == 2 else "baixa")
    )
    return {
        "independent_domains": unique_domains,
        "independent_domains_count": len(unique_domains),
        "quantitative_evidence": quantitative_mentions[:10],
        "confidence_level": confidence,
    }


def _synthesize_deep_report(
    query: str,
    sources: list[dict[str, Any]],
    cross_analysis: dict[str, Any],
    llm_fn: Callable[[str], str] | None = None,
    visual_context: dict[str, Any] | None = None,
) -> str:
    if not sources:
        return (
            f"Não foi possível extrair conteúdo profundo suficiente para '{query}' "
            "após 3 tentativas de busca e auto-correção."
        )

    effective_llm = llm_fn
    if effective_llm is None:
        try:
            import qwen_llm_service
            def _qwen_synth_wrapper(p: str) -> str:
                r = qwen_llm_service.gerar_resposta_qwen(p, temperatura=0.3, max_tokens=1024)
                return str(r.get("resposta") or "")
            effective_llm = _qwen_synth_wrapper
        except Exception:
            effective_llm = None

    if callable(effective_llm):
        try:
            context_blocks = []
            for s in sources[:6]:
                trecho = s.get("markdown", "")[:2500]
                context_blocks.append(
                    f"=== FONTE [{s['index']}] {s['title']} ({s['url']}) ===\n{trecho}"
                )
            prompt = (
                f"{AGENTIC_SYSTEM_PROMPT}\n\n"
                f"Tópico investigado: {query}\n\n"
                f"{chr(10).join(context_blocks)}\n\n"
                "Elabore um Relatório de Investigação Profunda em Markdown contendo:\n"
                "1. Resumo Executivo\n"
                "2. Cruzamento de Dados e Evidências ([1], [2], [3]...)\n"
                "3. Tendências, Previsões e Implicações de Mercado\n"
                "4. Fontes Consultadas"
            )
            ans = (effective_llm(prompt) or "").strip()
            if len(ans) >= 80:
                return ans
        except Exception as exc:
            logger.warning("Fallback determinístico na síntese profunda: %s", exc)

    # Relatório analítico determinístico estruturado em Markdown
    lines = [
        f"## Relatório de Pesquisa Profunda: {query}",
        "",
        f"**Fontes profundas analisadas:** {len(sources)} | "
        f"**Domínios independentes:** {cross_analysis.get('independent_domains_count', 0)} | "
        f"**Confiança cruzada:** {cross_analysis.get('confidence_level', 'media').upper()}",
        "",
        "### 1. Síntese e Cruzamento de Evidências",
    ]
    if visual_context:
        lines.append("### Evidências Visuais e Análise de Imagem (YOLOv8 + RapidOCR)")
        if visual_context.get("tags_busca"):
            lines.append(f"- **Elementos e Objetos Identificados:** {visual_context['tags_busca']}")
        if visual_context.get("texto_extraido"):
            lines.append(f"- **Texto Lido na Imagem:** {visual_context['texto_extraido']}")
        lines.append("")
    for s in sources:
        fatos = s.get("key_facts") or []
        resumo_fato = fatos[0] if fatos else s.get("markdown", "")[:220].replace("\n", " ")
        lines.append(f"- **[{s['index']}] {s['title']} ({s['domain']}):** {resumo_fato} [{s['index']}]({s['url']})")

    quant = cross_analysis.get("quantitative_evidence") or []
    if quant:
        lines += ["", "### 2. Indicadores Quantitativos e Tendências"]
        for q_item in quant[:6]:
            lines.append(
                f"- [{q_item['source_index']}] ({q_item['domain']}): {q_item['statement']}"
            )

    lines += ["", "### 3. Fontes Verificadas"]
    for s in sources:
        lines.append(f"{s['index']}. [{s['title']}]({s['url']}) — `{s['scrape_method']}`")

    return "\n".join(lines)


# ── 5. DESPACHO ASSÍNCRONO PARA WEBHOOK (ANTI-TIMEOUT) ──────────────────────

def _deliver_webhook_sync(
    webhook_url: str,
    envelope: dict[str, Any],
    secret: str = "",
    timeout: float = 8.0,
    max_attempts: int = 3,
) -> dict[str, Any]:
    """Envia o pacote JSON para o `webhook_url` com assinatura HMAC-SHA256 e retry."""
    research.url_segura(webhook_url)
    raw = json.dumps(envelope, ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "User-Agent": "VEXX-AI-Webhook-Dispatcher/1.0",
        "X-Vexx-Request-Id": str(envelope.get("request_id") or ""),
    }
    signing_secret = (secret or os.environ.get("JULIA_WEBHOOK_SECRET", "")).strip()
    if signing_secret:
        sig = hmac.new(signing_secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
        headers["X-Vexx-Signature"] = f"sha256={sig}"

    last_err = ""
    for attempt in range(1, max_attempts + 1):
        try:
            req = urllib.request.Request(webhook_url, data=raw, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                status = getattr(resp, "status", 200) or 200
                body = resp.read(65536).decode("utf-8", errors="replace")
                logger.info(
                    "Webhook entregue com sucesso para %s na tentativa %d (HTTP %d)",
                    webhook_url, attempt, status,
                )
                return {"delivered": True, "http_status": status, "attempt": attempt, "response": body[:500]}
        except Exception as exc:
            last_err = f"{type(exc).__name__}: {exc}"
            logger.warning(
                "Tentativa %d de entrega ao webhook %s falhou: %s",
                attempt, webhook_url, last_err,
            )
            if attempt < max_attempts:
                time.sleep(0.4 * attempt)

    return {"delivered": False, "error": last_err, "attempts": max_attempts}


def handle_webhook_response(
    data: dict[str, Any],
    webhook_url: str | None = None,
    secret: str = "",
    timeout: float = 8.0,
    background: bool = True,
    on_complete: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Estrutura a resposta final da pesquisa, empacota os dados de forma assíncrona
    e envia para o webhook do VEXX-AI sem bloquear (evitando timeout HTTP).
    """
    if not isinstance(data, dict):
        raise ValueError("`data` deve ser um dicionário estruturado.")

    request_id = str(data.get("request_id") or f"vexx-res-{uuid.uuid4().hex[:12]}")
    target_url = (webhook_url or data.get("webhook_url") or os.environ.get("VEXX_WEBHOOK_URL", "")).strip()

    envelope: dict[str, Any] = {
        "schema": "vexx.research.webhook.v1",
        "request_id": request_id,
        "status": "completed" if data.get("ok", True) else "failed",
        "mode": str(data.get("mode") or "deep_investigation"),
        "query": str(data.get("query") or ""),
        "timestamp": _now_iso(),
        "data": data,
    }

    if not target_url:
        logger.info("Webhook empacotado localmente (request_id=%s, sem callback externo).", request_id)
        return {
            "accepted": True,
            "request_id": request_id,
            "delivery_mode": "inline",
            "envelope": envelope,
        }

    # Valida a URL do webhook antecipadamente para falhar rápido em caso de SSRF/URL inválida
    research.url_segura(target_url)

    if not background:
        delivery = _deliver_webhook_sync(target_url, envelope, secret=secret, timeout=timeout)
        return {
            "accepted": delivery.get("delivered", False),
            "request_id": request_id,
            "delivery_mode": "sync",
            "delivery": delivery,
            "envelope": envelope,
        }

    def _worker():
        res = _deliver_webhook_sync(target_url, envelope, secret=secret, timeout=timeout)
        if callable(on_complete):
            try:
                on_complete(res)
            except Exception:
                pass

    try:
        loop = asyncio.get_running_loop()
        loop.run_in_executor(None, _worker)
        mode_used = "asyncio_executor"
    except RuntimeError:
        t = threading.Thread(target=_worker, name=f"vexx-webhook-{request_id}", daemon=True)
        t.start()
        mode_used = "background_thread"

    logger.info(
        "Webhook agendado em background (%s) para %s (request_id=%s)",
        mode_used, target_url, request_id,
    )
    return {
        "accepted": True,
        "request_id": request_id,
        "delivery_mode": mode_used,
        "webhook_url": target_url,
        "envelope": envelope,
    }
