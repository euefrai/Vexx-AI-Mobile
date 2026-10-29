"""Provedores de busca reais (V5.5) — sem chave, sem scraping agressivo.

Cada provedor usa API pública oficial ou feed oficial (RSS/JSON). Nada de
contornar CAPTCHA, bot-wall ou bloqueio: quando o provedor bloqueia, o
código é `bloqueado` e a busca segue para outro — nunca há bypass.

Contrato de cada achado: {titulo, url, trecho, origem, tipo, meta?}.
Tipos: pagina, noticia, enciclopedia, academico, tecnico, dados, imagem,
livro, saude, referencia.

`buscar(nome, consulta, ...)` levanta ErroProvedor(codigo) quando não há
resultado utilizável, com códigos honestos:
  rede        — falha de rede/DNS/timeout
  bloqueado   — bot-wall/CAPTCHA/403 (sem bypass)
  http        — status HTTP de erro
  formato     — resposta ilegível/HTML inesperado
  tipo        — content-type não suportado
  tamanho     — resposta grande demais
  vazio       — provedor respondeu, mas sem resultados
"""
import base64
import json
import os
import re
import time
import urllib.parse
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone

import free_sources

_SEARCH_AUDIT = ContextVar('search_audit', default=None)
_REQUEST_AUDIT = ContextVar('request_audit', default=None)


def _audit_text(value, limit=240):
    text = str(value or '')[:2000]
    text = re.sub(r'(?i)(?:bearer\s+\S+|(?:api[_-]?key|token|secret|password)\s*[:=]\s*\S+)', '[REDACTED]', text)
    return text[:limit]


def _audit_url(value):
    try:
        u=urllib.parse.urlsplit(str(value or ''))
        if u.scheme not in ('http','https') or not u.hostname:return ''
        # No credentials, fragments, arbitrary query parameters or error bodies.
        return urllib.parse.urlunsplit((u.scheme,u.hostname,u.path,'',''))[:500]
    except ValueError:return ''


@contextmanager
def observe_searches(callback, original_query):
    """Opt-in bounded diagnostics. No disk logging or global owner-shared trace."""
    token=_SEARCH_AUDIT.set((callback,_audit_text(original_query)))
    try:yield
    finally:_SEARCH_AUDIT.reset(token)


def _audit_request(url, *, final='', status=None):
    current=_REQUEST_AUDIT.get()
    if current is None or len(current)>=6:return
    parts=urllib.parse.urlsplit(url)
    allowed={'q','query','search','term','format','count','setlang','cc','hl','gl','ceid','action','list','srsearch','srlimit','limit'}
    params={k:_audit_text(v) for k,v in urllib.parse.parse_qsl(parts.query) if k in allowed}
    current.append({'url':_audit_url(url),'parameters':params,'http_status':status,
                    'final_url':_audit_url(final),'redirected':bool(final and _audit_url(url)!=_audit_url(final))})

MAX_BYTES = 768 * 1024
UA_LEGIVEL = "Mozilla/5.0 (JuliaResearch/1.0; +research-intelligence)"


class ErroProvedor(ValueError):
    def __init__(self, mensagem: str, codigo: str = "erro"):
        super().__init__(mensagem)
        self.codigo = codigo


def _research():
    import research  # import tardio: evita ciclo (research importa este módulo)
    return research


def _baixar(url: str, timeout: float, aceitar: str = "texto", max_bytes: int = MAX_BYTES):
    try:
        result=_research().baixar(url, timeout=timeout, max_bytes=max_bytes, aceitar=aceitar,
                                  user_agent=UA_LEGIVEL)
    except Exception as exc:
        _audit_request(url,status=getattr(exc,'http',None))
        raise
    _audit_request(url,final=result[0])
    return result


def _json(url: str, timeout: float):
    try:
        obj = _research()._baixar_json(url, timeout=timeout, user_agent=UA_LEGIVEL)
    except Exception as exc:
        _audit_request(url,status=getattr(exc,'http',None))
        raise _traduzir(exc)
    _audit_request(url)
    return obj


def _traduzir(exc: Exception) -> ErroProvedor:
    if isinstance(exc, ErroProvedor):
        return exc
    http = getattr(exc, "http", getattr(exc, "code", 0))
    if http == 429:
        # Public error code stays compatible; the diagnostic distinguishes 429.
        error = ErroProvedor("Limite de requisições do provedor (HTTP 429).", "bloqueado")
        error.http, error.categoria = 429, "rate_limited"
        return error
    codigo = getattr(exc, "codigo", "") or type(exc).__name__
    mapa = {"ssrf": "bloqueado", "tipo_bloqueado": "tipo", "redirect": "http",
            "http": "http", "rede": "rede", "tamanho": "tamanho", "formato": "formato",
            "vazio": "vazio", "timeout": "rede", "URLError": "rede",
            "socket.timeout": "rede", "HTTPError": "http", "ResearchErro": "erro",
            "OSError": "rede", "TimeoutError": "rede", "ConnectionError": "rede"}
    traduzido = mapa.get(codigo)
    if not traduzido and isinstance(exc, OSError):  # DNS/reset/pipe: rede ampla
        traduzido = "rede"
    error=ErroProvedor(str(exc)[:200], traduzido or codigo or "erro")
    if http:error.http=http
    return error


def _verificar_bloqueio(pagina: str) -> None:
    if _research().pagina_bloqueada(pagina):
        raise ErroProvedor("Provedor apresentou bot-wall/CAPTCHA (sem bypass).", "bloqueado")


def _limpar(texto, teto: int = 280) -> str:
    import html as _h
    txt = _h.unescape(re.sub(r"<[^>]+>", " ", str(texto or "")))
    return re.sub(r"\s+", " ", txt).strip()[:teto]


def _url_ok(url: str) -> str:
    url = (url or "").strip().replace("&amp;", "&")
    return url[:500] if url.lower().startswith("http") else ""


def buscar_crossref(consulta: str, limite: int = 6, timeout: float = 8.0) -> list:
    """Existing bibliographic normalizer, bounded safe downloader, no retries."""
    import academic_research as academic
    import search_orchestrator as orch
    from datetime import datetime, timezone
    core = _research()
    if core._circuito_fechado("crossref"):
        raise ErroProvedor("Crossref em espera após falha.", "bloqueado")
    q = orch.consulta_cientifica(consulta)
    params = {"query.bibliographic": q, "rows": max(1, min(int(limite), 10)),
              "select": academic.CROSSREF_FIELDS, "filter": "type:journal-article,has-abstract:true"}
    if orch.classificar(consulta)["temporal"]:
        year = datetime.now(timezone.utc).year
        params["filter"] += f",from-pub-date:{year-2}-01-01,until-pub-date:{datetime.now(timezone.utc).date().isoformat()}"
    url = academic.CROSSREF_WORKS_URL + "?" + urllib.parse.urlencode(params)
    try:
        payload = _json(url, timeout)
    except ErroProvedor as exc:
        if exc.codigo in ("bloqueado", "rate_limited"):
            core._circuito_falha("crossref")
        raise
    message = payload.get("message") if isinstance(payload, dict) else None
    items = message.get("items") if isinstance(message, dict) else None
    if not isinstance(items, list):
        raise ErroProvedor("Crossref sem lista de trabalhos.", "formato")
    out = []
    for item in items[:10]:
        if not isinstance(item, dict):
            continue
        record = academic.normalize_crossref(item, url)
        record.update(origem="crossref", tipo="academico", fonte_primaria=True,
                      publication_type=str(item.get("type") or "unknown"))
        if record.get("titulo") and record.get("doi"):
            out.append(record)
    if not out:
        raise ErroProvedor("Crossref sem resultados.", "vazio")
    return out[:limite]


# ── Bing (feed RSS oficial de busca e de notícias) ──────────────────
def buscar_ddg(consulta: str, limite: int = 8, timeout: float = 10.0) -> list:
    """Reuse the existing HTML search adapter; blocked responses stop here."""
    core = _research()
    if core._circuito_fechado("ddg"):
        raise ErroProvedor("DuckDuckGo em espera após bloqueio.", "bloqueado")
    try:
        results = core.buscar_ddg(consulta, max_resultados=limite, timeout=timeout)
    except Exception as exc:
        if getattr(exc, "codigo", "") == "bloqueado":
            core._circuito_falha("ddg")
        raise _traduzir(exc) from None
    if not results:
        if core.status_provedor("ddg").get("bloqueado"):
            core._circuito_falha("ddg")
            raise ErroProvedor("DuckDuckGo bloqueou a pesquisa.", "bloqueado")
        raise ErroProvedor("DuckDuckGo sem resultados.", "vazio")
    return results[:limite]


def buscar_bing(consulta: str, limite: int = 8, timeout: float = 10.0,
                _path: str = "/search", tipo: str = "pagina") -> list:
    q = (consulta or "").strip()[:200]
    if not q:
        raise ErroProvedor("Consulta vazia.", "vazio")
    url = ("https://www.bing.com" + _path + "?" + urllib.parse.urlencode(
        {"q": q, "format": "rss", "count": max(1, min(int(limite), 20)),
         "setlang": "pt-BR", "cc": "BR"}))
    pagina = _baixar(url, timeout, aceitar="feed")[1]
    _verificar_bloqueio(pagina)
    itens = re.findall(r"<item>(.*?)</item>", pagina or "", re.S)
    out = []
    for it in itens:
        titulo = _limpar((re.search(r"<title>(.*?)</title>", it, re.S) or [None, ""])[1], 160)
        link = _url_ok((re.search(r"<link>(.*?)</link>", it, re.S) or [None, ""])[1])
        desc = _limpar((re.search(r"<description>(.*?)</description>", it, re.S) or [None, ""])[1], 300)
        data = _limpar((re.search(r"<pubDate>(.*?)</pubDate>", it, re.S) or [None, ""])[1], 40)
        if not link or "bing.com" in link:
            continue
        if not titulo:
            continue
        out.append({"titulo": titulo, "url": link, "trecho": desc,
                    "origem": "bing" if tipo == "pagina" else "bing-news",
                    "tipo": tipo, "meta": {"publicado_em": data} if data else {}})
        if len(out) >= limite:
            break
    if not out:
        raise ErroProvedor("Bing sem resultados utilizáveis.", "vazio")
    return out


def buscar_bing_news(consulta: str, limite: int = 8, timeout: float = 10.0) -> list:
    return buscar_bing(consulta, limite, timeout, _path="/news/search", tipo="noticia")


def buscar_google_news(consulta: str, limite: int = 8, timeout: float = 10.0) -> list:
    """Public RSS discovery. Aggregator links remain aggregator links, not read evidence."""
    import xml.etree.ElementTree as ET
    import query_intelligence
    request=query_intelligence.analyze(consulta)
    query=request['search_query']
    params=request['parameters']
    if params.get('start_date'):
        query+=' after:'+params['start_date']+' before:'+params['end_date']
    url='https://news.google.com/rss/search?'+urllib.parse.urlencode({'q':query[:240],'hl':'pt-BR','gl':'BR','ceid':'BR:pt-419'})
    page=_baixar(url,timeout,aceitar='feed')[1]
    _verificar_bloqueio(page)
    try: root=ET.fromstring(page)
    except ET.ParseError: raise ErroProvedor('Feed de notícias inválido.','formato') from None
    out=[]
    for node in root.findall('./channel/item')[:max(1,min(20,int(limite)))]:
        link=_url_ok(node.findtext('link',''))
        title=_limpar(node.findtext('title',''),240)
        if not link or not title: continue
        source=node.find('source')
        out.append({'titulo':title,'url':link,'trecho':_limpar(node.findtext('description',''),600),
                    'origem':'google-news','tipo':'noticia','status':'encontrada',
                    'publicador':_limpar(source.text or '',120) if source is not None else '',
                    'publisher_url':_url_ok(source.get('url','')) if source is not None else '',
                    'meta':{'publicado_em':node.findtext('pubDate','')[:80]},'content_scope':'feed_metadata'})
    if not out: raise ErroProvedor('Feed sem notícias correspondentes.','vazio')
    return out


def buscar_feed_preferencial(feed_url, consulta, *, limite=6, timeout=6):
    """Original publisher RSS is discovery; each article still requires reading."""
    import xml.etree.ElementTree as ET
    import query_intelligence as qi
    import search_verticals
    host=urllib.parse.urlsplit(feed_url).hostname
    final,xml=_baixar(feed_url,timeout,aceitar='feed')
    if urllib.parse.urlsplit(final).hostname != host:
        raise ErroProvedor('Feed redirecionou para outro publicador.','redirect')
    try: root=ET.fromstring(xml)
    except ET.ParseError: raise ErroProvedor('Feed inválido.','formato') from None
    request=qi.analyze(consulta)
    out=[]
    for node in root.findall('./channel/item')[:40]:
        link=_url_ok(node.findtext('link',''))
        title=_limpar(node.findtext('title',''),240)
        if not link or not title or urllib.parse.urlsplit(link).hostname != host: continue
        description=node.findtext('description','')
        description=re.sub(r'<p[^>]*>\s*(?:O post|The post)\b.*?(?:apareceu primeiro em|appeared first on).*?</p>\s*$',
                           '',description,flags=re.I|re.S)
        row={'titulo':title,'url':link,'trecho':_limpar(description,1000),
             'origem':'publisher-rss','tipo':'noticia','publicador':host,
             'publicado_em':node.findtext('pubDate','')[:80],
             'content_scope':'article_candidate','source_recovery':{
                 'method':'preferred_publisher_rss','feed_url':final,'state':'original_candidate'}}
        if not search_verticals.assess(request,row)['eligible']: continue
        out.append(row)
        if len(out)>=max(1,min(12,int(limite))):break
    return out


def recuperar_feed_publicador(lead: dict, fetch) -> list:
    """Discover only feeds actually linked by the declared publisher.

    The caller owns the shared deadline/attempt budget for both fetches.
    Returned article URLs are candidates; RSS summaries are never read articles.
    """
    from html.parser import HTMLParser
    import xml.etree.ElementTree as ET
    import search_orchestrator as orch
    home = lead.get('publisher_url') or ''
    host = urllib.parse.urlsplit(home).hostname or ''
    if not host: return []
    class Links(HTMLParser):
        def __init__(self): super().__init__(); self.feeds=[]
        def handle_starttag(self, tag, attrs):
            attr=dict(attrs)
            if tag=='link' and 'alternate' in (attr.get('rel') or '').lower().split() and attr.get('type') in ('application/rss+xml','application/atom+xml'):
                url=urllib.parse.urljoin(home,attr.get('href') or '')
                if urllib.parse.urlsplit(url).hostname==host and url not in self.feeds:
                    self.feeds.append(url)
    final,page=fetch(home,'html')
    if urllib.parse.urlsplit(final).hostname!=host: return []
    links=Links();links.feed(page)
    import web_extract
    title=lead.get('titulo') or ''
    label=lead.get('publicador') or ''
    if label and title.endswith(' - '+label):title=title[:-(len(label)+3)]
    terms=set(orch._termos(title))
    direct=[]
    for link in web_extract.extrair_links(page,final,limite=100):
        target=urllib.parse.urlsplit(link['url']).hostname or ''
        overlap=len(terms & set(orch._termos(link['texto'])))/max(1,len(terms))
        is_article=urllib.parse.urlsplit(link['url']).path not in ('','/') and not orch._pagina_de_indice({'url':link['url']})
        if (target==host or target.endswith('.'+host)) and overlap>=0.6 and is_article and not any(row['url']==link['url'] for row in direct):
            direct.append({'titulo':link['texto'],'url':link['url'],'trecho':'',
                'origem':'publisher-feed','tipo':'noticia','content_scope':'article_candidate',
                'source_recovery':{'method':'publisher_link','publisher_url':home,
                    'feed_url':lead.get('url',''),'state':'original_candidate'}})
    if direct or not links.feeds: return direct[:2]
    feed_url,xml=fetch(links.feeds[0],'feed')
    try: root=ET.fromstring(xml)
    except ET.ParseError: return []
    out=[]
    entries=root.findall('./channel/item') or root.findall('{http://www.w3.org/2005/Atom}entry')
    for node in entries[:30]:
        atom='{http://www.w3.org/2005/Atom}'
        headline=node.findtext('title') or node.findtext(atom+'title') or ''
        url=node.findtext('link') or ''
        if not url:
            link=next((n for n in node.findall(atom+'link') if n.get('rel','alternate')=='alternate'),None)
            if link is not None:url=link.get('href','')
        url=urllib.parse.urljoin(feed_url,url)
        target=urllib.parse.urlsplit(url).hostname or ''
        overlap=len(terms & set(orch._termos(headline)))/max(1,len(terms))
        if not (target==host or target.endswith('.'+host)) or overlap<0.6: continue
        out.append({'titulo':_limpar(headline,240),'url':url,'trecho':'',
            'origem':'publisher-feed','tipo':'noticia', 'publicador':label,
            'publicado_em':node.findtext('pubDate') or node.findtext(atom+'published') or '',
            'date_source':'publisher_feed', 'content_scope':'article_candidate',
            'source_recovery':{'method':'publisher_feed_autodiscovery','feed_url':lead.get('url',''),
                'publisher_url':home,'original_feed_url':feed_url,'state':'original_candidate'}})
    return out[:2]


# ── Marginalia (índice independente; interface texto oficial) ───────
_MARG_SKIP = re.compile(r"(marginalia|about\.marginalia|donate|explore/random)", re.I)


def buscar_marginalia(consulta: str, limite: int = 8, timeout: float = 12.0) -> list:
    q = (consulta or "").strip()[:200]
    if not q:
        raise ErroProvedor("Consulta vazia.", "vazio")
    url = "https://old-search.marginalia.nu/search?" + urllib.parse.urlencode({"query": q})
    pagina = _baixar(url, timeout)[1]
    _verificar_bloqueio(pagina)
    # A successful HTTP response may still contain navigation/licence links.
    # Reuse the inert HTML parser; never follow challenge scripts or tokens.
    import web_extract as wx
    parser = wx._MiniDom()
    parser.feed((pagina or '')[:MAX_BYTES])
    out, vistos = [], set()
    for node in wx._descendentes(parser.raiz):
        if node.tag != 'a':
            continue
        parent = node.pai
        excluded = 'license' in str(node.attrs.get('rel') or '').lower().split()
        while parent is not None and not excluded:
            excluded = parent.tag in wx._IGNORAR
            parent = parent.pai
        if excluded:
            continue
        href, texto = node.attrs.get('href') or '', wx._texto_bloco(node)
        if not href.startswith(('https://', 'http://')):
            continue
        if _MARG_SKIP.search(href) or _MARG_SKIP.search(texto or ""):
            continue
        titulo = _limpar(texto, 200)
        link = _url_ok(href)
        if not link or link in vistos:
            continue
        # a interface antiga repete o link como texto do próprio <a>: ignora isso
        if titulo and titulo.startswith("http"):
            continue
        if not titulo or len(titulo) < 4:
            continue
        vistos.add(link)
        out.append({"titulo": titulo, "url": link, "trecho": "",
                    "origem": "marginalia", "tipo": "pagina", "meta": {}})
        if len(out) >= limite:
            break
    if not out:
        raise ErroProvedor("Marginalia sem resultados (índice pequeno).", "vazio")
    return out


# ── Wikipédia (opensearch oficial, já existente) ────────────────────
def buscar_wikipedia(consulta: str, limite: int = 4, timeout: float = 10.0) -> list:
    try:
        achados = _research().buscar_wikipedia(consulta, max_resultados=limite, timeout=timeout)
    except Exception as exc:
        raise _traduzir(exc)
    if not achados:
        raise ErroProvedor("Wikipédia sem verbete correspondente.", "vazio")
    for a in achados:
        a.setdefault("tipo", "enciclopedia")
    return achados


# ── Stack Exchange (API oficial; técnico) ──────────────────────────
_SE_SITES = ("stackoverflow", "pt.stackoverflow", "superuser", "serverfault", "askubuntu")


def buscar_stackexchange(consulta: str, limite: int = 5, timeout: float = 12.0) -> list:
    q = (consulta or "").strip()[:180]
    if not q:
        raise ErroProvedor("Consulta vazia.", "vazio")
    out, ultimo = [], None
    prazo = time.monotonic() + max(0.1, timeout)
    for site in _SE_SITES:
        restante = prazo - time.monotonic()
        if restante <= 0:
            ultimo = ErroProvedor("Prazo da busca Stack Exchange esgotado.", "rede")
            break
        url = ("https://api.stackexchange.com/2.3/search/advanced?" +
               urllib.parse.urlencode({"order": "desc", "sort": "relevance", "q": q,
                                       "site": site, "pagesize": max(1, min(limite, 8)),
                                       "filter": "withbody"}))
        try:
            dados = _json(url, min(timeout, restante))
        except ErroProvedor as exc:
            ultimo = exc
            if exc.codigo in ("bloqueado", "rate_limited"):
                break  # Same API host: another site is not a valid bypass.
            continue
        if dados.get("backoff") or dados.get("error_id") == 502:
            raise ErroProvedor("Stack Exchange solicitou pausa.", "rate_limited")
        for it in (dados.get("items") or [])[:limite]:
            link = _url_ok(it.get("link"))
            titulo = _limpar(it.get("title"), 160)
            if not link or not titulo:
                continue
            respondida = "respondida" if it.get("is_answered") else "sem resposta aceita"
            tags = ", ".join((it.get("tags") or [])[:4])
            trecho = f"{_limpar(it.get('body'), 220)} · {respondida} · {tags}".strip(" ·")[:300]
            out.append({"titulo": titulo, "url": link, "trecho": trecho,
                        "origem": "stackexchange", "tipo": "tecnico",
                        "meta": {"site": site, "score": it.get("score")}})
        if out:
            return out
    if ultimo is not None:
        raise ultimo
    raise ErroProvedor("Stack Exchange sem resultados.", "vazio")


# ── Hacker News (Algolia; técnico/comunidade) ──────────────────────
def buscar_hn(consulta: str, limite: int = 5, timeout: float = 10.0) -> list:
    q = (consulta or "").strip()[:180]
    if not q:
        raise ErroProvedor("Consulta vazia.", "vazio")
    url = "https://hn.algolia.com/api/v1/search?" + urllib.parse.urlencode(
        {"query": q, "tags": "story", "hitsPerPage": max(1, min(limite, 10))})
    dados = _json(url, timeout)
    out = []
    for h in (dados.get("hits") or [])[:limite]:
        titulo = _limpar(h.get("title") or h.get("story_title"), 160)
        link = _url_ok(h.get("url")) or (
            f"https://news.ycombinator.com/item?id={h.get('objectID')}" if h.get("objectID") else "")
        if not titulo or not link:
            continue
        pontos = h.get("points")
        comentarios = h.get("num_comments")
        trecho = _limpar(h.get("story_text"), 200) or \
            f"HN: {pontos or 0} pontos · {comentarios or 0} comentários"
        out.append({"titulo": titulo, "url": link, "trecho": trecho,
                    "origem": "hn", "tipo": "tecnico",
                    "meta": {"pontos": pontos, "comentarios": comentarios}})
    if not out:
        raise ErroProvedor("HN sem resultados.", "vazio")
    return out


# ── PubMed (E-utilities oficial; saúde/ciência) ────────────────────
def buscar_pubmed(consulta: str, limite: int = 5, timeout: float = 12.0) -> list:
    q = (consulta or "").strip()[:180]
    if not q:
        raise ErroProvedor("Consulta vazia.", "vazio")
    busca = _json("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?" +
                  urllib.parse.urlencode({"db": "pubmed", "term": q, "retmode": "json",
                                          "retmax": max(1, min(limite, 10)),
                                          "sort": "relevance"}), timeout)
    ids = ((busca.get("esearchresult") or {}).get("idlist") or [])[:limite]
    if not ids:
        raise ErroProvedor("PubMed sem resultados.", "vazio")
    resumo = _json("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?" +
                   urllib.parse.urlencode({"db": "pubmed", "id": ",".join(ids),
                                           "retmode": "json"}), timeout)
    res = resumo.get("result") or {}
    out = []
    for pid in ids:
        item = res.get(pid) or {}
        titulo = _limpar(item.get("title"), 200)
        if not titulo:
            continue
        autores = ", ".join((item.get("authors") or [{}])[0].get("name", "") for _ in [0])
        out.append({"titulo": titulo,
                    "url": f"https://pubmed.ncbi.nlm.nih.gov/{pid}/",
                    "trecho": f"{_limpar(item.get('source'), 80)} · "
                              f"{_limpar(item.get('pubdate'), 20)} · {autores}".strip(" ·"),
                    "origem": "pubmed", "tipo": "saude",
                    "meta": {"pmid": pid}})
    if not out:
        raise ErroProvedor("PubMed sem resultados utilizáveis.", "vazio")
    return out


# ── Open Library (API oficial; livros) ─────────────────────────────
def buscar_openlibrary(consulta: str, limite: int = 5, timeout: float = 12.0) -> list:
    q = (consulta or "").strip()[:180]
    if not q:
        raise ErroProvedor("Consulta vazia.", "vazio")
    dados = _json("https://openlibrary.org/search.json?" + urllib.parse.urlencode(
        {"q": q, "limit": max(1, min(limite, 10)),
         "fields": "key,title,author_name,first_publish_year,publisher"}), timeout)
    out = []
    for d in (dados.get("docs") or [])[:limite]:
        chave = str(d.get("key") or "")
        titulo = _limpar(d.get("title"), 200)
        if not chave.startswith("/") or not titulo:
            continue
        autores = ", ".join((d.get("author_name") or [])[:2])
        ano = d.get("first_publish_year")
        out.append({"titulo": titulo, "url": f"https://openlibrary.org{chave}"[:500],
                    "trecho": f"{autores}{' · ' + str(ano) if ano else ''}"[:200],
                    "origem": "openlibrary", "tipo": "livro", "meta": {}})
    if not out:
        raise ErroProvedor("Open Library sem resultados.", "vazio")
    return out


# ── Banco Mundial (API oficial; estatísticas) ──────────────────────
def buscar_worldbank(consulta: str, limite: int = 5, timeout: float = 12.0) -> list:
    q = (consulta or "").strip()[:120]
    if not q:
        raise ErroProvedor("Consulta vazia.", "vazio")
    # The indicator catalogue does not implement free-text `q`. It otherwise
    # returns its first page (poverty indicators) for unrelated population asks.
    codes = re.findall(r'\b[A-Z][A-Z0-9]*(?:\.[A-Z0-9]+){2,}\b', q)
    if len(set(codes)) == 1:
        indicator = codes[0]
    elif re.search(r'\b(?:population|popula[çc][aã]o)\b', q, re.I) and not re.search(
            r'\b(?:growth|crescimento|urban[ao]?s?|rural|rurais|male|female|masculin[ao]|feminin[ao]|idade|age|densidade|density)\b', q, re.I):
        indicator = 'SP.POP.TOTL'
    else:
        raise ErroProvedor("Banco Mundial: consulta sem código de indicador reconhecido.", "vazio")
    dados = _json("https://api.worldbank.org/v2/indicator/" + indicator + '?' + urllib.parse.urlencode(
        {"format": "json", "per_page": max(1, min(limite, 10))}), timeout)
    linhas = dados[1] if isinstance(dados, list) and len(dados) > 1 else []
    out = []
    for it in (linhas or [])[:limite]:
        if not isinstance(it, dict):
            continue
        nome = _limpar(it.get("name"), 200)
        codigo = str(it.get("id") or "")
        if not nome or codigo != indicator:
            continue
        out.append({"titulo": nome,
                    "url": f"https://data.worldbank.org/indicator/{codigo}"[:500],
                    "trecho": _limpar(it.get("note"), 200),
                    "origem": "worldbank", "tipo": "dados", "content_scope": "metadata_only",
                    "meta": {"indicador": codigo}})
    if not out:
        raise ErroProvedor("Banco Mundial sem indicador correspondente.", "vazio")
    return out


# ── Banco Central do Brasil (API oficial; séries e câmbio) ─────────
_BCB_SERIES = (
    (re.compile(r"(d[oó]lar|ptax|c[aâ]mbio)", re.I), 1, "Dólar comercial (PTAX venda)"),
    (re.compile(r"\bselic\b", re.I), 432, "Taxa Selic meta"),
    (re.compile(r"\bipca\b", re.I), 433, "IPCA (variação mensal)"),
    (re.compile(r"\bcdi\b", re.I), 12, "CDI (taxa diária)"),
)


def buscar_bcb(consulta: str, limite: int = 3, timeout: float = 12.0) -> list:
    q = (consulta or "").strip()[:120]
    if not q:
        raise ErroProvedor("Consulta vazia.", "vazio")
    out = []
    for rx, codigo, rotulo in _BCB_SERIES:
        if not rx.search(q):
            continue
        dados = _json(f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}"
                      f"/dados/ultimos/{max(1, min(limite, 5))}?formato=json", timeout)
        if not isinstance(dados, list) or not dados:
            continue
        ultimo = dados[-1] if isinstance(dados[-1], dict) else {}
        if not ultimo.get("data"):
            continue
        out.append({"titulo": f"{rotulo} — série SGS {codigo}",
                    "url": f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados",
                    "trecho": f"Valor oficial mais recente: {ultimo.get('valor')} "
                              f"em {ultimo.get('data')} (API do Banco Central do Brasil)",
                    "origem": "bcb", "tipo": "dados",
                    "meta": {"serie": codigo, "valor": ultimo.get("valor"),
                             "data": ultimo.get("data")}})
    if not out:
        raise ErroProvedor("BCB: nenhuma série conhecida para esta consulta.", "vazio")
    return out


# ── Wikimedia Commons (API oficial; imagens) ───────────────────────
def buscar_commons(consulta: str, limite: int = 6, timeout: float = 12.0) -> list:
    q = re.sub(r'\b(imagens?|fotos?|fotografias?|licenciad[oa]s?|com licen[cç]a|pesquise|encontre|mostre)\b',
               ' ', consulta or '', flags=re.I)
    q = re.sub(r'\b(d[aeo]s?|em|para)\b', ' ', q, flags=re.I)
    q = re.sub(r'\s+', ' ', q).strip()[:160]
    if not q:
        raise ErroProvedor("Consulta vazia.", "vazio")
    dados = _json("https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(
        {"action": "query", "generator": "search", "gsrsearch": q, "gsrnamespace": "6",
         "gsrlimit": max(1, min(limite, 10)), "prop": "imageinfo",
         "iiprop": "url|size|mime|extmetadata", "iiurlwidth": "640", "format": "json"}), timeout)
    paginas = ((dados.get("query") or {}).get("pages") or {})
    out = []
    for _pid, pg in list(paginas.items()):
        if not isinstance(pg, dict):
            continue
        ii = (pg.get("imageinfo") or [{}])
        ii = ii[0] if ii else {}
        ext = ii.get('extmetadata') or {}
        def field(name, limit=240):
            value = ext.get(name) or {}
            return _limpar(value.get('value') if isinstance(value, dict) else '', limit)
        titulo = _limpar(str(pg.get("title", "")).replace("File:", ""), 160)
        img = _url_ok(ii.get("thumburl") or ii.get("url"))
        pagina = _url_ok(pg.get("descriptionurl") or ii.get("descriptionurl"))
        if not titulo or not img:
            continue
        out.append({"titulo": titulo, "url": img,
                    'license':field('LicenseShortName'), 'attribution':field('Artist'),
                    'description':field('ImageDescription',600),
                    "trecho": f"{ii.get('width')}x{ii.get('height')} · {ii.get('mime')}"
                              + (f" · página: {pagina}" if pagina else ""),
                    "origem": "commons", "tipo": "imagem",
                    "meta": {"pagina": pagina, "mime": ii.get("mime"),
                             "largura": ii.get("width"), "altura": ii.get("height"),
                             'license_url':_url_ok(field('LicenseUrl',500)),
                             'thumb_url':_url_ok(ii.get('thumburl')), 'original_url':_url_ok(ii.get('url'))}})
    if not out:
        raise ErroProvedor("Commons sem imagens para esta busca.", "vazio")
    return out


# ── Registro de provedores ─────────────────────────────────────────
# `classes`: assuntos em que o provedor é forte; `peso`: prioridade de
# ranqueamento (0-10) — medido por uso real, não por preferência estética.
CLASSE_GERAL = "geral"
CLASSE_TECNICA = "tecnico"
CLASSE_ACADEMICA = "academico"
CLASSE_NOTICIA = "noticias"
CLASSE_ENCICLOPEDIA = "enciclopedia"
CLASSE_DADOS = "dados"
CLASSE_IMAGEM = "imagens"
CLASSE_LIVRO = "livros"
CLASSE_SAUDE = "saude"


def _provedor_disponivel(nome: str, meta: dict) -> bool:
    """Optional providers are advertised only when their key/config exists.

    Keyless free APIs can be disabled globally with ``JULIA_FREE_APIS=0``.
    A provider without ``classes`` (test fixtures) is still considered.
    """
    requer = meta.get("requer")
    if requer and not os.getenv(requer, "").strip():
        return False
    if meta.get("gratuito"):
        desligado = os.getenv("JULIA_FREE_APIS", "1").strip().lower()
        if desligado in ("0", "false", "off", "no"):
            return False
    return True


PROVEDORES: dict = {
    "crossref": {"rotulo": "Crossref (metadados públicos)", "classes": (CLASSE_ACADEMICA,),
                 "tipo": "academico", "peso": 8.0, "fn": buscar_crossref},
    "ddg": {"rotulo": "DuckDuckGo", "classes": (CLASSE_GERAL, CLASSE_TECNICA, CLASSE_ACADEMICA),
            "tipo": "pagina", "peso": 8.0, "fn": buscar_ddg},
    "bing": {"rotulo": "Bing (feed oficial)", "classes": (CLASSE_GERAL, CLASSE_NOTICIA),
             "tipo": "pagina", "peso": 8.0, "fn": buscar_bing},
    "marginalia": {"rotulo": "Marginalia Search", "classes": (CLASSE_GERAL,),
                   "tipo": "pagina", "peso": 5.0, "fn": buscar_marginalia},
    "wikipedia": {"rotulo": "Wikipédia", "classes": (CLASSE_ENCICLOPEDIA, CLASSE_GERAL),
                  "tipo": "enciclopedia", "peso": 7.0, "fn": buscar_wikipedia},
    "bing-news": {"rotulo": "Bing Notícias (feed oficial)",
                  "classes": (CLASSE_NOTICIA,), "tipo": "noticia", "peso": 7.0,
                  "fn": buscar_bing_news},
    "google-news": {"rotulo": "Google Notícias (RSS público)",
                    "classes": (CLASSE_NOTICIA,), "tipo": "noticia", "peso": 7.0,
                    "fn": buscar_google_news},
    "stackexchange": {"rotulo": "Stack Exchange (API oficial)",
                      "classes": (CLASSE_TECNICA,), "tipo": "tecnico", "peso": 8.0,
                      "fn": buscar_stackexchange},
    "hn": {"rotulo": "Hacker News (Algolia)", "classes": (CLASSE_TECNICA, CLASSE_NOTICIA),
           "tipo": "tecnico", "peso": 5.5, "fn": buscar_hn},
    "pubmed": {"rotulo": "PubMed (E-utilities)", "classes": (CLASSE_SAUDE, CLASSE_ACADEMICA),
               "tipo": "saude", "peso": 8.0, "fn": buscar_pubmed},
    "openlibrary": {"rotulo": "Open Library", "classes": (CLASSE_LIVRO,),
                    "tipo": "livro", "peso": 6.0, "fn": buscar_openlibrary},
    "worldbank": {"rotulo": "Banco Mundial", "classes": (CLASSE_DADOS,),
                  "tipo": "dados", "peso": 7.5, "fn": buscar_worldbank},
    "bcb": {"rotulo": "Banco Central do Brasil", "classes": (CLASSE_DADOS,),
            "tipo": "dados", "peso": 8.0, "fn": buscar_bcb},
    "commons": {"rotulo": "Wikimedia Commons", "classes": (CLASSE_IMAGEM,),
                "tipo": "imagem", "peso": 6.0, "fn": buscar_commons},
    # Free-tier APIs added in the public-sources phase. All are additive and
    # fail closed: a quota error or malformed payload never blocks fallback.
    "openalex": {"rotulo": "OpenAlex (metadados acadêmicos)",
                 "classes": (CLASSE_ACADEMICA,), "tipo": "academico", "peso": 9.0,
                 "fn": free_sources.buscar_openalex, "gratuito": True,
                 "limites": "keyless ~10 req/s; chave gratuita opcional eleva a cota"},
    "arxiv": {"rotulo": "arXiv (Atom público)", "classes": (CLASSE_ACADEMICA,),
              "tipo": "academico", "peso": 8.5, "fn": free_sources.buscar_arxiv,
              "gratuito": True, "limites": "keyless; ~1 requisição a cada 3 s recomendada"},
    "github": {"rotulo": "GitHub (busca de repositórios)",
               "classes": (CLASSE_TECNICA,), "tipo": "tecnico", "peso": 8.0,
               "fn": free_sources.buscar_github, "gratuito": True,
               "limites": "10 buscas/min sem token; GITHUB_TOKEN opcional eleva o limite"},
    "brasilapi": {"rotulo": "BrasilAPI (CEP/CNPJ)", "classes": (CLASSE_DADOS,),
                  "tipo": "dados", "peso": 9.0, "fn": free_sources.buscar_brasilapi,
                  "gratuito": True, "limites": "keyless; uma consulta por CEP/CNPJ explícito"},
    "coingecko": {"rotulo": "CoinGecko (mercado cripto)", "classes": (CLASSE_DADOS,),
                  "tipo": "dados", "peso": 9.0, "fn": free_sources.buscar_coingecko,
                  "gratuito": True, "limites": "keyless/demo; cotação pública, sem recomendação"},
    "brave": {"rotulo": "Brave Search (API opcional)", "classes": (
                  CLASSE_GERAL, CLASSE_NOTICIA, CLASSE_TECNICA, CLASSE_ACADEMICA,
                  CLASSE_ENCICLOPEDIA), "tipo": "pagina", "peso": 9.5,
              "fn": free_sources.buscar_brave, "requer": "BRAVE_SEARCH_API_KEY",
              "gratuito": True,
              "limites": "crédito gratuito mensal; desativado sem chave; quota do provedor"},
}


# ── Métricas por provedor (V5.7 F3) ────────────────────────────────
_METRICAS: dict = {}


def _metrica(nome: str, t0: float, *, resultados: int = 0, erro: str = "") -> None:
    m = _METRICAS.setdefault(nome, {"chamadas": 0, "ok": 0, "vazio": 0,
                                    "resultados": 0, "erros": {}, "ms_total": 0.0})
    m["chamadas"] += 1
    m["ms_total"] += max(0.0, (time.monotonic() - t0) * 1000.0)
    if erro:
        m["erros"][erro] = m["erros"].get(erro, 0) + 1
    elif resultados:
        m["ok"] += 1
        m["resultados"] += int(resultados)
    else:
        m["vazio"] += 1


def capacidades() -> dict:
    """Declared adapter fields, never an E2E or inventory guarantee."""
    measured = metricas()
    out = {}
    for name, meta in PROVEDORES.items():
        fields = ['title', 'url', 'snippet']
        if name in ('google-news', 'bing-news'):
            fields += ['published_at']
        if name == 'google-news':
            fields += ['publisher']
        if name in ('crossref', 'openalex'):
            fields += ['doi', 'authors', 'year', 'abstract', 'pdf_url', 'license']
        if name == 'openalex':
            fields += ['open_access', 'citation_count']
        if name == 'arxiv':
            fields += ['authors', 'year', 'published_at', 'doi', 'pdf_url']
        if name == 'github':
            fields += ['stars', 'language', 'updated_at', 'topics', 'license']
        if name == 'brasilapi':
            fields += ['cep', 'cnpj', 'address', 'ibge', 'coordinates', 'cnae', 'situacao']
        if name == 'coingecko':
            fields += ['price_brl', 'price_usd', 'change_24h_pct',
                       'market_cap_rank', 'updated_at']
        if name == 'brave':
            fields += ['age', 'hostname']
        if name == 'bcb':
            fields += ['rate', 'date']
        if name == 'commons':
            fields += ['media_url', 'media_type']
        requer = meta.get('requer')
        out[name] = {'categories': list(meta['classes']), 'declared_fields': fields,
                     'auth': 'optional_key' if requer else 'public_adapter_no_key',
                     'key_env': requer,
                     'access': 'metadata_or_public_search',
                     'license': 'source_specific; abstracts/media may have separate rights',
                     'commercial_use': 'not_assessed', 'freshness': 'source_declared_not_guaranteed',
                     'free_tier': bool(meta.get('gratuito')),
                     'limits': meta.get('limites') or (
                         'existing timeout, byte limit, circuit breaker; no private inventory'),
                     'observed': measured.get(name, {}), 'e2e_verified_fields': []}
    return out


def metricas() -> dict:
    """Métricas cumulativas por provedor (desde o início do processo)."""
    out = {}
    for nome in sorted(_METRICAS):
        m = _METRICAS[nome]
        out[nome] = {"chamadas": m["chamadas"], "ok": m["ok"], "vazio": m["vazio"],
                     "resultados": m["resultados"], "erros": dict(m["erros"]),
                     "ms_medio": round(m["ms_total"] / m["chamadas"], 1)
                     if m["chamadas"] else 0.0}
    return out


def _reset_metricas() -> None:
    """Zera métricas (bateria de testes / medição antes-depois)."""
    _METRICAS.clear()


def disponiveis(classes=None) -> list:
    """Nomes de provedores (filtrados por classe de assunto, se pedido)."""
    nomes = []
    for nome, meta in PROVEDORES.items():
        if not _provedor_disponivel(nome, meta):
            continue
        if classes and not (set(classes) & set(meta.get("classes") or (CLASSE_GERAL,))):
            continue
        nomes.append(nome)
    return sorted(nomes, key=lambda n: -PROVEDORES[n].get("peso", 0.0))


def buscar(nome: str, consulta: str, limite: int = 6, timeout: float = 10.0) -> list:
    audit=_SEARCH_AUDIT.get()
    if audit is None:return _buscar_impl(nome,consulta,limite,timeout)
    requests=[];token=_REQUEST_AUDIT.set(requests);started=time.monotonic()
    row={'original_query':audit[1],'adapter_query':_audit_text(consulta),'provider':nome,
         'at':datetime.now(timezone.utc).isoformat(),'limit':limite,'timeout_seconds':timeout}
    try:
        items=_buscar_impl(nome,consulta,limite,timeout)
        row.update(classification='UNJUDGED_DISCOVERY' if items else 'PROVIDER_EMPTY',
            result_count=len(items),results=[{'title':_audit_text(i.get('titulo'),160),'url':_audit_url(i.get('url'))} for i in items[:20]])
        return items
    except Exception as exc:
        http=getattr(exc,'http',None);code=getattr(exc,'codigo','erro')
        row.update(http_status=http,error_code=code,result_count=0,
            classification='PROVIDER_RATE_LIMITED' if http==429 else
            'PROVIDER_BLOCKED' if code=='bloqueado' else 'RESULT_PARSE_ERROR' if code=='formato' else
            'PROVIDER_EMPTY' if code=='vazio' else 'PROVIDER_ERROR')
        raise
    finally:
        _REQUEST_AUDIT.reset(token)
        row.update(requests=requests,latency_ms=round((time.monotonic()-started)*1000,2),
                   transport_scope='observed adapter helpers only; null HTTP status means not exposed, never assumed 200')
        try:audit[0](row)
        except Exception:
            import warnings
            warnings.warn('Search audit observer failed',RuntimeWarning,stacklevel=2)


def _buscar_impl(nome: str, consulta: str, limite: int = 6, timeout: float = 10.0) -> list:
    """Executa um provedor; levanta ErroProvedor com código honesto.

    Cada execução alimenta as métricas cumulativas (`metricas()`).
    """
    meta = PROVEDORES.get(nome)
    if not meta:
        raise ErroProvedor(f"Provedor desconhecido: {nome}", "indisponivel")
    t0 = time.monotonic()
    core = _research()
    if core._circuito_fechado(nome):
        _metrica(nome, t0, erro='circuit_open')
        raise ErroProvedor('Provedor em espera após bloqueio; sem nova requisição.', 'bloqueado')
    if not _provedor_disponivel(nome, meta):
        _metrica(nome, t0, erro='indisponivel')
        raise ErroProvedor(f'{nome} não configurado ou desativado.', 'indisponivel')
    try:
        achados = meta["fn"](consulta, limite=limite, timeout=timeout) or []
    except ErroProvedor as exc:
        if exc.codigo in ('bloqueado', 'rate_limited'):
            core._circuito_falha(nome)
        _metrica(nome, t0, erro=exc.codigo or "erro")
        raise
    except Exception as exc:
        trad = _traduzir(exc)
        if trad.codigo in ('bloqueado', 'rate_limited'):
            core._circuito_falha(nome)
        _metrica(nome, t0, erro=trad.codigo or "erro")
        raise trad
    for a in achados:
        a.setdefault("origem", nome)
        a.setdefault("tipo", meta["tipo"])
        a.setdefault("trecho", "")
        a.setdefault("meta", {})
    _metrica(nome, t0, resultados=len(achados))
    return achados


def diagnosticar(consulta: str = "notebook", timeout: float = 12.0) -> list:
    """Sonda cada provedor (uso real, sem bypass) para relatório de auditoria.

    Cada linha carrega o acumulado de `metricas()` do provedor até este ponto
    (chamadas/ok/vazio/erros/latência média) — medição contínua do processo,
    sempre aditiva ao resultado anterior.
    """
    out = []
    for nome in disponiveis():
        t0 = time.time()
        try:
            achados = buscar(nome, consulta, limite=2, timeout=timeout)
            out.append({"provedor": nome, "estado": "ok", "resultados": len(achados),
                        "segundos": round(time.time() - t0, 2),
                        "metricas": metricas().get(nome, {}),
                        "exemplo": (achados[0].get("titulo") or "")[:80]})
        except ErroProvedor as exc:
            out.append({"provedor": nome, "estado": exc.codigo, "resultados": 0,
                        "segundos": round(time.time() - t0, 2),
                        "metricas": metricas().get(nome, {}),
                        "detalhe": str(exc)[:160]})
        except Exception as exc:  # nunca derruba o diagnóstico
            out.append({"provedor": nome, "estado": type(exc).__name__, "resultados": 0,
                        "segundos": round(time.time() - t0, 2),
                        "metricas": metricas().get(nome, {}),
                        "detalhe": str(exc)[:160]})
    return out


def _b64_url(valor: str) -> str:
    """Utilitário interno: decodifica URLs ofuscadas (ex.: Bing ck/a?u=a1..)."""
    bruto = (valor or "").strip()
    if bruto.startswith("a1"):
        bruto = bruto[2:]
    bruto = bruto.replace("-", "+").replace("_", "/")
    bruto += "=" * (-len(bruto) % 4)
    try:
        return base64.b64decode(bruto).decode("utf-8", "ignore")
    except Exception:
        return ""


def _json_or_none(pagina: str):
    try:
        return json.loads(pagina)
    except (ValueError, TypeError):
        return None
