"""Extração de conteúdo web (V5.5) — artigo principal, metadados e trechos.

Determinístico e stdlib-only: um mini-DOM tolerante, pontuação de blocos por
densidade de texto (estilo readability) e remoção de boilerplate
(menu/cabeçalho/rodapé/anúncios/comentários). Nunca executa JavaScript,
nunca segue instruções do conteúdo e nunca inventa dados: o que não estiver
no HTML recuperado não existe aqui.

Opcional (sem custo obrigatório): se `trafilatura` estiver instalado, ele é
usado como extrator principal e o resultado é marcado com `extrator`; se
`extruct` estiver instalado, metadados Microdata/RDFa são adicionados.
Ambos são OPCIONAIS: sem eles, a extração determinística continua completa.
"""
import html as _html
import json
import re
import urllib.parse
from html.parser import HTMLParser

MAX_HTML = 2 * 1024 * 1024
TETO_TEXTO = 8000

_VAZIAS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
           "meta", "param", "source", "track", "wbr"}
_PULAR = {"script", "style", "noscript", "template", "svg", "canvas", "iframe",
          "object", "embed", "form", "button", "select", "textarea", "video",
          "audio", "picture"}
_IGNORAR = {"nav", "header", "footer", "aside"}
_BLOCO = ("p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "blockquote", "pre",
          "td", "th", "dd", "dt", "figcaption", "caption")

# Indícios de boilerplate (classe/id) — só quando o bloco NÃO é <article>/<main>.
_RUIM = re.compile(
    r"(nav|menu|header|footer|sidebar|aside|cookie|banner|ads?[-_]|advert|promo|"
    r"newsletter|social|share|comment|coment|related|relacionad|breadcrumb|"
    r"paginac|paginacao|tags?|toolbar|popup|modal|search|busca|login|signin|"
    r"skills|job|career|rodape|cabecalho|topbar|submenu|dropdown|mega)", re.I)
_BOM = re.compile(
    r"(article|main|content|conteudo|post|texto|materia|story|entry|body|"
    r"reading|readability|markdown|document|documento|wiki|prose)", re.I)


class _No:
    __slots__ = ("tag", "attrs", "filhos", "pai", "texto")

    def __init__(self, tag="", attrs=None, pai=None):
        self.tag = tag
        self.attrs = dict(attrs or {})
        self.filhos = []
        self.pai = pai
        self.texto = ""


class _MiniDom(HTMLParser):
    """Parser tolerante: constrói árvore, ignora scripts e auto-fecha tags."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.raiz = _No("#root")
        self.atual = self.raiz
        self._pular = 0
        self.titulo = ""
        self._no_titulo = False

    # -- tags --
    def handle_starttag(self, tag, attrs):
        tag = (tag or "").lower()
        if tag in _PULAR:
            self._pular += 1
            return
        if self._pular:
            return
        if tag == "title":
            self._no_titulo = True
            return
        if tag in _VAZIAS:
            self.atual.filhos.append(_No(tag, attrs, self.atual))
            return
        no = _No(tag, attrs, self.atual)
        self.atual.filhos.append(no)
        self.atual = no

    def handle_startendtag(self, tag, attrs):
        tag = (tag or "").lower()
        if tag in _VAZIAS and not self._pular:
            self.atual.filhos.append(_No(tag, attrs, self.atual))

    def handle_endtag(self, tag):
        tag = (tag or "").lower()
        if tag in _PULAR:
            if self._pular:
                self._pular -= 1
            return
        if self._pular:
            return
        if tag == "title":
            self._no_titulo = False
            return
        no = self.atual
        while no is not None and no.tag != tag:
            no = no.pai
        if no is not None and no.pai is not None:
            self.atual = no.pai

    def handle_data(self, data):
        if self._pular:
            return
        if self._no_titulo:
            self.titulo += data
            return
        self.atual.texto += data


def _normalizar(texto: str) -> str:
    return re.sub(r"\s+", " ", (texto or "")).strip()


def _limpar(texto: str, teto: int = 400) -> str:
    txt = _html.unescape(texto or "")
    return _normalizar(re.sub(r"<[^>]+>", " ", txt))[:teto]


# ── Pontuação de blocos (artigo principal) ──────────────────────────
def _texto_bloco(no: "_No") -> str:
    """Texto visível do bloco, sem boilerplate (nav/cabeçalho/rodapé/aside)."""
    partes = []

    def _anda(n):
        if n.tag in _PULAR or n.tag in _IGNORAR:
            return
        if n.texto and n.texto.strip():
            partes.append(n.texto)
        for f in n.filhos:
            _anda(f)

    _anda(no)
    return _normalizar(" ".join(partes))


def _texto_documento(raiz: "_No") -> str:
    """Texto literal do documento inteiro, pulando boilerplate (nav etc.).

    Usado como último recurso quando nenhum bloco atinge o limiar de
    pontuação (páginas curtas/simples) — nunca inventa, só reaproveita o
    texto real da página.
    """
    partes = []

    def _anda(n):
        if n.tag in _PULAR or n.tag in _IGNORAR:
            return
        if n.texto and n.texto.strip():
            partes.append(n.texto)
        for f in n.filhos:
            _anda(f)

    _anda(raiz)
    return _normalizar(" ".join(partes))


def _link_densidade(no: "_No", cache: dict | None = None) -> float:
    total = max(1, len(_texto_bloco(no)))
    texto_link = 0

    def _anda(n):
        nonlocal texto_link
        if n.tag == "a":
            texto_link += len(_normalizar(n.texto)) + sum(
                len(_normalizar(f.texto)) + len(_texto_bloco(f)) for f in n.filhos)
            return
        for f in n.filhos:
            _anda(f)

    _anda(no)
    return min(1.0, texto_link / total)


def _pista(no: "_No") -> str:
    a = no.attrs
    return " ".join(str(a.get(k, "")) for k in ("class", "id", "role", "itemprop"))


def _descendentes(no: "_No"):
    for f in no.filhos:
        yield f
        yield from _descendentes(f)


def melhor_bloco(raiz: "_No"):
    """Bloco que concentra o conteúdo principal (estilo readability).

    A pontuação nasce nos parágrafos/títulos reais e sobe para os ancestrais
    com peso decrescente (100% → 50% → 25%). Assim um contêiner grande não
    vence só por abranger o site inteiro (menus, barras laterais, rodapé):
    o bloco mais próximo dos parágrafos do artigo fica com a maior soma.
    """
    cache: dict = {}
    pontos: dict = {}
    nodes = list(_descendentes(raiz))
    abstracts = [n for n in nodes if re.search(r"(?:^|[\s_-])abstract(?:$|[\s_-])", _pista(n), re.I)
                 and n.tag not in _PULAR | _IGNORAR and len(_texto_bloco(n)) >= 120]
    if abstracts:
        abstract = max(abstracts, key=lambda n: len(_texto_bloco(n)))
        # An abstract landing page often has more promotional paragraphs than
        # scientific text. Prefer the labelled abstract unless a substantive
        # full article is actually present too.
        full_sections = any(n.tag in ("h2", "h3") and re.search(
            r"\b(introduction|methods|results|discussion|conclusion|introdução|metodologia|resultados|discussão|conclusão)\b",
            _texto_bloco(n), re.I) for n in nodes)
        if not any((n.tag == "article" or (n.tag == "main" and full_sections)) and
                   len(_texto_bloco(n)) > 2 * len(_texto_bloco(abstract)) for n in nodes):
            return abstract

    for no in _descendentes(raiz):
        if no.tag in _IGNORAR or no.tag in _PULAR or no.tag not in _BLOCO:
            continue
        n = len(_texto_bloco(no))
        if n < 40:
            continue
        pista = _pista(no)
        valor = min(n, 1200) / 12.0 + 8.0
        if no.tag in ("h1", "h2", "h3"):
            valor += 6.0
        elif no.tag in ("td", "th", "li", "blockquote", "pre", "dd", "dt"):
            valor *= 0.6
        if pista and _RUIM.search(pista):
            valor *= 0.35
        valor *= max(0.25, 1.0 - _link_densidade(no, cache))
        anc = no.pai
        for fator in (1.0, 0.8, 0.6):
            if anc is None or anc is raiz:
                break
            if anc.tag in _IGNORAR or anc.tag in _PULAR:
                break
            pontos[id(anc)] = pontos.get(id(anc), 0.0) + valor * fator
            anc = anc.pai

    melhor, melhor_pontos = None, 0.0
    for no in [raiz, *list(_descendentes(raiz))]:
        pts = pontos.get(id(no))
        if not pts:
            continue
        pista = _pista(no)
        if no.tag in ("article", "main"):
            pts *= 1.6
        if str(no.attrs.get("role", "")).lower() == "main" or \
                str(no.attrs.get("itemprop", "")).lower() == "articlebody":
            pts *= 1.4
        if pista and _BOM.search(pista):
            pts *= 1.25
        if pista and _RUIM.search(pista):
            pts *= 0.5
        if no.tag in ("body", "html") or no is raiz:
            # o contêiner total inclui menus/rodapé: só vence se nada melhor
            pts *= 0.35
        if pts > melhor_pontos:
            melhor, melhor_pontos = no, pts
    return melhor


# ── Extração de seções e texto ─────────────────────────────────────
def _paragrafos(no: "_No") -> list:
    """Lista [(tag, texto)] na ordem do documento, sem boilerplate."""
    saida = []

    def _anda(n, dentro_ignorada=False):
        ignorar = dentro_ignorada or n.tag in _IGNORAR
        if not ignorar and n.tag in _BLOCO:
            txt = _normalizar(n.texto) + " " + _texto_bloco_inline(n)
            txt = _normalizar(txt)
            if len(txt) >= 25:
                saida.append((n.tag, txt[:1200]))
        for f in n.filhos:
            _anda(f, ignorar)

    _anda(no)
    return saida


def _texto_bloco_inline(no: "_No") -> str:
    """Texto inline do bloco (negrito/itálico/links), sem sub-blocos."""
    partes = []

    def _anda(n, profundidade=0):
        if n.tag in _PULAR or n.tag in _IGNORAR or profundidade > 8:
            return
        if n.texto and n.texto.strip():
            partes.append(n.texto)
        for f in n.filhos:
            if f.tag in _BLOCO:
                continue
            _anda(f, profundidade + 1)

    for f in no.filhos:
        if f.tag in _BLOCO:
            continue
        _anda(f)
    return _normalizar(" ".join(partes))


def secoes(no: "_No", teto: int = 12) -> list:
    out = []
    atual = {"titulo": "", "texto": []}
    for tag, txt in _paragrafos(no):
        if tag in ("h1", "h2", "h3", "h4") and len(txt) <= 160:
            if atual["texto"] or atual["titulo"]:
                out.append({"titulo": atual["titulo"], "texto": "\n".join(atual["texto"])[:4000]})
            atual = {"titulo": txt, "texto": []}
        else:
            atual["texto"].append(txt)
        if len(out) >= teto:
            break
    if (atual["texto"] or atual["titulo"]) and len(out) < teto:
        out.append({"titulo": atual["titulo"], "texto": "\n".join(atual["texto"])[:4000]})
    return [s for s in out if s["texto"] or s["titulo"]]


# ── Metadados (meta/OG/JSON-LD; Microdata se extruct existir) ──────
_RX_META = re.compile(
    r"<meta[^>]+(?:property|name|itemprop)=[\"']([^\"']+)[\"'][^>]+content=[\"']([^\"']*)[\"']"
    r"|<meta[^>]+content=[\"']([^\"']*)[\"'][^>]+(?:property|name|itemprop)=[\"']([^\"']+)[\"']",
    re.IGNORECASE)
_RX_CANON = re.compile(
    r"<link[^>]+rel=[\"']canonical[\"'][^>]*href=[\"']([^\"']+)[\"']", re.IGNORECASE)
_RX_CANON2 = re.compile(
    r"<link[^>]+href=[\"']([^\"']+)[\"'][^>]*rel=[\"']canonical[\"']", re.IGNORECASE)
_RX_LDJSON = re.compile(
    r"<script[^>]+type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>", re.IGNORECASE | re.S)
_RX_TITULO = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.S)
_RX_LANG = re.compile(r"<html[^>]+lang=[\"']([^\"']+)[\"']", re.IGNORECASE)

_ARTIGO_TIPOS = {"article", "newsarticle", "blogposting", "report", "scholarlyarticle",
                 "techarticle", "review", "webpage", "product", "faqpage", "qapage",
                 "howto", "recipe", "dataset", "organization", "website", "person"}


def _ldjson_objs(pagina: str) -> list:
    objs = []
    for m in _RX_LDJSON.finditer(pagina or ""):
        bruto = (m.group(1) or "").strip()
        if not bruto or bruto.startswith("<!--"):
            continue
        try:
            obj = json.loads(bruto)
        except (ValueError, TypeError, RecursionError):
            continue
        objs.append(obj)
    return objs


def _ld_por_tipo(objs: list, tipos: set, teto: int = 8) -> list:
    out = []

    def _anda(o):
        if len(out) >= teto:
            return
        if isinstance(o, dict):
            t = str(o.get("@type", "")).lower()
            if t in tipos and isinstance(o, dict):
                out.append(o)
            if isinstance(o.get("@graph"), list):
                for g in o["@graph"]:
                    _anda(g)
            for v in o.values():
                if isinstance(v, (dict, list)):
                    _anda(v)
        elif isinstance(o, list):
            for i in o:
                _anda(i)

    for obj in objs or []:
        try:
            _anda(obj)
        except RecursionError:
            continue
    # dedupe por identidade (id/url/headline)
    vistos, unicos = set(), []
    for o in out:
        k = str(o.get("@id") or o.get("url") or o.get("headline") or o.get("name") or "")[:200]
        if k and k in vistos:
            continue
        vistos.add(k)
        unicos.append(o)
    return unicos


def _autor(valor) -> str:
    if isinstance(valor, dict):
        return _limpar(valor.get("name") or valor.get("legalName"), 120)
    if isinstance(valor, list):
        for v in valor:
            nome = _autor(v)
            if nome:
                return nome
        return ""
    return _limpar(valor, 120)


def _titulo_plausivel(titulo: str) -> bool:
    """Descarta 'título' que na verdade é frase-descrição (JSON-LD de wiki).

    Só rejeita o padrão inequívoco: começa minúsculo e termina em ponto
    (ex.: 'processo físico-químico ... solar.'). Títulos reais como
    'iPhone 15' continuam válidos.
    """
    t = (titulo or "").strip()
    if len(t) < 3:
        return False
    if t[:1].islower() and t.endswith("."):
        return False
    return True


def extrair_metadados(pagina: str, base_url: str = "") -> dict:
    """{titulo, descricao, canonica, og, twitter, idioma, publicado_em, autor,
    site, tipo, ld} — só o que existe no HTML."""
    import search_verticals
    metas: dict = {}
    for m in _RX_META.finditer(pagina or ""):
        k = (m.group(1) or m.group(4) or "").strip().lower()
        v = (m.group(2) if m.group(2) is not None else m.group(3)) or ""
        if k and v and k not in metas:
            metas[k] = _limpar(v, 500)
    ld_objs = _ldjson_objs(pagina)
    artigos = _ld_por_tipo(ld_objs, _ARTIGO_TIPOS, teto=6)
    principal = artigos[0] if artigos else {}
    can = ""
    m = _RX_CANON.search(pagina or "") or _RX_CANON2.search(pagina or "")
    if m:
        can = _url_absoluta(m.group(1), base_url)
    titulo_ld = _limpar(principal.get("headline") or principal.get("name"), 200)
    if not _titulo_plausivel(titulo_ld):
        titulo_ld = ""
    titulo_html = _limpar((_RX_TITULO.search(pagina or "") or [None, ""])[1]
                         if _RX_TITULO.search(pagina or "") else "", 200)
    idioma = ""
    ml = _RX_LANG.search(pagina or "")
    if ml:
        idioma = ml.group(1)[:12]
    ld = {}
    for o in artigos:
        for k in ("datePublished", "dateModified", "author", "publisher", "headline",
                  "articleSection", "keywords", "description", "inLanguage",
                  "contentLocation", "about"):
            v = o.get(k)
            if v is not None and k not in ld:
                ld[k] = v
    return {
        "titulo": titulo_ld or metas.get("og:title") or titulo_html,
        "descricao": _limpar(principal.get("description") or metas.get("description")
                            or metas.get("og:description"), 400),
        "canonica": can,
        "og": {k: v for k, v in metas.items() if k.startswith("og:")},
        "twitter": {k: v for k, v in metas.items() if k.startswith("twitter:")},
        "idioma": idioma or _limpar(principal.get("inLanguage"), 12),
        "publicado_em": _limpar(principal.get("datePublished")
                               or metas.get("article:published_time"), 40),
        "atualizado_em": _limpar(principal.get("dateModified")
                                or metas.get("article:modified_time"), 40),
        "autor": _autor(principal.get("author") or metas.get("author")),
        "site": _limpar((principal.get("publisher") or {}).get("name")
                       if isinstance(principal.get("publisher"), dict)
                       else metas.get("og:site_name"), 120),
        "tipo": str(principal.get("@type", "") or metas.get("og:type", ""))[:40],
        "ld": ld,
        "tem_ld": bool(ld_objs),
        "structured": search_verticals.structured(pagina),
    }


def _url_absoluta(url: str, base: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    try:
        return urllib.parse.urljoin(base or "", url)[:500]
    except ValueError:
        return ""


# ── Links, imagens e tabelas ───────────────────────────────────────
def extrair_links(pagina: str, base_url: str = "", *, limite: int = 30,
                  dominio_base: str = "") -> list:
    """Links reais do documento: {url, texto, interno}. Sem javascript/mailto."""
    rx = re.compile(r"<a\s[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", re.IGNORECASE | re.S)
    dom_base = dominio_base or (urllib.parse.urlsplit(base_url).hostname or "")
    out, vistos = [], set()
    for m in rx.finditer(pagina or ""):
        href, texto = m.group(1), _limpar(m.group(2), 160)
        if href.startswith(("javascript:", "mailto:", "tel:", "#", "data:")):
            continue
        url = _url_absoluta(href, base_url)
        if not url.startswith("http"):
            continue
        if url in vistos:
            continue
        vistos.add(url)
        host = (urllib.parse.urlsplit(url).hostname or "").lower()
        out.append({"url": url, "texto": texto,
                    "interno": bool(dom_base and host.endswith(dom_base.lower()))})
        if len(out) >= limite:
            break
    return out


def _ld_imagem(valor) -> list:
    """URLs de imagens declaradas em JSON-LD (string, lista ou objeto)."""
    out = []
    if isinstance(valor, str):
        if valor.strip():
            out.append(valor.strip())
    elif isinstance(valor, dict):
        u = valor.get("url") or valor.get("contentUrl") or valor.get("thumbnailUrl")
        if isinstance(u, str) and u.strip():
            out.append(u.strip())
        for k in ("image", "imageObject"):
            if k in valor:
                out.extend(_ld_imagem(valor[k]))
    elif isinstance(valor, list):
        for v in valor:
            out.extend(_ld_imagem(v))
    return out


_RX_IMG = re.compile(r"<img\s[^>]*?src=[\"']([^\"']+)[\"']", re.IGNORECASE)


def extrair_imagens(pagina: str, base_url: str = "", *, limite: int = 10) -> list:
    """Imagens referenciadas pelo documento: urls absolutas, dedup, sem `data:`.

    Prioridade: JSON-LD (`image`/`imageObject`/`thumbnailUrl`) → `og:image`/
    `twitter:image` → `<img src>`. Sem inferência: só o que o HTML declara.
    """
    urls = []
    for obj in _ld_por_tipo(_ldjson_objs(pagina), _ARTIGO_TIPOS, teto=6):
        for k in ("image", "imageObject", "thumbnailUrl"):
            if k in obj:
                urls.extend(_ld_imagem(obj[k]))
    for m in _RX_META.finditer(pagina or ""):
        k = (m.group(1) or m.group(4) or "").strip().lower()
        v = (m.group(2) if m.group(2) is not None else m.group(3)) or ""
        if v and k in ("og:image", "og:image:url", "og:image:secure_url",
                       "twitter:image", "twitter:image:src"):
            urls.append(v)
    for m in _RX_IMG.finditer(pagina or ""):
        urls.append(m.group(1))
    out, vistos = [], set()
    for u in urls:
        u = (u or "").strip()
        if not u or u.lower().startswith(("data:", "javascript:", "about:")):
            continue
        u = _url_absoluta(u, base_url)
        if not u.startswith("http") or u in vistos:
            continue
        vistos.add(u)
        out.append(u)
        if len(out) >= limite:
            break
    return out


def extrair_tabelas(pagina: str, limite: int = 5, linhas: int = 40) -> list:
    """[[celulas...], ...] por tabela — sem inferência, só o HTML."""
    out = []
    for tm in re.finditer(r"<table[\s\S]*?</table>", pagina or "", re.IGNORECASE):
        bloco = tm.group(0)
        grade = []
        for rm in re.finditer(r"<tr[\s\S]*?</tr>", bloco, re.IGNORECASE):
            cels = [_limpar(c, 160) for c in
                    re.findall(r"<t[hd][^>]*>([\s\S]*?)</t[hd]>", rm.group(0), re.IGNORECASE)]
            if any(cels):
                grade.append(cels)
            if len(grade) >= linhas:
                break
        if len(grade) >= 2:
            out.append(grade)
        if len(out) >= limite:
            break
    return out


# ── Trecho usado (proveniência) e legibilidade ─────────────────────
_REFS_RX = re.compile(
    r"consultado em|c[oó]pia arquivada|acesso em|dispon[ií]vel em|recuperado em|"
    r"arquivad[oa]|isbn|doi\s*:|\u2191|[\u00ab\u00bb]", re.I)


def _penalidade_citacoes(pedaco: str) -> float:
    """Referências/bibliografia não são conteúdo: descontam do trecho (V5.7)."""
    return min(30.0, len(_REFS_RX.findall(pedaco)) * 3.0)


def melhor_trecho(texto: str, consulta: str, janela: int = 280) -> str:
    """Trecho literal que melhor cobre os termos da consulta (sem gerar texto)."""
    texto = _normalizar(texto)
    if not texto or janela <= 0:
        return ""

    def janela_literal(inicio):
        # Character offsets must not turn 200 into 0, or truncate decimals/signs.
        limite = max(0, inicio - janela)
        while inicio > limite and not texto[inicio - 1].isspace():
            inicio -= 1
        if inicio and not texto[inicio - 1].isspace():
            return ""  # A token larger than the window cannot be cited whole.
        fim = min(len(texto), inicio + janela)
        if fim < len(texto) and not texto[fim].isspace():
            while fim > inicio and not texto[fim - 1].isspace():
                fim -= 1
        return texto[inicio:fim].strip()

    termos = {t for t in re.findall(r"[0-9a-zà-ú]{3,}", (consulta or "").lower())}
    if not termos:
        return janela_literal(0)
    melhor, melhor_pontos = "", 0.0
    passo = max(40, janela // 2)
    for i in range(0, max(1, len(texto) - janela // 2), passo):
        pedaco = janela_literal(i)
        baixo = pedaco.lower()
        pontos = sum(len(t) for t in termos if t in baixo)
        frases = pedaco.count(". ") + (1 if pedaco.endswith(".") else 0)
        pontos += frases * 3
        pontos -= _penalidade_citacoes(pedaco)
        if pontos > melhor_pontos:
            melhor, melhor_pontos = pedaco, pontos
    return melhor or janela_literal(0)


def ilegivel(texto: str) -> bool:
    """Conteúdo provavelmente ilegível (binário decodificado/página vazia)."""
    txt = texto or ""
    if len(_normalizar(txt)) < 40:
        return True
    estranhos = sum(1 for c in txt if ord(c) == 0xFFFD or (ord(c) < 32 and c not in "\n\r\t"))
    return (estranhos / max(1, len(txt))) > 0.02


# ── Trafilatura/Extruct opcionais ──────────────────────────────────
def _trafilatura(pagina: str, url: str = "") -> str:
    try:
        import trafilatura  # type: ignore
    except Exception:
        return ""
    try:
        return trafilatura.extract(pagina, url=url or None, include_comments=False,
                                   include_tables=True, favor_precision=True,
                                   no_fallback=False) or ""
    except Exception:
        return ""


def _extruct(pagina: str, url: str = "") -> dict:
    try:
        import extruct  # type: ignore
    except Exception:
        return {}
    try:
        dados = extruct.extract(pagina, base_url=url or None,
                                syntaxes=["microdata", "opengraph", "json-ld"],
                                errors="ignore")
        return dados if isinstance(dados, dict) else {}
    except Exception:
        return {}


# ── Entrada única ──────────────────────────────────────────────────
def extrair_pagina(pagina: str, base_url: str = "", consulta: str = "",
                   *, teto: int = TETO_TEXTO, usar_trafilatura: bool = True) -> dict:
    """Extração completa e honesta de uma página HTML já baixada.

    Retorna {titulo, texto, secoes, paragrafos, metadados, links, imagens,
    tabelas, trecho_usado, extrator, ilegivel, tamanho_html}. Campos vazios
    quando o documento não os tem — nada é preenchido por aparência.
    """
    html_txt = (pagina or "")[:MAX_HTML]
    metas = extrair_metadados(html_txt, base_url)
    texto_art = ""
    extrator = "deterministico"
    if usar_trafilatura:
        texto_art = _trafilatura(html_txt, base_url)
        if texto_art:
            extrator = "trafilatura"
    parser = _MiniDom()
    try:
        parser.feed(html_txt)
    except Exception:
        pass
    bloco = melhor_bloco(parser.raiz)
    abstract_only = bloco is not None and bool(re.search(
        r"(?:^|[\s_-])abstract(?:$|[\s_-])", _pista(bloco), re.I))
    texto_det = (_texto_bloco(bloco) if bloco is not None
                 else _texto_documento(parser.raiz))
    paragrafos = [t for _, t in _paragrafos(bloco)] if bloco is not None else []
    secs = secoes(bloco) if bloco is not None else []
    if abstract_only:
        texto_art, extrator = texto_det, "deterministico"
    elif not texto_art:
        texto_art = texto_det
    elif texto_det and len(texto_det) > len(texto_art) * 1.8:
        # trafilatura devolveu menos que o extrator local: o local é mais útil
        texto_art, extrator = texto_det, "deterministico"
    texto_final = texto_art[:teto]
    saida = {
        "titulo": metas["titulo"] or _limpar(parser.titulo, 200),
        "texto": texto_final,
        "paragrafos": paragrafos[:240],
        "secoes": secs,
        "metadados": metas,
        "links": extrair_links(html_txt, base_url),
        "imagens": extrair_imagens(html_txt, base_url),
        "tabelas": extrair_tabelas(html_txt),
        "trecho_usado": melhor_trecho(texto_final, consulta, 400),
        "extrator": extrator,
        "content_scope": "abstract_only" if abstract_only else "page_text",
        "ilegivel": ilegivel(texto_art),
        "tamanho_html": len(html_txt),
    }
    if usar_trafilatura:
        extra = _extruct(html_txt, base_url)
        if extra:
            saida["extruct"] = extra
    return saida


def texto_de_html(pagina: str, teto: int = TETO_TEXTO) -> tuple:
    """Compat: (titulo, texto) usando o melhor extrator disponível."""
    ext = extrair_pagina(pagina, consulta="", teto=teto)
    return ext["titulo"], ext["texto"]
