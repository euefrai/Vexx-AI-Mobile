"""V5.7 FASE 3 — origem declarada pela página (rel=canonical para outro domínio).

O sinal vem da própria página, nunca de presunção: agregador/cópia que declara
o original ganha a marca `origem_declarada`; mesma origem ou subdomínio não é
sinalizado; o link da fonte nunca é trocado automaticamente.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import research
import source_check

HTML_CANONICA = (
    '<html><head><title>Nota</title>'
    '<link rel="canonical" href="https://original.example/artigo">'
    '</head><body><p>Texto do artigo sobre o assunto com detalhes suficientes '
    'para uma leitura normal do conteúdo desta página.</p></body></html>')


def test_fonte_marca_origem_declarada_e_preserva_link():
    f = research._fonte_de(
        {"texto": "conteúdo real", "lida": True,
         "metadados": {"canonica": "https://original.example/artigo"}},
        {"url": "https://agregador.example/copia", "titulo": "T"}, "q")
    assert f["origem_declarada"] == "original.example"
    assert f["canonica"] == "https://original.example/artigo"
    assert f["url"] == "https://agregador.example/copia"  # link não é trocado


def test_fonte_sem_sinal_para_mesmo_dominio_subdominio_ou_vazio():
    for canonica in ("https://agregador.example/x",
                     "https://www.agregador.example/x",
                     ""):
        f = research._fonte_de(
            {"texto": "x", "lida": True,
             "metadados": {"canonica": canonica} if canonica else {}},
            {"url": "https://agregador.example/copia", "titulo": "T"}, "q")
        assert f["origem_declarada"] == "", canonica


def test_fonte_usa_final_da_recuperacao():
    f = research._fonte_de(
        {"texto": "x", "lida": True, "final": "https://cdn.agregador.example/copia",
         "metadados": {"canonica": "https://original.example/artigo"}},
        {"url": "https://encurtador.example/abc", "titulo": "T"}, "q")
    assert f["origem_declarada"] == "original.example"


def test_grounding_marca_origem_declarada():
    fontes = [{"id": "S1", "titulo": "Nota", "url": "https://agregador.example/n1",
               "trecho": "texto", "status": "aberta",
               "origem_declarada": "original.example"}]
    bloco = research.bloco_grounding(fontes, "18/10/2026")
    assert "página declara a origem em original.example" in bloco
    fontes[0]["origem_declarada"] = ""
    assert "declara a origem" not in research.bloco_grounding(fontes, "18/10/2026")


def test_avaliar_pagina_sinaliza_origem_declarada():
    out = source_check.avaliar_pagina(HTML_CANONICA, "https://agregador.example/copia")
    assert out["canonica"] == "https://original.example/artigo"
    assert out["origem_declarada"] == "original.example"

    mesmo = HTML_CANONICA.replace("https://original.example/artigo",
                                  "https://agregador.example/copia")
    out2 = source_check.avaliar_pagina(mesmo, "https://agregador.example/copia")
    assert "origem_declarada" not in out2
