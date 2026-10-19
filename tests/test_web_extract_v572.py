"""V5.7.2 — extração web: bloco principal, boilerplate e texto inline.

Defeitos reproduzíveis (2026-10-19, sonda real):
- `melhor_bloco` escolhia `#root`/`body` (Wikipédia e docs.python.org) porque
  a pontuação somava o texto de todos os descendentes; o texto extraído
  começava com "Ir para o conteúdo Menu principal ...".
- `_texto_bloco` incluía `<nav>/<header>/<footer>/<aside>` internos ao bloco.
- `_texto_bloco_inline` só preservava texto de `<a>`: `<b>65 W</b>` sumia dos
  parágrafos.
- JSON-LD da Wikipédia traz `headline` = frase-descrição; o título virava
  "processo físico-químico ... solar." em vez do título real.
"""
import web_extract


def test_texto_nao_comeca_com_menu():
    html = (
        '<html><body>'
        '<nav><a href="/">Página principal</a> Menu principal Navegação</nav>'
        '<header>Criar conta Entrar Ferramentas pessoais</header>'
        '<main><article>'
        '<h1>Fotossíntese</h1>'
        '<p>A fotossíntese converte energia luminosa em energia química, '
        'armazenando-a em moléculas orgânicas como a glicose.</p>'
        '<p>O processo ocorre nos cloroplastos e libera oxigênio como '
        'subproduto da fotólise da água.</p>'
        '</article></main>'
        '<footer>Rodapé Licença</footer>'
        '</body></html>')
    ext = web_extract.extrair_pagina(html, "https://wiki.example/fotossintese")
    texto = ext["texto"]
    assert "Fotossíntese" in texto and "glicose" in texto
    for lixo in ("Menu principal", "Criar conta", "Ferramentas pessoais",
                 "Rodapé Licença", "Página principal"):
        assert lixo not in texto


def test_melhor_bloco_nao_e_root_nem_body():
    html = (
        '<html><body><div class="topbar"><a href="/a">A</a> <a href="/b">B</a>'
        '</div><div class="site"><article><h1>Título</h1><p>' + "Texto real. " * 40
        + '</p></article></div><div class="sidebar"><a href="/x">X</a>'
        '</div></body></html>')
    parser = web_extract._MiniDom()
    parser.feed(html)
    bloco = web_extract.melhor_bloco(parser.raiz)
    assert bloco is not None
    assert bloco.tag not in ("#root", "body", "html")


def test_inline_preservado_nos_paragrafos():
    html = (
        '<html><body><article>'
        '<p>O consumo medido foi de <b>65 W</b> e a fonte é '
        '<a href="https://lab.example/fonte">o relatório oficial</a>, '
        'com margem de erro de 2 W.</p>'
        '</article></body></html>')
    ext = web_extract.extrair_pagina(html, "https://lab.example/review")
    paragrafos = " ".join(ext["paragrafos"])
    assert "65 W" in paragrafos
    assert "relatório oficial" in paragrafos


def test_headline_descritivo_nao_vira_titulo():
    html = (
        '<html><head><title>Fotossíntese – Wikipédia</title>'
        '<meta property="og:title" content="Fotossíntese – Wikipédia">'
        '<script type="application/ld+json">'
        '{"@type":"Article","headline":"processo físico-químico celular para '
        'obtenção de glicose através de energia solar."}'
        '</script></head><body><p>Conteúdo do artigo com extensão suficiente '
        'para a extração considerar o texto legível.</p></body></html>')
    ext = web_extract.extrair_pagina(html, "https://pt.wikipedia.org/wiki/Fotossintese")
    assert ext["titulo"].startswith("Fotossíntese")


def test_titulo_curto_minusculo_continua_valido():
    html = ('<html><head><script type="application/ld+json">'
            '{"@type":"Product","name":"iPhone 15"}</script></head>'
            '<body><p>Produto com descrição suficientemente longa para ser '
            'extraído como conteúdo principal desta página.</p></body></html>')
    ext = web_extract.extrair_pagina(html, "https://loja.example/iphone")
    assert ext["titulo"] == "iPhone 15"
