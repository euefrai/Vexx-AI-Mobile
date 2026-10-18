"""V5.7 FASE 3 — origem declarada no card de fontes da JDUI.

Paridade backend (`jdui.py`) × espelho frontend (`public/jdui.js`): campo
opcional `origem_declarada` (declarado pela página, nunca verificado) com o
mesmo teto de 120; render no cartão de fontes como "original declarado: X".
Fluxo real: fonte da pesquisa → evidência → fence de fontes.
"""
import json
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import jdui
import pc_agent
import research_agents as ra


def _db(nome="jdui_fontes_v57.sqlite3"):
    return pc_agent.open_db(Path(tempfile.mkdtemp()) / nome)


def _bloco(props):
    return {"version": jdui.VERSION,
            "blocks": [{"type": "ui", "component": "sources", "props": props}]}


ITEM = {"titulo": "Nota republicada", "url": "https://agregador.example/n1",
        "dominio": "agregador.example", "data": "2026-10-18",
        "trecho": "trecho", "status": "aberta",
        "origem_declarada": "original.example"}


def test_schema_aceita_origem_declarada_e_limita():
    ok, norm, errs = jdui.validar_mensagem(_bloco({"items": [ITEM]}))
    assert ok, errs
    assert norm["blocks"][0]["props"]["items"][0]["origem_declarada"] == "original.example"

    ok, norm, _ = jdui.validar_mensagem(_bloco(
        {"items": [dict(ITEM, origem_declarada="o" * 300)]}))
    assert ok
    assert len(norm["blocks"][0]["props"]["items"][0]["origem_declarada"]) == 120

    ok, norm, _ = jdui.validar_mensagem(_bloco(
        {"items": [{"titulo": "Sem marca", "url": "https://x.example/a"}]}))
    assert ok
    assert norm["blocks"][0]["props"]["items"][0]["origem_declarada"] == ""


def test_fonte_com_origem_declarada_chega_ao_fence():
    db = _db()
    job = ra.criar_job(db, "u-x", "nota republicada")
    f = {"id": "S1", "url": "https://agregador.example/n1", "titulo": "Nota",
         "dominio": "agregador.example", "acessado_em": "2026-10-18",
         "origem_declarada": "original.example"}
    ra.registrar_evidencia(db, job, f, "trecho lido da página")
    fence = pc_agent.fence_de_fontes(db, "u-x")
    corpo = json.loads(fence.split("```jdui", 1)[1].rsplit("```", 1)[0])
    item = corpo["blocks"][0]["props"]["items"][0]
    assert item["origem_declarada"] == "original.example"
    assert item["dominio"] == "agregador.example"
    db.close()


def test_fonte_sem_marca_nao_quebra_fence():
    db = _db()
    job = ra.criar_job(db, "u-x", "sem marca")
    f = {"id": "S1", "url": "https://x.example/a", "titulo": "T",
         "dominio": "x.example", "acessado_em": "2026-10-18"}
    ra.registrar_evidencia(db, job, f, "trecho")
    fence = pc_agent.fence_de_fontes(db, "u-x")
    corpo = json.loads(fence.split("```jdui", 1)[1].rsplit("```", 1)[0])
    assert corpo["blocks"][0]["props"]["items"][0]["origem_declarada"] == ""
    db.close()


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
const V = 'JULIA-ui-message/v1';
const item = { titulo: 'Nota republicada', url: 'https://agregador.example/n1',
  dominio: 'agregador.example', data: '2026-10-18', trecho: 'trecho',
  status: 'aberta', origem_declarada: 'original.example' };
const v = JDUI.validateMessage({ version: V, blocks: [
  { type: 'ui', component: 'sources', props: { items: [item] } }] });
t('schema-origem', v.ok === true &&
  v.msg.blocks[0].props.items[0].origem_declarada === 'original.example');
const longo = Object.assign({}, item, { origem_declarada: 'o'.repeat(300) });
const v2 = JDUI.validateMessage({ version: V, blocks: [
  { type: 'ui', component: 'sources', props: { items: [longo] } }] });
t('schema-origem-limite', v2.ok === true &&
  v2.msg.blocks[0].props.items[0].origem_declarada.length === 120);
const root = new Element('main');
JDUI.mount(root, [{ blocks: [{ type: 'ui', component: 'sources',
  props: { items: [item] } }] }], {});
t('card-origem', root.textContent.includes('original declarado: original.example'));
const sem = Object.assign({}, item);
delete sem.origem_declarada;
const root2 = new Element('main');
JDUI.mount(root2, [{ blocks: [{ type: 'ui', component: 'sources',
  props: { items: [sem] } }] }], {});
t('card-sem-origem', !root2.textContent.includes('original declarado'));
"""


def test_jdui_js_render_origem_no_node():
    import shutil as _sh
    import subprocess as _sp
    node = _sh.which("node")
    if node is None:
        pytest.skip("Node indisponível")
    with tempfile.TemporaryDirectory() as tmp:
        harness = Path(tmp) / "harness_fontes_v57.cjs"
        harness.write_text(HARNESS, encoding="utf-8")
        raiz = Path(__file__).resolve().parents[1]
        r = _sp.run([node, str(harness), str(raiz / "public" / "jdui.js")],
                    capture_output=True, text=True, timeout=60)
        assert r.returncode == 0, "STDOUT:\n" + r.stdout + "\nSTDERR:\n" + r.stderr
        assert "FAIL" not in r.stdout
