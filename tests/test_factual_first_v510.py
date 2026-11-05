"""P0-3: chat factual retrieval-first e citação inline obrigatória.

O golden set cobre 30 perguntas factuais em PT-BR. A busca é simulada para
provar o roteamento e a citação; nenhum teste depende da rede.
"""
from datetime import datetime, timezone

import pytest

import pc_agent
import research


GOLDEN = [
    "Quem foi Albert Einstein?",
    "Qual é a capital da França?",
    "Quando começou a Segunda Guerra Mundial?",
    "Onde fica o Monte Everest?",
    "Qual é a população do Japão?",
    "Como funciona a fotossíntese?",
    "Por que o céu é azul?",
    "Qual a diferença entre TCP e UDP?",
    "Qual é a melhor universidade da América Latina?",
    "O que é computação quântica?",
    "Quem inventou a lâmpada?",
    "Quando foi lançado o Windows 11?",
    "Qual a população de São Paulo?",
    "Onde ocorreu a Revolução Francesa?",
    "Quanto é a cotação do dólar hoje?",
    "Como surgiu a internet?",
    "Qual a altura do Cristo Redentor?",
    "Quem ganhou o Nobel de Física em 2025?",
    "Qual é a temperatura em Curitiba hoje?",
    "Compare Python e JavaScript para backend.",
    "Qual a diferença entre IA generativa e machine learning?",
    "O que aconteceu nas eleições dos EUA em 2024?",
    "Quais são as últimas notícias sobre inteligência artificial?",
    "Qual foi o resultado do campeonato brasileiro de 2025?",
    "Quem escreveu Dom Casmurro?",
    "Em que ano o Brasil foi descoberto?",
    "Qual é a melhor faculdade de medicina do Brasil?",
    "Como funciona o motor de um carro elétrico?",
    "Qual a distância da Terra à Lua?",
    "O que significa PIB?",
]

CONTROLES = [
    "me conta uma piada",
    "escreva um poema sobre o mar",
    "qual é o meu nome?",
    "quando é minha prova de biologia?",
    "como faço para criar um arquivo no PC?",
    "corrija esse código Python",
    "quanto é 2 + 2?",
    "que horas são?",
    "traduza 'bom dia' para o inglês",
    "resuma este documento anexado",
    "não pesquise sobre o preço do dólar",
    "lembre-se de comprar leite",
    "crie uma tabela com meus gastos",
    "me explique como você funciona",
    "faça um resumo da nossa conversa",
    "gere uma imagem de um gato",
    "quem é você?",
    "como estou me sentindo?",
    "quanto eu tenho na conta?",
    "O que já falei do SQLite?",
    "Qual a melhor pizza que você já comeu?",
]


@pytest.mark.parametrize("pergunta", GOLDEN)
def test_golden_factual_questions_are_retrieval_first(pergunta):
    assert pc_agent.intencao_factual(pergunta) is True


@pytest.mark.parametrize("pergunta", CONTROLES)
def test_personal_local_and_creative_questions_do_not_search(pergunta):
    assert pc_agent.intencao_factual(pergunta) is False


def _fonte(consulta):
    termos = research.termos_assunto(consulta) or ["assunto"]
    texto = consulta + " " + " ".join(termos) + " conteúdo lido de teste."
    return {
        "id": "S1",
        "titulo": "Fonte " + termos[0],
        "url": "https://exemplo.org/fonte",
        "status": "aberta",
        "relevante": True,
        "texto": texto,
        "texto_lido": texto,
        "trecho": texto,
        "content_scope": "document_text",
        # A publication instant must not become tomorrow's date when the runner
        # uses UTC while the news request uses America/Bahia near midnight.
        "publicado_em": datetime.now(timezone.utc).isoformat(),
    }


def _cfg():
    return {"system": "Teste", "context": 4, "pesquisa_web": True,
            "memoria_global": False}


def test_factual_question_runs_search_and_grounds_prompt(tmp_path, monkeypatch):
    db = pc_agent.open_db(tmp_path / "qa.sqlite")
    chamadas = []

    def fake(db_, owner, consulta, **kwargs):
        chamadas.append(consulta)
        return {"fontes": [_fonte(consulta)], "etapas": ["busca: 1"],
                "divergencias": [], "de_cache": False, "estado": "ok",
                "correspondencia": 1.0}

    monkeypatch.setattr(research, "pesquisa_rapida", fake)
    try:
        msgs, extras = pc_agent.ai_montar_mensagens(
            db, "conv-factual", _cfg(), "Quem foi Albert Einstein?", "u-test", {})
        assert chamadas == ["Quem foi Albert Einstein?"]
        assert extras["pesquisa_executada"] is True
        assert extras["fontes"]
        assert extras["factual_first"]["score"] >= 2
        assert "FONTES PESQUISADAS" in msgs[0]["content"]
        assert "[S1]" in msgs[0]["content"]
    finally:
        db.close()


@pytest.mark.parametrize("pergunta", [
    "qual é o meu nome?",
    "quando é minha prova de biologia?",
    "como faço para criar um arquivo no PC?",
    "corrija esse código Python",
])
def test_control_question_does_not_call_search(tmp_path, monkeypatch, pergunta):
    db = pc_agent.open_db(tmp_path / "qa.sqlite")
    monkeypatch.setattr(
        research, "pesquisa_rapida",
        lambda *a, **k: pytest.fail("busca indevida para pergunta de controle"))
    try:
        _, extras = pc_agent.ai_montar_mensagens(
            db, "conv-controle", _cfg(), pergunta, "u-test", {})
        assert not extras.get("pesquisa_executada")
        assert not extras.get("factual_first")
    finally:
        db.close()


def test_golden_set_has_source_and_inline_citation(tmp_path, monkeypatch):
    db = pc_agent.open_db(tmp_path / "qa.sqlite")

    def fake(db_, owner, consulta, **kwargs):
        return {"fontes": [_fonte(consulta)], "etapas": ["busca: 1"],
                "divergencias": [], "de_cache": False, "estado": "ok",
                "correspondencia": 1.0}

    monkeypatch.setattr(research, "pesquisa_rapida", fake)
    try:
        for i, pergunta in enumerate(GOLDEN):
            _, extras = pc_agent.ai_montar_mensagens(
                db, "conv-golden-%d" % i, _cfg(), pergunta, "u-test", {})
            assert extras.get("pesquisa_executada"), pergunta
            assert extras.get("fontes"), pergunta
            final = pc_agent.anexar_fontes(
                "Resposta do modelo sem citação.", extras["fontes"],
                pesquisa_executada=True, consulta=pergunta)
            assert "[S1]" in final, pergunta
    finally:
        db.close()


@pytest.mark.parametrize('instant', ['2020-01-01T00:30:00+00:00', '2020-01-01T04:30:00+00:00'])
def test_news_golden_fixture_at_utc_and_bahia_date_boundary(tmp_path, monkeypatch, instant):
    import query_intelligence
    import sys
    fixed = datetime.fromisoformat(instant)
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed.astimezone(tz) if tz else fixed.replace(tzinfo=None)
    monkeypatch.setattr(sys.modules[__name__], 'datetime', Clock)
    monkeypatch.setattr(query_intelligence, 'datetime', Clock)
    db = pc_agent.open_db(tmp_path/'news-date-boundary.sqlite3')
    monkeypatch.setattr(research, 'pesquisa_rapida', lambda db,owner,consulta,**kw: {'fontes':[_fonte(consulta)], 'estado':'ok', 'correspondencia':1.0})
    try:
        _, extras = pc_agent.ai_montar_mensagens(db,'news-boundary',_cfg(),GOLDEN[22],'u-test',{})
        assert extras['fontes'], 'A current publication instant must survive filtering in the request timezone'
    finally:
        db.close()


def test_uncited_answer_falls_back_to_cited_digest():
    fonte = _fonte("Quem foi Albert Einstein?")
    fonte["trecho"] = "Trecho recuperado sobre Einstein."
    final = pc_agent.anexar_fontes(
        "Einstein nasceu em 1879.", [fonte], pesquisa_executada=True,
        consulta="Quem foi Albert Einstein?")
    assert "não passou pela conferência de citações" in final
    assert "[S1]" in final
    assert "Einstein nasceu em 1879." not in final


def test_open_but_unread_source_uses_p03_fallback():
    fonte = _fonte("Quem foi Albert Einstein?")
    fonte["texto_lido"] = ""
    final = pc_agent.anexar_fontes(
        "Einstein nasceu em 1879.", [fonte], pesquisa_executada=True,
        consulta="Quem foi Albert Einstein?")
    assert "não citou as fontes lidas" in final
    assert "[S1]" in final
    assert "Einstein nasceu em 1879." not in final


def test_cited_answer_is_preserved():
    fonte = _fonte("Quem foi Albert Einstein?")
    texto = "Einstein nasceu em 1879 [S1]."
    final = pc_agent.anexar_fontes(
        texto, [fonte], pesquisa_executada=True,
        consulta="Quem foi Albert Einstein?")
    assert texto in final
    assert "não citou as fontes lidas" not in final
    assert "não passou pela conferência de citações" not in final


def test_ghost_citation_is_replaced():
    fonte = _fonte("Quem foi Albert Einstein?")
    final = pc_agent.anexar_fontes(
        "Einstein nasceu em 1879 [S9].", [fonte], pesquisa_executada=True,
        consulta="Quem foi Albert Einstein?")
    assert "não passou pela conferência de citações" in final
    assert "[S1]" in final
    assert "[S9]" not in final


def test_unread_source_does_not_trigger_citation_fallback():
    fonte = _fonte("Quem foi Albert Einstein?")
    fonte["status"] = "encontrada"
    final = pc_agent.anexar_fontes(
        "Resposta do modelo.", [fonte], pesquisa_executada=True,
        consulta="Quem foi Albert Einstein?")
    assert "não citou as fontes lidas" not in final


def test_deterministic_summary_can_emit_inline_ids():
    fonte = _fonte("Quem foi Albert Einstein?")
    texto = research.resumo_deterministico(
        [fonte], "Quem foi Albert Einstein?", citar=True)
    assert "[S1]" in texto
    assert fonte["url"] in texto
