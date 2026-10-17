"""V5.5 Source Check: veredito honesto de links, produtos e imagens (offline)."""
import sys
import urllib.error
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import research
import source_check


class _Resp:
    def __init__(self, corpo=b"", status=200, ctype="text/html", length=None, loc=""):
        self._corpo = corpo
        self.status = status
        self._ctype = ctype
        self._length = length
        self._loc = loc
        self.headers = self

    def get_content_type(self):
        return self._ctype

    def get_content_charset(self):
        return "utf-8"

    def get(self, k, d=""):
        if k == "Content-Length":
            return self._length if self._length is not None else len(self._corpo)
        if k == "Location":
            return self._loc
        if k == "Content-Type":
            return self._ctype
        return d

    def read(self, n=-1):
        return self._corpo if n is None or n < 0 else self._corpo[:n]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


PAG_PRODUTO = """<html><head><title>Notebook Gamer X 16GB RAM - Loja Certa</title>
<meta property="og:type" content="product">
<meta property="product:price:amount" content="4299.00">
<script type="application/ld+json">
{"@context":"https://schema.org/","@type":"Product","name":"Notebook Gamer X 16GB RAM",
 "brand":{"@type":"Brand","name":"MarcaX"},
 "offers":{"@type":"Offer","price":"4299.00","priceCurrency":"BRL",
           "availability":"https://schema.org/InStock"}}
</script></head>
<body><h1>Notebook Gamer X 16GB RAM</h1>
<p>Notebook com 16GB de RAM e SSD de 512GB.</p>
<button>Adicionar ao carrinho</button></body></html>"""

PAG_LISTA = """<html><head><title>Resultados para notebook 16gb ram</title></head>
<body><h1>Resultados para "notebook"</h1><p>Ordenar por: relevância</p>
<div class="card">Notebook A R$ 3.299,00</div>
<div class="card">Notebook B R$ 3.499,00</div>
<div class="card">Notebook C R$ 3.599,00</div>
<div class="card">Notebook D R$ 3.699,00</div>
<div class="card">Notebook E R$ 3.799,00</div>
<div class="card">Notebook F R$ 3.899,00</div>
<div class="card">Notebook G R$ 3.999,00</div>
<div class="card">Notebook H R$ 4.099,00</div>
</body></html>"""


def _png(largura, altura):
    return (b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR"
            + largura.to_bytes(4, "big") + altura.to_bytes(4, "big")
            + b"\x08\x02\x00\x00\x00" + b"\x00" * 16)


def _abrir(url, timeout=10.0, ua=""):
    if url.endswith("/produto/notebook"):
        return _Resp(PAG_PRODUTO.encode())
    if url.endswith("/busca"):
        return _Resp(PAG_LISTA.encode())
    if url.endswith("/r"):
        err = urllib.error.HTTPError(url, 301, "moved", {}, None)
        err.headers = {"Location": "https://loja.com/produto/notebook"}
        raise err
    if url.endswith("/404"):
        raise urllib.error.HTTPError(url, 404, "x", {}, None)
    if url.endswith("/403"):
        raise urllib.error.HTTPError(url, 403, "x", {}, None)
    if url.endswith("/pdf"):
        return _Resp(b"%PDF-1.4 x", ctype="application/pdf")
    if url.endswith("/foto.png"):
        return _Resp(_png(800, 600), ctype="image/png")
    if url.endswith("/pixel.gif"):
        return _Resp(b"GIF89a" + bytes([1, 0, 1, 0]) + b"\x00" * 10, ctype="image/gif")
    if url.endswith("/html-como-imagem"):
        return _Resp(PAG_PRODUTO.encode(), ctype="text/html")
    if url.endswith("/sem-rede"):
        raise OSError("cabo rompido")
    raise AssertionError("url inesperada: " + url)


@pytest.fixture(autouse=True)
def _sem_ssrf(monkeypatch):
    monkeypatch.setattr(research, "_ips_globais", lambda host: None)


def _validar(url, **kw):
    return source_check.validar_link(url, abrir=_abrir, **kw)


# ── Produto × listagem × correspondência ───────────────────────────
def test_produto_verificado():
    r = _validar("https://loja.com/produto/notebook",
                 esperado={"tipo": "produto", "dominio": "loja.com",
                           "termos": ["Notebook", "16GB RAM"]})
    assert r["veredito"] == "verificado" and r["codigo"] == "ok"
    assert r["http"] == 200 and r["sinais"]["eh_produto"] is True
    assert r["titulo"].startswith("Notebook Gamer X")


def test_listagem_reprovada_para_produto():
    r = _validar("https://loja.com/busca",
                 esperado={"tipo": "produto", "termos": ["notebook"]})
    assert r["veredito"] == "reprovado" and r["codigo"] == "listagem_nao_produto"
    assert r["sinais"]["eh_listagem"] is True


def test_pagina_de_produto_vale_para_pagina():
    r = _validar("https://loja.com/produto/notebook")
    assert r["veredito"] == "verificado" and r["sinais"]["eh_produto"] is True


def test_termos_ausentes_reprovam():
    r = _validar("https://loja.com/produto/notebook",
                 esperado={"tipo": "produto", "termos": ["Geladeira Frost Free"]})
    assert r["veredito"] == "reprovado" and r["codigo"] == "nao_corresponde"


def test_correspondencia_parcial():
    r = _validar("https://loja.com/produto/notebook",
                 esperado={"tipo": "produto", "termos": ["Notebook", "placa de vídeo RTX"]})
    assert r["veredito"] == "parcial" and r["codigo"] == "correspondencia_parcial"
    assert "RTX" in r["motivo"]


def test_dominio_inesperado_reprova():
    r = _validar("https://loja.com/produto/notebook",
                 esperado={"tipo": "produto", "dominio": "outraloja.com"})
    assert r["veredito"] == "reprovado" and r["codigo"] == "dominio_inesperado"


def test_redirect_revalidado_mantem_final():
    r = _validar("https://loja.com/r", esperado={"tipo": "produto"})
    assert r["url_final"] == "https://loja.com/produto/notebook"
    assert r["veredito"] == "verificado"


# ── Erros HTTP e rede: nunca "ok" ──────────────────────────────────
def test_404_reprovado_403_nao_verificado():
    r404 = _validar("https://loja.com/404")
    assert r404["veredito"] == "reprovado" and r404["codigo"] == "http_404"
    r403 = _validar("https://loja.com/403")
    assert r403["veredito"] == "nao_verificado" and r403["codigo"] == "bloqueado"


def test_rede_nao_verificado():
    r = _validar("https://loja.com/sem-rede")
    assert r["veredito"] == "nao_verificado" and r["codigo"] == "rede"


def test_tipo_inesperado_pdf_para_pagina():
    r = _validar("https://loja.com/pdf", esperado={"tipo": "pagina"})
    assert r["veredito"] == "reprovado" and r["codigo"] == "tipo_inesperado"


# ── Imagens ────────────────────────────────────────────────────────
def test_imagem_real_verificada():
    r = source_check.validar_imagem("https://loja.com/foto.png", abrir=_abrir)
    assert r["veredito"] == "verificado" and r["formato"] == "png"
    assert (r["largura"], r["altura"]) == (800, 600)


def test_pixel_reprovado():
    r = source_check.validar_imagem("https://loja.com/pixel.gif", abrir=_abrir)
    assert r["veredito"] == "reprovado" and r["codigo"] == "imagem_minuscula"


def test_html_como_imagem_reprovado():
    r = source_check.validar_imagem("https://loja.com/html-como-imagem", abrir=_abrir)
    assert r["veredito"] == "reprovado" and r["codigo"] == "nao_e_imagem"


def test_validar_link_tipo_imagem_delega():
    r = _validar("https://loja.com/foto.png", esperado={"tipo": "imagem"})
    assert r["veredito"] == "verificado" and r["formato"] == "png"


# ── Lote e resumo ──────────────────────────────────────────────────
def test_validar_muitos_e_resumo():
    resultados = source_check.validar_muitos(
        [("https://loja.com/produto/notebook", {"tipo": "produto"}),
         "https://loja.com/404",
         "https://loja.com/sem-rede"],
        abrir=_abrir)
    assert [r["veredito"] for r in resultados] == ["verificado", "reprovado",
                                                   "nao_verificado"]
    resumo = source_check.resumo_vereditos(resultados)
    assert resumo == {"verificado": 1, "parcial": 0, "reprovado": 1,
                      "nao_verificado": 1, "total": 3}


# ── Produto declarado via OpenGraph (sem JSON-LD) ──────────────────
PAG_OG_PRODUTO = """<html><head><title>Fone Y</title>
<meta property="og:type" content="product">
<meta property="og:title" content="Fone Y">
<meta property="product:price:amount" content="199.90">
</head><body><h1>Fone Y</h1><button>Comprar agora</button></body></html>"""

PAG_BLOG_OG = """<html><head><title>Blog</title>
<meta property="og:title" content="Post do blog">
<meta property="og:image" content="https://cdn.blog.com/p.jpg">
</head><body><p>texto corrido</p></body></html>"""


def test_og_type_produto_vira_produto_sem_ld():
    r = source_check.avaliar_pagina(PAG_OG_PRODUTO, "https://loja.com/produto/fone",
                                    esperado={"tipo": "produto"})
    assert r["veredito"] == "verificado"
    assert r["sinais"]["eh_produto"] is True


def test_og_sem_sinais_de_produto_reprova():
    r = source_check.avaliar_pagina(PAG_BLOG_OG, "https://blog.com/post",
                                    esperado={"tipo": "produto"})
    assert r["veredito"] == "reprovado"
    assert r["codigo"] == "sem_sinais_produto"
    assert r["sinais"]["eh_produto"] is False
