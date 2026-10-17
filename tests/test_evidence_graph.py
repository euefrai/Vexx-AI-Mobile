"""V4.6 FASE 2-8: grafo, proveniência, claims v2, verificação, independência."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import evidence_graph as eg
import pc_agent


def _db(nome="eg.sqlite3"):
    db = pc_agent.open_db(Path(tempfile.mkdtemp()) / nome)
    eg.criar_tabelas(db)
    return db


def test_grafo_crud_e_isolamento():
    db = _db()
    n1 = eg.criar_no(db, "u-x", "j1", "claim", "café faz bem", {"texto": "café faz bem"})
    n2 = eg.criar_no(db, "u-x", "j1", "source", "http://e/x", {"url": "http://e/x"})
    assert n1 == eg.criar_no(db, "u-x", "j1", "claim", "café faz bem", {"texto": "x"})  # id estável
    eg.ligar(db, "u-x", "j1", n1, n2, "MENTIONS", "lexico", "")
    try:
        eg.ligar(db, "u-x", "j1", n1, n2, "CURTIU")
        raise AssertionError("relação inválida deveria falhar")
    except eg.GraphErro as exc:
        assert exc.codigo == "relacao"
    try:
        eg.criar_no(db, "u-x", "j1", "nave", "x", {})
        raise AssertionError("kind inválido deveria falhar")
    except eg.GraphErro as exc:
        assert exc.codigo == "kind"
    assert len(eg.nos_do_job(db, "u-x", "j1")) == 2
    assert eg.arestas_do_job(db, "u-x", "j1") == [
        {"src": n1, "dst": n2, "tipo": "MENTIONS", "metodo": "lexico", "nota": ""}]
    assert eg.nos_do_job(db, "u-y", "j1") == []
    assert eg.arestas_do_job(db, "u-x", "j1", "SUPPORTS") == []
    db.close()


def test_proveniencia():
    assert eg.canonical_url("HTTPS://Exemplo.COM:443/Path/?utm_source=x&b=1") == \
        "https://exemplo.com/Path?b=1"
    assert eg.canonical_url("http://e/x/?fbclid=abc") == "http://e/x"
    assert eg.hash_conteudo("  Olá   Mundo ") == eg.hash_conteudo("olá mundo")
    assert eg.hash_conteudo("a") != eg.hash_conteudo("b")
    assert eg.contexto_trecho("0123456789abcdef", "abcdef", janela=3) == "789abcdef"
    assert eg.contexto_trecho("abc", "zzz") == ""


def test_claims_v2_split_e_condicoes():
    cs = eg.extrair_afirmacoes_v2("Esse processador consome bem menos energia elétrica "
                                  "e é 20% mais rápido que o modelo anterior em jogos.")
    assert len(cs) == 2
    consome = [c for c in cs if "consome" in c["texto"]][0]
    assert consome["condicoes"]["quantidades"] == []
    rapido = [c for c in cs if "20%" in c["texto"]][0]
    assert rapido["condicoes"]["quantidades"] == [{"valor": 20.0, "unidade": "%"}]
    assert "modelo anterior em jogos" in rapido["condicoes"]["comparado_a"]
    assert eg.extrair_afirmacoes_v2("oi") == []  # curto: não é afirmação
    assert eg.extrair_afirmacoes_v2("O céu é azul.") == []  # sem número/nome: não verificável
    com_data = eg.extrair_afirmacoes_v2("A safra de 2024 rendeu 30 milhões de sacas no Brasil.")
    assert com_data and "2024" in com_data[0]["condicoes"]["datas"]
    assert {"valor": 30.0, "unidade": "milhões"} in com_data[0]["condicoes"]["quantidades"]
    comp = eg.extrair_afirmacoes_v2("O modelo X é 40% mais rápido que o modelo Y em jogos.")
    assert len(comp) == 1
    assert "40" in str(comp[0]["condicoes"]["quantidades"])


def test_verificacao_quantidade_exata_e_provisoria():
    claim = {"texto": "O consumo é de 65 W em jogos.",
             "condicoes": {"comparado_a": "", "metrica": "",
                           "quantidades": [{"valor": 65.0, "unidade": "W"}], "datas": []}}
    r = eg.verificar_claim(claim, [{"id": "e1", "trecho": "medimos consumo de 65 W em jogos"}])
    assert r["estado"] == "SUPPORTED" and r["metodo"] == "quantidade+contexto"
    r2 = eg.verificar_claim(claim, [{"id": "e1", "trecho": "o aparelho é econômico e silencioso"}])
    assert r2["estado"] in ("PARTIALLY_SUPPORTED", "UNVERIFIED")  # nunca SUPPORTED por léxico
    assert r2["estado"] != "SUPPORTED"
    r3 = eg.verificar_claim(claim, [])
    assert r3 == {"estado": "INSUFFICIENT_EVIDENCE", "metodo": "sem-evidencia",
                  "evidencia": "", "cobertura_lexica": 0.0}
    sem_data = {"texto": "O rendimento subiu 5% no trimestre.",
                "condicoes": {"comparado_a": "", "metrica": "",
                              "quantidades": [{"valor": 5.0, "unidade": "%"}], "datas": []}}
    r4 = eg.verificar_claim(sem_data, [{"id": "e1", "trecho": "rendimento em alta forte"}])
    assert "data ausente p/ quantidade" in r4.get("condicoes_ausentes", [])


def test_independencia():
    a = {"url": "http://a/x", "texto": "O café é seguro em doses normais segundo estudo amplo."}
    b = {"url": "http://b/y", "texto": "O café é seguro em doses normais segundo estudo amplo."}
    r = eg.analisar_independencia(a, b)
    assert r["relacao"] in ("DUPLICATES", "DERIVED_FROM")  # cópia, mesmo com domínio distinto
    c = {"url": "http://c/z", "texto": "Chá verde contém cafeína e antioxidantes naturais."}
    r2 = eg.analisar_independencia(a, c)
    assert r2["relacao"] == "MENTIONS" and "NÃO presumida" in r2["motivo"]
    r3 = eg.analisar_independencia(a, dict(a, url="http://a/x?ref=1"))
    assert r3["relacao"] == "DUPLICATES"  # canônica igual
    assert 0.0 <= eg.jaccard({"a", "b"}, {"b", "c"}) <= 1.0


def test_investigar_divergencia_dimensoes():
    qa = {"texto": "x", "condicoes": {"quantidades": [{"valor": 65.0, "unidade": "W"}],
                                      "datas": [], "comparado_a": "", "metrica": ""}}
    qb = {"texto": "y", "condicoes": {"quantidades": [{"valor": 95.0, "unidade": "W"}],
                                      "datas": [], "comparado_a": "", "metrica": ""}}
    r = eg.investigar_divergencia(qa, qb, "S1", "S2")
    assert r["tipo"] == "valor_divergente" and r["status"] == "em_aberto"
    assert r["follow_up"]  # sugere esclarecimento, não inventa reconciliação
    qc = {"texto": "x", "condicoes": {"quantidades": [{"valor": 65.0, "unidade": "W"}],
                                      "datas": [], "comparado_a": "", "metrica": ""}}
    qd = {"texto": "y", "condicoes": {"quantidades": [{"valor": 0.065, "unidade": "kW"}],
                                      "datas": [], "comparado_a": "", "metrica": ""}}
    r2 = eg.investigar_divergencia(qc, qd, "S1", "S2")
    assert r2["tipo"] == "inconclusivo"  # conversível mas sem conversão implementada: honesto
    qe = {"texto": "x", "condicoes": {"quantidades": [{"valor": 5.0, "unidade": "%"}],
                                      "datas": ["2023"], "comparado_a": "", "metrica": ""}}
    qf = {"texto": "y", "condicoes": {"quantidades": [{"valor": 7.0, "unidade": "%"}],
                                      "datas": ["2025"], "comparado_a": "", "metrica": ""}}
    assert eg.investigar_divergencia(qe, qf, "S1", "S2")["tipo"] == "valor_divergente"


def test_auditor_20():
    claims = [{"texto": "O café sempre cura tudo."},
              {"texto": "O café rende 5% em testes."}]
    vereditos = {"O café sempre cura tudo.": {"estado": "UNVERIFIED"},
                 "O café rende 5% em testes.": {"estado": "SUPPORTED"}}
    rep = eg.auditar_resposta("Veja [E1] e [E9]. O café sempre cura tudo.",
                              claims, vereditos, [{"id": "E1"}])
    assert rep["citacoes_fantasma"] == ["[E9]"]
    assert len(rep["generalizacoes_excessivas"]) == 1
    assert len(rep["sem_evidencia_suficiente"]) == 1
    assert rep["etapa_semantica"] == "BLOQUEADA" and rep["ok"] is False
    ok = eg.auditar_resposta("Veja [E1].", [{"texto": "O café rende 5% em testes."}],
                             {"O café rende 5% em testes.": {"estado": "SUPPORTED"}},
                             [{"id": "E1"}])
    assert ok["ok"] is True


def _q(valor, unidade):
    return {"texto": "x", "condicoes": {"quantidades": [{"valor": valor, "unidade": unidade}],
                                        "datas": [], "comparado_a": "", "metrica": ""}}


def test_v55_divergencia_converte_unidades_reais():
    # W × kW com valores diferentes: mesma dimensão (conversão real) → divergência
    r = eg.investigar_divergencia(_q(65.0, "W"), _q(0.095, "kW"), "S1", "S2")
    assert r["tipo"] == "valor_divergente" and r["status"] == "em_aberto"
    assert "65" in r["explicacao"] and "0.095" in r["explicacao"]
    assert "dimensão" in r["explicacao"] and r["follow_up"]
    # 65 W == 0,065 kW: sem divergência inventada
    assert eg.investigar_divergencia(_q(65.0, "W"), _q(0.065, "kW"), "S1", "S2")["tipo"] \
        == "inconclusivo"
    # armazenamento gb × tb
    r2 = eg.investigar_divergencia(_q(512.0, "gb"), _q(0.6, "tb"), "S1", "S2")
    assert r2["tipo"] == "valor_divergente" and "512" in r2["explicacao"]
    # dimensões incompatíveis continuam unidade_ou_metrica (nunca converte)
    r3 = eg.investigar_divergencia(_q(65.0, "W"), _q(10.0, "h"), "S1", "S2")
    assert r3["tipo"] == "unidade_ou_metrica"
    # unidade desconhecida dos dois lados: mesmo rótulo, comparação legada preservada
    r4 = eg.investigar_divergencia(_q(10.0, "xpto"), _q(20.0, "xpto"), "S1", "S2")
    assert r4["tipo"] == "valor_divergente" and "Mesma unidade" in r4["explicacao"]


def test_v55_fonte_desatualizada_deterministica():
    assert eg.fonte_desatualizada({"publicado_em": "2019-03-01"}, ano_ref=2026) is True
    assert eg.fonte_desatualizada({"publicado_em": "2025-01-10"}, ano_ref=2026) is False
    assert eg.fonte_desatualizada({"year": 2024}, ano_ref=2026) is False  # limite exato
    assert eg.fonte_desatualizada({"year": 2023}, ano_ref=2026) is True
    assert eg.fonte_desatualizada({}) is False  # sem data: não acusa
    assert eg.fonte_desatualizada({"publicado_em": "sem data"}) is False
    assert eg.fonte_desatualizada({"publicado_em": "2020"}, ano_ref=2026,
                                  idade_max_anos=10) is False


def test_v55_auditor_lista_fontes_desatualizadas_sem_mudar_ok():
    import datetime as _dt
    ano_atual = _dt.datetime.now(_dt.timezone.utc).year
    rep = eg.auditar_resposta(
        "Veja [E1].",
        [{"texto": "O café rende 5% em testes."}],
        {"O café rende 5% em testes.": {"estado": "SUPPORTED"}},
        [{"id": "E1", "publicado_em": "2017-05-01"},
         {"id": "E2", "year": ano_atual}, {"id": "E3"}])
    assert rep["fontes_desatualizadas"] == ["E1"]
    assert rep["ok"] is True  # informativo: não bloqueia sozinho
    ruim = eg.auditar_resposta("Veja [E9].", [], {}, [{"id": "E1", "publicado_em": "2010"}])
    assert ruim["fontes_desatualizadas"] == ["E1"] and ruim["ok"] is False
