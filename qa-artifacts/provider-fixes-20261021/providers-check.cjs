// Run tests/preview_workspace.py with VEXX_PROVIDER_FIXTURES=1 first.
// Real browser, relay, agent, SQLite and .env; external provider is a test fixture.
const {chromium} = require('playwright');
const fs = require('fs'), assert = require('assert/strict');
(async () => {
  const browser = await chromium.launch({channel:'chrome', headless:true});
  try {
    const page = await browser.newPage({viewport:{width:390,height:844}}), errors=[], checks={};
    page.on('pageerror', e => errors.push(e.message));
    await page.goto('http://127.0.0.1:8770');
    await page.locator('#loginUser').fill('preview');
    await page.locator('#loginPassword').fill('preview-only-2026');
    await page.locator('#loginButton').click();
    await page.locator('#loginOverlay').waitFor({state:'hidden'});
    await page.waitForFunction(() => pcOnline && modelCatalog.providers.length > 1);
    await page.evaluate(() => abrirProvedores());
    const groq = page.locator('[data-provider="groq"]'), input=groq.locator('input');
    await input.fill('qa-valid-provider-first');
    await input.press('Enter');
    await page.waitForFunction(() => !providerMutation && modelCatalog.providers.some(p=>p.id==='groq' && p.configured && p.source==='arquivo'));
    checks.enterSaves = (await input.inputValue()) === '' && (await groq.locator('.provider-chip').innerText()) === 'Chave salva';
    checks.persistentConfirmation = (await page.locator('#providersNotice').innerText()).includes('campo fica vazio por segurança');
    const catalog = await page.evaluate(() => api('/api/ai/models'));
    checks.lateProviderAvailable = catalog.models.length > 500 && catalog.models.includes('groq/fixture-chat');
    checks.providerMetadata = catalog.items.some(i=>i.id==='groq/fixture-chat' && i.provider==='groq');
    checks.noSecretInCatalog = !JSON.stringify(catalog).includes('qa-valid-provider-first');
    await page.reload();
    await page.waitForFunction(() => pcOnline && modelCatalog.providers.some(p=>p.id==='groq' && p.configured));
    await page.evaluate(() => abrirProvedores());
    checks.survivesReload = (await input.inputValue()) === '' && (await groq.locator('.provider-source').innerText()).includes('Salva neste PC');
    await groq.getByRole('button', {name:'Escolher modelo deste provedor'}).click();
    checks.providerShortcutFilters = (await page.locator('#modelSearch').inputValue()) === 'Groq';
    await page.locator('#modelSelect').selectOption('groq/fixture-chat');
    checks.selectionMatchesSent = await page.evaluate(() => modeloAtivo()==='groq/fixture-chat');
    await page.locator('#modelSearch').fill('no-such-model-xyz');
    checks.emptySearchHonest = await page.evaluate(() => $('modelSelect').selectedIndex === -1 && modeloAtivo()==='groq/fixture-chat' && $('modelResults').textContent.includes('Nenhum modelo'));
    await page.locator('#modelSearch').fill('');
    checks.groupOrdering = await page.evaluate(() => {
      const labels=[...$('modelSelect').querySelectorAll('optgroup')].map(g=>g.label);
      const ranks=labels.map(s=>s.startsWith('Grátis')?0:s.startsWith('Suas API keys')?1:2);
      return ranks.includes(0)&&ranks.includes(1)&&ranks.includes(2)&&ranks.every((v,i)=>!i||v>=ranks[i-1]);
    });
    for (const width of [320,390,1280]) {
      await page.setViewportSize({width,height:900});
      await page.evaluate(() => abrirSeletorDeModelo());
      checks['layout'+width] = await page.evaluate(() => {
        const select=$('modelSelect').getBoundingClientRect(), drawer=$('drawer').getBoundingClientRect();
        return select.width>150 && select.right<=drawer.right+1 && document.documentElement.scrollWidth<=innerWidth;
      });
      await page.screenshot({path:`qa-artifacts/provider-fixes-20261021/models-${width}.png`});
    }
    await page.setViewportSize({width:390,height:844});
    await page.evaluate(() => {setDrawer(false);navigate('chat');});
    await page.locator('#messageInput').fill('Escreva uma frase simples sobre criatividade.');
    await page.locator('#messageInput').press('Enter');
    await page.waitForFunction(() => conversation.textContent.includes('Resposta de teste com a chave salva e o modelo fixture-chat.'), {timeout:30000});
    checks.savedKeyUsedForChat = true;
    // Delayed refresh must preserve a key being typed, rather than wiping it.
    let release, intercepted;
    const gate = new Promise(resolve=>release=resolve), started=new Promise(resolve=>intercepted=resolve);
    await page.route('**/api/ai/models', async route => {
      const response=await route.fetch(); intercepted(); await gate; await route.fulfill({response});
    });
    await page.evaluate(() => {modelsLoadedAt=0; window.openingProviders=abrirProvedores();});
    await started;
    await input.fill('qa-valid-provider-unsaved'); release();
    await page.evaluate(() => window.openingProviders);
    checks.refreshPreservesDraft = (await input.inputValue()) === 'qa-valid-provider-unsaved';
    await page.unroute('**/api/ai/models');
    // An actual HTTP failure must not wipe the draft or show a success notice.
    await page.route('**/api/providers', route=>route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({detail:'Falha de gravação simulada'})}));
    await groq.getByRole('button',{name:'Salvar',exact:true}).click();
    await page.waitForFunction(()=>!providerMutation && !$('providersError').hidden);
    checks.failedSavePreservesDraft = (await input.inputValue()) === 'qa-valid-provider-unsaved';
    checks.failedSaveExplained = (await page.locator('#providersError').innerText()).includes('Falha de gravação simulada') && !(await page.locator('#providersNotice').innerText());
    await page.unroute('**/api/providers');
    await input.fill('qa-rejected-provider'); await input.press('Enter');
    await page.waitForFunction(()=>!providerMutation && modelCatalog.providers.some(p=>p.id==='groq'&&p.auth_error));
    checks.rejectedKeyStillReportedSaved = (await groq.locator('.provider-chip').innerText()).includes('recusada') && (await page.locator('#providersError').innerText()).includes('foi salva');
    await input.fill('qa-valid-provider-updated'); await input.press('Enter');
    await page.waitForFunction(()=>!providerMutation && isConfigured('groq'));
    checks.replacingKeyClearsError = await page.locator('#providersError').isHidden();
    await page.screenshot({path:'qa-artifacts/provider-fixes-20261021/providers-390.png'});
    await groq.getByRole('button',{name:'Remover chave deste PC'}).click();
    await page.waitForFunction(()=>!providerMutation && !modelCatalog.providers.find(p=>p.id==='groq').configured);
    checks.removeKey = true;
    assert(Object.values(checks).every(Boolean), JSON.stringify(checks)); assert.deepEqual(errors,[]);
    const report={checks,errors,note:'Real Chrome/UI/relay/agent/.env/SQLite. External discovery and streaming use synthetic fixtures; no real provider credit or API key used.'};
    fs.writeFileSync('qa-artifacts/provider-fixes-20261021/providers-check.json',JSON.stringify(report,null,2));
    console.log(JSON.stringify(report));
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
