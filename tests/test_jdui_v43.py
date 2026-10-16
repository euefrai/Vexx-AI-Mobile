"""V4.3 Advanced JDUI: chart/dashboard/compare/conversor/update_of + evolução real."""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import jdui
import learning
import pc_agent

NODE = shutil.which("node")
RAIZ = Path(__file__).resolve().parents[1]
BASE = {"version": "JULIA-ui-message/v1", "blocks": []}
CHART = {"type": "bar", "title": "Notas", "labels": ["P1", "P2"],
         "series": [{"label": "nota %", "values": [70, 90]}],
         "source": "seu histórico"}


def _bloco(comp, props, update_of=None):
    b = {"type": "ui", "component": comp, "props": props}
    msg = dict(BASE, blocks=[b])
    if update_of:
        msg["update_of"] = update_of
    return msg


def test_chart_valido_e_abusos():
    ok, norm, _ = jdui.validar_mensagem(_bloco("chart", CHART))
    assert ok and norm["blocks"][0]["props"]["series"][0]["values"] == [70.0, 90.0]
    for ruim in (dict(CHART, type="3d"),
                 dict(CHART, series=[{"label": "x", "values": []}]),
                 dict(CHART, series=[{"label": "x", "values": list(range(25))}]),
                 dict(CHART, labels=["só-um"]),
                 dict(CHART, series=[{"label": "x", "values": [float("nan")]}]),
                 dict(CHART, series=[{"label": "x", "values": [float("inf")]}]),
                 dict(CHART, series=[{"label": "x", "values": [1e13]}])):
        assert jdui.validar_mensagem(_bloco("chart", ruim))[0] is False, ruim
    pie2 = dict(CHART, type="pie", series=[{"label": "a", "values": [1]},
                                           {"label": "b", "values": [2]}])
    assert jdui.validar_mensagem(_bloco("chart", pie2))[0] is False
    pie = {"type": "pie", "series": [{"label": "s", "values": [30, 70]}],
           "labels": ["A", "B"]}
    assert jdui.validar_mensagem(_bloco("chart", pie))[0] is True
    scat = {"type": "scatter", "series": [{"label": "s", "values": [[1, 2], [3, 4]]}]}
    assert jdui.validar_mensagem(_bloco("chart", scat))[0] is True
    scat_ruim = {"type": "scatter", "series": [{"label": "s", "values": [[1, 2, 3]]}]}
    assert jdui.validar_mensagem(_bloco("chart", scat_ruim))[0] is False


def test_dashboard_compare_conversor():
    dash = {"title": "Painel", "metrics": [{"label": "Provas", "value": "3", "hint": "total"}],
            "chart": CHART, "source": "SQLite"}
    ok, norm, _ = jdui.validar_mensagem(_bloco("dashboard", dash))
    assert ok and norm["blocks"][0]["props"]["metrics"][0]["value"] == "3"
    dash4 = dict(dash, chart=dict(CHART, series=[{"label": str(i), "values": [i]} for i in range(4)]))
    assert jdui.validar_mensagem(_bloco("dashboard", dash4))[0] is False
    assert jdui.validar_mensagem(_bloco("dashboard", {"metrics": []}))[0] is False
    comp = {"title": "X vs Y", "columns": ["A", "B"],
            "rows": [{"label": "Preço", "a": "10", "b": "12", "melhor": "a"}]}
    ok, norm, _ = jdui.validar_mensagem(_bloco("compare", comp))
    assert ok and norm["blocks"][0]["props"]["rows"][0]["melhor"] == "a"
    assert jdui.validar_mensagem(
        _bloco("compare", dict(comp, columns=["só"])))[0] is False
    ok, norm, _ = jdui.validar_mensagem(_bloco("calculator", {"kind": "conversor"}))
    assert ok and norm["blocks"][0]["props"]["kind"] == "conversor"
    assert jdui.validar_mensagem(_bloco("calculator", {"kind": "nuclear"}))[0] is False


def test_jdui_preserva_proveniencia_de_graficos_e_comparacoes():
    source = {"id": "doc-1", "title": "Manual", "url": "https://example.test/manual",
              "locator": "p. 4, seção 2", "period": "2025",
              "methodology": "manual review"}
    ok, norm, _ = jdui.validar_mensagem(_bloco("chart", dict(CHART, sources=[source])))
    normalized_source = norm["blocks"][0]["props"]["sources"][0]
    assert ok and normalized_source["id"] == source["id"]
    assert normalized_source["period"] == "2025"
    assert normalized_source["methodology"] == "manual review"

    compare = {
        "columns": ["A", "B"],
        "rows": [{"label": "Recurso", "a": "presente", "b": "não localizado"}],
        "sources": [dict(source, url="javascript:alert(1)")],
    }
    ok, norm, _ = jdui.validar_mensagem(_bloco("compare", compare))
    assert ok and norm["blocks"][0]["props"]["sources"][0]["url"] == ""
    assert jdui.validar_mensagem(
        _bloco("chart", dict(CHART, sources=[source, dict(source)])))[0] is False
    for unsafe_url in ("javascript:alert(1)", "http://", "https://user:pass@example.test/"):
        compare = {
            "columns": ["A", "B"],
            "rows": [{"label": "Recurso", "a": "present", "b": "not found"}],
            "sources": [dict(source, url=unsafe_url)],
        }
        ok, norm, _ = jdui.validar_mensagem(_bloco("compare", compare))
        assert ok and norm["blocks"][0]["props"]["sources"][0]["url"] == ""


def test_update_of_permitido_e_imutavel():
    ok, norm, _ = jdui.validar_mensagem(_bloco("chart", CHART, update_of="msg-abc_123"))
    assert ok and norm.get("update_of") == "msg-abc_123"
    ok, norm, errs = jdui.validar_mensagem(_bloco("table", {"columns": ["A"], "rows": [["1"]]},
                                                 update_of="msg-1"))
    assert ok and norm.get("update_of") == "msg-1"  # tabela pode
    for comp, props in (("exam", {"assessment_id": "av-1"}),
                        ("quiz", {"title": "Q", "questions": [
                            {"q": "2+2?", "options": ["3", "4"], "answer": 1}]}),
                        ("studyprogress", {})):
        ok, norm, errs = jdui.validar_mensagem(_bloco(comp, props, update_of="msg-1"))
        assert ok and "update_of" not in norm  # imutável: patch descartado, bloco mantido
        assert any("imutável" in e for e in errs)
    ok, norm, errs = jdui.validar_mensagem(_bloco("chart", CHART, update_of="../../x"))
    assert ok and "update_of" not in norm  # id malicioso descartado


def test_grafico_evolucao_dados_reais(tmp_path):
    db = pc_agent.open_db(tmp_path / "evolucao.sqlite3")
    assert "concluídos" in pc_agent.sintetizar_grafico_evolucao(db, "u-x")  # honesto sem dados
    learning.criar_assessment(db, "u-x", "P1", "mat", [
        {"id": "q1", "enunciado": "Quanto é 2+2?", "tipo": "multipla",
         "opcoes": ["3", "4"], "gabarito": 1}], assessment_id="av-e")
    att = learning.iniciar_tentativa(db, "u-x", "av-e", "att-e")["id"]
    learning.responder(db, "u-x", att, "q1", "1")
    learning.finalizar_tentativa(db, "u-x", att)
    fence = pc_agent.sintetizar_grafico_evolucao(db, "u-x")
    assert '"component": "chart"' in fence and "100.0" in fence  # número real, não inventado
    assert pc_agent.intencao_grafico_evolucao("mostre a evolução dos meus simulados")
    assert pc_agent.intencao_grafico_evolucao("mostra um gráfico da minha evolução")
    assert not pc_agent.intencao_grafico_evolucao("cria uma prova de matemática")
    assert pc_agent.JULIAPresentationEngine.sugerir("mostre um gráfico de barras") == "chart"
    assert pc_agent.JULIAPresentationEngine.sugerir("compare em tabela A e B") == "compare"
    assert pc_agent.JULIAPresentationEngine.sugerir("quanto é em milhas?") == "calculator"
    assert pc_agent.JULIAPresentationEngine.sugerir("qual é a capital?") == ""
    db.close()


HARNESS_V43 = r"""
const fs = require('fs');
class Element {
  constructor(tag) { this.tag = tag; this.children = []; this.events = {}; this.style = {}; this.attrs = {}; this.dataset = {}; this._text = ''; }
  appendChild(child) { this.children.push(child); return child; }
  append(...children) { children.forEach(c => this.appendChild(c)); }
  replaceChildren(...children) { this.children = []; this._text = ''; this.append(...children); }
  addEventListener(name, fn) { this.events[name] = fn; }
  setAttribute(name, value) { this.attrs[name] = value; }
  insertBefore(child, ref) { const i = ref ? this.children.indexOf(ref) : -1; if (i < 0) this.children.push(child); else this.children.splice(i, 0, child); return child; }
  querySelectorAll() { return []; }
  querySelector() { return null; }
  get firstChild() { return this.children[0]; }
  get textContent() { return this._text + this.children.map(c => c.textContent || '').join(''); }
  set textContent(value) { this._text = String(value); this.children = []; }
}
global.document = {
  createElement: tag => new Element(tag),
  createElementNS: (ns, tag) => new Element(tag)
};
global.location = { href: 'https://app.example.test/' };
global.window = {};
eval(fs.readFileSync(process.argv[2], 'utf8'));
const JDUI = global.window.JDUI;
const t = (name, cond) => {
  if (!cond) { console.error('FAIL ' + name); process.exitCode = 1; }
  else console.log('ok ' + name);
};
const V = 'JULIA-ui-message/v1';
const chart = { version: V, blocks: [{ type: 'ui', component: 'chart', props: {
  type: 'bar', title: 'N', labels: ['A', 'B'], series: [{ label: 's', values: [1, 2] }], source: 't' } }] };
t('chart-valido', JDUI.validateMessage(chart).ok === true);
t('chart-proveniencia', JDUI.validateMessage({ version: V, blocks: [{ type: 'ui', component: 'chart',
  props: { type: 'bar', series: [{ label: 's', values: [1] }],
    sources: [{ id: 'doc-1', title: 'Manual', url: 'https://example.test/manual', locator: 'p. 4' }] } }] }).ok === true);
t('provenance-no-credentials', JDUI.validateMessage({ version: V, blocks: [{ type: 'ui', component: 'chart',
  props: { type: 'bar', series: [{ label: 's', values: [1] }],
    sources: [{ id: 'doc-2', title: 'Unsafe link', url: 'https://user:pass@example.test/' }] } }] })
  .msg.blocks[0].props.sources[0].url === '');
t('chart-nan', JDUI.validateMessage({ version: V, blocks: [{ type: 'ui', component: 'chart',
  props: { type: 'bar', series: [{ label: 's', values: [NaN] }] } }] }).ok === false);
t('chart-pie2', JDUI.validateMessage({ version: V, blocks: [{ type: 'ui', component: 'chart',
  props: { type: 'pie', series: [{ label: 'a', values: [1] }, { label: 'b', values: [2] }] } }] }).ok === false);
t('dashboard-valido', JDUI.validateMessage({ version: V, blocks: [{ type: 'ui', component: 'dashboard',
  props: { title: 'D', metrics: [{ label: 'M', value: '1' }], chart: chart.blocks[0].props } }] }).ok === true);
t('compare-valido', JDUI.validateMessage({ version: V, blocks: [{ type: 'ui', component: 'compare',
  props: { columns: ['A', 'B'], rows: [{ label: 'x', a: '1', b: '2', melhor: 'a' }] } }] }).ok === true);
t('conversor-kind', JDUI.validateMessage({ version: V, blocks: [{ type: 'ui', component: 'calculator',
  props: { kind: 'conversor' } }] }).ok === true);
const upd = JDUI.validateMessage({ version: V, update_of: 'msg-1', blocks: chart.blocks });
t('update-chart-ok', upd.ok === true && upd.msg.update_of === 'msg-1');
const updEx = JDUI.validateMessage({ version: V, update_of: 'msg-1', blocks: [
  { type: 'ui', component: 'exam', props: { assessment_id: 'av-1' } }] });
t('update-exam-bloqueado', updEx.ok === true && !updEx.msg.update_of);
t('conversao-km-mi', Math.abs(JDUI.OPS.conversao(10, 'km', 'mi').valor - 6.2137) < 0.001);
t('conversao-fora-catalogo', JDUI.OPS.conversao(1, 'km', 'kg') === null);
t('conversao-mesma', JDUI.OPS.conversao(5, 'kg', 'kg').valor === 5);
function mount(component, props) {
  const root = new Element('main');
  JDUI.mount(root, [{ blocks: [{ type: 'ui', component, props }] }], {});
  return root;
}
const provenanceRoot = mount('chart', { type: 'bar', series: [{ label: 's', values: [1] }],
  sources: [{ id: 'doc-1', title: 'Manual', period: '2025', methodology: 'review' }] });
t('provenance-rendered', provenanceRoot.textContent.includes('Manual — 2025 · review'));
const croot = mount('chart', chart.blocks[0].props);
t('chart-render-svg', JSON.stringify(croot).includes('svg') || (function () {
  let found = false;
  (function walk(e) { if (e.tag === 'svg') found = true; (e.children || []).forEach(walk); })(croot);
  return found;
})());
const droot = mount('dashboard', { title: 'D', metrics: [{ label: 'M', value: '1', hint: 'h' }], chart: null });
t('dashboard-render', droot.textContent.includes('M'));
const kroot = mount('compare', { columns: ['A', 'B'], rows: [{ label: 'x', a: '1', b: '2', melhor: 'a' }] });
t('compare-render', kroot.textContent.includes('x'));
const vroot = mount('calculator', { kind: 'conversor', title: 'C' });
t('conversor-render', vroot.textContent.includes('Converter'));
const groots = mount('diagram', { title: 'F', direction: 'v',
  nodes: [{ id: 'a', label: 'Um', icon: '1', group: 'G', desc: 'detalhe' }, { id: 'b', label: 'Dois' }],
  edges: [{ from: 'a', to: 'b', label: 'vai' }] });
t('diagram-zoom-grupo', groots.textContent.includes('G'));
const troot = mount('table', { title: 'T', columns: ['A'], rows: [['x'], ['y']] });
t('table-filtro', (function () {
  let found = false;
  (function walk(e) {
    if (e.tag === 'input' && e.attrs && e.attrs['aria-label'] === 'Filtrar linhas da tabela') found = true;
    (e.children || []).forEach(walk);
  })(troot);
  return found;
})());
const lroot = mount('lesson', { lesson_id: 'aula-1', title: 'Aula' });
t('lesson-offline', lroot.textContent.includes('Conecte-se'));
const updQuiz = JDUI.validateMessage({ version: V, update_of: 'msg-9', blocks: [
  { type: 'ui', component: 'quiz', props: { title: 'Q', questions: [{ q: 'a?', options: ['x', 'y'], answer: 0 }] } }] });
t('update-quiz-bloqueado', updQuiz.ok === true && !updQuiz.msg.update_of);
const big = { version: V, blocks: [{ type: 'ui', component: 'chart',
  props: { type: 'bar', series: [{ label: 's', values: Array.from({ length: 25 }, (_, i) => i) }] } }] };
t('chart-teto-24', JDUI.validateMessage(big).ok === false);
const unk = JDUI.validateMessage({ version: V, blocks: [
  { type: 'ui', component: 'nave-espacial', props: {} }] });
t('componente-desconhecido', unk.ok === false);
const emptyChart = mount('chart', { type: 'bar', series: [] });
t('chart-sem-dados', emptyChart.textContent.includes('Sem dados'));
const egOk = JDUI.validateMessage({ version: V, blocks: [{ type: 'ui', component: 'evidencegraph',
  props: { title: 'G', nodes: [{ id: 'c1', label: 'Café faz bem', kind: 'claim', estado: 'UNVERIFIED' },
    { id: 'e1', label: 'Estudo', kind: 'evidence' }, { id: 's1', label: 'exemplo.com', kind: 'source' }],
    edges: [{ from: 'e1', to: 'c1', label: 'MENTIONS' }] } }] });
t('eg-valido', egOk.ok === true);
t('eg-kind-ruim', JDUI.validateMessage({ version: V, blocks: [{ type: 'ui', component: 'evidencegraph',
  props: { nodes: [{ id: 'x', label: 'X', kind: 'nave' }] } }] }).ok === false);
t('eg-nos-demais', JDUI.validateMessage({ version: V, blocks: [{ type: 'ui', component: 'evidencegraph',
  props: { nodes: Array.from({ length: 31 }, (_, i) => ({ id: 'n' + i, label: 'L' })) } }] }).ok === false);
const egroot = mount('evidencegraph', egOk.msg.blocks[0].props);
t('eg-render', egroot.textContent.includes('Café faz bem'));
const egUp = JDUI.validateMessage({ version: V, update_of: 'm2', blocks: [
  { type: 'ui', component: 'evidencegraph', props: { nodes: [{ id: 'a', label: 'A' }] } }] });
t('update-eg-ok', egUp.ok === true && egUp.msg.update_of === 'm2');
"""


def test_jdui_v43_no_node():
    import pytest as _pt
    if NODE is None:
        _pt.skip("Node indisponível")
    with tempfile.TemporaryDirectory() as tmp:
        harness = Path(tmp) / "harness_v43.cjs"
        harness.write_text(HARNESS_V43, encoding="utf-8")
        r = subprocess.run([NODE, str(harness), str(RAIZ / "public" / "jdui.js")],
                           capture_output=True, text=True, timeout=60)
        assert r.returncode == 0, "STDOUT:\n" + r.stdout + "\nSTDERR:\n" + r.stderr
        assert "FAIL" not in r.stdout
