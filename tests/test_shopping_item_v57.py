"""V5.7 — Validação positiva: página do item declarada no JSON-LD é aberta.

Caso real (KaBuM, 2026-10-18): categoria/listagem com JSON-LD Products cujo
`offers.url` aponta para a página do produto. Antes, o card saía sempre
`item_de_listagem`/`item_nao_aberto` (oferta parcial) porque NENHUM passo
abria a URL declarada. Agora `pesquisar` abre a URL do item (orçamento
próprio, mesmo downloader, sem contorno de bloqueio) e só promove quando há
evidência: `source_check.avaliar_pagina` confirma produto + identidade
(termos do card, variante primeiro) e existe preço em dado estruturado.
Preço/estoque/foto passam a vir da página do item; página bloqueada ou de
outro produto preserva o card parcial exatamente como estava.

Fixtures locais; sem rede (DNS mockado).
"""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pc_agent
import research
import shopping


@pytest.fixture(autouse=True)
def _sem_dns(monkeypatch):
    monkeypatch.setattr(research, "_ips_globais", lambda host: None)


def _db():
    return pc_agent.open_db(Path(tempfile.mkdtemp()) / "item57.sqlite3")


URL_LISTA = "https://lojax.com.br/esporte/notebooks"
URL_BUSCA = "https://lojax.com.br/busca/notebooks"
URL_ITEM = "https://lojax.com.br/produto/notebook-alpha-12gb"
URL_ITEM2 = "https://lojax.com.br/produto/notebook-beta-16gb"
NOME = "Notebook Alpha 12GB"
PRECO_LISTA = 3999.00
PRECO_ITEM = 3499.00


def _itens_jsonld(itens: list) -> str:
    return json.dumps(itens, ensure_ascii=False)


def _pagina_lista(itens, *, url=URL_LISTA, titulo="Notebooks — Loja X"):
    """Página com cara de categoria (8 preços visíveis), mas classificada como
    dedicada o bastante para não virar `listagem` — mesmo perfil da KaBuM."""
    precos = " ".join(f"R$ {i + 3}99,00" for i in range(8))  # >6 preços
    return ('<html><head><title>' + titulo + '</title>'
            '<script type="application/ld+json">'
            + _itens_jsonld(itens) + '</script>'
            '</head><body><h1>Notebooks</h1>' + precos + '</body></html>')


def _pagina_busca(itens):
    """Classificação explícita de listagem (URL /busca/ + título de busca)."""
    return _pagina_lista(itens, url=URL_BUSCA,
                         titulo="Resultados para notebooks | Loja X")


def _pagina_item(nome=NOME, preco=PRECO_ITEM, url=URL_ITEM, com_preco=True):
    ofertas = ('"offers":{"@type":"Offer","price":"%.2f",'
               '"priceCurrency":"BRL",'
               '"availability":"https://schema.org/InStock"},' % preco
               if com_preco else "")
    meta_preco = ('<meta property="product:price:amount" content="%.2f">' % preco
                  if com_preco else "")
    preco_txt = "R$ 3.499,00" if com_preco else ""
    return (
        f'<html><head><title>{nome} — Loja X</title>'
        '<meta property="og:type" content="product">'
        + meta_preco +
        '<script type="application/ld+json">'
        f'{{"@context":"https://schema.org/","@type":"Product","name":"{nome}",'
        f'"image":"https://cdn.lojax.com.br/alpha.jpg","url":"{url}",'
        f'{ofertas}"brand":"LojaX"}}</script></head><body><h1>{nome}</h1>'
        f'<button>Adicionar ao carrinho</button> {preco_txt}</body></html>')


def _item_jsonld(nome=NOME, preco=PRECO_LISTA, url_item=URL_ITEM,
                 com_url_produto=False):
    item = {"@type": "Product", "name": nome,
            "offers": {"@type": "Offer", "price": "%.2f" % preco,
                       "priceCurrency": "BRL", "url": url_item}}
    if com_url_produto:
        item["url"] = url_item
    return item


def _pesquisar_com_lista(db, conv, pagina_lista, mapa_item=None,
                         url_lista=URL_LISTA, consulta="notebook"):
    """Pesquisa offline: 1 candidata (listagem) + páginas de item injetadas."""
    chamadas = []
    mapa = {url_lista: pagina_lista}
    mapa.update(mapa_item or {})

    def _baixar(url):
        chamadas.append(url)
        if url in mapa:
            return {"final": url, "texto": mapa[url]}
        raise research.ResearchErro("Provedor bloqueou (403).", "bloqueado")

    res = shopping.pesquisar(
        db, "ana", consulta, conv,
        buscar_fn=lambda q: [{"titulo": "Notebooks — Loja X",
                              "url": url_lista, "trecho": "notebook"}],
        baixar_fn=_baixar)
    return res, chamadas


# ── Promoção: só com evidência ────────────────────────────────────────

def test_pagina_do_item_aberta_promove_para_confirmada():
    db = _db()
    res, chamadas = _pesquisar_com_lista(
        db, "i1", _pagina_lista([_item_jsonld()]),
        {URL_ITEM: _pagina_item()})
    assert len(res["produtos"]) == 1
    p = res["produtos"][0]
    assert URL_ITEM in chamadas  # a página do item foi realmente aberta
    assert p["link_veredito"] == "verificado"
    assert p["link_codigo"] == "ok"
    assert p["item_de_listagem"] is False
    assert "produto confirmado" in p["link_motivo"]
    assert p["url_item"] == URL_ITEM
    assert p["url_verificada"] == URL_ITEM
    # Dados da página do item (mais específicos) vencem os da listagem.
    assert p["preco"] == PRECO_ITEM and p["preco_confirmado"] is True
    assert p["preco_origem"] == "jsonld"
    assert p["disponibilidade"] == "em_estoque"
    assert p["imagem"] == "https://cdn.lojax.com.br/alpha.jpg"
    assert shopping._tier(p) == "confirmada"
    assert res["verificacao"]["links"]["verificado"] == 1


def test_item_de_listagem_com_url_propria_tambem_e_confirmado():
    """Categoria classificada como listagem (URL de busca) sai com
    `item_de_listagem`; aberta a página do item, o card é promovido."""
    db = _db()
    pagina = _pagina_busca([_item_jsonld(com_url_produto=True)])
    # Pré-condição: extração sozinha nunca herda "verificado".
    saidas = shopping._recuperar_ofertas(
        URL_BUSCA, "Notebooks", consulta="notebook",
        baixar_fn=lambda u: {"final": u, "texto": pagina})
    assert saidas and saidas[0]["link_codigo"] == "item_de_listagem"
    assert saidas[0]["item_de_listagem"] is True
    res, chamadas = _pesquisar_com_lista(
        db, "i2", pagina, {URL_ITEM: _pagina_item()}, url_lista=URL_BUSCA)
    p = res["produtos"][0]
    assert URL_ITEM in chamadas
    assert p["item_de_listagem"] is False
    assert p["link_veredito"] == "verificado"
    assert p["preco"] == PRECO_ITEM
    assert shopping._tier(p) == "confirmada"


def test_pagina_item_sem_preco_mantem_preco_da_listagem():
    """Link verificado + preço em dado estruturado (da listagem) já sustentam
    "confirmada"; a página do item sem preço não apaga dado real existente."""
    db = _db()
    res, _ = _pesquisar_com_lista(
        db, "i3", _pagina_lista([_item_jsonld()]),
        {URL_ITEM: _pagina_item(com_preco=False)})
    p = res["produtos"][0]
    assert p["link_veredito"] == "verificado"
    assert p["preco"] == PRECO_LISTA and p["preco_confirmado"] is True
    assert shopping._tier(p) == "confirmada"


# ── Preservação: bloqueio e página errada nunca promovem ──────────────

def test_pagina_do_item_bloqueada_preserva_parcial_sem_contorno():
    db = _db()
    res, chamadas = _pesquisar_com_lista(db, "i4", _pagina_lista([_item_jsonld()]))
    assert URL_ITEM in chamadas  # tentou abrir
    p = res["produtos"][0]
    # Card intacto: continua parcial, com o motivo original.
    assert p["link_veredito"] == "nao_verificado"
    assert p["link_codigo"] == "item_nao_aberto"
    assert p["item_de_listagem"] is False
    assert "não foi aberta" in p["link_motivo"]
    assert p["preco"] == PRECO_LISTA and p["preco_confirmado"] is True
    assert shopping._tier(p) == "parcial"


def test_pagina_do_item_de_outro_produto_nao_promove():
    db = _db()
    res, _ = _pesquisar_com_lista(
        db, "i5", _pagina_lista([_item_jsonld()]),
        {URL_ITEM: _pagina_item(nome="Panela Elétrica 5L", preco=199.90)})
    p = res["produtos"][0]
    assert p["link_veredito"] == "nao_verificado"
    assert p["link_codigo"] == "item_nao_aberto"
    assert p["preco"] == PRECO_LISTA  # dados de outra página nunca adotados
    assert shopping._tier(p) == "parcial"


def test_orcamento_de_validacoes_item_e_respeitado(monkeypatch):
    """Só MAX_VALIDACOES_ITEM páginas de item por consulta; o excedente
    preserva o card parcial (nunca abre além do orçamento)."""
    monkeypatch.setattr(shopping, "MAX_VALIDACOES_ITEM", 1)
    db = _db()
    itens = [_item_jsonld(nome=NOME, url_item=URL_ITEM),
             _item_jsonld(nome="Notebook Beta 16GB", url_item=URL_ITEM2)]
    res, chamadas = _pesquisar_com_lista(db, "i6", _pagina_lista(itens))
    abertos = [u for u in chamadas if "/produto/" in u]
    assert abertos == [URL_ITEM]
    assert len(res["produtos"]) == 2
    assert res["produtos"][0]["link_veredito"] == "nao_verificado"
    assert res["produtos"][1]["link_veredito"] == "nao_verificado"


# ── Identidade: variante vem primeiro ─────────────────────────────────

def test_identidade_do_card_prioriza_variante():
    p = {"nome": "Fone Bluetooth JBL Tune 510BT", "modelo": "",
         "variante": "Preto"}
    termos = shopping._identidade_do_card(p)
    assert termos[0] == "preto"
    assert len(termos) == 3 and "bluetooth" in termos


def test_identidade_do_card_ordem_deterministica():
    p = {"nome": NOME, "modelo": "", "variante": ""}
    assert shopping._identidade_do_card(p) == ["notebook", "alpha", "12gb"]


# ── JDUI: payload da oferta confirmada + render no espelho do frontend ─

HARNESS = r"""
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
const t = (name, cond) => {
  if (!cond) { console.error('FAIL ' + name); process.exitCode = 1; }
  else console.log('ok ' + name);
};
const msg = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
const v = JDUI.validateMessage(msg);
t('payload-valido', v.ok === true);
t('payload-oferta-confirmada',
  v.msg.blocks[0].props.produto.link_veredito === 'verificado' &&
  v.msg.blocks[0].props.produto.item_de_listagem === false &&
  v.msg.blocks[0].props.produto.link_motivo.indexOf('produto confirmado') >= 0);
const root = new Element('main');
JDUI.mount(root, [msg], {});
t('render-link-verificado', root.textContent.includes('Link verificado'));
t('render-sem-selo-listagem', !root.textContent.includes('Link de listagem'));
"""


def test_fence_de_oferta_confirmada_renderiza_link_verificado_no_node():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node indisponível")
    db = _db()
    res, _ = _pesquisar_com_lista(
        db, "i7", _pagina_lista([_item_jsonld()]),
        {URL_ITEM: _pagina_item()})
    fence = shopping.fence_resultado(res)
    assert "```jdui" in fence
    msg = json.loads(fence.split("```jdui", 1)[1].rsplit("```", 1)[0])
    with tempfile.TemporaryDirectory() as tmp:
        harness = Path(tmp) / "harness_item_v57.cjs"
        harness.write_text(HARNESS, encoding="utf-8")
        payload = Path(tmp) / "payload.json"
        payload.write_text(json.dumps(msg, ensure_ascii=False), encoding="utf-8")
        raiz = Path(__file__).resolve().parents[1]
        r = subprocess.run(
            [node, str(harness), str(raiz / "public" / "jdui.js"), str(payload)],
            capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, "STDOUT:\n" + r.stdout + "\nSTDERR:\n" + r.stderr
    assert "FAIL" not in r.stdout
