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
t('widget-iframe', hw.includes('<iframe') && hw.includes('sandbox="allow-scripts"'));
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
t('code-block', renderMarkdown('ex:\n```python\nprint("oi")\n```').includes('<pre><code>'));
t('xss-escaped', renderMarkdown('<img src=x onerror=evil()>').includes('&lt;img'));
t('table', renderMarkdown('| a | b |\n|---|---|\n| 1 | 2 |').includes('<table>'));
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
const quiz = { version: 'julia-ui-message/v1', blocks: [
  { type: 'ui', component: 'quiz', props: { title: 'Py', questions: [
    { q: '2+2?', options: ['3', '4'], answer: 1 }] } }] };
const r1 = JDUI.validateMessage(quiz);
t('quiz-valido', r1.ok === true);
t('quiz-invalido', JDUI.validateMessage({ version: 'julia-ui-message/v1', blocks: [
  { type: 'ui', component: 'quiz', props: { questions: [] } }] }).ok === false);
t('desconhecido', JDUI.validateMessage({ version: 'julia-ui-message/v1', blocks: [
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
    assert "openDb" in texto and ", 3)" in texto  # DB v3 tem stores META/UISTATE
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
        r = subprocess.run([NODE, str(harness), str(APP_JS)],
                           capture_output=True, text=True, timeout=60)
        assert r.returncode == 0, 'STDOUT:\n' + r.stdout + '\nSTDERR:\n' + r.stderr
        assert 'FAIL' not in r.stdout
