"""V5.7.2 — JDUI: renderização real do card e da fonte declarada.

Cobre as pendências de exibição: a imagem extraída aparece no card com o
selo honesto de verificação (parcial/não verificada nunca viram "ok") e a
fonte cuja origem foi DECLARADA pela página mostra "original declarado",
sem ganhar status de verificada.
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
  constructor(tag) { this.tag = tag; this.children = []; this.events = {}; this.style = {}; this.attrs = {}; this.dataset = {}; this._text = ''; this.className = ''; this.parentNode = null; this.classList = { toggle: () => {}, add: () => {}, remove: () => {}, contains: () => false }; }
  appendChild(child) { child.parentNode = this; this.children.push(child); return child; }
  append(...children) { children.forEach(c => this.appendChild(c)); }
  replaceChildren(...children) { this.children = []; this._text = ''; this.append(...children); }
  replaceChild(novo, antigo) { const i = this.children.indexOf(antigo); if (i >= 0) this.children[i] = novo; return antigo; }
  removeChild(alvo) { const i = this.children.indexOf(alvo); if (i >= 0) this.children.splice(i, 1); return alvo; }
  addEventListener(name, fn) { (this.events[name] = this.events[name] || []).push(fn); }
  setAttribute(name, value) { this.attrs[name] = value; }
  querySelectorAll() { return []; }
  querySelector() { return null; }
  get textContent() { return this._text + this.children.map(c => c.textContent || '').join(''); }
  set textContent(value) { this._text = String(value); this.children = []; }
}
global.document = { createElement: tag => new Element(tag),
  createElementNS: (ns, tag) => new Element(tag),
  body: new Element('body'),
  createTextNode: t => { const e = new Element('#text'); e.textContent = t; return e; } };
global.location = { href: 'https://app.example.test/' };
global.window = {};
eval(fs.readFileSync(process.argv[2], 'utf8'));
const JDUI = global.window.JDUI;
const V = 'JULIA-ui-message/v1';
const find = (node, pred) => { if (pred(node)) return node;
  for (const c of (node.children || [])) { const r = find(c, pred); if (r) return r; } return null; };
const t = (name, cond) => {
  if (!cond) { console.error('FAIL ' + name); process.exitCode = 1; }
  else console.log('ok ' + name);
};
"""

_CORPO = r"""
// 1) productcard com imagem e vereditos honestos
const card = { version: V, blocks: [{ type: 'ui', component: 'productcard', props: { produto: {
  nome: 'Fone X', preco: 'R$ 1.299,00', preco_valor: 1299,
  imagem: 'https://cdn.example/f.jpg', imagem_veredito: 'nao_verificado',
  link_veredito: 'parcial', loja: 'loja.test' } } }] };
const v1 = JDUI.validateMessage(card);
t('card-valida', v1.ok === true);
const root1 = new Element('div');
JDUI.mount(root1, [v1.msg]);
const txt1 = root1.textContent;
t('card-mostra-preco', txt1.indexOf('R$ 1.299,00') >= 0);
t('card-selo-imagem', txt1.indexOf('Imagem não verificada') >= 0);
t('card-selo-link', txt1.indexOf('Verificação parcial') >= 0);
const img = find(root1, n => n.tag === 'img');
t('card-imagem-src', !!img && img.src === 'https://cdn.example/f.jpg');

// 2) sem imagem confirmada: placeholder, nunca foto inventada
const card2 = { version: V, blocks: [{ type: 'ui', component: 'productcard', props: { produto: {
  nome: 'Fone Y', preco: 'R$ 99,00', preco_valor: 99 } } }] };
const v2 = JDUI.validateMessage(card2);
const root2 = new Element('div');
JDUI.mount(root2, [v2.msg]);
t('card-sem-foto-placeholder', root2.textContent.indexOf('Sem foto') >= 0);

// 3) sources: origem declarada pela página aparece como declarada
const src = { version: V, blocks: [{ type: 'ui', component: 'sources', props: {
  title: 'Fontes', items: [{ titulo: 'Manual', url: 'https://x.example/a',
  dominio: 'x.example', trecho: 'trecho real', status: 'encontrada',
  origem_declarada: 'Manual do fabricante' }] } }] };
const v3 = JDUI.validateMessage(src);
t('sources-valida', v3.ok === true);
const root3 = new Element('div');
JDUI.mount(root3, [v3.msg]);
t('sources-origem-declarada',
  root3.textContent.indexOf('original declarado: Manual do fabricante') >= 0);
t('sources-status-encontrada', root3.textContent.indexOf('Encontrada') >= 0);
"""


def _node():
    node = shutil.which("node")
    if node is None:
        cand = Path(r"C:\Users\efrai\AppData\Local\hermes\node\node.exe")
        node = str(cand) if cand.exists() else None
    return node


def test_js_render_card_e_fonte_declarada():
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


def test_python_sources_preserva_origem_declarada():
    msg = {"version": jdui.VERSION, "blocks": [
        {"type": "ui", "component": "sources", "props": {
            "title": "Fontes",
            "items": [{"titulo": "Manual", "url": "https://x.example/a",
                       "dominio": "x.example", "trecho": "trecho real",
                       "status": "encontrada",
                       "origem_declarada": "Manual do fabricante"}]}}]}
    ok, norm, erros = jdui.validar_mensagem(msg)
    assert ok, erros
    item = norm["blocks"][0]["props"]["items"][0]
    assert item["origem_declarada"] == "Manual do fabricante"
    assert item["status"] == "encontrada"  # declarada nunca vira "verificada"
