/* V5.4.2: provedores externos REAIS + troca do modelo a qualquer momento.
   Pré-requisito: tests/preview_workspace.py rodando em 127.0.0.1:8770.
   Uso: node tools/3d/qa-ia-providers.cjs  (a partir da raiz do repositório)

   O que prova, com dados reais (nenhuma simulação de rede):
   1. Seletor honesto: provedor com chave recusada aparece desabilitado.
   2. Atalho Status -> Modelo abre o seletor sem sair do chat.
   3. Mensagem com "openai/gpt-4o-mini": o pedido SAI para a API da OpenAI
      e volta 401 — a bolha mostra o motivo real (e não "sem chave").
   4. Mesma conversa, troca para "gemini/gemini-2.0-flash": a próxima
      resposta acusa o NOVO provedor (sem chave no PC) — a troca vale
      para a próxima mensagem, sem recomeçar a conversa. */
const {chromium} = require('playwright');
const fs = require('fs'), path = require('path'), assert = require('assert/strict');
const out = path.resolve('qa-artifacts/ia-providers'); fs.mkdirSync(out, {recursive: true});
const url = 'http://127.0.0.1:8770';
let browser, page;
(async () => {
  browser = await chromium.launch({channel: 'chrome', headless: true});
  const context = await browser.newContext({viewport: {width: 420, height: 900}});
  const errors = [], esperados = [];
  page = await context.newPage();
  page.on('pageerror', e => errors.push(e.message));
  page.on('console', m => {
    if (m.type() !== 'error') return;
    const t = m.text(), u = m.location().url || '';
    if (u.includes('/api/session') || /401/.test(t)) esperados.push(t); else errors.push(t + ' ' + u);
  });
  await page.goto(url);
  await page.locator('#loginUser').fill('preview');
  await page.locator('#loginPassword').fill('preview-only-2026');
  await page.locator('#loginButton').click();
  await page.locator('#loginOverlay').waitFor({state: 'hidden'});
  await page.locator('#messageInput').waitFor({timeout: 15000});

  /* 1) Seletor honesto + botão Atualizar (catálogo recarregado de verdade). */
  await page.locator('#drawerOpen').click();
  await page.locator('.drawer-connection summary').click();
  await page.locator('#modelRefresh').waitFor({timeout: 15000});
  await page.locator('#modelRefresh').click();
  await page.getByText('Lista de modelos atualizada').first().waitFor({timeout: 25000});
  const picker = await page.evaluate(() => {
    const sel = document.querySelector('#modelSelect');
    const grupos = [...sel.querySelectorAll('optgroup')].map(g => ({
      rotulo: g.label,
      opcoes: g.querySelectorAll('option').length,
      desabilitadas: [...g.querySelectorAll('option')].filter(o => o.disabled).length,
    }));
    return {grupos, openai: grupos.find(g => /OpenAI/.test(g.rotulo)) || null};
  });
  assert(picker.openai, 'grupo OpenAI deve existir (há chave no PC): ' + JSON.stringify(picker.grupos));
  assert(/chave recusada/i.test(picker.openai.rotulo),
    'OpenAI deve avisar "chave recusada"; veio: ' + picker.openai.rotulo);
  assert.equal(picker.openai.desabilitadas, picker.openai.opcoes,
    'opções OpenAI devem estar desabilitadas');
  const statusTexto = await page.evaluate(() => document.querySelector('#aiStatus').textContent);
  assert(!/sem chave/.test(statusTexto),
    'modelo Hermes (id com barra) não pode virar "sem chave": ' + statusTexto);
  await page.screenshot({path: path.join(out, 'picker-honesto.png')});

  /* 2) Status -> Modelo abre o seletor (troca a qualquer momento). */
  await page.locator('#drawerClose').click();
  await page.locator('#statusButton').click();
  await page.locator('#popModelRow').click();
  await page.waitForFunction(() => document.querySelector('#drawer').classList.contains('open'));
  assert(await page.evaluate(() => document.querySelector('.drawer-connection').open),
    'atalho do status deve abrir a seção do seletor');
  await page.screenshot({path: path.join(out, 'atalho-modelo.png')});
  await page.locator('#drawerClose').click();

  /* 3) Chamada REAL a OpenAI (chave recusada): erro honesto e persistente. */
  await page.evaluate(() => localStorage.setItem('julia-model', 'openai/gpt-4o-mini'));
  await page.reload();
  await page.locator('#loginOverlay').waitFor({state: 'hidden'}).catch(() => {});
  await page.locator('#messageInput').fill('Responda apenas: ok');
  await page.getByRole('button', {name: 'Enviar', exact: true}).click();
  const bolha1 = page.locator('.message.ai.failed .bubble').last();
  await bolha1.waitFor({timeout: 45000});
  const texto1 = await bolha1.innerText();
  assert(/OpenAI/i.test(texto1) && /recusou a chave/i.test(texto1),
    'bolha deve trazer o motivo real do provedor; veio: ' + texto1);
  assert(!/sem chave/i.test(texto1),
    'não pode alegar "sem chave": a chave existe e foi recusada (401)');
  assert(await page.locator('.message.ai.failed .message-retry').last().isVisible(),
    'botão "Tentar novamente" presente');
  await page.screenshot({path: path.join(out, 'erro-honesto.png')});

  /* 4) Mesma conversa: troca o modelo e a PRÓXIMA tentativa muda de provedor. */
  await page.evaluate(() => localStorage.setItem('julia-model', 'gemini/gemini-2.0-flash'));
  await page.locator('#messageInput').fill('Responda apenas: ok');
  await page.getByRole('button', {name: 'Enviar', exact: true}).click();
  const bolhas = page.locator('.message.ai.failed .bubble');
  await page.waitForFunction(n => document.querySelectorAll('.message.ai.failed .bubble').length >= n,
    (await bolhas.count()) + 1, {timeout: 45000});
  const texto2 = await bolhas.last().innerText();
  assert(/Gemini/i.test(texto2) && /sem chave/i.test(texto2),
    'troca de modelo na mesma conversa deve acusar o NOVO provedor; veio: ' + texto2);
  await page.screenshot({path: path.join(out, 'troca-na-mesma-conversa.png')});

  fs.writeFileSync(path.join(out, 'metrics.json'), JSON.stringify({
    picker, primeiroErro: texto1.slice(0, 200), segundoErro: texto2.slice(0, 200),
    errors, esperados,
    checks: 'seletor honesto (chave recusada desabilitada), atualizar real, atalho status->modelo, ' +
            'OpenAI 401 real com motivo honesto, troca para Gemini na mesma conversa sem recomeçar',
  }, null, 2));
  assert.deepEqual(errors, []);
  console.log(JSON.stringify({ok: true, out, picker: picker.grupos.length + ' grupos'}));
})().catch(async e => {
  console.error(e);
  await page?.screenshot({path: path.join(out, 'failure.png'), fullPage: true}).catch(() => {});
  process.exitCode = 1;
}).finally(async () => { await browser?.close(); });
