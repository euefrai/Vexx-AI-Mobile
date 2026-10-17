/* V5.4.3: menu "Provedores de IA" — chave salva/removida SÓ no PC (.env local).
   Pré-requisito: tests/preview_workspace.py rodando em 127.0.0.1:8770
   (o preview usa um .env descartável via JULIA_ENV_FILE — nunca o do repo).
   Uso: node tools/3d/qa-provedores-ui.cjs  (a partir da raiz do repositório)

   O que prova, com dados reais (nenhuma simulação de rede):
   1. Menu na interface lista os 7 provedores externos com status honesto.
   2. Salvar chave (fake) no Groq: fica no PC, campo é limpo, nada no
      localStorage, status/origem mudam de verdade (chamada real de listagem).
   3. Remover: volta ao estado inicial (sem chave) sem deixar rastro.
   4. As respostas de /api/providers nunca contêm a chave. */
const {chromium} = require('playwright');
const fs = require('fs'), path = require('path'), assert = require('assert/strict');
const out = path.resolve('qa-artifacts/ia-providers'); fs.mkdirSync(out, {recursive: true});
const url = 'http://127.0.0.1:8770';
const CHAVE_FAKE = 'gsk_qa_fake_0123456789';
let browser, page;
const respostasProviders = [];
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
  page.on('response', async r => {
    if (!r.url().includes('/api/providers')) return;
    try { respostasProviders.push({status: r.status(), body: await r.text()}); } catch (_) {}
  });
  await page.goto(url);
  await page.locator('#loginUser').fill('preview');
  await page.locator('#loginPassword').fill('preview-only-2026');
  await page.locator('#loginButton').click();
  await page.locator('#loginOverlay').waitFor({state: 'hidden'});
  await page.locator('#messageInput').waitFor({timeout: 15000});

  /* 1) Catálogo recarregado de verdade (como no dia a dia). */
  await page.locator('#drawerOpen').click();
  await page.locator('.drawer-connection summary').click();
  await page.locator('#modelRefresh').click();
  await page.getByText('Lista de modelos atualizada').first().waitFor({timeout: 25000});

  /* 2) Menu "Provedores de IA" abre o gerenciador com os 7 provedores. */
  await page.locator('#providersOpen').click();
  await page.locator('#providersDialog[open]').waitFor({timeout: 5000});
  await page.locator('.provider-row').first().waitFor({timeout: 5000});
  const linhas = await page.locator('.provider-row').count();
  assert.equal(linhas, 7, 'devem listar os 7 provedores externos (sem hermes)');
  const rotulos = await page.evaluate(() => [...document.querySelectorAll('.provider-row')].map(r => ({
    id: r.dataset.provider,
    chip: r.querySelector('.provider-chip') ? r.querySelector('.provider-chip').textContent : '',
    temRemover: !!r.querySelector('.provider-remove'),
  })));
  for (const r of rotulos) assert(r.chip.length > 0, 'chip de status presente em ' + r.id);
  const groqInicial = rotulos.find(r => r.id === 'groq');
  assert(groqInicial, 'linha do Groq presente');
  assert(/sem chave/i.test(groqInicial.chip), 'Groq deve começar sem chave neste PC; veio: ' + groqInicial.chip);
  assert.equal(groqInicial.temRemover, false, 'sem "Remover" quando não há chave do app');
  await page.screenshot({path: path.join(out, 'provedores-antes.png')});

  /* 3) Salva uma chave FAKE do Groq: fica só no PC e o status muda. */
  const linhaGroq = page.locator('.provider-row[data-provider="groq"]');
  await linhaGroq.locator('input').fill(CHAVE_FAKE);
  await linhaGroq.getByRole('button', {name: 'Salvar'}).click();
  await page.getByText('Chave salva só neste PC').first().waitFor({timeout: 30000});
  await linhaGroq.locator('.provider-remove').waitFor({timeout: 30000});
  const depoisSalvar = await page.evaluate(() => {
    const r = document.querySelector('.provider-row[data-provider="groq"]');
    const chip = r.querySelector('.provider-chip') ? r.querySelector('.provider-chip').textContent : '';
    const fonte = r.querySelector('.provider-source') ? r.querySelector('.provider-source').textContent : '';
    const entrada = r.querySelector('input') ? r.querySelector('input').value : '';
    return {chip, fonte, entrada, segredosLimpos: !JSON.stringify(localStorage).includes('gsk_qa_fake')};
  });
  assert(!/sem chave/i.test(depoisSalvar.chip), 'chip deve indicar chave configurada: ' + depoisSalvar.chip);
  assert(/neste PC/i.test(depoisSalvar.fonte), 'origem deve dizer "neste PC": ' + depoisSalvar.fonte);
  assert.equal(depoisSalvar.entrada, '', 'campo limpo depois de salvar (chave nunca fica na tela)');
  assert(depoisSalvar.segredosLimpos, 'navegador não pode guardar a chave');
  await page.screenshot({path: path.join(out, 'provedores-chave-salva.png')});

  /* 4) Remove: volta ao estado inicial, sem rastro. */
  await linhaGroq.locator('.provider-remove').click();
  await page.getByText('Chave removida deste PC').first().waitFor({timeout: 30000});
  await page.waitForFunction(() => {
    const r = document.querySelector('.provider-row[data-provider="groq"]');
    const chip = r && r.querySelector('.provider-chip') ? r.querySelector('.provider-chip').textContent : '';
    return r && !r.querySelector('.provider-remove') && /sem chave/i.test(chip);
  }, null, {timeout: 30000});
  const segredosFinal = await page.evaluate(() => !JSON.stringify(localStorage).includes('gsk_qa_fake'));
  assert(segredosFinal, 'navegador segue sem a chave após remover');
  await page.screenshot({path: path.join(out, 'provedores-depois.png')});

  /* 5) Respostas do relay nunca ecoam a chave. */
  assert(respostasProviders.length >= 2, 'esperava chamadas reais a /api/providers');
  for (const r of respostasProviders) {
    assert.equal(r.status, 200, 'POST /api/providers deveria ter respondido 200');
    assert(!r.body.includes(CHAVE_FAKE), 'resposta não pode conter a chave');
  }

  fs.writeFileSync(path.join(out, 'metrics-provedores.json'), JSON.stringify({
    provedores: rotulos.map(r => r.id), groqInicial, depoisSalvar,
    chamadasProviders: respostasProviders.map(r => r.status), errors, esperados,
    checks: 'menu na interface, 7 provedores com status, chave salva só no PC (campo limpo, sem localStorage), ' +
            'remover restaura o estado e nenhuma resposta ecoa a chave',
  }, null, 2));
  assert.deepEqual(errors, []);
  console.log(JSON.stringify({ok: true, out, provedores: rotulos.length}));
})().catch(async e => {
  console.error(e);
  await page?.screenshot({path: path.join(out, 'failure.png'), fullPage: true}).catch(() => {});
  process.exitCode = 1;
}).finally(async () => { await browser?.close(); });
