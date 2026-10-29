"""V5.9.9 — fontes preferenciais por assunto, sem allowlist exclusiva.

A preferência muda ordem de consulta/provedor e desempata candidatos. Ela não
cria resultados, não confirma conteúdo e não impede a busca geral: quando a
fonte preferida falha, o fluxo existente continua e a falha fica registrada.
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

import query_intelligence as qi
import research
import search_orchestrator as orch
import search_providers as sp
import shopping
import source_priority as spri

NOW = datetime(2026, 10, 24, 14, tzinfo=timezone.utc)


def _hoje():
    return datetime.now(timezone.utc).astimezone(
        ZoneInfo("America/Bahia")).date().isoformat()


# ── Catálogo de fontes por assunto ─────────────────────────────────────

@pytest.mark.parametrize("consulta,pack,primary", [
    ("Notícias de hoje de Ubatã e região", "ubata_news", "ubatanoticias.com.br"),
    ("Notícias da semana de Ubatã", "ubata_news", "ubatanoticias.com.br"),
    ("Últimas notícias de Salvador", "bahia_news", "g1.globo.com"),
    ("Notícias gerais do mundo hoje", "world_news", "g1.globo.com"),
    ("Principais notícias do Brasil hoje", "brazil_news", "g1.globo.com"),
    ("Quais os melhores jogos de RPG de 2026", "games", "ign.com.br"),
    ("Comportamento humano e psicologia", "psychology", "scielo.br"),
    ("Quem foi Nietzsche e o que é niilismo", "philosophy", "plato.stanford.edu"),
    ("Teorema de Pitágoras exercícios", "mathematics", "mathworld.wolfram.com"),
    ("Filmes da Marvel para assistir", "entertainment", "g1.globo.com"),
])
def test_topic_packs_have_a_real_primary_source(consulta, pack, primary):
    plan = spri.detect(consulta)
    assert plan and plan["id"] == pack
    assert plan["primary"][0] == primary


def test_specific_news_topic_does_not_become_generic_world_news():
    assert spri.detect("Notícias energia solar") is None
    assert spri.detect("Notícias de hoje")["id"] == "world_news"


def test_ubata_query_is_scoped_to_the_local_site_without_inventing():
    plan = spri.detect("Notícias de hoje de Ubatã e região")
    assert plan["primary"] == ("ubatanoticias.com.br",)
    assert spri.site_queries(plan, "Notícias de hoje de Ubatã e região", 1) == [
        "Notícias de hoje de Ubatã e região site:ubatanoticias.com.br"]


def test_explicit_source_wins_and_is_not_duplicated_in_query():
    plan = spri.detect("Notícias de hoje no G1")
    assert plan["explicit"] is True
    assert plan["primary"] == ("g1.globo.com",)
    assert spri.site_queries(plan, "Notícias de hoje no G1", 1) == [
        "Notícias de hoje site:g1.globo.com"]


def test_explicit_domain_is_recognized_even_without_catalog():
    plan = spri.detect("Notícias no site example.com.br")
    assert plan["id"] == "explicit_source"
    assert plan["primary"] == ("example.com.br",)


def test_long_queries_keep_the_complete_domain_and_balanced_store_expression():
    query='notebook '+('processador memória armazenamento '*12)
    plan=spri.detect('Notícias de hoje de Ubatã')
    scoped=spri.site_queries(plan,query)[0]
    assert len(scoped)<=240 and scoped.endswith('site:ubatanoticias.com.br')
    stores=spri.shopping_queries('comprar notebook',query)[0]
    assert len(stores)<=240 and stores.count('(')==stores.count(')')


def test_non_news_questions_about_ubata_do_not_select_the_local_paper():
    for query in ('qual o clima em Ubatã','distância de Ubatã até Salvador'):
        plan=spri.detect(query)
        assert not plan or plan['id']!='ubata_news'


def test_ambiguous_portal_aliases_need_news_context():
    for consulta in ("O que é um globo ocular", "A tarde é melhor para estudar"):
        plan = spri.detect(consulta)
        assert not (plan and plan.get("explicit"))
    assert spri.detect("Notícias de hoje no Globo")["primary"] == ("g1.globo.com",)


# ── Shopping: lojas preferidas ─────────────────────────────────────────

def test_shopping_preferred_store_order_is_explicit():
    query = spri.shopping_queries("quero comprar um notebook", "notebook", 1)[0]
    positions = [query.index(f"site:{domain}") for domain in (
        "kabum.com.br", "shopee.com.br", "mercadolivre.com.br",
        "americanas.com.br", "magazineluiza.com.br", "amazon.com.br")]
    assert positions == sorted(positions)
    assert spri.shopping_rank("https://www.kabum.com.br/produto/1/x") == 0
    assert spri.shopping_rank("https://www.shopee.com.br/product/1") == 1
    assert spri.shopping_rank("https://loja-independente.com.br/produto/x") == 99


def test_explicit_store_query_drops_the_store_name_but_keeps_scope():
    assert spri.shopping_queries("preço do Galaxy S24 na Kabum",
                                 "Galaxy S24", 2) == [
        "Galaxy S24 site:kabum.com.br"]


def test_product_queries_keep_legacy_shape_and_order():
    criterios = shopping.extrair_criterios(
        "Notebook Lenovo 16GB RAM até R$ 3000")
    consultas = shopping._consultas_produto(criterios, criterios["texto"])
    assert len(consultas) <= 2
    assert "comprar oferta" in consultas[0]
    assert "preço até 3000" in consultas[1]


def test_candidate_order_prefers_store_only_inside_the_same_type():
    ordered = shopping._ordenar_candidatos([
        {"url": "https://loja-independente.com.br/produto/notebook"},
        {"url": "https://www.magazineluiza.com.br/notebook/informatica/s/in/note/"},
        {"url": "https://www.amazon.com.br/dp/B0TESTE"},
        {"url": "https://www.kabum.com.br/produto/1/notebook"},
    ])
    assert [item["url"] for item in ordered] == [
        "https://www.kabum.com.br/produto/1/notebook",
        "https://www.amazon.com.br/dp/B0TESTE",
        "https://loja-independente.com.br/produto/notebook",
        "https://www.magazineluiza.com.br/notebook/informatica/s/in/note/",
    ]


def _sem_mlb(*args, **kwargs):
    raise research.ResearchErro("Provedor HTTP 403.", "http")


def _web(by_query):
    chamadas = []

    def _fn(consulta, max_resultados=6, timeout=8.0, orcamento=None):
        chamadas.append(consulta)
        return ([dict(item) for item in by_query(consulta)],
                {"estado": "ok", "provedores": {"usados": {"bing": 1}},
                 "etapas": []})
    _fn.chamadas = chamadas
    return _fn


def test_shopping_chain_queries_preferred_store_before_generic_web(monkeypatch):
    monkeypatch.setattr(shopping, "buscar_mlb", _sem_mlb)
    monkeypatch.setattr(research, "buscar_ddg", lambda *a, **k: [])
    def _resultado(consulta):
        if "site:" in consulta:
            return [
                {"titulo": "Notebook KaBuM 1", "trecho": "notebook",
                 "url": "https://www.kabum.com.br/produto/1/notebook"},
                {"titulo": "Notebook KaBuM 2", "trecho": "notebook",
                 "url": "https://www.kabum.com.br/produto/2/notebook"},
            ]
        return [{"titulo": "Notebook loja", "trecho": "notebook",
                 "url": "https://loja-independente.com.br/produto/notebook"}]
    web = _web(_resultado)
    monkeypatch.setattr(research, "_buscar_orquestrado", web)

    achados, etapas = shopping.buscar_com_fallback(
        "notebook", texto_lojas="quero comprar um notebook")

    assert web.chamadas and "site:kabum.com.br" in web.chamadas[0]
    assert all("kabum.com.br" in item["url"] for item in achados)
    assert any(etapa.startswith("web:") for etapa in etapas)


def test_shopping_chain_falls_back_to_generic_web_when_store_fails(monkeypatch):
    monkeypatch.setattr(shopping, "buscar_mlb", _sem_mlb)
    monkeypatch.setattr(research, "buscar_ddg", lambda *a, **k: [])
    def _resultado(consulta):
        if "site:" in consulta:
            return [{"titulo": "Guia de notebooks", "trecho": "guia",
                     "url": "https://blog.example/guia-notebooks"}]
        return [
            {"titulo": "Notebook Lenovo 1", "trecho": "notebook",
             "url": "https://loja-a.example/produto/notebook-1"},
            {"titulo": "Notebook Lenovo 2", "trecho": "notebook",
             "url": "https://loja-b.example/produto/notebook-2"},
        ]
    web = _web(_resultado)
    monkeypatch.setattr(research, "_buscar_orquestrado", web)

    achados, _etapas = shopping.buscar_com_fallback(
        "notebook", texto_lojas="quero comprar um notebook")

    assert len(web.chamadas) == 2 and "site:" in web.chamadas[0]
    assert "site:" not in web.chamadas[1]
    urls = {item["url"] for item in achados}
    assert {"https://loja-a.example/produto/notebook-1",
            "https://loja-b.example/produto/notebook-2"} <= urls


# ── Query Intelligence: local, região e escopo mundial ─────────────────

def test_ubata_region_is_location_not_extra_entity_and_week_is_inferred():
    req = qi.analyze("Notícias da semana de Ubatã e região", now=NOW)
    params = req["parameters"]
    assert params["location"] == "Ubatã"
    assert params["start_date"] == "2026-10-17"
    assert params["end_date"] == "2026-10-24"
    assert params["window_inferred"] is True
    assert req["search_query"] == '"Ubatã" notícias'


def test_today_in_ubata_region_keeps_only_the_city():
    req = qi.analyze("Notícias de hoje de Ubatã e região", now=NOW)
    assert req["parameters"]["location"] == "Ubatã"
    assert req["parameters"]["start_date"] == "2026-10-24"


def test_world_news_is_scope_not_a_city_constraint():
    req = qi.analyze("Últimas notícias do mundo", now=NOW)
    assert "location" not in req["parameters"]
    assert req["parameters"]["scope"] == "world"


def test_named_source_is_not_a_news_location():
    req = qi.analyze("Notícias de hoje no G1", now=NOW)
    assert "location" not in req["parameters"]
    assert req["parameters"]["start_date"] == "2026-10-24"


def test_named_source_with_topic_keeps_topic_and_drops_source():
    req = qi.analyze("Notícias de hoje no G1 sobre economia", now=NOW)
    assert "location" not in req["parameters"]
    assert req["parameters"]["topic"] == "economia"
    assert "economia" in req["search_query"]


# ── Orquestrador: prioridade primeiro, fallback honesto ────────────────

def test_orchestrator_tries_ubata_site_first_and_marks_priority(monkeypatch):
    # O feed do publicador é uma fonte adicional real; este teste mede a
    # ordem dos provedores, então isola a rede e desliga o feed.
    monkeypatch.setenv("JULIA_PREFERRED_NEWS_FEEDS", "0")
    chamadas = []

    def _search(nome, consulta, **kwargs):
        chamadas.append((nome, consulta))
        if "site:ubatanoticias.com.br" in consulta:
            return [{"titulo": "Ubatã: prefeitura anuncia obras na cidade",
                     "trecho": "Ubatã obras", "tipo": "noticia",
                     "url": "https://ubatanoticias.com.br/noticia/obras",
                     "origem": nome, "publicado_em": _hoje()}]
        raise sp.ErroProvedor("sem resultados", "sem_resultados")

    monkeypatch.setattr(sp, "buscar", _search)
    resultado = orch.pesquisar(
        "Notícias de hoje de Ubatã e região",
        orcamento={"max_consultas": 1, "max_provedores": 4,
                   "timeout_total": 5.0, "min_resultados": 1})

    assert chamadas and chamadas[0][1].endswith("site:ubatanoticias.com.br")
    assert resultado["prioridade_fonte"]["id"] == "ubata_news"
    assert resultado["achados"][0]["prioridade_fonte"] == "primary"


def test_priority_failure_continues_with_general_search(monkeypatch):
    monkeypatch.setenv("JULIA_PREFERRED_NEWS_FEEDS", "0")
    chamadas = []

    def _search(nome, consulta, **kwargs):
        chamadas.append((nome, consulta))
        if "site:" in consulta:
            raise sp.ErroProvedor("sem resultados", "sem_resultados")
        return [{"titulo": "Ubatã: prefeitura anuncia obras na cidade",
                 "trecho": "Ubatã obras", "tipo": "noticia",
                 "url": "https://example.org/ubata/obras", "origem": nome,
                 "publicado_em": _hoje()}]

    monkeypatch.setattr(sp, "buscar", _search)
    resultado = orch.pesquisar(
        "Notícias de hoje de Ubatã e região",
        orcamento={"max_consultas": 2, "max_provedores": 2,
                   "max_tentativas": 5, "timeout_total": 5.0,
                   "min_resultados": 1})

    assert chamadas[0][1].endswith("site:ubatanoticias.com.br")
    assert any("site:" not in consulta for _, consulta in chamadas)
    assert any("retomando a busca geral" in etapa
               for etapa in resultado["etapas"])


def test_explicit_providers_keep_legacy_query_order(monkeypatch):
    chamadas = []

    def _search(nome, consulta, **kwargs):
        chamadas.append(consulta)
        return [{"titulo": "Ubatã: obra", "trecho": "Ubatã obra",
                 "tipo": "noticia", "url": "https://example.org/ubata",
                 "origem": nome, "publicado_em": _hoje()}]

    monkeypatch.setattr(sp, "buscar", _search)
    resultado = orch.pesquisar(
        "Notícias de hoje de Ubatã e região", provedores=["bing"],
        orcamento={"max_consultas": 1, "timeout_total": 5.0})

    assert chamadas == ['"Ubatã" notícias']
    assert resultado["prioridade_fonte"] is None
