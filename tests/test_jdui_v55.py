"""V5.5 JDUI: selo de verificação do link nos cards de produto.

Backend (`jdui.py`) × espelho frontend (`public/jdui.js`): mesmos campos,
mesmos limites; render com selo honesto (verificado/parcial/reprovado/não
verificado/listagem) e links longos sem estourar layout.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import jdui
import shopping


def _bloco(comp, props):
    return {"version": jdui.VERSION,
            "blocks": [{"type": "ui", "component": comp, "props": props}]}


PROD = {"nome": "Notebook X 16GB", "preco": "R$ 4.299,00", "preco_valor": 4299.0,
        "loja": "loja.com", "url": "https://loja.com/produto/x",
        "link_veredito": "verificado", "link_motivo": "página do item abriu (http 200)",
        "item_de_listagem": False, "imagem_veredito": "verificado"}


# ── Backend: normalização dos campos de verificação ──────────────────

def test_oferta_verificacao_normalizada():
    ok, norm, errs = jdui.validar_mensagem(_bloco("productcard", {"produto": PROD}))
    assert ok, errs
    p = norm["blocks"][0]["props"]["produto"]
    assert p["link_veredito"] == "verificado"
    assert p["imagem_veredito"] == "verificado"
    assert p["item_de_listagem"] is False
    assert "página do item" in p["link_motivo"]


def test_oferta_veredito_invalido_vira_vazio():
    ok, norm, _ = jdui.validar_mensagem(_bloco(
        "productcard", {"produto": {**PROD, "link_veredito": "confiavel",
                                    "imagem_veredito": "talvez"}}))
    assert ok
    p = norm["blocks"][0]["props"]["produto"]
    assert p["link_veredito"] == "" and p["imagem_veredito"] == ""


def test_oferta_listagem_e_limite_do_motivo():
    ok, norm, _ = jdui.validar_mensagem(_bloco(
        "productcard", {"produto": {**PROD, "item_de_listagem": 1,
                                    "link_motivo": "m" * 300}}))
    assert ok
    p = norm["blocks"][0]["props"]["produto"]
    assert p["item_de_listagem"] is True
    assert len(p["link_motivo"]) == 120


def test_fence_resultado_leva_selo_ao_card():
    p = {"nome": "Notebook X", "preco": 4299.0, "preco_texto": "R$ 4.299,00",
         "moeda": "BRL", "loja": "loja.com", "url_item": "https://loja.com/produto/x",
         "specs": {}, "verificado_em": "2026-10-16T12:00:00+00:00",
         "link_veredito": "nao_verificado",
         "link_motivo": "link do item veio de listagem (página do item NÃO aberta)",
         "item_de_listagem": True, "imagem_veredito": ""}
    fence = shopping.fence_resultado({"produtos": [p], "fontes": []})
    corpo = json.loads(fence.split("```jdui", 1)[1].rsplit("```", 1)[0])
    prod = corpo["blocks"][0]["props"]["produto"]
    assert prod["link_veredito"] == "nao_verificado"
    assert prod["item_de_listagem"] is True
    assert "listagem" in prod["link_motivo"]
    ok, _, _ = jdui.validar_mensagem(corpo)
    assert ok


# ── Harness Node: validação + render do selo ─────────────────────────

HARNESS_V55 = r"""
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
const V = 'JULIA-ui-message/v1';
function mount(component, props) {
  const root = new Element('main');
  JDUI.mount(root, [{ blocks: [{ type: 'ui', component, props }] }], {});
  return root;
}
function walk(e, pred) {
  if (pred(e)) return e;
  for (const c of (e.children || [])) { const f = walk(c, pred); if (f) return f; }
  return null;
}
const P = { nome: 'Notebook X 16GB', preco: 'R$ 4.299,00', preco_valor: 4299,
  loja: 'loja.com', url: 'https://loja.com/produto/x', specs: {},
  link_veredito: 'verificado', link_motivo: 'página do item abriu (http 200)',
  item_de_listagem: false };
const v = JDUI.validateMessage({ version: V, blocks: [
  { type: 'ui', component: 'productcard', props: { produto: P } }] });
t('valida-selo', v.ok === true && v.msg.blocks[0].props.produto.link_veredito === 'verificado');
const ruim = JDUI.validateMessage({ version: V, blocks: [
  { type: 'ui', component: 'productcard',
    props: { produto: Object.assign({}, P, { link_veredito: 'sempre_confiavel' }) } }] });
t('veredito-invalido-limpo', ruim.ok === true &&
  ruim.msg.blocks[0].props.produto.link_veredito === '');
const card = mount('productcard', { produto: P });
t('card-selo-ok', card.textContent.includes('Link verificado'));
const path = 'https://loja.com/produto/' + 'x'.repeat(220) + '?ref=busca';
const longo = mount('productcard', { produto: Object.assign({}, P, { url: path }) });
const cta = walk(longo, e => e.tag === 'a');
t('card-link-longo', !!cta && cta.href.slice(0, 15) === 'https://loja.co');
const reprov = mount('productcard', { produto: Object.assign({}, P,
  { link_veredito: 'reprovado', link_motivo: 'http 404' }) });
t('card-selo-reprovado', reprov.textContent.includes('Link reprovado'));
const cta2 = walk(reprov, e => e.tag === 'a');
t('card-cta-neutro', !!cta2 && cta2.textContent.includes('Abrir link'));
const listagem = mount('productcard', { produto: Object.assign({}, P,
  { item_de_listagem: true, link_veredito: 'nao_verificado' }) });
t('card-selo-listagem', listagem.textContent.includes('Link de listagem'));
const seloEl = walk(listagem, e => (e.className || '').indexOf('jdui-pver') >= 0);
t('card-selo-titulo', !!seloEl && !!seloEl.attrs.title);
const legado = mount('productcard', { produto: { nome: 'N', preco: 'R$ 1,00' } });
t('card-legado-sem-selo', !walk(legado, e => (e.className || '').indexOf('jdui-pver') >= 0));
"""


def test_jdui_v55_selo_no_node():
    import shutil as _sh
    import subprocess as _sp
    node = _sh.which("node")
    if node is None:
        pytest.skip("Node indisponível")
    import tempfile as _tf
    with _tf.TemporaryDirectory() as tmp:
        harness = Path(tmp) / "harness_v55.cjs"
        harness.write_text(HARNESS_V55, encoding="utf-8")
        raiz = Path(__file__).resolve().parents[1]
        r = _sp.run([node, str(harness), str(raiz / "public" / "jdui.js")],
                    capture_output=True, text=True, timeout=60)
        assert r.returncode == 0, "STDOUT:\n" + r.stdout + "\nSTDERR:\n" + r.stderr
        assert "FAIL" not in r.stdout
