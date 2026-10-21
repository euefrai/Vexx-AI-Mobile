// Disposable preview only. Clipboard/share/print transports are simulated.
const { chromium } = require('playwright');
const fs = require('fs');
const assert = require('assert/strict');
(async () => {
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
    const errors = [], checks = {};
    page.on('pageerror', e => errors.push(e.message));
    await page.goto('http://127.0.0.1:8770');
    await page.locator('#loginUser').fill('preview');
    await page.locator('#loginPassword').fill('preview-only-2026');
    await page.locator('#loginButton').click();
    await page.locator('#loginOverlay').waitFor({ state: 'hidden' });
    await page.waitForFunction(() => pcOnline && !busy);
    await page.evaluate(async () => {
      window.testCopies = [];
      Object.defineProperty(navigator, 'clipboard', { configurable: true, value: undefined });
      Object.defineProperty(navigator, 'share', { configurable: true, value: undefined });
      document.execCommand = command => {
        if (command !== 'copy') throw Error('Unexpected command');
        testCopies.push(document.activeElement.value); return true;
      };
      await saveItem({ title: 'QA copy', text: 'Texto salvo de teste' });
      setActiveConversation('preview-week-plan');
      navigate('settings');
      await Promise.all([paintSavedItems(), paintSavedItems()]);
    });
    checks.savedItemsNotDuplicated = await page.locator('#savedItems .saved-item').filter({ hasText: 'QA copy' }).count() === 1;
    await page.locator('#savedItems .saved-item').filter({ hasText: 'QA copy' }).getByRole('button', { name: 'Copiar', exact: true }).click();
    await page.waitForFunction(() => testCopies.includes('Texto salvo de teste'));
    checks.savedCopyFallback = true;
    await page.locator('#shareConversation').click();
    await page.waitForFunction(() => testCopies.some(t => t.includes('Lucas: Vamos começar')));
    checks.shareButtonFallback = true;
    Object.assign(checks, await page.evaluate(async () => {
      const before = testCopies.length;
      Object.defineProperty(navigator, 'share', { configurable: true, value: async () => { throw new DOMException('Canceled', 'AbortError'); } });
      await shareText('Cancel', 'Do not copy', true);
      const canceled = testCopies.length === before;
      Object.defineProperty(navigator, 'share', { configurable: true, value: async () => { throw new Error('Unavailable'); } });
      await shareText('Fallback', 'Fallback after failure', true);
      const failedShare = testCopies.at(-1) === 'Fallback after failure';
      await renderTimeline();
      return { canceledShareDoesNotCopy: canceled, failedShareFallsBack: failedShare,
        activityIdentity: $('timeline').textContent.includes('Lucas') && !$('timeline').textContent.includes('Júlia') };
    }));
    for (const format of ['Txt', 'Csv', 'Md']) {
      const downloadPromise = page.waitForEvent('download');
      await page.locator('#export' + format).click();
      const download = await downloadPromise;
      const content = fs.readFileSync(await download.path(), 'utf8');
      checks['export' + format] = content.includes('Lucas') && !content.includes('Júlia');
      if (format === 'Md') checks.exportBrand = content.includes('Exportado do Vexx AI');
    }
    Object.assign(checks, await page.evaluate(async () => {
      let html = '';
      await printConversation({ document: { open() {}, write(s) { html = s; }, close() {} }, focus() {}, print() {} });
      const printIdentity = html.includes('<strong>Lucas') && !html.includes('Júlia');
      const originalMessages = allMessages, originalSessions = ownSessions;
      const originalOwner = currentUid;
      const row = text => ({ id: 'qa-' + text, owner: currentUid, role: 'assistant', text, conversation_id: activeConversation, created_at: new Date().toISOString() });
      const search = query => { $('historySearch').value = query; return searchHistory(); };
      const results = $('historyResults');
      let release;
      try {
        allMessages = () => new Promise(resolve => { release = resolve; });
        const older = search('alpha');
        allMessages = async () => [row('beta')];
        await search('beta');
        release([row('alpha')]); await older;
        const latestQueryWins = results.children.length === 1 && results.textContent.includes('beta') && !results.textContent.includes('alpha');
        const historyIdentity = results.textContent.includes('Lucas');
        allMessages = () => new Promise(resolve => { release = resolve; });
        const clearing = search('alpha'); await search('');
        release([row('alpha')]); await clearing;
        const clearedSearchStaysEmpty = results.children.length === 0;
        allMessages = async () => [row('alpha')];
        ownSessions = () => new Promise(resolve => { release = resolve; });
        const staleTitles = search('alpha'); await Promise.resolve();
        ownSessions = originalSessions;
        allMessages = async () => [row('beta')]; await search('beta');
        release([]); await staleTitles;
        const delayedTitlesIgnored = results.children.length === 1 && !results.textContent.includes('alpha');
        allMessages = () => new Promise(resolve => { release = resolve; });
        const switched = search('alpha'); const oldRow = row('alpha');
        currentUid = 'qa-other-owner'; release([oldRow]); await switched;
        const accountSwitchIgnoresPending = results.children.length === 0;
        currentUid = originalOwner;
        const clearedCache = search('alpha'); storageGeneration++;
        release([row('alpha')]); await clearedCache;
        const cacheResetIgnoresPending = results.children.length === 0;
        return { printIdentity, latestQueryWins, historyIdentity, clearedSearchStaysEmpty,
          delayedTitlesIgnored, accountSwitchIgnoresPending, cacheResetIgnoresPending };
      } finally { allMessages = originalMessages; ownSessions = originalSessions; currentUid = originalOwner; }
    }));
    assert(Object.values(checks).every(Boolean), JSON.stringify(checks));
    assert.deepEqual(errors, []);
    const report = { checks, errors, note: 'Chrome mobile viewport, real app/IndexedDB/downloads. Clipboard, sharing, print transports and search delays simulated; no OS print or clipboard integration claimed.' };
    fs.writeFileSync('qa-artifacts/ui-bugs-20261021/controls-check.json', JSON.stringify(report, null, 2));
    console.log(JSON.stringify(report));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
