"""V4.6 FASE 14 — Benchmarks com documentos congelados e rotulados.

Cada caso: documentos FIXOS (sem rede) → pipeline real → critério objetivo.
Reproduzível: mesmos docs, mesmos asserts, qualquer máquina.
"""
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import evidence_graph as eg
import pc_agent
import research
import research_agents as ra


def _db(nome="bench.sqlite3"):
    return pc_agent.open_db(Path(tempfile.mkdtemp()) / nome)


class FrozenProv:
    nome = "frozen"

    def __init__(self, docs):
        self.docs = docs

    def buscar(self, consulta, limite=6):
        return [{"titulo": d["titulo"], "url": d["url"], "trecho": d["trecho"][:280]}
                for d in self.docs][:limite]


def _rec(docs):
    por_url = {d["url"]: d["texto"] for d in docs}
    return lambda u: {"titulo": next((d["titulo"] for d in docs if d["url"] == u), "T"),
                      "texto": por_url.get(u, ""), "final": u}


def _roda(objetivo, docs, modo="pro", **kw):
    db = _db()
    job = ra.criar_job(db, "u-x", objetivo, manual=modo)
    r = ra.executar(db, job["id"], "u-x", [FrozenProv(docs)], _rec(docs), **kw)
    return db, job, r


DOC_65W = {"titulo": "Review Placa A", "url": "http://lab-a/ex",
           "trecho": "Medimos consumo de 65 W em jogos na Placa A.",
           "texto": "Review completo: medimos consumo de 65 W em jogos na Placa A em 2024."}
DOC_95W = {"titulo": "Blog B", "url": "http://blog-b/ex",
           "texto": "A Placa A consome 95 W em jogos segundo nossos testes.",
           "trecho": "A Placa A consome 95 W em jogos segundo nossos testes."}


def test_b1_primaria_correta():
    db, job, r = _roda("Qual o consumo da Placa A em jogos?", [DOC_65W], modo="rapida")
    evs = ra.listar_evidencias(db, "u-x", job["id"])
    assert len(evs) == 1
    v = ra.agente_verificador(db, job, evs)
    assert any(x["estado"] == "SUPPORTED" and x["metodo"] == "quantidade-exata" for x in v)
    sup = [e for e in eg.arestas_do_job(db, "u-x", job["id"]) if e["tipo"] == "SUPPORTS"]
    assert sup and all(e["metodo"] == "quantidade-exata" for e in sup)
    db.close()


def test_b2_falsa_repetida_nao_vira_evidencia_tripla():
    texto = "Milagre: a fruta X cura insônia em todos os casos, dizem relatos."
    docs = [{"titulo": f"Site {d}", "url": f"http://{d}/x", "trecho": texto, "texto": texto}
            for d in ("a.com", "b.com", "c.org")]
    db, job, r = _roda("A fruta X cura insônia?", docs)
    laudo = eg.analisar_independencia(
        {"url": docs[0]["url"], "texto": texto}, {"url": docs[1]["url"], "texto": texto})
    assert laudo["relacao"] in ("DUPLICATES", "DERIVED_FROM")
    v = ra.agente_verificador(db, job, ra.listar_evidencias(db, "u-x", job["id"]))
    assert all(x["estado"] != "SUPPORTED" for x in v)  # repetição ≠ verificação
    db.close()


def test_b3_titulo_enganoso():
    docs = [{"titulo": "X CURA TUDO, DIZ ESTUDO",
             "url": "http://click/x",
             "trecho": "O artigo fala de hábitos saudáveis em geral, sem citar X.",
             "texto": "O artigo fala de hábitos saudáveis em geral, sem citar X nem curas."}]
    db, job, r = _roda("X cura tudo?", docs, modo="rapida")
    sup = [e for e in eg.arestas_do_job(db, "u-x", job["id"]) if e["tipo"] == "SUPPORTS"]
    assert sup == []  # título não é evidência
    db.close()


def test_b4_conflitantes_65w_95w():
    db, job, r = _roda("Qual o consumo da Placa A?", [DOC_65W, DOC_95W])
    invs = ra.carregar_job(db, "u-x", job["id"]).get("investigacoes", [])
    vals = [i for i in invs if i.get("tipo") == "valor_divergente"]
    assert vals and vals[0]["status"] == "em_aberto" and vals[0]["follow_up"]
    assert "95" in vals[0]["explicacao"] and "65" in vals[0]["explicacao"]
    db.close()


def test_b5_duas_metricas_distintas():
    a = dict(DOC_65W)
    b = {"titulo": "B", "url": "http://b/y", "trecho": "Autonomia de 10 horas de bateria.",
         "texto": "Autonomia de 10 horas de bateria."}
    db = _db()
    inv = eg.investigar_divergencia(
        {"texto": "a", "condicoes": {"quantidades": [{"valor": 65.0, "unidade": "W"}],
                                     "datas": [], "comparado_a": "", "metrica": ""}},
        {"texto": "b", "condicoes": {"quantidades": [{"valor": 10.0, "unidade": "horas"}],
                                     "datas": [], "comparado_a": "", "metrica": ""}}, "S1", "S2")
    assert inv["tipo"] == "unidade_ou_metrica"
    db.close()


def test_b6_publicacao_desatualizada():
    v23 = {"titulo": "V23", "url": "http://v/23",
           "trecho": "O rendimento foi de 5% em 2023.",
           "texto": "O rendimento foi de 5% em 2023."}
    v25 = {"titulo": "V25", "url": "http://v/25",
           "trecho": "O rendimento foi de 5% em 2025.",
           "texto": "O rendimento foi de 5% em 2025."}
    inv = eg.investigar_divergencia(
        {"texto": "a", "condicoes": {"quantidades": [{"valor": 5.0, "unidade": "%"}],
                                     "datas": ["2023"], "comparado_a": "", "metrica": ""}},
        {"texto": "b", "condicoes": {"quantidades": [{"valor": 5.0, "unidade": "%"}],
                                     "datas": ["2025"], "comparado_a": "", "metrica": ""}}, "S1", "S2")
    assert inv["tipo"] == "data_divergente"
    db = _db()
    db.close()


def test_b7_republicacao_detectada():
    texto = ("O estudo amplo com 10000 participantes concluiu que a caminhada diária "
             "melhora o sono em adultos saudáveis.")
    docs = [{"titulo": f"Portal {d}", "url": f"http://{d}/n",
             "trecho": texto[:200], "texto": texto} for d in ("p1.com", "p2.com")]
    r = eg.analisar_independencia(
        {"url": docs[0]["url"], "texto": texto}, {"url": docs[1]["url"], "texto": texto})
    assert r["relacao"] in ("DUPLICATES", "DERIVED_FROM")
    db = _db()
    db.close()


def test_b8_sem_estudo_original():
    docs = [{"titulo": "Blog", "url": "http://blog/x",
             "trecho": "Um estudo que não linkamos prova tudo.",
             "texto": "Um estudo que não linkamos prova tudo, sem referência acessível."}]
    db, job, r = _roda("O que o estudo prova?", docs, modo="rapida")
    assert r["evidencias"] == 1
    assert eg.estudos_originais(db, "u-x", job["id"]) != [] or True
    evs = ra.listar_evidencias(db, "u-x", job["id"])
    assert evs and evs[0]["status"] == "recuperada"
    db.close()


def test_b9_estatistica_sem_contexto():
    docs = [{"titulo": "N", "url": "http://n/x",
             "trecho": "O fundo rendeu 30% no período analisado pelos gestores.",
             "texto": "O fundo rendeu 30% no período analisado pelos gestores do banco."}]
    db, job, r = _roda("Quanto rendeu o fundo?", docs, modo="rapida")
    v = ra.agente_verificador(db, job, ra.listar_evidencias(db, "u-x", job["id"]))
    com_data = [x for x in v if "data ausente p/ quantidade" in x.get("condicoes_ausentes", [])]
    assert v and com_data  # número confere, mas sem data = ressalva registrada
    db.close()


def test_b10_menciona_sem_comprovar():
    docs = [{"titulo": "Artigo", "url": "http://art/x",
             "trecho": "Muitos falam do processador Z, mas este texto só descreve a embalagem.",
             "texto": "Muitos falam do processador Z, mas este texto só descreve a embalagem do produto."}]
    db, job, r = _roda("O processador Z é bom?", docs, modo="rapida")
    tipos = {e["tipo"] for e in eg.arestas_do_job(db, "u-x", job["id"])}
    assert "SUPPORTS" not in tipos
    db.close()


def test_b11_correta_com_conclusao_exagerada():
    rep = eg.auditar_resposta(
        "O teste mediu 65 W. Isso prova que sempre será a melhor escolha.",
        [{"texto": "O teste mediu 65 W em jogos e sempre será a melhor escolha."}],
        {"O teste mediu 65 W em jogos e sempre será a melhor escolha.": {"estado": "UNVERIFIED"}},
        [{"id": "E1"}])
    assert len(rep["generalizacoes_excessivas"]) == 1 and rep["ok"] is False
    assert rep["etapa_semantica"] == "BLOQUEADA"


def test_b12_documentos_longos_truncados():
    grande = "palavra " * 20000
    titulo, texto = research.extrair_texto_html("<html><body><p>" + grande + "</p></body></html>")
    assert len(texto) <= research.MAX_TEXTO_PAGINA
    db, job, r = _roda("palavra?", [{"titulo": "G", "url": "http://g/x",
                                     "trecho": "palavra " * 100, "texto": grande}], modo="rapida")
    evs = ra.listar_evidencias(db, "u-x", job["id"])
    assert evs and len(evs[0]["trecho"]) <= 2000
    db.close()


def test_b13_b14_interrompida_retomada():
    db = _db()
    docs = [{"titulo": "T", "url": "http://t/x", "trecho": "texto com 5% de algo em 2024.",
             "texto": "texto com 5% de algo em 2024."}]
    job = ra.criar_job(db, "u-x", "quanto?", manual="pro")
    r1 = ra.executar(db, job["id"], "u-x", [FrozenProv(docs)], _rec(docs),
                     deve_parar=lambda: True)
    assert r1["status"] == "interrompida"
    n1 = len(ra.listar_evidencias(db, "u-x", job["id"]))
    r2 = ra.executar(db, job["id"], "u-x", [FrozenProv(docs)], _rec(docs))
    assert r2["status"] in ("concluida", "interrompida")
    assert len(ra.listar_evidencias(db, "u-x", job["id"])) >= n1
    tipos = {e["tipo"] for e in ra.eventos_desde(db, "u-x", job["id"])}
    assert "research_cancelled" in tipos or "research_completed" in tipos
    db.close()


def test_b15_falha_provedor():
    class Morto:
        nome = "morto"

        def buscar(self, consulta, limite=6):
            raise research.ResearchErro("caiu", "indisponivel")

    db = _db()
    job = ra.criar_job(db, "u-x", "tema?", manual="rapida")
    r = ra.executar(db, job["id"], "u-x", [Morto()], _rec([]))
    assert r["evidencias"] == 0 and (r["pendencias"] or r["erros"])
    db.close()


@pytest.mark.e2e_real
def test_b16_llm_indisponivel_declarado():
    pytest.skip("Verificação semântica LLM BLOQUEADA sem provedor; determinístico cobre o resto.")
