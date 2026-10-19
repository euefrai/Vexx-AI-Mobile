"""V5.7 FINAL — conteúdo lido da página chega ao prompt do Lucas.

Antes: toda fonte entrava no grounding com `trecho[:400]` mesmo quando a
página foi realmente lida (texto extraído até 8000 chars). Agora a fonte
aberta carrega `texto_lido` (teto 1200) e o bloco do prompt usa esse
conteúdo; fonte só encontrada continua com trecho do índice (≤400) e marca
"NÃO lida"; cache antigo (sem `texto_lido`) cai no comportamento anterior.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pc_agent
import research


def _db():
    return pc_agent.open_db(Path(tempfile.mkdtemp()) / "gc57f.sqlite3")


_MARCADOR = "SENTINELA-V57F"


def test_fonte_aberta_carrega_texto_lido():
    texto = ("O artigo descreve o funcionamento em detalhes técnicos. " * 12
             + f"{_MARCADOR}: o rendimento medido foi de 42 unidades por hora. "
             + "Conclusão publicada após medição em campo. " * 8)
    db = _db()
    achado = {"titulo": "Estudo técnico", "url": "https://tecnica.example/estudo",
              "trecho": "estudo técnico"}
    rec = {"titulo": achado["titulo"], "texto": texto, "final": achado["url"],
           "trecho_usado": texto[:400], "metadados": {}, "lida": True}
    rap = research.pesquisa_rapida(db, "ana", "rendimento tecnico",
                                   buscar_fn=lambda q: [dict(achado)],
                                   recuperar_fn=lambda u: dict(rec))
    f = rap["fontes"][0]
    assert f["status"] == "aberta"
    assert f["texto_lido"].startswith("O artigo")
    assert _MARCADOR in f["texto_lido"]
    bloco = research.bloco_grounding(rap["fontes"], "18/10/2026", rap)
    assert _MARCADOR in bloco, "texto_lido deveria alimentar o grounding"
    db.close()


def test_grounding_encontrada_mantem_trecho_e_marca():
    fontes = [{"id": "S1", "titulo": "Só índice", "url": "https://indice.example/a",
               "trecho": "resumo do índice sobre o tema", "status": "encontrada"}]
    bloco = research.bloco_grounding(fontes, "18/10/2026")
    assert "NÃO lida" in bloco and "resumo do índice" in bloco
    # aberta sem texto_lido (cache antigo) mantém o trecho
    fontes2 = [dict(fontes[0], status="aberta", texto_lido="")]
    b2 = research.bloco_grounding(fontes2, "18/10/2026")
    assert "resumo do índice" in b2


def test_fonte_guarda_texto_lido_so_de_pagina_lida():
    f = research._fonte_de({"texto": "conteúdo lido curto", "lida": True},
                           {"url": "https://a.example/x", "titulo": "T"}, "q")
    assert f["texto_lido"].startswith("conteúdo lido")
    f2 = research._fonte_de({"texto": "", "lida": False},
                            {"url": "https://a.example/y", "titulo": "T",
                             "trecho": "trecho do índice"}, "q")
    assert f2["texto_lido"] == "" and f2["status"] == "encontrada"


def test_teto_do_texto_lido():
    texto = "x" * 5000
    f = research._fonte_de({"texto": texto, "lida": True},
                           {"url": "https://a.example/z", "titulo": "T"}, "q")
    assert len(f["texto_lido"]) == 1200


def test_janela_lida_comeca_no_trecho_relevante():
    """Menu/boilerplate no início da página não consome o prompt."""
    texto = ("menu principal " * 100
             + "conteúdo relevante sobre o tema, medido em campo e publicado. " * 40)
    f = research._fonte_de(
        {"texto": texto, "lida": True,
         "trecho_usado": "conteúdo relevante sobre o tema, medido em campo e publicado."},
        {"url": "https://a.example/w", "titulo": "T"}, "q")
    assert not f["texto_lido"].startswith("menu")
    assert "conteúdo relevante" in f["texto_lido"]
    assert len(f["texto_lido"]) <= 1200
