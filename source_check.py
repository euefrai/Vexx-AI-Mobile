"""Verificação de fontes, links e imagens (V5.5) — veredito honesto por URL.

Cada verificação responde, em ordem: a URL é pública (SSRF)? abriu? para onde
redirecionou? qual o status HTTP? que tipo de recurso é? o conteúdo foi mesmo
recuperado? é a página certa (produto × listagem/capa)? o conteúdo corresponde
ao pedido? — e devolve um veredito com motivo explícito:

  verificado      — abriu, tipo certo, conteúdo corresponde
  parcial         — abriu e corresponde, mas falta parte do esperado
  reprovado       — não abriu (4xx), tipo errado, página de lista ou nada a ver
  nao_verificado  — rede/bloqueio/limite: não deu para checar (NUNCA vira "ok")

O que nunca acontece aqui: contornar bloqueio/CAPTCHA, aprovar página de busca
ou categoria como se fosse produto, aceitar imagem por aparência de URL, ou
inventar título/preço/dimensão. Sem navegador, sem JS, stdlib pura.
"""
import re
import time
import unicodedata
import urllib.error
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

import research
import web_extract

VEREDITOS = ("verificado", "parcial", "reprovado", "nao_verificado")
UA_PADRAO = "Mozilla/5.0 (JuliaResearch/1.0; +source-check)"
MAX_BYTES_PAGINA = 1_500_000
MAX_BYTES_IMAGEM = 2_500_000

# ── Download com cabeçalhos (mesma disciplina SSRF de research.baixar) ──
def _baixar_bytes(url: str, *, timeout: float = 8.0, max_bytes: int = MAX_BYTES_PAGINA,
                  abrir=None, user_agent: str = "") -> tuple:
    """GET honesto: (url_final, http, content_type, bytes).

    Revalida SSRF a cada redirect, respeita teto e nunca lê além dele.
    Levanta ResearchErro com códigos iguais aos de `research.baixar`
    (`ssrf`, `rede`, `bloqueado`, `http`, `tamanho`, `redirect`) — e, para
    `http`, o status real fica em `exc.http`.
    """
    atual = research.url_segura(url)
    abrir = abrir or research._abrir
    for _ in range(research.MAX_REDIRECTS + 1):
        try:
            try:
                resp = abrir(atual, timeout, user_agent or UA_PADRAO)
            except TypeError:
                resp = abrir(atual, timeout)
        except urllib.error.HTTPError as exc:
            if exc.code in (301, 302, 303, 307, 308):
                loc = exc.headers.get("Location", "")
                if not loc:
                    raise research.ResearchErro("Redirect sem destino.", "redirect")
                atual = research.url_segura(urllib.parse.urljoin(atual, loc))
                continue
            err = research.ResearchErro(
                f"Provedor bloqueou ({exc.code})." if exc.code in (401, 403, 429)
                else f"Página HTTP {exc.code}.",
                "bloqueado" if exc.code in (401, 403, 429) else "http")
            err.http = exc.code
            raise err
        except (OSError, TimeoutError, ValueError) as exc:
            err = research.ResearchErro(f"Falha de rede ({type(exc).__name__}).", "rede")
            err.http = 0
            raise err
        with resp:
            status = getattr(resp, "status", 200)
            if status >= 400:
                err = research.ResearchErro(
                    f"Provedor bloqueou ({status})." if status in (401, 403, 429)
                    else f"Página HTTP {status}.",
                    "bloqueado" if status in (401, 403, 429) else "http")
                err.http = status
                raise err
            try:
                ctype = (resp.headers.get_content_type()
                         if hasattr(resp.headers, "get_content_type")
                         else str(resp.headers.get("Content-Type", "")).split(";")[0])
            except Exception:
                ctype = ""
            try:
                total = int(resp.headers.get("Content-Length") or 0)
            except (TypeError, ValueError):
                total = 0
            if total > max_bytes:
                raise research.ResearchErro("Recurso grande demais.", "tamanho")
            raw = resp.read(max_bytes + 1)
            if len(raw) > max_bytes:
                raise research.ResearchErro("Recurso grande demais.", "tamanho")
            return atual, status, (ctype or "").lower().strip(), raw
    raise research.ResearchErro("Redirects demais.", "redirect")


def _texto(raw: bytes, ctype: str = "", teto: int = 40000) -> str:
    charset = "utf-8"
    m = re.search(r"charset=([\w\-]+)", ctype or "")
    if m:
        charset = m.group(1)
    return raw.decode(charset, errors="ignore")[:teto]


def _sem_acentos(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", (texto or "").lower())
                   if not unicodedata.combining(c))


def _dominio(url: str) -> str:
    try:
        return (urllib.parse.urlsplit(url or "").hostname or "").lower()[:120]
    except ValueError:
        return ""


# ── Sinais: página de produto × listagem/capa × anúncio ────────────
_RX_URL_PRODUTO = re.compile(
    r"/(produto|produtos?/|dp|pd|item|p|anuncio|oferta|shop|product)(s?/|/|\?|$)", re.I)
_RX_URL_LISTA = re.compile(
    r"/(busca|buscar|search|pesquisa|categoria|category|resultados?|listagem|"
    r"colecao|coleção|dept|departamento|catalogo)(/|\?|$|s)", re.I)
_RX_TXT_LISTA = re.compile(
    r"(resultados? para|ordenar por|refine sua busca|filtrar por|exibindo \d+|"
    r"itens encontrados|\d+ (produtos|resultados) encontrad|adicionar ao carrinho</)"
    r"|\d+\s?(produtos|resultados)\b", re.I)
_RX_COMPRAR = re.compile(
    r"(adicionar (ao|no) carrinho|comprar agora|add to cart|buy now|"
    r"adicionar à sacola|tenho interesse|falar com (o )?vendedor)", re.I)
_RX_ANUNCIO = re.compile(
    r"\b(anúncio|anuncio|usado|semi-?novo|recondicionado|revisado|"
    r"leilão|leilao|à venda por|publicado (há|em))\b", re.I)
_RX_PRECO_VISIVEL = re.compile(r"R\$\s?\d{1,3}(?:\.\d{3})*(?:,\d{2})?")

# V5.7 hotfix: sinais fortes de "produto fora do catálogo" em página HTTP 200
# (soft 404). Roda sobre o TEXTO VISÍVEL normalizado (sem acento, minúsculo) —
# nunca sobre <script>/<template>/atributos, para não bater em string de
# template de SPA. "Esgotado"/"sem estoque"/"fora de estoque" NÃO entram:
# são out-of-stock (o produto existe) — conceito diferente de removido.
_RX_BLOQUEIO_PAGINA = re.compile(
    r"(complete o captcha|resolva o captcha|"
    r"confirme que voce (e|eh) humano|verifique que voce (e|eh) humano|"
    r"verify (that )?you are (a )?human|checking your browser|just a moment|"
    r"unusual traffic|are you a robot|enable (java ?script )?and cookies)")
_RX_REMOVIDO = re.compile(
    r"(produto|an[uú]ncio|item|oferta|p[aá]gina)\s+(?:foi\s+|j[aá]\s+foi\s+)?"
    r"(?:removid[oa]s?|exclu[ií]d[oa]s?|desativad[oa]s?|inativad[oa]s?|"
    r"finalizad[oa]s?|expirad[oa]s?|inexistente|indispon[ií]vel)"
    r"|(produto|an[uú]ncio|item|oferta)\s+n[aã]o\s+(?:foi\s+)?"
    r"(?:encontrad[oa]s?|existe|est[aá]\s+dispon[ií]vel)"
    r"|n[aã]o\s+est[aá]\s+mais\s+(?:dispon[ií]vel|a\s+venda|no\s+ar)"
    r"|(?:saiu\s+do\s+ar|p[aá]gina\s+n[aã]o\s+encontrada)"
    r"|(product|listing|item|offer)\s+(?:was\s+|has\s+been\s+)?"
    r"(?:removed|deleted|unavailable|expired|not\s+found)"
    r"|no\s+longer\s+available", re.I)


def _texto_visivel(html: str, teto: int = 40000) -> str:
    """Aproximação do texto visível: remove script/style/template/noscript e
    tags — para procurar frases na página sem bater em código/atributos."""
    limpo = re.sub(r"<(script|style|template|noscript)\b[^>]*>.*?</\1\s*>",
                   " ", html or "", flags=re.I | re.S)
    limpo = re.sub(r"<[^>]{0,600}>", " ", limpo)
    return limpo[:teto]


def classificar_sinais(pagina: str, url_final: str = "") -> dict:
    """Sinais determinísticos de produto × listagem × anúncio, com evidências.

    Não decide sozinho "isto é um produto": pontua sinais reais do HTML/URL
    (JSON-LD Product, og:type=product, preço em meta, verbo de compra) e de
    listagem (URL de busca/categoria, texto de listagem, muitos preços).
    """
    html = pagina or ""
    baixo = html.lower()
    pontos_p, pontos_l = 0, 0
    evidencias = []
    try:
        objs = web_extract._ldjson_objs(html)
    except Exception:
        objs = []
    prods = web_extract._ld_por_tipo(objs, {"product"}, teto=3)
    if prods:
        pontos_p += 3
        evidencias.append("JSON-LD Product")
    if web_extract._ld_por_tipo(objs, {"offer", "aggregateoffer"}, teto=3):
        pontos_p += 1
        evidencias.append("JSON-LD Offer")
    metas = {}
    try:
        metas = web_extract.extrair_metadados(html, url_final)
    except Exception:
        metas = {}
    og = metas.get("og") or {}
    og_produto = str(og.get("og:type", "")).lower() == "product"
    if og_produto:
        pontos_p += 2
        evidencias.append("og:type=product")
    preco_meta = False
    for chave in ("product:price:amount", "og:price:amount", "product:price"):
        if og.get(chave):
            preco_meta = True
            pontos_p += 2
            evidencias.append(f"meta {chave}")
            break
    caminho = urllib.parse.urlsplit(url_final or "").path or ""
    if _RX_URL_PRODUTO.search(caminho + "/"):
        pontos_p += 1
        evidencias.append("URL de produto")
    if _RX_COMPRAR.search(html):
        pontos_p += 1
        evidencias.append("verbo de compra na página")
    if _RX_URL_LISTA.search(caminho):
        pontos_l += 3
        evidencias.append("URL de busca/categoria")
    if url_final and caminho in ("", "/"):
        # FASE 4: raiz do site é capa/home — nunca página de produto.
        # Guarda para URL desconhecida: só vale quando a URL foi informada.
        pontos_l += 3
        evidencias.append("URL raiz do site (capa, não página de produto)")
    if _RX_TXT_LISTA.search(html):
        pontos_l += 2
        evidencias.append("texto de listagem")
    n_precos = len(_RX_PRECO_VISIVEL.findall(html))
    if n_precos > 6:
        pontos_l += 2
        evidencias.append(f"{n_precos} preços na página (listagem)")
    elif n_precos in (1, 2):
        pontos_p += 1
        evidencias.append("preço visível único")
    titulo = (metas.get("titulo") or "").lower()
    if any(t in titulo for t in ("resultados para", "busca por", "categoria")):
        pontos_l += 2
        evidencias.append("título de listagem")
    anuncio = bool(_RX_ANUNCIO.search(baixo[:20000]))
    if anuncio:
        evidencias.append("indícios de anúncio/classificado")
    pagina_str = _sem_acentos(_texto_visivel(html))
    achado_removido = _RX_REMOVIDO.search(pagina_str)
    removido = bool(achado_removido)
    frase_removido = " ".join(achado_removido.group(0).split())[:60] if removido else ""
    if removido:
        evidencias.append("página diz que o produto não existe mais: "
                          f"“{frase_removido}”")
    bloqueio = bool(_RX_BLOQUEIO_PAGINA.search(pagina_str))
    if bloqueio:
        evidencias.append("página de proteção anti-bot (CAPTCHA/verificação)")
    tem_dado_produto = bool(prods) or og_produto or preco_meta
    return {"eh_produto": bool(pontos_p >= 3 and pontos_p > pontos_l
                               and tem_dado_produto),
            "eh_listagem": pontos_l >= 3 and pontos_l >= pontos_p,
            "pontos_produto": pontos_p, "pontos_listagem": pontos_l,
            "precos_visiveis": n_precos, "anuncio": anuncio,
            "removido": removido, "removido_frase": frase_removido,
            "bloqueio": bloqueio,
            "evidencias": evidencias[:8]}


_RX_URL_BUSCA_RAIZ = re.compile(
    r"/(busca|buscar|search|pesquisa|pesquisar|categoria|category|"
    r"resultados?|lists?|lista|listas|listagem)(/|\?|$|s)", re.I)


def url_parece_produto(url: str) -> bool:
    """URL com cara de página de item (nunca home/busca/categoria).

    Só um sinal de caminho: não valida conteúdo nem autoriza sozinho um card.
    Serve para aceitar como link a página analisada quando o caminho é de item
    e existe dado estruturado real por trás.
    """
    try:
        partes = urllib.parse.urlsplit(url or "")
    except ValueError:
        return False
    if not partes.netloc or url_de_listagem(url):
        return False
    return bool(_RX_URL_PRODUTO.search((partes.path or "") + "/"))


def url_de_listagem(url: str) -> bool:
    """URL com cara de home/busca/categoria? (heurística conservadora)

    Usada só para NUNCA tratar home/listagem como página do item — nunca
    aprova nada sozinha. `/catalogo`, `/colecao` etc. ficam de fora de
    propósito (lojas também usam esses caminhos para produtos). `/list`
    (Shopee) entrou na auditoria de descoberta de 2026-10-18: é listagem
    dinâmica, nunca página de item."""
    try:
        partes = urllib.parse.urlsplit(url or "")
    except ValueError:
        return False
    if not partes.netloc:
        return False
    caminho = partes.path or ""
    return caminho in ("", "/") or bool(_RX_URL_BUSCA_RAIZ.search(caminho))


def url_de_catalogo_produtos(url: str) -> bool:
    """Product destinations only; catalog sources remain valid research links."""
    if url_de_listagem(url): return True
    try: path = urllib.parse.urlsplit(url or '').path
    except ValueError: return False
    return bool(re.search(r'/(?:placas-de-videos?|graphics-cards|video-cards|gpus)/?$', path, re.I))


# ── Imagens: formato real e dimensões (sem PIL) ────────────────────
def _formato_imagem(raw: bytes, ctype: str = "") -> str:
    if raw[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if raw[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if raw[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "webp"
    if raw[:2] == b"BM":
        return "bmp"
    if b"<svg" in raw[:600].lower() and "image/svg" in (ctype or ""):
        return "svg"
    if (ctype or "").startswith("image/"):
        return "desconhecido"
    return ""


def _dimensoes(raw: bytes, formato: str) -> tuple:
    """(largura, altura) ou (0, 0) — só o que o arquivo declara."""
    try:
        if formato == "png" and len(raw) >= 24:
            return (int.from_bytes(raw[16:20], "big"), int.from_bytes(raw[20:24], "big"))
        if formato == "gif" and len(raw) >= 10:
            return (raw[6] | (raw[7] << 8), raw[8] | (raw[9] << 8))
        if formato == "jpeg":
            i = 2
            while i + 9 < len(raw):
                if raw[i] != 0xFF:
                    i += 1
                    continue
                marker = raw[i + 1]
                if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
                    return ((raw[i + 7] << 8) | raw[i + 8], (raw[i + 5] << 8) | raw[i + 6])
                if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
                    i += 2
                    continue
                seg = (raw[i + 2] << 8) | raw[i + 3]
                i += 2 + max(2, seg)
        if formato == "webp" and len(raw) >= 30:
            if raw[12:16] == b"VP8X":
                return ((raw[24] | (raw[25] << 8) | (raw[26] << 16)) + 1,
                        (raw[27] | (raw[28] << 8) | (raw[29] << 16)) + 1)
            if raw[12:16] == b"VP8 ":
                return ((raw[26] | (raw[27] << 8)) & 0x3FFF,
                        (raw[28] | (raw[29] << 8)) & 0x3FFF)
            if raw[12:16] == b"VP8L" and raw[20] == 0x2F:
                b = raw[21:25]
                return (((b[0] | ((b[1] & 0x3F) << 8)) + 1),
                        (((b[1] >> 6) | (b[2] << 2) | ((b[3] & 0x0F) << 10)) + 1))
        if formato == "bmp" and len(raw) >= 26:
            return (int.from_bytes(raw[18:22], "little"), int.from_bytes(raw[22:26], "little"))
    except Exception:
        pass
    return (0, 0)


def validar_imagem(url: str, *, timeout: float = 8.0, abrir=None,
                   max_bytes: int = MAX_BYTES_IMAGEM) -> dict:
    """Valida uma imagem real: abriu? é imagem? formato? dimensões? tamanho?"""
    t0 = time.monotonic()
    out = {"url": (url or "")[:500], "url_final": "", "http": 0, "content_type": "",
           "bytes": 0, "dominio": "", "formato": "", "largura": 0, "altura": 0,
           "veredito": "", "codigo": "", "motivo": "",
           "acessado_em": research.agora_iso(), "segundos": 0.0}
    try:
        final, status, ctype, raw = _baixar_bytes(url, timeout=timeout, max_bytes=max_bytes,
                                                  abrir=abrir)
    except research.ResearchErro as exc:
        codigo = getattr(exc, "codigo", "erro")
        http = getattr(exc, "http", 0)
        out.update({"http": http, "codigo": codigo,
                    "veredito": "reprovado" if http in (404, 410) else "nao_verificado",
                    "motivo": str(exc)[:200],
                    "segundos": round(time.monotonic() - t0, 2)})
        return out
    out.update({"url_final": final, "http": status, "content_type": ctype,
                "bytes": len(raw), "dominio": _dominio(final)})
    formato = _formato_imagem(raw, ctype)
    if not formato:
        out.update({"veredito": "reprovado", "codigo": "nao_e_imagem",
                    "motivo": f"conteúdo {ctype or 'sem tipo'} não é imagem"})
    elif formato == "desconhecido":
        out.update({"formato": formato, "veredito": "parcial",
                    "codigo": "formato_desconhecido",
                    "motivo": f"tipo {ctype} sem assinatura conhecida"})
    else:
        largura, altura = _dimensoes(raw, formato)
        out.update({"formato": formato, "largura": largura, "altura": altura})
        if largura and altura and (largura < 16 or altura < 16):
            out.update({"veredito": "reprovado", "codigo": "imagem_minuscula",
                        "motivo": f"imagem {largura}x{altura} (rastreador/ícone)"})
        elif largura and altura and (largura < 64 or altura < 64):
            out.update({"veredito": "parcial", "codigo": "imagem_pequena",
                        "motivo": f"imagem {largura}x{altura} pequena para card"})
        elif not (largura and altura):
            out.update({"veredito": "parcial", "codigo": "sem_dimensoes",
                        "motivo": f"imagem {formato} sem dimensões legíveis"})
        else:
            out.update({"veredito": "verificado", "codigo": "ok",
                        "motivo": f"imagem {formato} {largura}x{altura}"})
    out["segundos"] = round(time.monotonic() - t0, 2)
    return out


# ── Verificação de link/página ─────────────────────────────────────
_MAPA_ERRO = {
    "ssrf": ("reprovado", "URL não pública/bloqueada (SSRF)"),
    "rede": ("nao_verificado", "falha de rede na verificação"),
    "bloqueado": ("nao_verificado", "provedor recusou (bot-wall/CAPTCHA); sem bypass"),
    "http": ("nao_verificado", "HTTP de erro"),
    "tamanho": ("nao_verificado", "recurso grande demais para verificar"),
    "redirect": ("nao_verificado", "redirect inválido/em excesso"),
    "tipo_bloqueado": ("reprovado", "tipo de arquivo bloqueado"),
}


def avaliar_pagina(pagina: str, url_final: str = "", *, consulta: str = "",
                   esperado: dict = None, http: int = 200, ctype: str = "text/html",
                   bytes_len: int = 0) -> dict:
    """Avalia uma página JÁ baixada, sem rede (mesmas regras do validador).

    Usado por quem já recuperou a página (research/shopping) para não baixar
    de novo; devolve o mesmo veredito/sinais de `validar_link`.
    """
    esperado = dict(esperado or {})
    tipo = str(esperado.get("tipo") or "pagina").lower()
    t0 = time.monotonic()
    out = {"url": "", "url_final": (url_final or "")[:500], "http": http,
           "content_type": ctype or "", "bytes": int(bytes_len or 0),
           "dominio": _dominio(url_final), "titulo": "", "canonica": "", "trecho": "",
           "sinais": {}, "codigo": "", "motivo": "", "veredito": "",
           "acessado_em": research.agora_iso(), "segundos": 0.0,
           "esperado": esperado}
    ctype_base = (ctype or "").split(";")[0].strip().lower()
    aceitos = {
        "pagina": ("text/html", "application/xhtml+xml"),
        "html": ("text/html", "application/xhtml+xml"),
        "json": ("application/json", "text/json", "application/ld+json",
                 "text/plain", "application/xml", "text/xml"),
        "documento": ("application/pdf", "text/plain", "text/html",
                      "application/xhtml+xml"),
    }.get(tipo, ("text/html", "application/xhtml+xml"))
    if ctype_base and not any(ctype_base.startswith(a) for a in aceitos) \
            and not ctype_base.endswith("+xml"):
        out.update({"codigo": "tipo_inesperado", "veredito": "reprovado",
                    "motivo": f"esperado {tipo}; veio {ctype_base}",
                    "segundos": round(time.monotonic() - t0, 2)})
        return out
    if "\x00" in (pagina or "")[:2000]:
        out.update({"codigo": "binario", "veredito": "reprovado",
                    "motivo": "conteúdo binário (não é página legível)",
                    "segundos": round(time.monotonic() - t0, 2)})
        return out
    try:
        ext = web_extract.extrair_pagina(pagina, url_final, consulta, teto=6000,
                                         usar_trafilatura=True)
    except Exception:
        ext = {}
    metas = ext.get("metadados") or {}
    out.update({"titulo": (ext.get("titulo") or metas.get("titulo") or "")[:160],
                "canonica": (metas.get("canonica") or "")[:500],
                "trecho": (ext.get("trecho_usado") or (ext.get("texto") or "")[:400])[:400]})
    # rel=canonical apontando para OUTRO domínio: origem declarada pela página
    # (agregador/cópia declara o original). Declarado, não verificado aqui.
    dom_can = _dominio(out["canonica"])
    if dom_can and out["dominio"] and dom_can != out["dominio"] \
            and not dom_can.endswith("." + out["dominio"]) \
            and not out["dominio"].endswith("." + dom_can):
        out["origem_declarada"] = dom_can
    sinais = classificar_sinais(pagina, url_final)
    out["sinais"] = sinais

    dom_esperado = str(esperado.get("dominio") or "").lower().strip()
    if dom_esperado and not (out["dominio"] == dom_esperado
                             or out["dominio"].endswith("." + dom_esperado)):
        out.update({"codigo": "dominio_inesperado", "veredito": "reprovado",
                    "motivo": f"abriu em {out['dominio']}, esperado {dom_esperado}",
                    "segundos": round(time.monotonic() - t0, 2)})
        return out
    if sinais.get("bloqueio") and tipo != "json":
        # Página de CAPTCHA/verificação anti-bot servida com HTTP 200: não dá
        # para confirmar NADA — "não verificado (proteção)", nunca "quebrado".
        out.update({"codigo": "bloqueio_pagina", "veredito": "nao_verificado",
                    "motivo": ("página pediu verificação anti-bot (CAPTCHA); "
                               "sem bypass — não foi possível confirmar o conteúdo"),
                    "segundos": round(time.monotonic() - t0, 2)})
        return out
    if tipo == "produto":
        if sinais.get("eh_listagem"):
            out.update({"codigo": "listagem_nao_produto", "veredito": "reprovado",
                        "motivo": "link abre listagem/categoria, não página do produto",
                        "segundos": round(time.monotonic() - t0, 2)})
            return out
        if sinais.get("removido"):
            # HTTP 200 de "produto não encontrado/removido/indisponível" é
            # soft 404: nunca vira oferta válida, mesmo com JSON-LD residual.
            frase = str(sinais.get("removido_frase") or "")[:60]
            out.update({"codigo": "produto_removido", "veredito": "reprovado",
                        "motivo": ("página diz que o produto foi removido/indisponível"
                                   + (f" (“{frase}”)" if frase else "")),
                        "segundos": round(time.monotonic() - t0, 2)})
            return out
        if not sinais.get("eh_produto"):
            out.update({"codigo": "sem_sinais_produto", "veredito": "reprovado",
                        "motivo": "página sem sinais de produto (JSON-LD/og:type/preço)",
                        "segundos": round(time.monotonic() - t0, 2)})
            return out
    termos = [t for t in (esperado.get("termos") or []) if str(t).strip()]
    faltando = []
    if termos:
        alvo = _sem_acentos(out["titulo"] + " " + (ext.get("texto") or "")[:4000])
        presentes = [t for t in termos if _sem_acentos(str(t)) in alvo]
        faltando = [t for t in termos if t not in presentes]
        if not presentes:
            out.update({"codigo": "nao_corresponde", "veredito": "reprovado",
                        "motivo": "conteúdo não menciona o item pedido",
                        "segundos": round(time.monotonic() - t0, 2)})
            return out
    ilegivel = bool(ext.get("ilegivel")) and not (ext.get("texto") or "").strip()
    if ilegivel and tipo != "json":
        out.update({"codigo": "ilegivel", "veredito": "parcial",
                    "motivo": "conteúdo não legível como texto (página vazia/JS)",
                    "segundos": round(time.monotonic() - t0, 2)})
        return out
    if faltando:
        out.update({"codigo": "correspondencia_parcial", "veredito": "parcial",
                    "motivo": ("não menciona: " + "; ".join(str(t)[:40] for t in faltando[:4])),
                    "segundos": round(time.monotonic() - t0, 2)})
        return out
    out.update({"codigo": "ok", "veredito": "verificado",
                "motivo": "abriu, tipo certo" + (" e produto confirmado" if tipo == "produto" else ""),
                "segundos": round(time.monotonic() - t0, 2)})
    return out


def validar_link(url: str, *, consulta: str = "", esperado: dict = None,
                 timeout: float = 8.0, abrir=None,
                 max_bytes: int = MAX_BYTES_PAGINA) -> dict:
    """Verifica um link/página com veredito honesto e motivo explícito.

    `esperado` (opcional): {"tipo": "pagina"|"produto"|"json"|"documento"|"imagem",
    "dominio": "loja.com", "termos": ["nome", "16gb"]} — tipo errado, domínio
    errado, listagem no lugar de produto ou conteúdo sem correspondência são
    reprovados/parciais, nunca "ok" silencioso.
    """
    esperado = dict(esperado or {})
    tipo = str(esperado.get("tipo") or "pagina").lower()
    if tipo == "imagem":
        return validar_imagem(url, timeout=timeout, abrir=abrir)
    t0 = time.monotonic()
    out = {"url": (url or "")[:500], "url_final": "", "http": 0, "content_type": "",
           "bytes": 0, "dominio": "", "titulo": "", "canonica": "", "trecho": "",
           "sinais": {}, "codigo": "", "motivo": "", "veredito": "",
           "acessado_em": research.agora_iso(), "segundos": 0.0,
           "esperado": esperado}
    try:
        final, status, ctype, raw = _baixar_bytes(url, timeout=timeout,
                                                  max_bytes=max_bytes, abrir=abrir)
    except research.ResearchErro as exc:
        codigo = getattr(exc, "codigo", "erro")
        http = getattr(exc, "http", 0)
        veredito, motivo = _MAPA_ERRO.get(codigo, ("nao_verificado", "erro na verificação"))
        if codigo == "http" and http in (404, 410):
            veredito, motivo = "reprovado", f"página não existe (HTTP {http})"
        out.update({"http": http, "codigo": f"http_{http}" if codigo == "http" else codigo,
                    "veredito": veredito,
                    "motivo": (f"{motivo} ({str(exc)[:120]})").strip(),
                    "segundos": round(time.monotonic() - t0, 2)})
        return out
    aval = avaliar_pagina(_texto(raw, ctype), final, consulta=consulta,
                          esperado=esperado, http=status, ctype=ctype,
                          bytes_len=len(raw))
    aval["url"] = (url or "")[:500]
    aval["segundos"] = round(time.monotonic() - t0, 2)
    return aval


def validar_muitos(itens: list, *, consulta: str = "", timeout: float = 8.0,
                   abrir=None, workers: int = 4) -> list:
    """Valida vários links em paralelo, preservando a ordem.

    `itens`: lista de URLs ou de (url, esperado).
    """
    tarefas = []
    for it in itens or []:
        if isinstance(it, (list, tuple)) and len(it) == 2 and isinstance(it[1], dict):
            tarefas.append((str(it[0]), it[1]))
        else:
            tarefas.append((str(it), {}))
    if not tarefas:
        return []
    with ThreadPoolExecutor(max_workers=max(1, min(workers, 6)),
                            thread_name_prefix="juliasrc") as pool:
        futs = [pool.submit(validar_link, u, consulta=consulta, esperado=e,
                            timeout=timeout, abrir=abrir) for u, e in tarefas]
        return [f.result() for f in futs]


def resumo_vereditos(resultados: list) -> dict:
    """Contagem por veredito (para progresso/relatório) — sem inventar nada."""
    out = {v: 0 for v in VEREDITOS}
    for r in resultados or []:
        v = (r or {}).get("veredito", "")
        if v in out:
            out[v] += 1
    out["total"] = sum(out[v] for v in VEREDITOS)
    return out
