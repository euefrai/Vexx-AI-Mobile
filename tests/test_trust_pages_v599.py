"""V5.9.9 — camada pública de transparência e reputação.

As páginas institucionais não prometem empresa, CNPJ, fundador ou e-mail que
não existam. Elas descrevem o que o código realmente faz e apontam para o
GitHub Issues como canal oficial.
"""
from datetime import datetime
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest
from fastapi.testclient import TestClient

import server

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"

PAGES = {
    "/sobre": ("sobre.html", "Sobre o Vexx AI", "Quem mantém o projeto"),
    "/privacidade": ("privacidade.html", "Política de Privacidade", "IndexedDB"),
    "/termos": ("termos.html", "Termos de Uso", "Uso aceitável"),
    "/seguranca": ("seguranca.html", "Segurança e transparência", "security.txt"),
    "/contato": ("contato.html", "Fale com o projeto", "GitHub Issues"),
}


def _html(name: str) -> str:
    return (PUBLIC / name).read_text(encoding="utf-8")


@pytest.mark.parametrize("route,meta", PAGES.items())
def test_trust_pages_are_public_complete_and_accessible(route, meta):
    name, title, marker = meta
    html = _html(name)
    assert title in html
    assert marker in html
    assert '<html lang="pt-BR">' in html
    assert f'<link rel="canonical" href="https://vexx-ai.space{route}" />' in html
    assert '<meta name="robots" content="index,follow" />' in html
    # CSP do relay não permite script/style inline: as páginas usam só CSS externo.
    assert "<script" not in html
    assert " style=" not in html
    # Nenhuma página institucional inventa contato ou empresa.
    assert "TODO" not in html and "Lorem ipsum" not in html
    assert "example.com" not in html


@pytest.mark.parametrize("route,meta", PAGES.items())
def test_clean_routes_serve_html_with_security_headers(route, meta):
    name, title, _ = meta
    with TestClient(server.app) as client:
        response = client.get(route)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert title in response.text
    assert "default-src 'self'" in response.headers["content-security-policy"]
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert "camera=()" in response.headers["permissions-policy"]
    assert "geolocation=(self)" in response.headers["permissions-policy"]


def test_same_pages_are_also_available_as_static_html():
    with TestClient(server.app) as client:
        response = client.get("/privacidade.html")
    assert response.status_code == 200
    assert "Política de Privacidade" in response.text


def test_robots_points_to_sitemap_and_keeps_private_routes_out():
    with TestClient(server.app) as client:
        response = client.get("/robots.txt")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    body = response.text
    assert "User-agent: *" in body
    assert "Disallow: /api/" in body
    assert "Disallow: /admin.html" in body
    assert "Sitemap: https://vexx-ai.space/sitemap.xml" in body


def test_sitemap_lists_only_canonical_public_pages():
    with TestClient(server.app) as client:
        response = client.get("/sitemap.xml")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/xml")
    root = ET.fromstring(response.text)
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    locs = {node.text for node in root.findall("sm:url/sm:loc", ns)}
    assert locs == {
        "https://vexx-ai.space/",
        "https://vexx-ai.space/sobre",
        "https://vexx-ai.space/privacidade",
        "https://vexx-ai.space/termos",
        "https://vexx-ai.space/seguranca",
        "https://vexx-ai.space/contato",
    }


def test_security_txt_follows_rfc_9116_fields_and_has_a_future_expiry():
    with TestClient(server.app) as client:
        response = client.get("/.well-known/security.txt")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    fields = {}
    for line in response.text.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            fields[key.strip()] = value.strip()
    assert fields["Contact"] == "https://github.com/euefrai/Vexx-AI-Mobile/issues"
    assert fields["Canonical"] == "https://vexx-ai.space/.well-known/security.txt"
    assert fields["Policy"] == "https://vexx-ai.space/seguranca"
    expires = datetime.fromisoformat(fields["Expires"].replace("Z", "+00:00"))
    assert expires > datetime(2026, 10, 28, tzinfo=expires.tzinfo)


def test_app_settings_and_login_link_to_the_legal_pages():
    html = _html("index.html")
    for route in ("/sobre", "/privacidade", "/termos", "/seguranca", "/contato"):
        assert f'href="{route}"' in html
    assert 'class="login-legal"' in html
    assert "Ao entrar, você concorda" in html


def test_security_policy_and_offline_shell_include_the_trust_layer():
    security = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
    assert "Como relatar uma vulnerabilidade" in security
    assert "Não há programa de recompensas financeiras nem SLA" in security
    assert "https://vexx-ai.space/.well-known/security.txt" in security
    playbook = (ROOT / "docs" / "TRUST_PLAYBOOK.md").read_text(encoding="utf-8")
    assert "Google Search Console" in playbook
    assert "Assinatura de código" in playbook
    sw = (PUBLIC / "sw.js").read_text(encoding="utf-8")
    for route in PAGES:
        assert f"'{route}'" in sw
    assert "'/trust.css'" in sw


def test_public_claims_are_limited_to_verified_facts():
    sobre = _html("sobre.html")
    assert "Não há informação canônica confirmada sobre empresa criadora" in sobre
    assert "github.com/euefrai/Vexx-AI-Mobile" in sobre
    # O projeto não deve inventar um canal de e-mail ou telefone.
    assert "suporte@" not in sobre
    assert "telefone" in sobre.lower()
    privacidade = _html("privacidade.html")
    assert "não mantém um banco de conversas" in privacidade
    assert "Chaves de API" in privacidade
