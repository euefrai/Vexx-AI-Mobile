"""V5.7 — Honestidade de erro na pesquisa: interno ≠ provedor indisponível.

Regressão real (auditoria V5.7, P6): um erro interno (ex.: assinatura errada
→ TypeError) virava `erro: provedor_indisponivel`, escondendo que o problema
era da própria busca — o provedor nunca tinha sido consultado.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pc_agent
import research


def _db():
    return pc_agent.open_db(Path(tempfile.mkdtemp()) / "v57.sqlite3")


def test_erro_interno_nao_e_mascarado_como_provedor_indisponivel():
    def buscar(q):
        raise TypeError("assinatura errada (bug interno)")
    r = research.pesquisa_rapida(_db(), "u-x", "consulta qualquer", buscar_fn=buscar)
    assert r["erro"] == "erro_interno"
    assert r["estado"] == "indisponivel"
    assert r["etapas"] == ["erro interno na busca (TypeError)"]


def test_falha_real_de_provedor_continua_indisponivel():
    def buscar(q):
        raise research.ResearchErro("proxy fora do ar", "rede")
    r = research.pesquisa_rapida(_db(), "u-x", "consulta qualquer", buscar_fn=buscar)
    assert r["erro"] == "provedor_indisponivel"
    assert r["estado"] == "indisponivel"
    assert r["etapas"] == ["busca indisponível (rede)"]


def test_erro_interno_com_codigo_vazio_tambem_e_interno():
    class ErroEstranho(Exception):
        codigo = ""

    def buscar(q):
        raise ErroEstranho("sem codigo")
    r = research.pesquisa_rapida(_db(), "u-x", "consulta qualquer", buscar_fn=buscar)
    assert r["erro"] == "erro_interno"
    assert r["etapas"] == ["erro interno na busca (ErroEstranho)"]
