"""V5.7 — Extração web: trecho usado não pode vir de referências/bibliografia.

Regressão real coberta (auditoria V5.7, 2026-10-17): em artigos com seção de
referências (ex.: Wikipédia), o trecho exibido vinha de "Consultado em …
Cópia arquivada …" porque citações citam o tema em frases curtas e ganhavam
o ranking de palavras-chave.
"""
import web_extract


def test_trecho_nao_vem_de_referencias():
    corpo = ("O sistema de travagem antibloqueio evita que as rodas bloqueiem "
             "durante travagens bruscas. O ABS atua bombeando a pressão do freio "
             "para manter a dirigibilidade do veículo em piso escorregadio. ")
    refs = ("«Freios ABS e Airbag obrigatório». Consultado em 15 de outubro de "
            "2014. Cópia arquivada em 3 de março de 2016. ↑ Jusbrasil. "
            "Consultado em 3 de janeiro de 2024. Cópia arquivada em 3 de "
            "janeiro de 2024. «O Código de Trânsito e o ABS». Consultado em 27 "
            "de fevereiro de 2014.")
    trecho = web_extract.melhor_trecho(corpo + refs, "freio ABS", 200)
    assert "travagem" in trecho or "rodas bloqueiem" in trecho
    assert "Cópia arquivada" not in trecho
    assert "Consultado em" not in trecho


def test_trecho_sem_termos_usa_inicio():
    texto = "Primeiro parágrafo do documento. Segundo parágrafo do documento."
    assert web_extract.melhor_trecho(texto, "", 40).startswith("Primeiro parágrafo")


def test_trecho_normal_continua_escolhendo_por_termo():
    texto = ("Introdução sem relação alguma. Depois falamos de notebook com "
             "processador rápido e memória. Mais texto irrelevante adiante. "
             "Outra seção qualquer para preencher o restante do conteúdo.")
    trecho = web_extract.melhor_trecho(texto, "notebook memória", 60)
    assert "notebook" in trecho


def test_penalidade_citacoes_e_limitada():
    pedaco = ("Consultado em 2020. Cópia arquivada. Consultado em 2021. "
              "Cópia arquivada. Consultado em 2022. Cópia arquivada. "
              "Consultado em 2023. Cópia arquivada.")
    assert web_extract._penalidade_citacoes(pedaco) <= 30.0
    assert web_extract._penalidade_citacoes(pedaco) > web_extract._penalidade_citacoes(
        "mencionado em uma referência: Consultado em 2020.")
    assert web_extract._penalidade_citacoes("texto normal sem citações") == 0.0


def test_trecho_usado_fica_dentro_do_texto_guardado():
    """Achado V5.7 FINAL: a janela era escolhida no texto completo e podia
    ficar fora de `texto[:teto]` — o conteúdo lido então caía no fallback
    (menus). O trecho usado tem que pertencer ao texto guardado."""
    partes = [f"Seção {i} sem termo exclusivo algum para desviar o ranking. "
              for i in range(60)]
    partes.append("Palavra-chave zzpalavra exclusiva aparece só no fim do artigo. ")
    html = ("<html><body><article><p>" + "".join(partes)
            + "</p></article></body></html>")
    ext = web_extract.extrair_pagina(html, "https://a.example/x", "zzpalavra", teto=500)
    assert ext["trecho_usado"]
    assert ext["trecho_usado"][:60] in ext["texto"]


# ── FASE 3: imagens referenciadas ──────────────────────────────────
def test_imagens_og_jsonld_e_img_relativo():
    html = (
        '<html><head>'
        '<meta property="og:image" content="https://cdn.example/foto.jpg">'
        '<meta name="twitter:image" content="/social.png">'
        '<script type="application/ld+json">'
        '{"@type":"Product","name":"Placa","image":'
        '["https://cdn.example/placa-1.jpg",'
        ' {"@type":"ImageObject","contentUrl":"https://cdn.example/placa-2.jpg"}]}'
        '</script></head><body>'
        '<img src="foto-interna.jpg"><img src="https://cdn.example/foto.jpg">'
        '</body></html>')
    imgs = web_extract.extrair_imagens(html, "https://loja.example/pagina")
    assert imgs[0] == "https://cdn.example/placa-1.jpg"  # JSON-LD primeiro
    assert "https://cdn.example/placa-2.jpg" in imgs
    assert "https://cdn.example/foto.jpg" in imgs
    assert "https://loja.example/social.png" in imgs
    assert "https://loja.example/foto-interna.jpg" in imgs
    assert imgs.count("https://cdn.example/foto.jpg") == 1  # dedup


def test_imagens_ignoram_data_uri_e_so_http():
    html = ('<img src="data:image/png;base64,AAA">'
            '<img src="javascript:void(0)">'
            '<img src="espaco.jpg">')
    assert web_extract.extrair_imagens(html, "https://x.example/a") == [
        "https://x.example/espaco.jpg"]


def test_extrair_pagina_expoe_imagens():
    html = ('<html><head><title>Nota</title>'
            '<meta property="og:image" content="https://cdn.example/capa.jpg">'
            '</head><body><p>Texto do artigo com conteúdo suficiente para '
            'não ser ilegível nesta extração de teste.</p></body></html>')
    out = web_extract.extrair_pagina(html, "https://nota.example/n/1")
    assert out["imagens"] == ["https://cdn.example/capa.jpg"]
