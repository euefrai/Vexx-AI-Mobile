"""V5.7 — Shopping: marca obrigatória, alternativas explícitas, specs pareadas.

Regressões reais cobertas (auditoria V5.7, 2026-10-17): o pedido
"notebook lenovo ideapad 3i 8gb 512gb" devolvia Asus Vivobook e Dell Alienware
como se fossem o pedido (o filtro nunca olhava `criterios.marcas`) e o par
"8gb 512gb" não virava spec de RAM/armazenamento.
"""
import shopping


def _p(nome, marca="", preco=3000.0, **kw):
    base = {"id": nome.lower().replace(" ", "-")[:40], "nome": nome, "marca": marca,
            "modelo": "", "variante": "", "imagem": "", "descricao": "",
            "loja": "loja.example", "loja_dominio": "loja.example",
            "url": "https://loja.example/p", "url_final": "https://loja.example/p",
            "url_item": "", "preco": preco, "moeda": "BRL",
            "preco_confirmado": True, "preco_texto": f"R$ {preco:,.2f}",
            "preco_origem": "jsonld", "disponibilidade": "desconhecida",
            "avaliacao": None, "n_avaliacoes": 0, "specs": {},
            "verificado_em": "2026-10-17T00:00:00+00:00"}
    base.update(kw)
    return base


# ── Marca pedida é critério obrigatório ──────────────────────────────

def test_marca_pedida_filtra_e_vira_alternativa_explicita():
    lenovo = _p("Notebook Lenovo IdeaPad Slim 3 8GB 512GB", marca="KaBuM!")
    asus = _p("Notebook Asus Vivobook Go 15 16GB 512GB", marca="Loja Asus")
    generico = _p("Notebook 15.6 polegadas 8GB 512GB", marca="KaBuM!")
    criterios = {"orcamento": {}, "specs": {}, "marcas": ["lenovo"], "texto": "x"}
    dentro, fora = shopping.aplicar_filtros([lenovo, asus, generico], criterios)
    assert [p["nome"] for p in dentro] == [lenovo["nome"]]
    codigos = {p["nome"]: p.get("excluido_codigos") for p in fora}
    assert codigos[asus["nome"]] == ["marca_diferente"]
    assert codigos[generico["nome"]] == ["marca_nao_confirmada"]
    alts = shopping.separar_alternativas(fora, criterios)
    textos = " | ".join(a["diferencas"] for a in alts)
    assert "outra marca: asus" in textos
    assert "marca não confirmada" in textos
    assert all("pedido: lenovo" in a["diferencas"] for a in alts)


def test_marca_diferente_com_preco_acima_mostra_as_duas_diferencas():
    caro = _p("Notebook Asus Vivobook", marca="Asus", preco=5800.0,
              preco_texto="R$ 5.800,00")
    criterios = {"orcamento": {"max": 5000.0}, "specs": {}, "marcas": ["lenovo"],
                 "texto": "x"}
    _, fora = shopping.aplicar_filtros([caro], criterios)
    assert set(fora[0]["excluido_codigos"]) == {"preco_acima", "marca_diferente"}
    alts = shopping.separar_alternativas(fora, criterios)
    assert alts and "outra marca" in alts[0]["diferencas"]
    assert "acima do teto" in alts[0]["diferencas"]


def test_sem_marcas_no_pedido_nada_muda():
    asus = _p("Notebook Asus Vivobook Go 15", marca="Asus")
    dentro, fora = shopping.aplicar_filtros([asus], {"orcamento": {}, "specs": {}})
    assert dentro == [asus] and fora == []


def test_marca_conhecida_ignora_gpu_no_fim_do_nome():
    p = _p("Notebook Gamer Dell Alienware 15, Intel Core i5, 8GB RAM, SSD 512GB, "
           "NVIDIA GeForce RTX 4050", marca="KaBuM!")
    criterios = {"orcamento": {}, "specs": {}, "marcas": ["lenovo"], "texto": "x"}
    _, fora = shopping.aplicar_filtros([p], criterios)
    alts = shopping.separar_alternativas(fora, criterios)
    assert alts and "outra marca: dell" in alts[0]["diferencas"]


# ── Armazenamento: RAM pequena não engana ────────────────────────────

def test_armazenamento_nao_confunde_ram_com_ssd():
    criterios = {"orcamento": {}, "specs": {"armazenamento_gb": 512},
                 "marcas": ["lenovo"], "texto": "x"}
    ok = _p("Notebook Lenovo LOQ 16GB RAM SSD 512GB", marca="Lenovo")
    dentro, fora = shopping.aplicar_filtros([ok], criterios)
    assert dentro == [ok] and fora == []
    p2 = _p("Notebook Lenovo 8GB RAM SSD 256GB", marca="Lenovo")
    _, fora2 = shopping.aplicar_filtros([p2], criterios)
    assert "armazenamento_abaixa" in fora2[0]["excluido_codigos"]
    alts = shopping.separar_alternativas(fora2, criterios)
    assert alts and "armazenamento 256GB" in alts[0]["diferencas"]


# ── Specs pareadas "8gb 512gb" ───────────────────────────────────────

def test_criterios_capturam_par_ram_armazenamento():
    c = shopping.extrair_criterios("notebook lenovo ideapad 3i 8gb 512gb")
    assert c["categoria"] == "notebook"
    assert c["marcas"] == ["lenovo"]
    assert c["specs"].get("ram_fisica_gb") == 8
    assert c["specs"].get("armazenamento_gb") == 512


def test_par_de_numeros_fora_de_contexto_nao_vira_spec():
    c = shopping.extrair_criterios("fone bluetooth 8gb 512gb")
    assert "ram_fisica_gb" not in c["specs"]
    assert "armazenamento_gb" not in c["specs"]


# ── Card JDUI: link exato e vereditos ────────────────────────────────

def test_card_prefere_url_item_e_carrega_vereditos():
    p = _p("Notebook Lenovo IdeaPad Slim 3", marca="Lenovo",
           url="https://loja.example/c/notebooks",
           url_item="https://loja.example/produto/9",
           link_veredito="verificado", imagem_veredito="verificado")
    card = shopping._jdui_produto(p)
    assert card["url"] == "https://loja.example/produto/9"
    assert card["link_veredito"] == "verificado"
    assert card["imagem_veredito"] == "verificado"


def test_selo_nao_esconde_listagem_ou_nao_verificado():
    p = _p("Notebook Lenovo", marca="Lenovo", item_de_listagem=True)
    assert "listagem" in shopping._selo_verificacao(p)
    p2 = _p("Notebook Lenovo", marca="Lenovo")
    assert "não verificado" in shopping._selo_verificacao(p2)
    p3 = _p("Notebook Lenovo", marca="Lenovo", link_veredito="reprovado")
    assert "REPROVADO" in shopping._selo_verificacao(p3)
