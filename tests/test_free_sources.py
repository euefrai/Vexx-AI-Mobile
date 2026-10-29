"""Free-source adapters: deterministic fixtures, no live network calls."""
import json
import urllib.error
import urllib.parse
from email.message import Message

import pytest

import free_sources as fs
import research
import search_orchestrator as orch
import search_providers as sp
import shopping


class Resp:
    def __init__(self, body=b"{}", status=200, ctype="application/json"):
        self._body = body
        self.status = status
        self.headers = Message()
        self.headers["Content-Type"] = ctype
        self.headers["Content-Length"] = str(len(body))

    def read(self, n=-1):
        return self._body if n is None or n < 0 else self._body[:n]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _http_error(url, code, location=None):
    headers = Message()
    if location:
        headers["Location"] = location
    return urllib.error.HTTPError(url, code, "fixture", headers, None)


# ── Safe JSON/Atom client ──────────────────────────────────────────────

def test_json_client_sends_optional_headers_and_parses(monkeypatch):
    monkeypatch.setattr(research, "url_segura", lambda url: url)
    seen = {}

    def abrir(url, timeout, **kwargs):
        seen.update(url=url, timeout=timeout, **kwargs)
        return Resp(b'{"ok": true}')

    monkeypatch.setattr(research, "_abrir", abrir)
    value = fs._json_request("https://api.example/v1", timeout=3.0,
                             headers={"Authorization": "Bearer secret"})
    assert value == {"ok": True}
    assert seen["headers"]["Authorization"] == "Bearer secret"
    assert seen["method"] == "GET"
    assert "secret" not in seen["url"]


def test_json_client_429_is_blocked_rate_limit(monkeypatch):
    monkeypatch.setattr(research, "url_segura", lambda url: url)
    monkeypatch.setattr(research, "_abrir", lambda *a, **k: (_ for _ in ()).throw(
        _http_error("https://api.example/v1", 429)))
    with pytest.raises(fs.ErroFonte) as caught:
        fs._json_request("https://api.example/v1", timeout=3.0)
    assert caught.value.codigo == "bloqueado"
    assert caught.value.http == 429


def test_json_client_revalidates_redirects(monkeypatch):
    monkeypatch.setattr(research, "url_segura", lambda url: url)
    calls = []

    def abrir(url, timeout, **kwargs):
        calls.append(url)
        if len(calls) == 1:
            raise _http_error(url, 302, "/next")
        return Resp(b'{"ok": 1}')

    monkeypatch.setattr(research, "_abrir", abrir)
    assert fs._json_request("https://api.example/start", timeout=3.0) == {"ok": 1}
    assert calls == ["https://api.example/start", "https://api.example/next"]


def test_json_client_rejects_non_json_and_oversize(monkeypatch):
    monkeypatch.setattr(research, "url_segura", lambda url: url)
    monkeypatch.setattr(research, "_abrir", lambda *a, **k: Resp(
        b"%PDF", ctype="application/pdf"))
    with pytest.raises(fs.ErroFonte) as caught:
        fs._json_request("https://api.example/v1", timeout=3.0)
    assert caught.value.codigo == "tipo"

    monkeypatch.setattr(research, "_abrir", lambda *a, **k: Resp(b'{"long": true}'))
    with pytest.raises(fs.ErroFonte) as caught:
        fs._json_request("https://api.example/v1", timeout=3.0, max_bytes=4)
    assert caught.value.codigo == "tamanho"


# ── Adapters ───────────────────────────────────────────────────────────

def test_github_normalizes_repositories(monkeypatch):
    seen = {}

    def fake(url, **kwargs):
        seen.update(url=url, headers=kwargs.get("headers") or {})
        return {"items": [{
            "full_name": "fastapi/fastapi", "html_url": "https://github.com/fastapi/fastapi",
            "description": "High performance framework", "stargazers_count": 100,
            "language": "Python", "updated_at": "2026-10-01T00:00:00Z",
            "topics": ["api"], "archived": False, "license": {"spdx_id": "MIT"},
        }]}

    monkeypatch.setattr(fs, "_json_request", fake)
    rows = fs.buscar_github("fastapi", 2)
    assert rows[0]["titulo"] == "fastapi/fastapi"
    assert rows[0]["url"] == "https://github.com/fastapi/fastapi"
    assert "100 estrelas" in rows[0]["trecho"]
    assert rows[0]["meta"]["license"] == "MIT"
    assert "q=fastapi" in seen["url"]
    assert seen["headers"]["Accept"] == "application/vnd.github+json"


def test_brave_requires_key_and_sends_it_only_in_header(monkeypatch):
    monkeypatch.delenv("BRAVE_SEARCH_API_KEY", raising=False)
    with pytest.raises(fs.ErroFonte) as caught:
        fs.buscar_brave("notícias de hoje")
    assert caught.value.codigo == "indisponivel"

    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "brave-secret")
    seen = {}

    def fake(url, **kwargs):
        seen.update(url=url, headers=kwargs.get("headers") or {})
        return {"web": {"results": [{
            "title": "Notícia real", "url": "https://news.example/a",
            "description": "Resumo", "age": "2 horas atrás",
            "meta_url": {"hostname": "news.example"}, "language": "pt",
        }]}}

    monkeypatch.setattr(fs, "_json_request", fake)
    rows = fs.buscar_brave("notícias de hoje", 2)
    assert rows[0]["titulo"] == "Notícia real"
    assert seen["headers"]["X-Subscription-Token"] == "brave-secret"
    assert "brave-secret" not in seen["url"]
    assert "freshness=pw" in seen["url"]


def test_brasilapi_cep_and_cnpj_normalization(monkeypatch):
    def fake(url, **kwargs):
        if "/cep/" in url:
            return {"cep": "01310100", "state": "SP", "city": "São Paulo",
                    "neighborhood": "Bela Vista", "street": "Avenida Paulista",
                    "service": "open-cep", "ibge": {"city": "3550308", "state": "35"},
                    "timezoneName": "America/Sao_Paulo",
                    "location": {"coordinates": {"longitude": "-46.63", "latitude": "-23.54"}}}
        return {"cnpj": "19131243000197", "razao_social": "Banco do Brasil S.A.",
                "nome_fantasia": "Banco do Brasil", "municipio": "Brasília",
                "uf": "DF", "cnae_fiscal_descricao": "Bancos múltiplos",
                "descricao_situacao_cadastral": "ATIVA",
                "data_inicio_atividade": "1966-01-01"}

    monkeypatch.setattr(fs, "_json_request", fake)
    cep = fs.buscar_brasilapi("Qual o CEP 01310-100?", 1)[0]
    assert "01310-100" in cep["titulo"] and "01310100" in cep["trecho"]
    assert cep["meta"]["kind"] == "cep" and cep["meta"]["state"] == "SP"
    cnpj = fs.buscar_brasilapi("CNPJ 19.131.243/0001-97", 1)[0]
    assert "Banco do Brasil S.A." in cnpj["titulo"]
    assert "19131243000197" in cnpj["trecho"]
    assert cnpj["meta"]["kind"] == "cnpj" and cnpj["meta"]["uf"] == "DF"


def test_brasilapi_without_document_is_empty_not_invented():
    with pytest.raises(fs.ErroFonte) as caught:
        fs.buscar_brasilapi("qual a capital da França")
    assert caught.value.codigo == "vazio"


def test_coingecko_filters_unrelated_search_hits(monkeypatch):
    def fake(url, **kwargs):
        if "/search" in url:
            return {"coins": [
                {"id": "bitcoin", "name": "Bitcoin", "symbol": "btc", "market_cap_rank": 1},
                {"id": "dog-go-to-the-moon-rune", "name": "DOG", "symbol": "dog",
                 "market_cap_rank": 300},
            ]}
        return {"bitcoin": {"brl": 350000.0, "usd": 65000.0,
                            "brl_24h_change": 1.25, "last_updated_at": 1700000000}}

    monkeypatch.setattr(fs, "_json_request", fake)
    rows = fs.buscar_coingecko("preço do bitcoin hoje", 6)
    assert len(rows) == 1
    assert rows[0]["titulo"].startswith("Bitcoin (BTC)")
    assert "R$ 350.000,00" in rows[0]["titulo"]
    assert rows[0]["meta"]["market_cap_rank"] == 1


def test_coingecko_generic_query_lists_market_leaders(monkeypatch):
    def fake(url, **kwargs):
        if "/coins/markets" in url:
            return [{"id": "bitcoin", "name": "Bitcoin", "symbol": "btc",
                     "market_cap_rank": 1}]
        return {"bitcoin": {"brl": 350000.0, "usd": 65000.0,
                            "brl_24h_change": -0.5, "last_updated_at": 1700000000}}

    monkeypatch.setattr(fs, "_json_request", fake)
    rows = fs.buscar_coingecko("criptomoedas hoje", 3)
    assert rows[0]["meta"]["id"] == "bitcoin"
    assert "24h -0.50%" in rows[0]["trecho"]


def test_arxiv_parses_atom_without_live_network(monkeypatch):
    feed = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/1706.03762v7</id>
    <title>Attention Is All You Need</title>
    <summary>We propose the Transformer.</summary>
    <published>2017-06-12T17:57:34Z</published>
    <author><name>Ashish Vaswani</name></author>
    <link rel="alternate" href="http://arxiv.org/abs/1706.03762v7" type="text/html"/>
    <arxiv:doi>10.48550/arXiv.1706.03762</arxiv:doi>
  </entry>
</feed>"""
    monkeypatch.setattr(fs, "_request", lambda *a, **k: (feed, "application/atom+xml"))
    rows = fs.buscar_arxiv("transformer attention", 2)
    assert rows[0]["titulo"] == "Attention Is All You Need"
    assert rows[0]["url"] == "https://arxiv.org/abs/1706.03762v7"
    assert rows[0]["year"] == 2017
    assert rows[0]["authors"] == ["Ashish Vaswani"]
    assert rows[0]["pdf_url"].endswith("/pdf/1706.03762v7")


def test_openalex_reuses_provider_contract(monkeypatch):
    called = {}

    class FakeProvider:
        def buscar(self, consulta, limite):
            called.update(consulta=consulta, limite=limite)
            return [{"titulo": "Paper", "url": "https://doi.org/10.1/x",
                     "doi": "10.1/x", "trecho": "Abstract", "authors": ["A"],
                     "year": 2024, "pdf_url": "https://repo.example/x.pdf",
                     "open_access": True, "citation_count": 3}]

    monkeypatch.setattr(fs, "_openalex_provider", lambda: FakeProvider())
    rows = fs.buscar_openalex("solid state batteries", 4)
    assert called == {"consulta": "solid state batteries", "limite": 4}
    assert rows[0]["metadata_source"] == "academic_provider"
    assert rows[0]["meta"]["citation_count"] == 3


# ── Availability and routing ───────────────────────────────────────────

def test_brave_is_only_advertised_with_key(monkeypatch):
    monkeypatch.setenv("JULIA_FREE_APIS", "1")
    monkeypatch.delenv("BRAVE_SEARCH_API_KEY", raising=False)
    assert "brave" not in sp.disponiveis()
    sp._reset_metricas()
    with pytest.raises(sp.ErroProvedor) as caught:
        sp.buscar("brave", "consulta")
    assert caught.value.codigo == "indisponivel"
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "fixture-key")
    assert "brave" in sp.disponiveis()


def test_free_apis_can_be_disabled_without_affecting_legacy(monkeypatch):
    monkeypatch.setenv("JULIA_FREE_APIS", "0")
    monkeypatch.delenv("BRAVE_SEARCH_API_KEY", raising=False)
    for nome in ("openalex", "arxiv", "github", "brasilapi", "coingecko", "brave"):
        assert nome not in sp.disponiveis()
    assert "bing" in sp.disponiveis()
    sp._reset_metricas()
    with pytest.raises(sp.ErroProvedor) as caught:
        sp.buscar("openalex", "consulta")
    assert caught.value.codigo == "indisponivel"


def test_classificar_detects_documents_and_crypto():
    cep = orch.classificar("Qual o CEP 01310-100?")
    assert cep["documento"] == "cep" and cep["documento_valor"] == "01310100"
    cnpj = orch.classificar("Qual o CNPJ 19.131.243/0001-97?")
    assert cnpj["documento"] == "cnpj" and cnpj["documento_valor"] == "19131243000197"
    assert orch.classificar("preço do bitcoin hoje")["cripto"] is True
    assert orch.classificar("história da criptografia")["cripto"] is False


def test_routing_prefers_authoritative_structured_sources():
    info = orch.classificar("Qual o CEP 01310-100?")
    nomes = orch._escolher_provedores(
        info["classes"], info, disponiveis=["brasilapi", "bing", "ddg"])
    assert nomes[0] == "brasilapi"

    info = orch.classificar("cotação do bitcoin hoje")
    nomes = orch._escolher_provedores(
        info["classes"], info, disponiveis=["coingecko", "bing", "ddg"])
    assert nomes[0] == "coingecko"


def test_routing_puts_academic_and_code_sources_in_order():
    info = orch.classificar("artigos científicos sobre transformers")
    nomes = orch._escolher_provedores(
        info["classes"], info,
        disponiveis=["crossref", "openalex", "arxiv", "bing", "ddg"])
    assert nomes[:3] == ["crossref", "openalex", "arxiv"]

    info = orch.classificar("biblioteca python para requisições http")
    info["request"] = {"original_request": "biblioteca python para requisições http",
                       "domain": "general"}
    nomes = orch._escolher_provedores(
        info["classes"], info,
        disponiveis=["stackexchange", "hn", "github", "bing", "ddg"])
    assert nomes[:3] == ["stackexchange", "hn", "github"]


# ── Optional Mercado Livre token ───────────────────────────────────────

def test_mercado_livre_token_goes_only_in_authorization_header(monkeypatch):
    seen = {}

    def fake(url, timeout, headers=None):
        seen["headers"] = headers
        return {"results": [{
            "permalink": "https://produto.mercadolivre.com.br/MLB-1",
            "title": "Notebook", "price": 1000, "currency_id": "BRL",
        }]}

    monkeypatch.setattr(shopping, "_get_json", fake)
    monkeypatch.setenv("MERCADO_LIVRE_ACCESS_TOKEN", "token-secreto")
    rows = shopping.buscar_mlb("notebook", 1)
    assert seen["headers"] == {"Authorization": "Bearer token-secreto"}
    assert rows and "token-secreto" not in json.dumps(rows)


def test_mercado_livre_without_token_keeps_public_request(monkeypatch):
    seen = {}

    def fake(url, timeout, headers=None):
        seen["headers"] = headers
        return {"results": []}

    monkeypatch.setattr(shopping, "_get_json", fake)
    monkeypatch.delenv("MERCADO_LIVRE_ACCESS_TOKEN", raising=False)
    with pytest.raises(research.ResearchErro):
        shopping.buscar_mlb("notebook", 1)
    assert seen["headers"] is None
