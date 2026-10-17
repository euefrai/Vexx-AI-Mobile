"""V5.5 Research: provedor web orquestrado nos agentes de pesquisa.

Offline: ``research._buscar_orquestrado`` / provedores são substituídos; a
rede real só é exercitada nos testes e2e_real. Cobre: ProvedorOrquestrado
(achados, info, erros honestos), propagação de diagnóstico no fallback,
ordem legada de ``provedores_reais``, lacunas de recuperação e o
replanejamento em triple busca+ler+analisar.
"""
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pc_agent
import research
import research_agents as ra


def _db(nome="resv55.sqlite3"):
    return pc_agent.open_db(Path(tempfile.mkdtemp()) / nome)


class WebProv:
    """Provedor com diagnóstico, como o ProvedorOrquestrado real."""

    nome = "web"

    def __init__(self, achados=None, info=None):
        self.achados = achados if achados is not None else [
            {"titulo": "Review Placa A", "url": "https://lab-a/placa-a",
             "trecho": "Medimos consumo de 65 W em jogos na Placa A.", "origem": "bing"}]
        self.info = info if info is not None else {
            "estado": "parcial", "estado_texto": "poucas fontes lidas",
            "lacunas": ["benchmark placa a"],
            "recuperacao": ["benchmark placa a 2026"],
            "provedores": {"usados": {"bing": 1}, "falhas": [], "vazios": []}}
        self.chamadas = []

    def buscar(self, consulta, limite=6):
        self.chamadas.append(consulta)
        return [dict(a) for a in self.achados][:limite]


# ── ProvedorOrquestrado: achados + info + erro honesto ───────────────

def test_provedor_orquestrado_devolve_achados_e_guarda_info(monkeypatch):
    chamadas = []
    info = {"estado": "ok", "provedores": {"usados": {"bing": 2}},
            "lacunas": ["preço médio"], "recuperacao": ["preço médio 2026"]}

    def _fake(consulta, max_resultados=6, timeout=8.0, orcamento=None):
        chamadas.append((consulta, max_resultados, orcamento))
        return ([{"titulo": "T", "url": "https://exemplo.com/a", "trecho": "x",
                  "origem": "bing"}], dict(info))

    monkeypatch.setattr(research, "_buscar_orquestrado", _fake)
    p = ra.ProvedorOrquestrado(orcamento={"max_consultas": 1})
    achados = p.buscar("notebook 16gb", 4)
    assert p.nome == "web"
    assert [a["url"] for a in achados] == ["https://exemplo.com/a"]
    assert p.info == info
    assert chamadas == [("notebook 16gb", 4, {"max_consultas": 1})]


def test_provedor_orquestrado_bloqueado_levanta_com_codigo(monkeypatch):
    monkeypatch.setattr(research, "_buscar_orquestrado",
                        lambda consulta, max_resultados=6, timeout=8.0, orcamento=None:
                        ([], {"estado": "bloqueado", "provedores": {}}))
    p = ra.ProvedorOrquestrado()
    with pytest.raises(research.ResearchErro) as exc:
        p.buscar("qualquer coisa")
    assert exc.value.codigo == "bloqueado"
    assert p.info["estado"] == "bloqueado"


def test_provedor_orquestrado_vazio_sem_bloqueio_nao_levanta(monkeypatch):
    monkeypatch.setattr(research, "_buscar_orquestrado",
                        lambda consulta, max_resultados=6, timeout=8.0, orcamento=None:
                        ([], {"estado": "sem_resultados", "provedores": {}}))
    assert ra.ProvedorOrquestrado().buscar("sem resultados") == []


# ── Fallback: detalhe do provedor sobe para o chamador ───────────────

def test_buscar_com_fallback_anexa_detalhe_de_provedor_com_info():
    achados, info = ra.buscar_com_fallback([WebProv()], "consulta")
    assert [a["url"] for a in achados] == ["https://lab-a/placa-a"]
    assert info["provedor"] == "web"
    assert info["detalhe"]["estado"] == "parcial"
    assert info["detalhe"]["recuperacao"] == ["benchmark placa a 2026"]


def test_buscar_com_fallback_sem_info_nao_inventa_detalhe():
    class Plain:
        nome = "plain"

        def buscar(self, consulta, limite=6):
            return [{"titulo": "T", "url": "https://exemplo.com/y", "trecho": "t"}]

    achados, info = ra.buscar_com_fallback([Plain()], "consulta")
    assert achados and "detalhe" not in info


# ── agente_busca: recuperação/lacunas/estado registrados ─────────────

def test_agente_busca_registra_recuperacao_lacunas_e_estado():
    db = _db()
    try:
        job = ra.criar_job(db, "u-x", "notebook 16gb vale a pena?", manual="rapida")
        etapa = {"id": "p1", "tipo": "busca", "alvo": "notebook 16gb vale a pena?",
                 "status": "pendente", "tentativas": 0, "prioridade": 10,
                 "dependencias": []}
        prov = WebProv()
        achados = ra.agente_busca(db, job, etapa, [prov], vistas=set())
        assert [a["url"] for a in achados] == ["https://lab-a/placa-a"]
        assert job["usados"]["recuperacao_busca"] == ["benchmark placa a 2026"]
        assert job["usados"]["lacunas_busca"] == ["benchmark placa a"]
        assert job["usados"]["provedores"]["web"]["ok"] == 2  # original + variação
        eventos = [e for e in ra.eventos_desde(db, "u-x", job["id"])
                   if e["tipo"] == "search_completed"]
        assert eventos and any(e["meta"].get("estado") == "parcial" for e in eventos)
    finally:
        db.close()


# ── Lacunas e replanejamento por consulta complementar ───────────────

def test_lacunas_inclui_recuperacao_do_orquestrador_sem_duplicar():
    job = {"plano": [
        {"tipo": "busca", "alvo": "tema principal"},
        {"tipo": "busca", "alvo": "frente coberta"},
        {"tipo": "ler", "alvo": "frente coberta", "_evidencias": [{"id": "e1"}]},
    ], "usados": {"recuperacao_busca": ["consulta complementar x", "frente coberta"]}}
    assert ra._lacunas(job) == ["tema principal", "consulta complementar x"]


def test_replanejar_cria_triple_para_lacuna_complementar():
    db = _db()
    try:
        job = ra.criar_job(db, "u-x", "tema qualquer bem longo?", manual="rapida")
        v0, n0 = job["plano_versao"], len(job["plano"])
        ra.replanejar(db, job, ["consulta complementar do orquestrador"])
        novas = job["plano"][n0:]
        assert [s["tipo"] for s in novas] == ["busca", "ler", "analisar"]
        assert all(s["alvo"] == "consulta complementar do orquestrador" for s in novas)
        assert novas[1]["dependencias"] == [novas[0]["id"]]
        assert novas[2]["dependencias"] == [novas[1]["id"]]
        assert all(s["status"] == "pendente" for s in novas)
        assert job["usados"]["replans"] == 1 and job["plano_versao"] == v0 + 1
        salvo = ra.carregar_job(db, "u-x", job["id"])
        assert salvo["plano_versao"] == v0 + 1
        assert any(s["tipo"] == "busca" and s["alvo"] == "consulta complementar do orquestrador"
                   for s in salvo["plano"])
    finally:
        db.close()


def test_replanejar_nao_repete_frente_ja_executada():
    db = _db()
    try:
        job = ra.criar_job(db, "u-x", "outro tema bem longo?", manual="rapida")
        job["plano"] = [
            {"id": "p1", "tipo": "busca", "alvo": "frente x", "status": "feita",
             "tentativas": 1, "prioridade": 10, "dependencias": []},
            {"id": "p2", "tipo": "ler", "alvo": "frente x", "status": "feita",
             "tentativas": 1, "prioridade": 30, "dependencias": ["p1"]},
        ]
        ra.replanejar(db, job, ["frente x"])
        assert len(job["plano"]) == 2
        assert job["usados"].get("replans", 0) == 0
    finally:
        db.close()


# ── Ordem dos provedores: legado intacto, web por último ─────────────

def test_provedores_reais_legado_intacto_e_web_por_ultimo(monkeypatch):
    monkeypatch.delenv("JULIA_ACADEMIC_RESEARCH", raising=False)
    monkeypatch.delenv("JULIA_SEARXNG_URL", raising=False)
    assert [p.nome for p in ra.provedores_reais()] == ["ddg", "searxng", "wikipedia"]
    orq = ra.provedores_reais(orquestrado=True)
    assert [p.nome for p in orq] == ["ddg", "searxng", "wikipedia", "web"]
    assert isinstance(orq[-1], ra.ProvedorOrquestrado)
    monkeypatch.setenv("JULIA_ACADEMIC_RESEARCH", "1")
    assert [p.nome for p in ra.provedores_reais()] == [
        "ddg", "searxng", "wikipedia", "academic"]
    assert [p.nome for p in ra.provedores_reais(orquestrado=True)] == [
        "ddg", "searxng", "wikipedia", "academic", "web"]


# ── Pipeline completo: lacuna real vira nova frente executada ────────

def test_executar_replaneja_por_lacuna_do_orquestrador(monkeypatch):
    monkeypatch.setitem(ra.MODOS["rapida"], "buscas", 8)  # espaço p/ rodada extra
    db = _db()
    try:
        prov = WebProv()
        job = ra.criar_job(db, "u-x", "qual o consumo da placa a em jogos?",
                           manual="rapida")

        def _recuperar(url):
            return {"titulo": "Review Placa A",
                    "texto": "Review completo: medimos consumo de 65 W em jogos na Placa A.",
                    "final": url}

        r = ra.executar(db, job["id"], "u-x", [prov], _recuperar)
        assert r["status"] in ("concluida", "interrompida")
        salvo = ra.carregar_job(db, "u-x", job["id"])
        assert salvo["usados"]["recuperacao_busca"] == ["benchmark placa a 2026"]
        assert salvo["usados"]["lacunas_busca"] == ["benchmark placa a"]
        novas = [s for s in salvo["plano"]
                 if s["tipo"] == "busca" and s["alvo"] == "benchmark placa a 2026"]
        assert novas and novas[0]["status"] == "feita"  # rodada extra executada
        assert any(s["tipo"] == "ler" and s["alvo"] == "benchmark placa a 2026"
                   for s in salvo["plano"])
        assert salvo["plano_versao"] >= 3
    finally:
        db.close()
