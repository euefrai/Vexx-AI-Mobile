#!/usr/bin/env python3
"""Bateria determinística de experiência real — V5.7 FINAL (FASE A).

Reproduz os pedidos reais do briefing contra o pipeline verdadeiro, sem
rede (DNS mockado como nos testes) e com fixtures locais. Cada checagem
mede o resultado do ponto de vista do usuário: a resposta teria como ser
sustentada com o que o sistema realmente recuperou?

Antes/depois: rodar antes das correções registra o "resultado anterior";
rodar de novo depois registra o posterior. Não grava nada por padrão;
--salvar grava artefato JSON em qa-artifacts/v57/.

Uso:
    python tools/bench_experiencia_real.py [--salvar] [--filtro TEXTO]

Limitação honesta: as fixtures validam o pipeline determinístico; não
substituem fontes externas reais (smokes externos são registrados à parte
e um provedor bloqueado não equivale a um teste aprovado).
"""
from __future__ import annotations

import argparse
import contextlib
import json
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

import docs_agent  # noqa: E402
import evidence_graph  # noqa: E402
import jdui  # noqa: E402
import pc_agent  # noqa: E402
import research  # noqa: E402
import search_orchestrator  # noqa: E402
import shopping  # noqa: E402

HOJE = "18/10/2026"
_MARCADOR = "MARCADOR-PAGINA-V57F"


# ── Infra mínima (sem pytest) ────────────────────────────────────────

def _db(nome: str):
    return pc_agent.open_db(Path(tempfile.mkdtemp()) / nome)


@contextlib.contextmanager
def _trocado(obj, nome: str, valor):
    antigo = getattr(obj, nome)
    setattr(obj, nome, valor)
    try:
        yield
    finally:
        setattr(obj, nome, antigo)


def _cfg():
    return {"proxy": "http://127.0.0.1:9/v1", "model": "m", "system": "BASE",
            "context": 12, "max_tokens": 500, "memoria_global": True,
            "pesquisa_web": True}


def _stub_sem_pesquisa():
    vazio = {"fontes": [], "etapas": ["(stub sem rede)"], "divergencias": [],
             "de_cache": False, "estado": "sem_resultados", "estado_texto": "",
             "provedores": {}, "lacunas": [], "consultas": [], "descartes": [],
             "correspondencia": 0.0}
    return lambda *a, **k: dict(vazio)


def _html_produto(nome: str, preco: float, url: str, marca: str = "MarcaX") -> str:
    preco_txt = ("R$ %.2f" % preco).replace(".", ",")
    return ('<html><head><title>' + nome + ' — Loja Certa</title>'
            '<meta property="og:type" content="product">'
            '<meta property="product:price:amount" content="%.2f">' % preco +
            '<script type="application/ld+json">'
            '{"@context":"https://schema.org/","@type":"Product","name":"' + nome + '",'
            '"image":"https://cdn.lojacerta.com.br/produto.jpg",'
            '"url":"' + url + '",'
            '"offers":{"@type":"Offer","price":"%.2f",' % preco +
            '"priceCurrency":"BRL","availability":"https://schema.org/InStock"},'
            '"brand":"' + marca + '"}'
            '</script></head><body><h1>' + nome + '</h1>'
            '<button>Adicionar ao carrinho</button> ' + preco_txt + '</body></html>')


# ── Checagens: pesquisa geral ────────────────────────────────────────

def _c_geral_grounding():
    """Conteúdo lido da página precisa chegar ao prompt além do trecho curto."""
    db = _db("er-geral1.sqlite3")
    try:
        texto = ("O artigo descreve o funcionamento em detalhes técnicos. " * 12
                 + f"{_MARCADOR}: o rendimento medido foi de 42 unidades por hora. "
                 + "Conclusão do estudo publicada após medição em campo. " * 8)
        achado = {"titulo": "Estudo técnico do rendimento",
                  "url": "https://tecnica.example/estudo",
                  "trecho": "estudo técnico do rendimento"}
        rec = {"titulo": achado["titulo"], "texto": texto, "final": achado["url"],
               "trecho_usado": texto[:400], "metadados": {}, "lida": True}
        rap = research.pesquisa_rapida(db, "ana", "rendimento tecnico",
                                       buscar_fn=lambda q: [dict(achado)],
                                       recuperar_fn=lambda u: dict(rec))
        fontes = rap["fontes"]
        assert fontes, "nenhuma fonte produzida"
        assert fontes[0]["status"] == "aberta", fontes[0]["status"]
        bloco = research.bloco_grounding(fontes, HOJE, rap)
        assert _MARCADOR in bloco, \
            "conteúdo real da página lida (além do trecho curto) não chega ao prompt"
        return "marcador de conteúdo presente no grounding"
    finally:
        db.close()


def _c_geral_aberta_vs_encontrada():
    """Página aberta x página só encontrada têm marcas honestas distintas."""
    db = _db("er-geral2.sqlite3")
    try:
        a1 = {"titulo": "Guia aberto", "url": "https://aberta.example/guia",
              "trecho": "guia aberto sobre o tema"}
        a2 = {"titulo": "Resumo de índice", "url": "https://indice.example/itens",
              "trecho": "resumo do índice sobre o tema"}

        def rec(u):
            if u == a2["url"]:
                raise research.ResearchErro("Provedor bloqueou (403).", "bloqueado")
            return {"titulo": a1["titulo"], "texto": "conteúdo realmente lido da página",
                    "final": u, "metadados": {}, "lida": True}

        rap = research.pesquisa_rapida(db, "ana", "tema do guia",
                                       buscar_fn=lambda q: [dict(a1), dict(a2)],
                                       recuperar_fn=rec)
        status = {f["url"]: f["status"] for f in rap["fontes"]}
        assert status.get(a1["url"]) == "aberta", status
        assert status.get(a2["url"]) == "encontrada", status
        bloco = research.bloco_grounding(rap["fontes"], HOJE, rap)
        i1, i2 = bloco.find("[S1]"), bloco.find("[S2]")
        assert i1 >= 0 and i2 > i1, bloco
        assert "NÃO lida" not in bloco[i1:i2]
        assert "NÃO lida" in bloco[i2:]
        assert "resumo do índice" in bloco
        return "aberta sem marca; encontrada marcada 'NÃO lida'"
    finally:
        db.close()


def _c_geral_sem_resultados():
    """Provedor vazio ⇒ estado honesto e bloco de falha com motivo real."""
    db = _db("er-geral3.sqlite3")
    try:
        fake = {"achados": [], "estado": "sem_resultados", "estado_texto": "",
                "provedores": {"usados": {}, "falhas": [], "vazios": ["bing"]},
                "lacunas": [], "recuperacao": [], "consultas": [], "descartes": [],
                "correspondencia": 0.0, "segundos": 0.1, "recuperou": False,
                "etapas": ["bing: sem resultados"]}
        with _trocado(search_orchestrator, "pesquisar_com_recuperacao",
                      lambda *a, **k: dict(fake)):
            rap = research.pesquisa_rapida(db, "ana", "assunto sem resultado")
        assert rap["fontes"] == [], rap["fontes"]
        assert rap["estado"] == "sem_resultados", rap["estado"]
        falha = research.bloco_falha(HOJE, rap["estado"])
        assert "sem resultados" in falha and "sem inventar links" in falha
        return "estado sem_resultados + aviso honesto"
    finally:
        db.close()


# ── Checagens: página pedida pelo usuário (URL no pedido) ────────────

def _html_pagina() -> str:
    return ('<html><head><title>Relatório de campo</title></head><body><article><p>'
            + "Texto introdutório do relatório com informações úteis para a análise. " * 10
            + f'{_MARCADOR} aparece no corpo do documento e resume o resultado. '
            + "Conteúdo adicional com detalhes medidos em campo, tabelas e conclusões. " * 20
            + '</p></article></body></html>')


def _c_pagina_lida():
    """\"Analise esta página: URL\" ⇒ conteúdo real da página no prompt."""
    db = _db("er-pag1.sqlite3")
    try:
        url = "https://exemplo.com/relatorio"
        stub = _stub_sem_pesquisa()
        with _trocado(research, "baixar", lambda u, timeout=10.0, **k: (u, _html_pagina())), \
             _trocado(research, "pesquisa_rapida", stub), \
             _trocado(research, "pesquisa_aprofundada", stub):
            msgs, extras = pc_agent.ai_montar_mensagens(
                db, "conv-pu", _cfg(),
                "analise esta página para mim: " + url)
        sistema = msgs[0]["content"]
        fontes = extras.get("fontes") or []
        assert fontes, "a página pedida deveria virar fonte utilizada"
        assert fontes[0]["url"].startswith(url), fontes[0]["url"]
        assert _MARCADOR in sistema, "conteúdo da página pedida não entrou no prompt"
        assert url in sistema
        return "página lida entrou no prompt como fonte"
    finally:
        db.close()


def _c_pagina_bloqueada():
    """Página bloqueada ⇒ aviso honesto, sem fonte e sem conteúdo inventado."""
    db = _db("er-pag2.sqlite3")
    try:
        url = "https://bloqueado.example/x"

        def bloqueia(u, timeout=10.0, **k):
            raise research.ResearchErro("Provedor bloqueou (403).", "bloqueado")

        stub = _stub_sem_pesquisa()
        with _trocado(research, "baixar", bloqueia), \
             _trocado(research, "pesquisa_rapida", stub), \
             _trocado(research, "pesquisa_aprofundada", stub):
            msgs, extras = pc_agent.ai_montar_mensagens(
                db, "conv-pb", _cfg(), "resuma esta página: " + url)
        sistema = msgs[0]["content"]
        assert not extras.get("fontes"), extras.get("fontes")
        assert url in sistema, "a URL pedida precisa ser citada no aviso"
        assert "não são contornados" in sistema, "motivo real do bloqueio ausente"
        return "bloqueio explicado sem contorno"
    finally:
        db.close()


def _c_pagina_controle_sem_url():
    """Pedido de leitura SEM URL não ativa o caminho de página."""
    db = _db("er-pag3.sqlite3")
    try:
        stub = _stub_sem_pesquisa()
        with _trocado(research, "pesquisa_rapida", stub), \
             _trocado(research, "pesquisa_aprofundada", stub):
            _, extras = pc_agent.ai_montar_mensagens(
                db, "conv-pc", _cfg(), "pode analisar isso para mim?")
        assert not extras.get("pagina_usuario"), extras.get("pagina_usuario")
        return "sem URL, sem leitura de página"
    finally:
        db.close()


# ── Checagens: comercial ─────────────────────────────────────────────

def _c_comercial_confirmada():
    """Produto específico ⇒ card com link do item e preço real."""
    db = _db("er-shop1.sqlite3")
    try:
        url = "https://lojacerta.com.br/produto/fone-xz400"
        cand = {"titulo": "Fone Bluetooth XZ-400 — Loja Certa", "url": url,
                "trecho": "fone bluetooth xz-400 com case"}
        html = _html_produto("Fone Bluetooth XZ-400", 299.90, url)
        res = shopping.pesquisar(db, "ana", "fone bluetooth xz-400", "c1",
                                 buscar_fn=lambda q: [dict(cand)],
                                 baixar_fn=lambda u: {"final": u, "texto": html})
        produtos = res.get("produtos") or []
        assert produtos, "nenhum produto confirmado"
        p = produtos[0]
        alvo = p.get("url_item") or p.get("url") or ""
        assert alvo.startswith(url), alvo
        texto_preco = str(p.get("preco_texto") or p.get("preco") or "")
        assert "299" in texto_preco, texto_preco
        fence = shopping.fence_resultado(res)
        assert fence and '"productcard"' in fence, "fence de produto ausente"
        corpo = json.loads(fence.split("```jdui", 1)[1].rsplit("```", 1)[0])
        ok, _, erros = jdui.validar_mensagem(corpo)
        assert ok, erros
        return f"{len(produtos)} card(s) confirmado(s) com link do item"
    finally:
        db.close()


def _c_comercial_orcamento():
    """Orçamento explícito ⇒ acima do teto nunca vira oferta."""
    db = _db("er-shop2.sqlite3")
    try:
        ua = "https://lojacerta.com.br/produto/fone-xz400"
        ub = "https://lojacerta.com.br/produto/fone-ultra9"
        cands = [{"titulo": "Fone Bluetooth XZ-400 — Loja Certa", "url": ua},
                 {"titulo": "Fone Bluetooth Ultra 9 — Loja Certa", "url": ub}]
        paginas = {ua: _html_produto("Fone Bluetooth XZ-400", 299.90, ua),
                   ub: _html_produto("Fone Bluetooth Ultra 9", 899.00, ub)}
        res = shopping.pesquisar(db, "ana", "fone bluetooth até R$ 300", "c1",
                                 buscar_fn=lambda q: [dict(c) for c in cands],
                                 baixar_fn=lambda u: {"final": u, "texto": paginas[u]})
        produtos = res.get("produtos") or []
        assert produtos, "o produto dentro do orçamento deveria confirmar"
        urls = {(p.get("url_item") or p.get("url") or "") for p in produtos}
        assert any(u.startswith(ua) for u in urls), urls
        assert not any(u.startswith(ub) for u in urls), \
            "produto acima do orçamento virou oferta"
        return "oferta dentro do teto; acima do teto fora"
    finally:
        db.close()


def _c_comercial_sem_ofertas():
    """Sem resultados de busca ⇒ nenhuma oferta inventada."""
    db = _db("er-shop3.sqlite3")
    try:
        res = shopping.pesquisar(db, "ana", "produto xyz inexistente", "c1",
                                 buscar_fn=lambda q: [],
                                 baixar_fn=lambda u: {"final": u, "texto": ""})
        assert res.get("produtos") == [], res.get("produtos")
        assert shopping.fence_resultado(res) == "", "fence sem produtos"
        texto = shopping.resumo_texto(res)
        assert texto.strip(), "resumo vazio (o usuário ficaria sem explicação)"
        return "sem produtos, explicação presente"
    finally:
        db.close()


# ── Checagens: documentos ────────────────────────────────────────────

def _c_docs_txt():
    db = _db("er-doc1.sqlite3")
    try:
        conteudo = ("Cláusula 7: multa de R$ 500 por atraso no pagamento. " * 50)
        m = docs_agent.salvar_documento(db, "contrato.txt",
                                        conteudo.encode("utf-8"), "conv-d")
        assert m["chars"] > 100, m
        hits = docs_agent.trechos_relevantes(db, "multa por atraso", m["doc_id"])
        assert hits, "nenhum trecho relevante encontrado"
        assert "multa" in docs_agent.obter_texto(db, m["doc_id"]).lower()
        return f"{len(hits)} trecho(s) relevantes"
    finally:
        db.close()


def _c_docs_csv():
    db = _db("er-doc2.sqlite3")
    try:
        m = docs_agent.salvar_documento(
            db, "vendas.csv", b"produto,preco\nfone,299\nnotebook,3999\n", "conv-d")
        texto = docs_agent.obter_texto(db, m["doc_id"]).lower()
        assert "notebook" in texto and "3999" in texto, texto[:120]
        hits = docs_agent.trechos_relevantes(db, "preço do notebook", m["doc_id"])
        assert hits and any(h.get("table_hint") for h in hits), hits
        return "CSV extraído como tabela com trecho relevante"
    finally:
        db.close()


# ── Checagens: evidência ─────────────────────────────────────────────

def _c_evidencia():
    # Fixture canônica do repositório (tests/test_evidence_graph.py):
    # quantidade exata + contexto compartilhado ⇒ SUPPORTED; sem fonte ⇒ honesto.
    claim = {"texto": "O consumo é de 65 W em jogos.",
             "condicoes": {"comparado_a": "", "metrica": "",
                           "quantidades": [{"valor": 65.0, "unidade": "W"}],
                           "datas": []}}
    r1 = evidence_graph.verificar_claim(
        claim, [{"id": "E1", "trecho": "medimos consumo de 65 W em jogos"}])
    assert r1["estado"] == "SUPPORTED", r1
    r2 = evidence_graph.verificar_claim(claim, [])
    assert r2["estado"] == "INSUFFICIENT_EVIDENCE", r2
    return "SUPPORTED com fonte; INSUFFICIENT_EVIDENCE sem fonte"


# ── Checagens: JDUI (paridade produto) ───────────────────────────────

def _prod_bloco(props: dict) -> dict:
    return {"version": jdui.VERSION,
            "blocks": [{"type": "ui", "component": "productcard",
                        "props": {"produto": props}}]}


def _c_jdui_python():
    ok, norm, _ = jdui.validar_mensagem(_prod_bloco({"nome": "P", "preco": 299.9}))
    assert ok and norm["blocks"][0]["props"]["produto"]["preco_valor"] == 299.9
    ok, norm, _ = jdui.validar_mensagem(_prod_bloco({"nome": "P", "item_de_listagem": "sim"}))
    assert ok and norm["blocks"][0]["props"]["produto"]["item_de_listagem"] is True
    ok, norm, _ = jdui.validar_mensagem(_prod_bloco({"nome": "P", "item_de_listagem": 0}))
    assert ok and norm["blocks"][0]["props"]["produto"]["item_de_listagem"] is False
    ok, _, _ = jdui.validar_mensagem(_prod_bloco({"nome": "P", "specs": [1, 2]}))
    assert not ok, "specs como lista não vazia deveria falhar"
    ok, norm, _ = jdui.validar_mensagem(_prod_bloco({"nome": "P", "specs": []}))
    assert ok and norm["blocks"][0]["props"]["produto"]["specs"] == {}
    ok, _, _ = jdui.validar_mensagem(_prod_bloco({"nome": "P", "specs": "x"}))
    assert not ok, "specs como string deveria falhar"
    return "fallback de preço, coerção e specs conforme o backend"


_HARNESS_BASE = r"""
const fs = require('fs');
class Element {
  constructor(tag) { this.tag = tag; this.children = []; this.events = {}; this.style = {}; this.attrs = {}; this.dataset = {}; this._text = ''; this.className = ''; this.classList = { toggle: () => {}, add: () => {}, remove: () => {}, contains: () => false }; }
  appendChild(child) { this.children.push(child); return child; }
  append(...children) { children.forEach(c => this.appendChild(c)); }
  replaceChildren(...children) { this.children = []; this._text = ''; this.append(...children); }
  addEventListener(name, fn) { this.events[name] = fn; }
  setAttribute(name, value) { this.attrs[name] = value; }
  querySelectorAll() { return []; }
  querySelector() { return null; }
  get textContent() { return this._text + this.children.map(c => c.textContent || '').join(''); }
  set textContent(value) { this._text = String(value); this.children = []; }
}
global.document = { createElement: tag => new Element(tag),
  createElementNS: (ns, tag) => new Element(tag) };
global.location = { href: 'https://app.example.test/' };
global.window = {};
eval(fs.readFileSync(process.argv[2], 'utf8'));
const JDUI = global.window.JDUI;
const V = 'JULIA-ui-message/v1';
const t = (name, cond) => {
  if (!cond) { console.error('FAIL ' + name); process.exitCode = 1; }
  else console.log('ok ' + name);
};
const prod = (props) => ({ version: V, blocks: [
  { type: 'ui', component: 'productcard', props: { produto: props } }] });
""".lstrip()


def _rodar_node(extra: str) -> str:
    node = shutil.which("node")
    if node is None:
        candidato = Path(r"C:\Users\efrai\AppData\Local\hermes\node\node.exe")
        node = str(candidato) if candidato.exists() else None
    if node is None:
        raise AssertionError("node indisponível para o harness JS")
    with tempfile.TemporaryDirectory() as tmp:
        arq = Path(tmp) / "harness_v57f.cjs"
        arq.write_text(_HARNESS_BASE + extra, encoding="utf-8")
        r = subprocess.run([node, str(arq), str(RAIZ / "public" / "jdui.js")],
                           capture_output=True, text=True, timeout=60)
    saida = (r.stdout + "\n" + r.stderr).strip()
    if r.returncode != 0 or "FAIL" in r.stdout:
        raise AssertionError("node: " + saida[:220])
    return "harness node ok"


def _c_jdui_js_preco():
    return _rodar_node("""
const v = JDUI.validateMessage(prod({ nome: 'Fone X', preco: 299.9,
  url: 'https://loja.example/f' }));
t('js-preco-fallback', v.ok === true &&
  v.msg.blocks[0].props.produto.preco_valor === 299.9);
""")


def _c_jdui_js_listagem():
    return _rodar_node("""
const casos = [[1, true], [0, false], ['sim', true], ['', false]];
casos.forEach(([entrada, esperado]) => {
  const v = JDUI.validateMessage(prod({ nome: 'P', item_de_listagem: entrada }));
  t('js-lista-' + JSON.stringify(entrada), v.ok === true &&
    v.msg.blocks[0].props.produto.item_de_listagem === esperado);
});
""")


def _c_jdui_js_specs():
    return _rodar_node("""
const r1 = JDUI.validateMessage(prod({ nome: 'P', specs: [1, 2] }));
t('js-specs-lista-falha', r1.ok === false);
const r2 = JDUI.validateMessage(prod({ nome: 'P', specs: [] }));
t('js-specs-lista-vazia-ok', r2.ok === true &&
  Object.keys(r2.msg.blocks[0].props.produto.specs).length === 0);
const r3 = JDUI.validateMessage(prod({ nome: 'P', specs: 'x' }));
t('js-specs-string-falha', r3.ok === false);
const r4 = JDUI.validateMessage(prod({ nome: 'P', specs: { mem: '8GB' } }));
t('js-specs-objeto-ok', r4.ok === true &&
  r4.msg.blocks[0].props.produto.specs.mem === '8GB');
""")


# ── Execução ─────────────────────────────────────────────────────────

def checagens() -> list:
    return [
        {"grupo": "pesquisa geral", "id": "geral_grounding_carrega_conteudo_lido",
         "desc": "conteúdo lido da página chega ao prompt (além do trecho curto)",
         "fn": _c_geral_grounding},
        {"grupo": "pesquisa geral", "id": "geral_aberta_vs_encontrada",
         "desc": "página aberta x só encontrada com marcas honestas",
         "fn": _c_geral_aberta_vs_encontrada},
        {"grupo": "pesquisa geral", "id": "geral_sem_resultados_honesto",
         "desc": "provedor vazio vira estado honesto + aviso",
         "fn": _c_geral_sem_resultados},
        {"grupo": "página do usuário", "id": "pagina_usuario_lida_entra_no_prompt",
         "desc": "\"analise esta página: URL\" traz o conteúdo real",
         "fn": _c_pagina_lida},
        {"grupo": "página do usuário", "id": "pagina_usuario_bloqueada_honesta",
         "desc": "página bloqueada: aviso honesto, sem invenção",
         "fn": _c_pagina_bloqueada},
        {"grupo": "página do usuário", "id": "pagina_usuario_controle_sem_url",
         "desc": "pedido de leitura sem URL não ativa o caminho",
         "fn": _c_pagina_controle_sem_url},
        {"grupo": "comercial", "id": "comercial_oferta_confirmada_com_link",
         "desc": "produto específico vira card com link do item e preço",
         "fn": _c_comercial_confirmada},
        {"grupo": "comercial", "id": "comercial_orcamento_respeitado",
         "desc": "acima do orçamento nunca vira oferta",
         "fn": _c_comercial_orcamento},
        {"grupo": "comercial", "id": "comercial_sem_ofertas_nao_inventa",
         "desc": "sem resultados: nenhuma oferta inventada",
         "fn": _c_comercial_sem_ofertas},
        {"grupo": "documentos", "id": "documento_txt_trechos",
         "desc": "TXT salvo, trechos relevantes recuperáveis",
         "fn": _c_docs_txt},
        {"grupo": "documentos", "id": "documento_csv_tabela",
         "desc": "CSV extraído como tabela com trecho relevante",
         "fn": _c_docs_csv},
        {"grupo": "evidência", "id": "evidencia_claim_estados",
         "desc": "claim com/sem evidência: SUPPORTED/INSUFFICIENT_EVIDENCE",
         "fn": _c_evidencia},
        {"grupo": "JDUI", "id": "jdui_python_produto",
         "desc": "validador Python: preço, coerção e specs",
         "fn": _c_jdui_python},
        {"grupo": "JDUI", "id": "jdui_js_preco_fallback",
         "desc": "espelho JS: preço numérico sem preco_valor informa valor",
         "fn": _c_jdui_js_preco},
        {"grupo": "JDUI", "id": "jdui_js_item_de_listagem",
         "desc": "espelho JS: coerção de item_de_listagem igual ao backend",
         "fn": _c_jdui_js_listagem},
        {"grupo": "JDUI", "id": "jdui_js_specs_tipo",
         "desc": "espelho JS: specs com mesmo aceite/recusa do backend",
         "fn": _c_jdui_js_specs},
    ]


def executar(filtro: str = "") -> list:
    antigo_ips = research._ips_globais
    research._ips_globais = lambda host: None  # DNS mockado, como nos testes
    try:
        resultados = []
        for c in checagens():
            if filtro and filtro not in c["id"]:
                continue
            t0 = time.monotonic()
            try:
                detalhe = c["fn"]() or "ok"
                ok = True
            except AssertionError as exc:
                ok, detalhe = False, (str(exc) or "assertion")
            except Exception as exc:  # nunca mascara: tipo + mensagem
                ok, detalhe = False, f"{type(exc).__name__}: {exc}"
            resultados.append({"grupo": c["grupo"], "id": c["id"],
                               "desc": c["desc"], "ok": ok,
                               "detalhe": str(detalhe)[:240],
                               "ms": int((time.monotonic() - t0) * 1000)})
        return resultados
    finally:
        research._ips_globais = antigo_ips


def _commit() -> str:
    try:
        r = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=RAIZ,
                           capture_output=True, text=True, timeout=10)
        return r.stdout.strip()
    except Exception:
        return ""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Bateria de experiência real V5.7 FINAL")
    ap.add_argument("--salvar", action="store_true",
                    help="grava artefato JSON em qa-artifacts/v57/")
    ap.add_argument("--filtro", default="", help="roda só ids que contenham o texto")
    args = ap.parse_args(argv)
    res = executar(args.filtro)
    for r in res:
        marca = "ok   " if r["ok"] else "FALHA"
        print(f"[{marca}] {r['id']} ({r['ms']} ms) — {r['desc']}")
        if r["detalhe"] and r["detalhe"] != "ok":
            print(f"         -> {r['detalhe']}")
    ok = sum(1 for r in res if r["ok"])
    print(f"\nresultado: {ok}/{len(res)} checagens ok")
    if args.salvar:
        pasta = RAIZ / "qa-artifacts" / "v57"
        pasta.mkdir(parents=True, exist_ok=True)
        dia = datetime.now().strftime("%Y-%m-%d")
        alvo = pasta / f"bench-experiencia-real-{dia}.json"
        alvo.write_text(json.dumps(
            {"criado_em": datetime.now().isoformat(timespec="seconds"),
             "commit": _commit(), "resultados": res,
             "resumo": {"ok": ok, "total": len(res), "falhas": len(res) - ok}},
            ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"artefato: {alvo}")
    return 0 if ok == len(res) else 1


if __name__ == "__main__":
    raise SystemExit(main())
