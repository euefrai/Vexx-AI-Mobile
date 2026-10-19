"""V5.7 FINAL — paridade backend (jdui.py) × espelho frontend (public/jdui.js)
no productcard: fallback de preço (`preco` numérico sem `preco_valor`),
coerção de `item_de_listagem` (igual a bool() do backend) e tipo de `specs`
(lista não vazia/string/true falham; lista vazia/falsy viram {}).

Mesmo contrato nos dois lados: o que o backend aceita o frontend aceita; o
que o backend recusa o frontend recusa.
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import jdui

RAIZ = Path(__file__).resolve().parents[1]

_HARNESS = r"""
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
"""

_CORPO = r"""
const v1 = JDUI.validateMessage(prod({ nome: 'Fone X', preco: 299.9 }));
t('preco-fallback', v1.ok === true &&
  v1.msg.blocks[0].props.produto.preco_valor === 299.9);
const casos = [[1, true], [0, false], ['sim', true], ['', false],
               [true, true], [false, false]];
casos.forEach(([entrada, esperado]) => {
  const v = JDUI.validateMessage(prod({ nome: 'P', item_de_listagem: entrada }));
  t('lista-' + JSON.stringify(entrada), v.ok === true &&
    v.msg.blocks[0].props.produto.item_de_listagem === esperado);
});
const r1 = JDUI.validateMessage(prod({ nome: 'P', specs: [1, 2] }));
t('specs-lista-falha', r1.ok === false);
const r2 = JDUI.validateMessage(prod({ nome: 'P', specs: [] }));
t('specs-lista-vazia-ok', r2.ok === true &&
  Object.keys(r2.msg.blocks[0].props.produto.specs).length === 0);
const r3 = JDUI.validateMessage(prod({ nome: 'P', specs: 'x' }));
t('specs-string-falha', r3.ok === false);
const r4 = JDUI.validateMessage(prod({ nome: 'P', specs: { mem: '8GB' } }));
t('specs-objeto-ok', r4.ok === true &&
  r4.msg.blocks[0].props.produto.specs.mem === '8GB');
"""


def _node():
    node = shutil.which("node")
    if node is None:
        cand = Path(r"C:\Users\efrai\AppData\Local\hermes\node\node.exe")
        node = str(cand) if cand.exists() else None
    return node


def test_js_paridade_produto():
    node = _node()
    if node is None:
        pytest.skip("node indisponível")
    with tempfile.TemporaryDirectory() as tmp:
        arq = Path(tmp) / "harness.cjs"
        arq.write_text(_HARNESS + _CORPO, encoding="utf-8")
        r = subprocess.run([node, str(arq), str(RAIZ / "public" / "jdui.js")],
                           capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, (r.stdout or "") + (r.stderr or "")
    assert "FAIL" not in r.stdout, (r.stdout or "") + (r.stderr or "")


def _prod(props):
    return {"version": jdui.VERSION,
            "blocks": [{"type": "ui", "component": "productcard",
                        "props": {"produto": props}}]}


def test_python_preco_fallback():
    ok, norm, _ = jdui.validar_mensagem(_prod({"nome": "P", "preco": 299.9}))
    assert ok and norm["blocks"][0]["props"]["produto"]["preco_valor"] == 299.9


def test_python_item_de_listagem_coercao():
    casos = [(1, True), (0, False), ("sim", True), ("", False),
             (True, True), (False, False)]
    for entrada, esperado in casos:
        ok, norm, _ = jdui.validar_mensagem(
            _prod({"nome": "P", "item_de_listagem": entrada}))
        assert ok, entrada
        assert norm["blocks"][0]["props"]["produto"]["item_de_listagem"] is esperado, entrada


def test_python_specs_tipo():
    ok, _, _ = jdui.validar_mensagem(_prod({"nome": "P", "specs": [1, 2]}))
    assert not ok
    ok, norm, _ = jdui.validar_mensagem(_prod({"nome": "P", "specs": []}))
    assert ok and norm["blocks"][0]["props"]["produto"]["specs"] == {}
    ok, _, _ = jdui.validar_mensagem(_prod({"nome": "P", "specs": "x"}))
    assert not ok
    ok, norm, _ = jdui.validar_mensagem(_prod({"nome": "P", "specs": {"mem": "8GB"}}))
    assert ok and norm["blocks"][0]["props"]["produto"]["specs"] == {"mem": "8GB"}
