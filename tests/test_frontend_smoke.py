"""Fumaça do frontend: executa o renderMarkdown REAL do public/app.js no Node.

Pega os bugs que `node --check` não pega (ReferenceError, parser SSE, XSS no
renderer). Pula se o Node não estiver instalado.
"""
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

NODE = shutil.which('node')
RAIZ = Path(__file__).resolve().parents[1]
APP_JS = RAIZ / 'public' / 'app.js'

HARNESS = r"""
const fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8');
global.location = { href: 'http://127.0.0.1:8123/' };
function escText(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
global.document = { createElement: () => {
  let v = '';
  return { set textContent(x) { v = escText(x); }, get innerHTML() { return v; } };
} };
const jduiSrc = fs.readFileSync(process.argv[3], 'utf8');
global.window = {};
eval(jduiSrc);
global.JDUI = global.window.JDUI;
const start = src.indexOf('/* ----- Markdown');
const end = src.indexOf('/* ----- Render');
if (start < 0 || end < 0 || end < start) { console.error('markers missing'); process.exit(2); }
function esc(s) {
  return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
function validUrl(u) {
  try {
    const p = new URL(String(u).trim(), location.href);
    return (p.protocol === 'http:' || p.protocol === 'https:' || p.protocol === 'data:') ? p.href : '';
  } catch (_) { return ''; }
}
eval(src.slice(start, end));
const t = (name, cond) => {
  if (!cond) { console.error('FAIL ' + name); process.exitCode = 1; }
  else console.log('ok ' + name);
};
const hw = renderMarkdown('texto\n```widget-html\n<button onclick="x()">oi</button>\n```\nfim');
t('widget-iframe-sem-execucao', hw.includes('<iframe') && hw.includes('sandbox=""') && !hw.includes('allow-scripts'));
t('widget-toggle', hw.includes('Ver c'));
t('widget-no-naked-button', !hw.includes('<button onclick'));
const hs = renderMarkdown('veja:\n```svg\n<svg xmlns="http://www.w3.org/2000/svg" width="100" height="50"><rect width="100" height="50" fill="red" onclick="evil()"/><script>alert(1)</script></svg>\n```');
t('svg-inline', hs.includes('<svg') && hs.includes('<rect'));
t('svg-no-script', !hs.includes('<script'));
t('svg-no-onclick', !hs.includes('onclick'));
const hi = renderMarkdown('olha ![gato fofo](https://example.com/gato.jpg) aqui');
t('img-render', hi.includes('class="chat-img"') && hi.includes('onerror='));
t('img-src-intacto', hi.includes('src="https://example.com/gato.jpg"') && !hi.includes('src="<a'));
const mdReal = '[Mostrando uma imagem de Tom e Jerry]\n\n![tom do desenho tom and jerry](https://loremflickr.com/800/500/tom%20do%20desenho%20tom%20and%20jerry)';
const hr = renderMarkdown(mdReal);
t('img-loremflickr-intacto', hr.includes('src="https://loremflickr.com/800/500/tom%20do%20desenho%20tom%20and%20jerry"'));
t('code-url-sem-link', renderMarkdown('rode `https://x.com/a` ai').includes('<code>https://x.com/a</code>'));
const mdDot = renderMarkdown('veja https://x.com/a.');
t('url-ponto-final', mdDot.includes('href="https://x.com/a"') && mdDot.includes('</a>.'));
// quiz client-side a partir de código Python (padrão dos prints)
const codeQuiz = '# Pergunta 1\nprint("1. Quanto é 2+2?")\nprint("a) 3  b) 4")\nresp = input()\nif resp == "b":\n    print("ok")';
const qc = JDUI.quizFromCode(codeQuiz);
t('quiz-from-code', !!qc && qc.blocks[0].props.questions[0].answer === 1);
t('quiz-from-code-null', JDUI.quizFromCode('print("oi")') === null);
const txtQuiz = 'Pergunta 1: Quanto é 2+2?\na) 3\nb) 4\nResposta: b\n\nPergunta 2: Tipo de []?\na) list\nb) dict\nResposta: a';
const qt = JDUI.quizFromText(txtQuiz);
t('quiz-from-text', !!qt && qt.blocks[0].props.questions.length === 2);
t('quiz-from-text-ruido', JDUI.quizFromText('oi, tudo bem? me conta uma piada') === null);
// dual-view: código de quiz vira Interface|Código, e backend-quiz evita duplicar
const mdDuo = renderMarkdown('Rode no terminal:\n```python\n' + codeQuiz + '\n```');
takeJduiSlots();
t('dual-view', mdDuo.includes('jdui-duo') && mdDuo.includes('data-duo="ui"') && mdDuo.includes('data-duo="code"'));
const mdPlain = renderMarkdown('Exemplo:\n```python\nprint("oi")\n```');
takeJduiSlots();
t('codigo-comum-sem-duo', !mdPlain.includes('jdui-duo') && mdPlain.includes('codeblock'));
t('code-block', renderMarkdown('ex:\n```python\nprint("oi")\n```').includes('<pre><code>'));
t('xss-escaped', renderMarkdown('<img src=x onerror=evil()>').includes('&lt;img'));
t('table', renderMarkdown('| a | b |\n|---|---|\n| 1 | 2 |').includes('<table>'));
t('table-empty-cell', renderMarkdown('| a | b | c |\n|---|---|---|\n| 1 | | 3 |').includes('<td>1</td><td></td><td>3</td>'));
t('code-emphasis-literal', renderMarkdown('`**literal**`').includes('<code>**literal**</code>'));
t('no-fake-image', !renderMarkdown('![teste](https://example.com/a.png)').includes('picsum'));
const sources = renderMarkdown('Afirmação [S1]. Sem fonte [S2].\n\n## Fontes\n- [S1] [Documento](https://example.com/prova)');
t('real-citation', sources.includes('class="citation" href="https://example.com/prova"') && sources.includes('Sem fonte [S2]'));
t('source-url-not-markdown', !sources.includes('href="https://example.com/prova)'));
t('heading-levels', renderMarkdown('# Título\n## Seção\n### Detalhe').includes('<h2>Título</h2><h3>Seção</h3><h4>Detalhe</h4>'));
t('responsive-table-wrapper', renderMarkdown('| a | b |\n|---|---|\n| 1 | 2 |').includes('<div class="table-wrap"><table>'));
"""


def test_app_js_sintaxe_e_regressoes():
    if NODE is None:
        pytest.skip('Node indisponível')
    r = subprocess.run([NODE, '--check', str(APP_JS)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    texto = APP_JS.read_text(encoding='utf-8')
    # Regressão: ReferenceError que quebrava envio/render (faltava declarar).
    assert 'let sessionsCache = [];' in texto
    # Regressão: parser SSE corrompia todo delta/done ('{}' + json inválido).
    assert "dados = '{}'" not in texto


HARNESS_JDUI = r"""
const fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8');
global.location = { href: 'http://127.0.0.1:8123/' };
global.window = {};
global.document = { createElement: () => { throw new Error('sem DOM'); } };
eval(src);
const JDUI = global.window.JDUI;
const t = (name, cond) => {
  if (!cond) { console.error('FAIL ' + name); process.exitCode = 1; }
  else console.log('ok ' + name);
};
t('componentes', JDUI.COMPONENTS.indexOf('quiz') >= 0 && JDUI.COMPONENTS.indexOf('calculator') >= 0);
const quiz = { version: 'JULIA-ui-message/v1', blocks: [
  { type: 'ui', component: 'quiz', props: { title: 'Py', questions: [
    { q: '2+2?', options: ['3', '4'], answer: 1 }] } }] };
const r1 = JDUI.validateMessage(quiz);
t('quiz-valido', r1.ok === true);
t('quiz-invalido', JDUI.validateMessage({ version: 'JULIA-ui-message/v1', blocks: [
  { type: 'ui', component: 'quiz', props: { questions: [] } }] }).ok === false);
t('desconhecido', JDUI.validateMessage({ version: 'JULIA-ui-message/v1', blocks: [
  { type: 'ui', component: 'nave', props: {} }] }).ok === false);
const fence = 'texto\n```jdui\n' + JSON.stringify(quiz) + '\n```\nfim';
const ext = JDUI.extractBlocks(fence);
t('extract-1', ext.length === 1 && ext[0].blocks[0].component === 'quiz');
t('extract-parcial', JDUI.extractBlocks('```jdui\n{"version":').length === 0);
t('calc-expr', JDUI.calcExpr('2+3*4') === 14 && JDUI.calcExpr('(10-4)/3') === 2);
let jogou = false;
try { JDUI.calcExpr('process.exit(1)'); } catch (_) { jogou = true; }
t('calc-sem-eval', jogou);
"""

HARNESS_JDUI_STATE = r"""
const fs = require('fs');
class Element {
  constructor(tag) { this.tag = tag; this.children = []; this.events = {}; this.style = {}; this.attrs = {}; this._text = ''; }
  appendChild(child) { this.children.push(child); return child; }
  append(...children) { children.forEach(c => this.appendChild(c)); }
  replaceChildren(...children) { this.children = []; this._text = ''; this.append(...children); }
  addEventListener(name, fn) { this.events[name] = fn; }
  setAttribute(name, value) { this.attrs[name] = value; }
  focus() {}
  click() { if (this.events.click) this.events.click({ target: this }); }
  get firstChild() { return this.children[0]; }
  get textContent() { return this._text + this.children.map(c => c.textContent || '').join(''); }
  set textContent(value) { this._text = String(value); this.children = []; }
}
global.document = { createElement: tag => new Element(tag) };
global.window = {};
eval(fs.readFileSync(process.argv[2], 'utf8'));
const JDUI = global.window.JDUI;
const states = {};
const ctx = {
  loadState: key => states[key],
  saveState: (key, value) => { states[key] = JSON.parse(JSON.stringify(value)); }
};
function find(root, test) {
  if (test(root)) return root;
  for (const child of root.children) { const hit = find(child, test); if (hit) return hit; }
  return null;
}
function mount(component, props) {
  const root = new Element('main');
  JDUI.mount(root, [{ blocks: [{ type: 'ui', component, props }] }], ctx);
  return root;
}
function assert(name, condition) {
  if (!condition) throw new Error('FAIL ' + name);
  console.log('ok ' + name);
}
let checklist = mount('checklist', { title: 'Plano', items: [{ label: 'Ler', checked: false }] });
find(checklist, e => e.tag === 'input' && e.attrs['aria-label'] === 'Nova tarefa').value = 'Revisar';
find(checklist, e => e.tag === 'button' && e.textContent === 'Adicionar').click();
assert('checklist-add-persisted', states['0:0:checklist'].items.length === 2);
checklist = mount('checklist', { title: 'Plano', items: [{ label: 'Ler', checked: false }] });
assert('checklist-remount', find(checklist, e => e.textContent === 'Revisar') !== null);
find(checklist, e => e.tag === 'button' && e.textContent === 'Reiniciar').click();
assert('checklist-reset', states['0:0:checklist'].items.length === 1);

let table = mount('table', { title: 'Custos', columns: ['Item', 'Valor'], rows: [['Café', '10']] });
find(table, e => e.tag === 'button' && e.textContent === 'Editar tabela').click();
const cell = find(table, e => e.tag === 'input' && e.attrs['aria-label'] === 'Item, linha 1');
cell.value = 'Almoço'; cell.events.input();
assert('table-edit-persisted', states['0:0:table'].rows[0][0] === 'Almoço');
find(table, e => e.tag === 'button' && e.textContent === 'Adicionar linha').click();
assert('table-add-row', states['0:0:table'].rows.length === 2);
table = mount('table', { title: 'Custos', columns: ['Item', 'Valor'], rows: [['Café', '10']] });
assert('table-remount', find(table, e => e.tag === 'input' && e.value === 'Almoço') !== null);
find(table, e => e.tag === 'button' && e.textContent === 'Restaurar original').click();
assert('table-reset', states['0:0:table'].rows[0][0] === 'Café');

let form = mount('form', { title: 'Dados', fields: [{ name: 'nome', label: 'Nome', type: 'text' }] });
let field = find(form, e => e.tag === 'input' && e.name === 'nome');
field.value = 'Júlia'; field.events.input();
form = mount('form', { title: 'Dados', fields: [{ name: 'nome', label: 'Nome', type: 'text' }] });
assert('form-remount', find(form, e => e.tag === 'input' && e.value === 'Júlia') !== null);

let calc = mount('calculator', { title: 'Conta', kind: 'basic' });
find(calc, e => e.tag === 'button' && e.textContent === '1').click();
find(calc, e => e.tag === 'button' && e.textContent === '+').click();
find(calc, e => e.tag === 'button' && e.textContent === '2').click();
find(calc, e => e.tag === 'button' && e.textContent === '=').click();
assert('calculator-result-persisted', states['0:0:calculator'].expression === '3');
calc = mount('calculator', { title: 'Conta', kind: 'basic' });
assert('calculator-remount', find(calc, e => e.className === 'jdui-disp').textContent === '3');
"""


def test_jdui_js_paridade():
    if NODE is None:
        pytest.skip('Node indisponível')
    with tempfile.TemporaryDirectory() as tmp:
        harness = Path(tmp) / 'harness_jdui.cjs'
        harness.write_text(HARNESS_JDUI, encoding='utf-8')
        r = subprocess.run([NODE, str(harness), str(RAIZ / 'public' / 'jdui.js')],
                           capture_output=True, text=True, timeout=60)
        assert r.returncode == 0, 'STDOUT:\n' + r.stdout + '\nSTDERR:\n' + r.stderr
        assert 'FAIL' not in r.stdout


def test_jdui_interacoes_persistem():
    if NODE is None:
        pytest.skip('Node indisponível')
    with tempfile.TemporaryDirectory() as tmp:
        harness = Path(tmp) / 'harness_jdui_state.cjs'
        harness.write_text(HARNESS_JDUI_STATE, encoding='utf-8')
        r = subprocess.run([NODE, str(harness), str(RAIZ / 'public' / 'jdui.js')],
                           capture_output=True, text=True, timeout=60)
        assert r.returncode == 0, 'STDOUT:\n' + r.stdout + '\nSTDERR:\n' + r.stderr
        assert 'FAIL' not in r.stdout


def test_html_sem_classes_escapadas():
    """Regressão: `class=\\"` literal quebra todo o CSS (login fora do overlay)."""
    html = (RAIZ / 'public' / 'index.html').read_text(encoding='utf-8')
    assert '\\"' not in html
    for cls in ('login-overlay', 'login-card', 'drawer', 'composer', 'conversation',
                'session-list', 'memory-list', 'status-pop'):
        assert f'class="{cls}"' in html, cls
    # msg-menu-pop é criado dinamicamente pelo JS
    assert 'msg-menu-pop' in (RAIZ / 'public' / 'app.js').read_text(encoding='utf-8')
    for eid in ('loginOverlay', 'loginForm', 'registerForm', 'conversation', 'composer',
                'sessionList', 'drawer', 'statusPop'):
        assert f'id="{eid}"' in html, eid


def test_estilos_legiveis_para_markdown_no_chat():
    css = (RAIZ / 'public' / 'interface.css').read_text(encoding='utf-8')
    for regra in (
        '.message.ai .bubble h2',
        '.bubble blockquote',
        '.bubble .codeblock pre code',
        '.table-wrap',
        '.bubble tbody tr:nth-child(even)',
    ):
        assert regra in css, regra


def test_acoes_de_historico_arquivos_e_contexto_local_ligadas():
    html = (RAIZ / 'public' / 'index.html').read_text(encoding='utf-8')
    js = APP_JS.read_text(encoding='utf-8')
    for eid in ('historySearch', 'historyResults', 'savedItems', 'exportTxt',
                'exportCsv', 'exportXlsx', 'exportPdf', 'shareConversation',
                'contextCity', 'locationEnabled', 'useCurrentLocation', 'clearLocation',
                'deviceTimeStatus'):
        assert f'id="{eid}"' in html, eid
        assert f"$('{eid}')" in js, eid
    assert '/api/export/xlsx' in js
    assert 'navigator.geolocation.getCurrentPosition' in js
    assert 'local_time: localTime' in js and 'timezone' in js
    assert "item('save', 'Salvar item neste aparelho')" in js


def test_streaming_sem_sucesso_vazio():
    js = APP_JS.read_text(encoding="utf-8")
    assert "throw new Error('Resposta vazia da IA')" in js
    assert "tipo === 'error'" in js or 'tipo === "error"' in js
    assert 'tentar_modelos' in (RAIZ / 'pc_agent.py').read_text(encoding='utf-8')
    assert 'chat_stream_fb' in (RAIZ / 'hermes_bridge.py').read_text(encoding='utf-8')


def test_envia_para_ia_sem_aguardar_sincronizacao_completa():
    js = APP_JS.read_text(encoding="utf-8")
    inicio = js.index("async function sendMessage(raw)")
    fim = js.index("\ncomposer.addEventListener('submit'", inicio)
    envio = js[inicio:fim]
    assert "requestAI(row, { immediate: true, onStarted: syncAndRefresh, sentAt, storedAt })" in envio
    assert envio.index("await storeMessages([row])") < envio.index("requestAI(row,")
    assert envio.index("requestAI(row,") < envio.index("await touchSession(")
    assert "await syncAndRefresh()" not in envio
    assert "text: userRow.text" in js  # IA persiste o texto piggyback no PC
    assert "const aiQueue = []" in js and "aiQueue.push(" in js and "pumpAIQueue()" in js
    ai_inicio = js.index("function requestAI(userRow, options = {})")
    ai_fim = js.index("\nfunction stopAI()", ai_inicio)
    pedido = js[ai_inicio:ai_fim]
    assert "(!pcOnline && !options.immediate)" in pedido
    assert "const streamRequest = fetch(" in pedido
    assert pedido.index("const streamRequest = fetch(") < pedido.index("options.onStarted()")
    assert "d.codigo !== 'sem_mensagem'" in pedido
    assert "syncResult.confirmed_ids || []" in pedido
    assert "await api('/api/ai', { method: 'POST'" in pedido
    preflight = pedido[:pedido.index("const streamRequest = fetch(")]
    assert "messageById(replyId)" in preflight and "await allMessages()" not in preflight
    assert "await renderMessages()" not in preflight
    assert "'[chat-timing]'" in pedido


def test_estudos_ligado_e_com_cache_offline():
    html = (RAIZ / 'public' / 'index.html').read_text(encoding='utf-8')
    js = APP_JS.read_text(encoding='utf-8')
    assert 'data-tab="estudos"' in html and 'id="page-estudos"' in html
    for eid in ('estudosGrid', 'estProvas', 'estAcertos', 'estItens', 'estDue',
                'estudosAviso', 'estudosAssuntos', 'estudosRecs', 'estudosPlanos',
                'estudosDue', 'estudosErros', 'estudosRefresh'):
        assert f'id="{eid}"' in html, eid
        assert eid in js, eid
    assert "if (tab === 'estudos') renderEstudos();" in js
    assert '/api/learn/stats' in js and '/api/learn/plans' in js
    assert '/api/learn/cards/due' in js and '/api/learn/mistakes' in js
    assert 'learnCacheGet' in js and 'Offline' in js  # fallback offline real
    # fila offline educacional (V4.2.1 §4): outbox idempotente + correção no servidor
    for sym in ('learnOutbox', 'learnEnqueue', 'learnSyncOutbox', 'queueLearn'):
        assert sym in js, sym
    assert 'ctx.queueLearn' in (RAIZ / 'public' / 'jdui.js').read_text(encoding='utf-8')
    # anti-corrida sync→IA: texto acompanha o pedido; pendentes só sincronizados
    assert 'text: userRow.text' in js and 'created_at: userRow.created_at' in js
    assert "m.status === 'synced'" in js


def test_jdui_v43_fiacao():
    js = (RAIZ / 'public' / 'jdui.js').read_text(encoding='utf-8')
    app = APP_JS.read_text(encoding='utf-8')
    css = (RAIZ / 'public' / 'styles.css').read_text(encoding='utf-8')
    for comp in ('R.chart', 'R.dashboard', 'R.compare', 'R.lesson',
                 'OPS.conversao', 'update_of', 'precisaConexao'):
        assert comp in js, comp
    assert 'update_of' in app and 'update-of' not in app  # patch in-place, sem gambiarra
    for regra in ('.jdui-chart svg', '.jdui-dashgrid', '@media(max-width:360px)',
                  '.jdui-cmp', '.jdui-metric'):
        assert regra in css, regra  # responsivo 320–768 sem CSS novo pesado


def test_live_research_fiacao():
    html = (RAIZ / 'public' / 'index.html').read_text(encoding='utf-8')
    js = APP_JS.read_text(encoding='utf-8')
    for eid in ('researchBar', 'researchLabel', 'researchToggle', 'researchCancel',
                'researchPanel', 'researchSteps', 'researchSources', 'researchResult',
                'researchPause'):
        assert f'id="{eid}"' in html, eid
        assert eid in js, eid
    assert 'id="researchFilters"' in html
    for sym in ('researchAttach', 'researchPoll', 'researchCarregaFontes',
                '/api/research/status', '/api/research/cancel', '/api/research/evidence',
                'researchPollSSE', 'researchPollHTTP', 'researchRecebe', 'researchFilters',
                'researchAplicaFiltro', '/api/research/stream',
                '/api/research/pause', 'researchPause'):
        assert sym in js, sym
    # intervene é via chat (cmd_pesquisa), coberto nos testes de API
    css = (RAIZ / 'public' / 'styles.css').read_text(encoding='utf-8')
    assert '.research-bar' in css and '.research-panel' in css


def test_sessoes_sem_fragmentacao():
    """Regressão: cada mensagem virando um chat (id ativo só no localStorage).

    O id da conversa ativa deve passar SEMPRE por setActiveConversation
    (espelha no IndexedDB) e o boot deve retomar a sessão mais recente com
    mensagens em vez de criar uma nova.
    """
    texto = APP_JS.read_text(encoding='utf-8')
    assert 'function setActiveConversation' in texto
    assert 'function resolveActiveConversation' in texto
    assert 'function healSessions' in texto
    assert texto.count('setActiveConversation(') >= 6  # def + 5 usos
    for linha in texto.splitlines():
        s = linha.strip()
        if s.startswith('activeConversation = newId()'):
            raise AssertionError('atribuição direta cria chats fantasmas: ' + s)
    assert "openDb" in texto and ", 4)" in texto  # DB v4 inclui a biblioteca local de itens salvos
    # Excluída não ressuscita: tombstone filtra merge, listas, contas e resolve.
    for fn in ('loadTombstones', 'tombstone(', 'isDeleted(', "deleted:'"):
        assert fn in texto, fn
    assert 'conv_forget' in (RAIZ / 'pc_agent.py').read_text(encoding='utf-8')
    assert 'conv_forget' in (RAIZ / 'server.py').read_text(encoding='utf-8')


def test_render_markdown_no_node():
    if NODE is None:
        pytest.skip('Node indisponível')
    with tempfile.TemporaryDirectory() as tmp:
        harness = Path(tmp) / 'harness.cjs'
        harness.write_text(HARNESS, encoding='utf-8')
        r = subprocess.run([NODE, str(harness), str(APP_JS), str(RAIZ / 'public' / 'jdui.js')],
                           capture_output=True, text=True, timeout=60)
        assert r.returncode == 0, 'STDOUT:\n' + r.stdout + '\nSTDERR:\n' + r.stderr
        assert 'FAIL' not in r.stdout
