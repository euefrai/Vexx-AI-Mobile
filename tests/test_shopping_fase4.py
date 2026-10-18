"""FASE 4 (V5.7) — identidade do produto: versão/edição, modelo e consultas.

Regras testadas (sem rede; tudo local):

- variante/versão incompatível NUNCA vira correspondência exata;
- conflito só com indicação legível no anúncio (s23 ≠ s24; iphone 14 ≠ 15);
- "pro" de pt-BR ("para o" — 'notebook pro meu filho') não é versão;
- ausência de modelo no anúncio não é promovida a correspondência: vira
  alternativa explícita, nunca card de "modelo confirmado";
- a busca inclui a referência pedida (modelo), sem descartá-la.
"""

import shopping


def _p(nome, **kw):
    base = {"nome": nome, "marca": kw.pop("marca", ""),
            "modelo": kw.pop("modelo", ""), "preco": kw.pop("preco", 1999.0),
            "preco_texto": kw.pop("preco_texto", "R$ 1.999,00"),
            "preco_confirmado": True, "specs": kw.pop("specs", {})}
    base.update(kw)
    return base


# ── Extração de versão/edição ────────────────────────────────────────

def test_pro_contracao_ptbr_nao_vira_versao():
    s = shopping.extrair_criterios("quero um notebook pro meu filho até 3000")
    assert "tiers" not in s["specs"]


def test_pro_modelo_vira_versao():
    s = shopping.extrair_criterios("iphone 15 pro 256gb")["specs"]
    assert s.get("tiers") == ["pro"]


def test_pro_max_nao_duplica_pro_e_max():
    s = shopping.extrair_criterios("iphone 15 pro max 256gb")["specs"]
    assert s.get("tiers") == ["pro max"]


def test_ultra_vira_versao():
    s = shopping.extrair_criterios("galaxy s24 ultra")["specs"]
    assert s.get("tiers") == ["ultra"]


def test_no_max_de_orcamento_nao_vira_versao():
    s = shopping.extrair_criterios("tv 50 polegadas no max 2000")["specs"]
    assert "tiers" not in s


# ── Extração de modelo/família ───────────────────────────────────────

def test_token_de_modelo_capturado():
    s = shopping.extrair_criterios("celular galaxy s24 256gb")["specs"]
    assert s.get("modelos") == ["s24"]


def test_familia_com_numero_capturada():
    s = shopping.extrair_criterios("iphone 15 128gb")["specs"]
    assert s.get("familias") == {"iphone": ["15"]}


def test_par_gb_nao_vira_modelo():
    s = shopping.extrair_criterios("notebook 8gb 512gb")["specs"]
    assert "modelos" not in s and "familias" not in s


# ── Filtros: versão ──────────────────────────────────────────────────

def test_versao_padrao_nao_vira_pedido_pro():
    c = shopping.extrair_criterios("iphone 15 pro 256gb")
    padrao = _p("Apple iPhone 15 256GB", marca="Apple")
    dentro, fora = shopping.aplicar_filtros([padrao], c)
    assert dentro == [] and fora
    assert "versao_diferente" in fora[0]["excluido_codigos"]
    alts = shopping.separar_alternativas(fora, c)
    assert alts and "sem indicação" in alts[0]["diferencas"]
    assert "pedido: pro" in alts[0]["diferencas"]


def test_pro_max_atende_pedido_pro():
    c = shopping.extrair_criterios("iphone 15 pro 256gb")
    pro_max = _p("Apple iPhone 15 Pro Max 256GB", marca="Apple")
    dentro, _ = shopping.aplicar_filtros([pro_max], c)
    assert dentro


def test_pro_nao_atende_pedido_pro_max():
    c = shopping.extrair_criterios("iphone 15 pro max 256gb")
    pro = _p("Apple iPhone 15 Pro 256GB", marca="Apple")
    _, fora = shopping.aplicar_filtros([pro], c)
    assert "versao_diferente" in fora[0]["excluido_codigos"]
    alts = shopping.separar_alternativas(fora, c)
    assert alts and "pro" in alts[0]["diferencas"]


def test_tenis_pro_model_nao_aceita_outro_modelo_adidas():
    c = shopping.extrair_criterios("tênis adidas pro model 2.0")
    superstar = _p("Tênis Adidas Superstar", marca="Adidas")
    _, fora = shopping.aplicar_filtros([superstar], c)
    assert "versao_diferente" in fora[0]["excluido_codigos"]
    certo = _p("Tênis Adidas Pro Model 2.0", marca="Adidas")
    dentro, _ = shopping.aplicar_filtros([certo], c)
    assert dentro


def test_marca_esportiva_pedida_filtra_outra_marca():
    c = shopping.extrair_criterios("tênis adidas pro model 2.0")
    nike = _p("Tênis Nike Air Max 90", marca="Nike")
    _, fora = shopping.aplicar_filtros([nike], c)
    assert "marca_diferente" in fora[0]["excluido_codigos"]
    alts = shopping.separar_alternativas(fora, c)
    assert alts and "outra marca" in alts[0]["diferencas"]


# ── Filtros: modelo ──────────────────────────────────────────────────

def test_modelo_irmao_diferente_rejeitado():
    c = shopping.extrair_criterios("celular galaxy s24 256gb")
    s23 = _p("Smartphone Samsung Galaxy S23 256GB", marca="Samsung")
    dentro, fora = shopping.aplicar_filtros([s23], c)
    assert dentro == [] and "modelo_diferente" in fora[0]["excluido_codigos"]
    alts = shopping.separar_alternativas(fora, c)
    assert alts and "s23" in alts[0]["diferencas"]


def test_familia_com_numero_diferente_rejeitada():
    c = shopping.extrair_criterios("iphone 15 128gb")
    i14 = _p("Apple iPhone 14 128GB", marca="Apple")
    _, fora = shopping.aplicar_filtros([i14], c)
    assert "modelo_diferente" in fora[0]["excluido_codigos"]
    i15 = _p("Apple iPhone 15 128GB", marca="Apple")
    dentro, _ = shopping.aplicar_filtros([i15], c)
    assert dentro


def test_modelo_ausente_no_anuncio_vira_alternativa_explicita():
    c = shopping.extrair_criterios("celular galaxy s24")
    generico = _p("Smartphone Samsung Galaxy 5G 128GB", marca="Samsung")
    dentro, fora = shopping.aplicar_filtros([generico], c)
    assert dentro == []
    assert "modelo_nao_confirmado" in fora[0]["excluido_codigos"]
    alts = shopping.separar_alternativas(fora, c)
    assert alts and "modelo não indicado" in alts[0]["diferencas"]


def test_titulo_com_modelo_exato_passa():
    c = shopping.extrair_criterios("celular galaxy s24")
    exato = _p("Samsung Galaxy S24 5G 128GB", marca="Samsung")
    dentro, _ = shopping.aplicar_filtros([exato], c)
    assert dentro


def test_pedido_sem_modelo_nao_rejeita_por_modelo():
    c = shopping.extrair_criterios("celular samsung até 1000")
    p = _p("Samsung Galaxy A54 128GB", marca="Samsung",
           preco=899.0, preco_texto="R$ 899,00")
    dentro, _ = shopping.aplicar_filtros([p], c)
    assert dentro


# ── Orçamento: modelo e capacidade não viram teto ────────────────────

def test_pro_max_nao_vira_orcamento():
    c = shopping.extrair_criterios("iphone 15 pro max 256gb")
    assert not c["orcamento"]


def test_milhar_sem_separador_nao_e_truncado():
    c = shopping.extrair_criterios("quero gastar até uns R$ 7000")
    assert c["orcamento"].get("max") == 7000.0


def test_capacidade_nao_vira_orcamento():
    c = shopping.extrair_criterios("celular até 512gb de armazenamento")
    assert not c["orcamento"]


# ── Consultas de busca: a referência pedida entra ────────────────────

def test_consulta_inclui_modelo_e_orcamento_sem_duplicar():
    txt = "celular galaxy s24 até R$ 3000"
    c = shopping.extrair_criterios(txt)
    qs = shopping._consultas_produto(c, txt)
    assert qs and "s24" in qs[0] and "3000" not in qs[0]
    assert "preço até 3000" in qs[1]


def test_consulta_adidas_pro_model_com_frases_de_pedido():
    txt = "Adidas pro model 2.0 me mostre o preço, imagem e link"
    c = shopping.extrair_criterios(txt)
    qs = shopping._consultas_produto(c, txt)
    assert any("pro model 2.0" in q for q in qs)
    assert "comprar oferta" in qs[0]
    assert "imagem" not in qs[0] and "preço" not in qs[0] and "link" not in qs[0]


def test_termo_referencia_sem_frases_de_pedido():
    ref = shopping._termo_referencia("me mostre o preço do Galaxy S24 por favor")
    assert "Galaxy S24" in ref
    assert "mostre" not in ref.lower()
    assert "preço" not in ref.lower()


def test_consultas_fallback_quando_so_pedido():
    txt = "me mostre o preço, imagem e link"
    c = shopping.extrair_criterios(txt)
    qs = shopping._consultas_produto(c, txt)
    assert qs and all(q.strip() for q in qs)


# ── Preços: faixa/múltiplas ofertas → menor + "a partir de" ──────────

def _extraido(nome, ofertas):
    return {"nome": nome, "marca": "", "modelo": "", "variante": "",
            "imagem": "", "descricao": "", "avaliacao": None,
            "n_avaliacoes": None, "ofertas_ld": ofertas}


def _oferta(preco, loja="", moeda="BRL", disp="em_estoque", alto=None):
    o = {"preco": preco, "moeda": moeda, "preco_confirmado": preco is not None,
         "disponibilidade": disp, "url_oferta": "", "loja": loja,
         "valido_ate": ""}
    if alto is not None:
        o["preco_alto"] = alto
    return o


def test_oferta_unica_continua_preco_exato():
    ext = _extraido("Fone X", [_oferta(199.9, loja="Loja A")])
    p = shopping.montar_produto(ext, "https://loja.com/p",
                                "https://loja.com/p", "Loja")
    assert p["preco"] == 199.9 and p["preco_texto"] == "R$ 199,90"
    assert p["preco_a_partir_de"] is False


def test_multiplas_ofertas_distintas_usam_menor_com_a_partir_de():
    ext = _extraido("Fone X", [_oferta(299.9, loja="Loja A"),
                               _oferta(249.9, loja="Loja B",
                                       disp="estoque_limitado")])
    p = shopping.montar_produto(ext, "https://loja.com/p",
                                "https://loja.com/p", "Loja")
    assert p["preco"] == 249.9
    assert p["preco_texto"] == "a partir de R$ 249,90"
    assert p["preco_a_partir_de"] is True
    assert p["loja"] == "Loja A"  # loja: 1ª com loja (como antes)
    assert p["disponibilidade"] == "estoque_limitado"  # do preço exibido


def test_ofertas_de_mesmo_preco_nao_viram_faixa():
    ext = _extraido("Fone X", [_oferta(199.9, loja="A"), _oferta(199.9, loja="B")])
    p = shopping.montar_produto(ext, "https://x.com/p", "https://x.com/p", "X")
    assert p["preco_texto"] == "R$ 199,90"
    assert p["preco_a_partir_de"] is False


def test_aggregate_offer_lowprice_vira_a_partir_de():
    pagina = ('<script type="application/ld+json">'
              '{"@type":"Product","name":"Fone Faixa",'
              '"offers":{"@type":"AggregateOffer","lowPrice":"199.90",'
              '"highPrice":"249.90","priceCurrency":"BRL"}}</script>')
    prods = shopping.extrair_ofertas_jsonld(pagina)
    assert prods and prods[0]["ofertas_ld"][0]["preco"] == 199.9
    assert prods[0]["ofertas_ld"][0]["preco_alto"] == 249.9
    p = shopping.montar_produto(prods[0], "https://loja.com/p",
                                "https://loja.com/p", "Loja")
    assert p["preco"] == 199.9 and p["preco_a_partir_de"] is True
    assert p["preco_texto"] == "a partir de R$ 199,90"


def test_aggregate_offer_sem_preco_nao_inventa():
    pagina = ('<script type="application/ld+json">'
              '{"@type":"Product","name":"Fone Z",'
              '"offers":{"@type":"AggregateOffer","priceCurrency":"BRL"}}'
              '</script>')
    prods = shopping.extrair_ofertas_jsonld(pagina)
    p = shopping.montar_produto(prods[0], "https://l.com/p",
                                "https://l.com/p", "L")
    assert p["preco"] is None and not p["preco_confirmado"]
    assert p["preco_texto"] == shopping.PRECO_NAO_CONFIRMADO
    assert p["preco_a_partir_de"] is False


def test_dedupe_mantem_flag_da_oferta_mais_barata():
    a = shopping.montar_produto(_extraido("Fone X", [_oferta(299.9, loja="A")]),
                                "https://a.com/p", "https://a.com/p", "A")
    b = shopping.montar_produto(_extraido("Fone X", [_oferta(199.9, loja="B"),
                                                     _oferta(219.9, loja="B")]),
                                "https://b.com/p", "https://b.com/p", "B")
    unicos = shopping.deduplicar([a, b])
    assert len(unicos) == 1
    assert unicos[0]["preco"] == 199.9
    assert unicos[0]["preco_a_partir_de"] is True
    assert unicos[0]["preco_texto"] == "a partir de R$ 199,90"


# ── Métricas: descartes e alternativas por código ──────────────────────

def test_resumo_verificacao_conta_codigos_de_descarte():
    descartes = [{"excluido_codigos": ["modelo_diferente", "usado"]},
                 {"excluido_codigos": ["modelo_diferente"]},
                 {"excluido_codigos": []}]
    alternativas = [{"excluido_codigos": ["preco_acima"]}]
    r = shopping._resumo_verificacao(
        [{"link_veredito": "verificado", "imagem_veredito": "parcial"}],
        descartes, alternativas)
    assert r["links"]["verificado"] == 1 and r["links"]["total"] == 1
    assert r["imagens"]["parcial"] == 1 and r["imagens"]["total"] == 1
    assert r["descartes_por_codigo"] == {"modelo_diferente": 2, "usado": 1}
    assert r["alternativas_por_codigo"] == {"preco_acima": 1}


def test_resumo_verificacao_retrocompativel_sem_listas():
    r = shopping._resumo_verificacao([])
    assert set(r) == {"links", "imagens"}  # sem listas, saída antiga intacta
