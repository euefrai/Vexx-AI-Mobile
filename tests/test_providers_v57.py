"""V5.7 FASE 3 — provedores: métricas cumulativas e classificação honesta.

- `sp.buscar` alimenta métricas por provedor (chamadas/ok/vazio/erros/ms).
- HTTP 403/429 → `bloqueado` (sem bypass); 5xx → `http`; timeout → `rede`;
  202 sem corpo → `vazio` (nunca sucesso inventado).
- Falha interna não vira código falso: mantém o tipo observado.
"""
import sys
import urllib.error
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import research
import search_providers as sp


class _Resp:
    def __init__(self, corpo=b"", status=200, ctype="text/html"):
        self._corpo = corpo
        self.status = status
        self._ctype = ctype
        self.headers = self

    def get_content_type(self):
        return self._ctype

    def get_content_charset(self):
        return "utf-8"

    def get(self, k, d=""):
        return d

    def read(self, n=-1):
        return self._corpo if n < 0 else self._corpo[:n]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture(autouse=True)
def _metricas_limpas():
    sp._reset_metricas()
    yield
    sp._reset_metricas()


def _sem_ssrf(monkeypatch):
    monkeypatch.setattr(research, "_ips_globais", lambda host: None)


def _abrir_http(monkeypatch, *, status=200, erro=None, corpo=b""):
    def abrir(url, timeout=10.0, *args):
        if erro:
            raise urllib.error.HTTPError(url, erro, "x", {}, None)
        return _Resp(corpo, status=status)
    monkeypatch.setattr(research, "_abrir", abrir)


def _provedor_fake(monkeypatch, fn):
    monkeypatch.setitem(sp.PROVEDORES, "prova-v57",
                        {"rotulo": "Prova V5.7", "classes": (sp.CLASSE_GERAL,),
                         "tipo": "pagina", "peso": 1.0, "fn": fn})


def test_metricas_ok_vazio_e_erro(monkeypatch):
    def fn(consulta, limite=6, timeout=10.0):
        if consulta == "bloqueia":
            raise sp.ErroProvedor("bot-wall", "bloqueado")
        if consulta == "vazio":
            return []
        return [{"titulo": "T", "url": "https://a.example/1"}]
    _provedor_fake(monkeypatch, fn)

    assert len(sp.buscar("prova-v57", "ok")) == 1
    assert sp.buscar("prova-v57", "vazio") == []
    with pytest.raises(sp.ErroProvedor) as ei:
        sp.buscar("prova-v57", "bloqueia")
    assert ei.value.codigo == "bloqueado"

    m = sp.metricas()["prova-v57"]
    assert m["chamadas"] == 3 and m["ok"] == 1 and m["vazio"] == 1
    assert m["resultados"] == 1 and m["erros"] == {"bloqueado": 1}
    assert isinstance(m["ms_medio"], float) and m["ms_medio"] >= 0.0

    sp._reset_metricas()
    assert sp.metricas() == {}


def test_falha_interna_mantem_o_tipo_observado(monkeypatch):
    def fn(consulta, limite=6, timeout=10.0):
        raise TypeError("boom")
    _provedor_fake(monkeypatch, fn)
    with pytest.raises(sp.ErroProvedor) as ei:
        sp.buscar("prova-v57", "x")
    assert ei.value.codigo == "TypeError"
    assert sp.metricas()["prova-v57"]["erros"] == {"TypeError": 1}


def test_rede_ampla_vira_codigo_rede(monkeypatch):
    for exc in (OSError("dns"), TimeoutError("tempo"), ConnectionResetError("reset")):
        def fn(consulta, limite=6, timeout=10.0, _exc=exc):
            raise _exc
        _provedor_fake(monkeypatch, fn)
        with pytest.raises(sp.ErroProvedor) as ei:
            sp.buscar("prova-v57", "x")
        assert ei.value.codigo == "rede", type(exc).__name__
    assert sp.metricas()["prova-v57"]["erros"] == {"rede": 3}


def test_provedor_desconhecido_sem_metrica():
    with pytest.raises(sp.ErroProvedor) as ei:
        sp.buscar("nao-existe", "x")
    assert ei.value.codigo == "indisponivel"
    assert "nao-existe" not in sp.metricas()


def test_http_403_e_429_bloqueado_sem_bypass(monkeypatch):
    _sem_ssrf(monkeypatch)
    for codigo in (403, 429):
        _abrir_http(monkeypatch, erro=codigo)
        with pytest.raises(sp.ErroProvedor) as ei:
            sp.buscar("bing", "abs freio")
        assert ei.value.codigo == "bloqueado", codigo
    assert sp.metricas()["bing"]["erros"] == {"bloqueado": 2}


def test_http_5xx_e_timeout_classificados(monkeypatch):
    _sem_ssrf(monkeypatch)
    _abrir_http(monkeypatch, erro=503)
    with pytest.raises(sp.ErroProvedor) as ei:
        sp.buscar("bing", "abs freio")
    assert ei.value.codigo == "http"

    _abrir_http(monkeypatch, erro=500)
    with pytest.raises(sp.ErroProvedor) as ei:
        sp.buscar("bing", "abs freio")
    assert ei.value.codigo == "http"

    def abrir(url, timeout=10.0, *args):
        raise OSError("timed out")
    monkeypatch.setattr(research, "_abrir", abrir)
    with pytest.raises(sp.ErroProvedor) as ei:
        sp.buscar("bing", "abs freio")
    assert ei.value.codigo == "rede"

    assert sp.metricas()["bing"]["erros"] == {"http": 2, "rede": 1}


def test_http_202_sem_corpo_e_vazio_honesto(monkeypatch):
    _sem_ssrf(monkeypatch)
    _abrir_http(monkeypatch, status=202, corpo=b"")
    with pytest.raises(sp.ErroProvedor) as ei:
        sp.buscar("bing", "abs freio")
    assert ei.value.codigo == "vazio"
    assert sp.metricas()["bing"]["erros"] == {"vazio": 1}


def test_diagnosticar_inclui_metricas(monkeypatch):
    def fn(consulta, limite=6, timeout=10.0):
        if consulta == "falha":
            raise sp.ErroProvedor("sem rede", "rede")
        return [{"titulo": "T", "url": "https://a.example/1"}]
    _provedor_fake(monkeypatch, fn)
    monkeypatch.setattr(sp, "disponiveis", lambda classes=None: ["prova-v57"])

    linha = sp.diagnosticar("tema", timeout=1.0)[0]
    assert linha["estado"] == "ok" and linha["resultados"] == 1
    assert linha["metricas"]["chamadas"] == 1 and linha["metricas"]["ok"] == 1

    linha2 = sp.diagnosticar("falha", timeout=1.0)[0]
    assert linha2["estado"] == "rede"
    assert linha2["metricas"]["erros"] == {"rede": 1}


def test_metricas_provedores_junta_status(monkeypatch):
    def fn(consulta, limite=6, timeout=10.0):
        return [{"titulo": "T", "url": "https://a.example/1"}]
    _provedor_fake(monkeypatch, fn)
    sp.buscar("prova-v57", "tema")

    monkeypatch.setattr(research, "_STATUS_PROVEDOR", {})
    research.registrar_status("prova-v57", resultados=1)

    m = research.metricas_provedores()["prova-v57"]
    assert m["chamadas"] == 1 and m["resultados"] == 1
    assert m["ultimo_status"]["resultados"] == 1
