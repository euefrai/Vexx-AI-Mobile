"""V5.1 Intent Engine 2.0: estrutura, restrições, referências, validador."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import intent


def test_shopping_completo_spec():
    r = intent.analisar(
        "Lucas, encontre notebooks até R$ 2.000, apenas novos, com 8 GB de RAM, e mostre fotos.")
    assert r["intencao"] == "shopping"
    assert r["entidades"]["categoria"] == "notebook"
    assert r["entidades"]["orcamento"]["max"] == 2000.0
    assert r["entidades"]["specs"]["ram_fisica_gb"] == 8
    assert r["ferramentas"][0] == "shopping"
    assert r["restricoes"]["formato"].get("midia") == "imagens"


def test_sem_evidencia_e_conversa():
    for t in ("qual a capital da França?", "oi", "", "hmm..."):
        r = intent.analisar(t)
        assert r["intencao"] == "conversa"
        assert r["ferramentas"] == ["llm"]


def test_uma_evidencia_fraca_nao_roteia():
    r = intent.analisar("oferta")
    assert r["intencao"] == "conversa"
    assert "shopping" in r["secundarias"]


def test_negativas_e_proibicao_pesquisa():
    r = intent.analisar("Não quero produtos usados.")
    assert "produtos usados" in r["restricoes"]["proibidas"]
    r = intent.analisar("Não pesquise, apenas explique.")
    assert "pesquisar" in r["restricoes"]["proibidas"]
    assert r["podem_pesquisar"] is False
    assert "research" not in r["ferramentas"] and "shopping" not in r["ferramentas"]


def test_formato_linhas():
    assert intent.analisar("Responda em duas linhas.")["restricoes"]["formato"] == {"max_linhas": 2}
    assert intent.analisar("resuma em 3 linhas")["restricoes"]["formato"] == {"max_linhas": 3}
    assert intent.analisar("seja breve")["restricoes"]["formato"] == {}


def test_correcao_explicita():
    assert intent.analisar("Não, eu quis dizer outro modelo.")["correcao"] is True
    assert intent.analisar("na verdade era 8GB, não 4GB")["correcao"] is True
    assert intent.analisar("Compare os dois primeiros.")["correcao"] is False
    assert intent.analisar("crie um quiz de Python")["correcao"] is False


def test_referencias():
    assert intent.analisar("Compare os dois primeiros.")["referencias"] == {"tipo": "primeiros_n", "n": 2}
    assert intent.analisar("explique melhor o último ponto.")["referencias"]["tipo"] == "ultimo"
    assert intent.analisar("retire a terceira opção.")["referencias"]["tipo"] == "terceira"


def test_followup_resolve_com_contexto():
    r = intent.analisar("Compare os dois primeiros.",
                        {"ultimos_resultados": "shopping"})
    assert r["intencao"] == "shopping"
    assert r["ferramentas"][0] == "shopping"
    r = intent.analisar("Compare os dois primeiros.")
    assert r["intencao"] == "conversa"


def test_identidade_memoria_calculo():
    assert intent.analisar("qual é o seu nome?")["intencao"] == "identidade"
    assert intent.analisar("lembre-se que meu foco é concursos")["intencao"] == "memoria"
    assert intent.analisar("quanto é 15% de 200?")["intencao"] == "calculo"
    assert intent.analisar("pesquise a fundo sobre buracos negros")["intencao"] == "pesquisa_profunda"


def test_validador():
    it = intent.analisar("Responda em duas linhas.")
    v = intent.validar(it, "linha um\nlinha dois\nlinha três\nlinha quatro\nlinha cinco")
    assert v["ok"] is False
    assert v["violacoes"][0]["codigo"] == "formato_longo"
    v2 = intent.validar(it, "linha um\nlinha dois")
    assert v2["ok"] is True
    it2 = intent.analisar("Não quero nada usado.")
    v3 = intent.validar(it2, "recomendo este usado em ótimo estado")
    assert any(x["codigo"] == "restricao_proibida" for x in v3["violacoes"])
    v4 = intent.validar(intent.analisar("pesquise sobre café e traga as fontes"),
                        "pesquisei nas fontes e concluí X",
                        {"ferramentas_usadas": []})
    assert any(x["codigo"] == "acao_nao_executada" for x in v4["violacoes"])
    v5 = intent.validar(intent.analisar("oi"), "")
    assert v5["violacoes"][0]["codigo"] == "resposta_vazia"


def test_validador_card_sem_dados():
    it = {"intencao": "shopping", "restricoes": {"proibidas": [], "formato": {}},
          "ferramentas": ["shopping"]}
    v = intent.validar(it, "veja ```jdui productgrid x", {"produtos": []})
    assert any(x["codigo"] == "card_sem_dados" for x in v["violacoes"])


def test_nunca_levanta():
    assert intent.analisar(None)["intencao"] == "conversa"
    assert intent.validar({}, None)["violacoes"][0]["codigo"] == "resposta_vazia"


# ── Integração pc_agent ─────────────────────────────────────────────

def _db50():
    import tempfile
    from pathlib import Path
    import pc_agent as _p
    return _p.open_db(Path(tempfile.mkdtemp()) / "intent50.sqlite3")


def test_montar_traz_intent_e_respeita_nao_pesquise():
    import pc_agent as _p
    db = _db50()
    cfg = {"system": "sys", "context": 5, "max_tokens": 50,
           "memoria_global": False, "pesquisa_web": True}
    msgs, extras = _p.ai_montar_mensagens(
        db, "convx", cfg, "Não pesquise, apenas explique sobre café.", "ana")
    assert extras["intent"]["podem_pesquisar"] is False
    assert extras["fontes"] == []
    assert extras["shop"] is False
    assert extras["ferramentas_usadas"] == []


def test_montar_diretiva_formato():
    import pc_agent as _p
    db = _db50()
    cfg = {"system": "sys", "context": 5, "max_tokens": 50,
           "memoria_global": False, "pesquisa_web": False}
    msgs, _ = _p.ai_montar_mensagens(db, "convx", cfg, "Responda em duas linhas.", "ana")
    assert "no máximo 2 linhas" in msgs[0]["content"]


def test_filtrar_usados_restricao():
    import pc_agent as _p
    novo = {"nome": "A", "specs": {"Condicao": "Novo"}}
    usado = {"nome": "B", "specs": {"Condicao": "Usado"}}
    res = {"produtos": [novo, usado], "excluidos": []}
    out = _p._filtrar_usados_restricao(
        res, {"restricoes": {"proibidas": ["produtos usados"], "formato": {}}})
    assert [p["nome"] for p in out["produtos"]] == ["A"]
    assert "somente novos" in out["excluidos"][0]["excluido_por"]
    res2 = {"produtos": [novo, usado], "excluidos": []}
    out2 = _p._filtrar_usados_restricao(res2, {"restricoes": {"proibidas": [], "formato": {}}})
    assert len(out2["produtos"]) == 2
