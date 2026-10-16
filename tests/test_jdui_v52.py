"""V5.2 Advanced Visual JDUI: sources/video/roadmap, tabela (CSV/página),
transformações determinísticas."""
import json
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import jdui
import pc_agent


def _db(nome="jdui52.sqlite3"):
    return pc_agent.open_db(Path(tempfile.mkdtemp()) / nome)


def _bloco(comp, props):
    return {"version": jdui.VERSION,
            "blocks": [{"type": "ui", "component": comp, "props": props}]}


# ── Validadores backend ───────────────────────────────────────────────

def test_sources_ok_e_limites():
    item = {"titulo": "Artigo", "url": "https://exemplo.com/a",
            "dominio": "exemplo.com", "data": "2026-10-16",
            "trecho": "trecho", "status": "utilizada"}
    ok, norm, errs = jdui.validar_mensagem(_bloco("sources", {"items": [item]}))
    assert ok, errs
    assert norm["blocks"][0]["props"]["items"][0]["status"] == "utilizada"
    ok, _, _ = jdui.validar_mensagem(_bloco("sources", {"items": []}))
    assert not ok
    ruim = dict(item, status="mentira")
    ok, norm, _ = jdui.validar_mensagem(_bloco("sources", {"items": [ruim]}))
    assert ok and norm["blocks"][0]["props"]["items"][0]["status"] == "encontrada"


def test_video_allowlist():
    ok, _, errs = jdui.validar_mensagem(
        _bloco("video", {"titulo": "V", "url": "https://www.youtube.com/watch?v=abc"}))
    assert ok, errs
    ok, _, _ = jdui.validar_mensagem(
        _bloco("video", {"url": "https://youtu.be/abc"}))
    assert ok
    for ruim in ("https://evil.com/v.mp4", "javascript:alert(1)",
                 "https://youtube.com.evil.com/x", ""):
        ok, _, _ = jdui.validar_mensagem(_bloco("video", {"url": ruim}))
        assert not ok, ruim


def test_roadmap_ok_e_limites():
    stages = [{"id": "s1", "title": "Base", "status": "done"},
              {"id": "s2", "title": "Topo", "status": "doing", "marco": True}]
    ok, norm, errs = jdui.validar_mensagem(_bloco("roadmap", {"title": "R", "stages": stages}))
    assert ok, errs
    assert norm["blocks"][0]["props"]["stages"][1]["marco"] is True
    ok, _, _ = jdui.validar_mensagem(_bloco("roadmap", {"stages": [{"id": "s1"}]}))
    assert not ok
    ok, _, _ = jdui.validar_mensagem(
        _bloco("roadmap", {"stages": [{"id": "s1", "title": "T", "status": "voando"}]}))
    assert ok  # status desconhecido cai para todo


def test_num_celula():
    assert pc_agent._num_celula("R$ 1.234,56") == 1234.56
    assert pc_agent._num_celula("12%") == 12.0
    assert pc_agent._num_celula("1,234.5") == 1234.5
    assert pc_agent._num_celula("abc") is None
    assert pc_agent._num_celula("") is None
    assert pc_agent._num_celula("2026-10-16") is None


# ── Transformações determinísticas ────────────────────────────────────

def _guarda_tabela(db, owner, conv, mid, columns, rows):
    fence = {"version": jdui.VERSION, "blocks": [
        {"type": "ui", "component": "table",
         "props": {"title": "Vendas", "columns": columns, "rows": rows}}]}
    ok, _, _ = jdui.validar_mensagem(fence)
    assert ok
    texto = "segue\n\n```jdui\n" + json.dumps(fence, ensure_ascii=False) + "\n```"
    pc_agent.persist_messages(db, [{
        "id": mid, "conversation_id": conv, "origin": "mobile",
        "role": "assistant", "text": texto, "created_at": pc_agent.agora_iso()}], owner)


def test_tabela_para_grafico():
    db = _db()
    _guarda_tabela(db, "ana", "conv1", "msg-tab-01", ["Mês", "Vendas"],
                   [["jan", "10"], ["fev", "20"], ["mar", "15"]])
    fence = pc_agent.fence_tabela_para_grafico(db, "ana", "conv1")
    assert "```jdui" in fence and '"component": "chart"' in fence
    corpo = fence.split("```jdui", 1)[1].rsplit("```", 1)[0]
    ok, norm, errs = jdui.validar_mensagem(json.loads(corpo))
    assert ok, errs
    assert norm["blocks"][0]["props"]["series"][0]["values"] == [10.0, 20.0, 15.0]
    assert pc_agent.fence_tabela_para_grafico(db, "ana", "conv1") == fence  # determinístico
    assert "Não encontrei tabela" in pc_agent.fence_tabela_para_grafico(db, "ana", "outra")


def test_tabela_sem_numeros_honesta():
    db = _db()
    _guarda_tabela(db, "ana", "conv1", "msg-tab-02", ["Nome", "Cor"],
                   [["a", "azul"], ["b", "verde"]])
    fence = pc_agent.fence_tabela_para_grafico(db, "ana", "conv1")
    assert "```jdui" not in fence and "inventar" in fence


def test_fence_de_fontes_sem_job_vazio():
    assert pc_agent.fence_de_fontes(_db(), "ninguem") == ""


def test_transformacao_visual_sem_dados():
    db = _db()
    out = pc_agent.fence_transformacao_visual(db, "ana", "conv1", "transforme em tabela")
    assert "Ainda não há pesquisa" in out


# ── Harness Node ──────────────────────────────────────────────────────

HARNESS_V52 = r"""
const fs = require('fs');
class Element {
  constructor(tag) { this.tag = tag; this.children = []; this.events = {}; this.style = {}; this.attrs = {}; this.dataset = {}; this._text = ''; this.classList = { toggle: () => {}, add: () => {}, remove: () => {}, contains: () => false }; }
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
function mount(component, props, ctx) {
  const root = new Element('main');
  JDUI.mount(root, [{ blocks: [{ type: 'ui', component, props }] }], ctx || {});
  return root;
}
function walk(e, pred) {
  if (pred(e)) return e;
  for (const c of (e.children || [])) { const f = walk(c, pred); if (f) return f; }
  return null;
}
t('sources-valido', JDUI.validateMessage({ version: V, blocks: [{ type: 'ui', component: 'sources',
  props: { items: [{ titulo: 'A', url: 'https://exemplo.com/a', status: 'utilizada' }] } }] }).ok === true);
t('sources-teto', JDUI.validateMessage({ version: V, blocks: [{ type: 'ui', component: 'sources',
  props: { items: Array.from({ length: 11 }, (_, i) => ({ titulo: 'T' + i })) } }] }).ok === false);
t('video-youtube', JDUI.validateMessage({ version: V, blocks: [{ type: 'ui', component: 'video',
  props: { url: 'https://www.youtube.com/watch?v=abc' } }] }).ok === true);
t('video-bloqueado', JDUI.validateMessage({ version: V, blocks: [{ type: 'ui', component: 'video',
  props: { url: 'https://evil.com/v.mp4' } }] }).ok === false);
t('roadmap-valido', JDUI.validateMessage({ version: V, blocks: [{ type: 'ui', component: 'roadmap',
  props: { stages: [{ id: 's1', title: 'A', status: 'done' }, { id: 's2', title: 'B' }] } }] }).ok === true);
const src = mount('sources', { title: 'F', items: [
  { titulo: 'Artigo', url: 'https://exemplo.com/a', dominio: 'exemplo.com', status: 'utilizada' }] });
t('sources-render', src.textContent.includes('Artigo') && src.textContent.includes('Utilizada'));
const vid = mount('video', { titulo: 'V', url: 'https://youtu.be/abc', duracao: '10:00' });
t('video-render', vid.textContent.includes('Assistir'));
const rm = mount('roadmap', { title: 'R', stages: [
  { id: 's1', title: 'Base', status: 'done' }, { id: 's2', title: 'Topo', status: 'todo', desc: 'det' }] });
t('roadmap-progresso', rm.textContent.includes('50%'));
const rows13 = Array.from({ length: 13 }, (_, i) => ['L' + i, String(i)]);
const tab = mount('table', { title: 'T', columns: ['A', 'B'], rows: rows13 });
t('table-paginacao', tab.textContent.includes('Página 1 de 2'));
t('table-filtro', tab.textContent.includes('Filtrar') || JSON.stringify(tab).includes('Filtrar'));
let csv = null;
const tab2 = mount('table', { title: 'T', columns: ['A'], rows: [['x']] },
  { download: (n, m, c) => { csv = c; } });
const btn = walk(tab2, e => e.tag === 'button' && (e.textContent || '').includes('CSV'));
t('table-csv-btn', !!btn);
if (btn) btn.events.click();
t('table-csv-dados', typeof csv === 'string' && csv.includes('x'));
"""


def test_jdui_v52_no_node():
    import shutil as _sh
    import subprocess as _sp
    node = _sh.which("node")
    if node is None:
        pytest.skip("Node indisponível")
    import tempfile as _tf
    with _tf.TemporaryDirectory() as tmp:
        harness = Path(tmp) / "harness_v52.cjs"
        harness.write_text(HARNESS_V52, encoding="utf-8")
        raiz = Path(__file__).resolve().parents[1]
        r = _sp.run([node, str(harness), str(raiz / "public" / "jdui.js")],
                     capture_output=True, text=True, timeout=60)
        assert r.returncode == 0, "STDOUT:\n" + r.stdout + "\nSTDERR:\n" + r.stderr
        assert "FAIL" not in r.stdout
