async page => {
  const cases = [
    ['museum', 'Pesquisa profunda sobre a história do Museu do Amanhã fontes oficiais e data de inauguração.'],
    ['company', 'Pesquisa profunda sobre a história da empresa WEG fontes primárias.'],
    ['technical', 'Pesquisa profunda sobre asyncio.TaskGroup documentação oficial exemplos e limitações.'],
    ['images', 'Pesquise imagens da Ponte Estaiada de São Paulo.'],
    ['cancel', 'Pesquisa profunda sobre tecnologias de armazenamento de energia e limitações.']
  ];
  const index = await page.evaluate(() => Number(sessionStorage.getItem('v5992-next') || 0));
  if (index >= cases.length) return {complete: true};
  const [name, query] = cases[index], errors = [];
  const onError = e => errors.push(e.message);
  page.on('pageerror', onError);
  try {
    if (await page.locator('.message').count()) {
      if (!(await page.locator('#newChatCta').isVisible())) await page.locator('#drawerOpen').click();
      await page.locator('#newChatCta').click();
    }
    const start = Date.now();
    await page.getByRole('textbox', {name: 'Mensagem', exact: true}).fill(query);
    const pending = page.waitForResponse(r => r.url().includes('/api/ai/stream') && r.request().method() === 'POST');
    await page.getByRole('button', {name: 'Enviar', exact: true}).click();
    const response = await pending;
    await page.locator('.message.ai').last().waitFor({state: 'visible', timeout: 15000});
    await page.locator('#stopGen').waitFor({state: 'hidden', timeout: 110000});
    const initial = await page.locator('.message.ai').last().innerText();
    const job = (initial.match(/id (rj-[a-z0-9]+)/) || [])[1];
    let status = null;
    if (job) {
      if (name === 'cancel') await page.locator('#researchCancel').click();
      if (name === 'technical') await page.reload();
      const deadline = Date.now() + 140000;
      do {
        status = await page.evaluate(async id => (await (await fetch('/api/research/status?job_id=' + encodeURIComponent(id))).json()).resumo, job);
        if (['concluida', 'cancelada', 'falhou', 'interrompida'].includes(status?.status)) break;
        await new Promise(resolve => setTimeout(resolve, 2500));
      } while (Date.now() < deadline);
      if (status?.chat_result_id) await page.locator('.message.ai').getByText('Resultado da pesquisa', {exact: true}).last().waitFor({state: 'visible', timeout: 20000});
    }
    const messages = await page.locator('.message.ai').allInnerTexts();
    const stored = await page.locator('.message.ai').evaluateAll(nodes => nodes.map(n => ({id: n.dataset.mid, text: JSON.parse(n._renderSignature)[0]})));
    const sources = await page.locator('.message.ai .jdui-srccard').allInnerTexts();
    const links = await page.locator('.message.ai .jdui-srccard a').evaluateAll(nodes => nodes.map(a => ({text: a.innerText, url: a.href})));
    const media = await page.locator('.message.ai .jdui-media-grid .jdui-pcard').count();
    await page.screenshot({path: 'qa-artifacts/v5992/chat-' + name + '.png', fullPage: true});
    await page.reload();
    await page.locator('#loginOverlay').waitFor({state: 'hidden'});
    await page.locator('[data-mid="' + stored.at(-1).id + '"]').waitFor({state: 'visible', timeout: 20000});
    const after = await page.locator('.message.ai').allInnerTexts();
    const restored = await page.locator('.message.ai').evaluateAll(nodes => nodes.map(n => ({id: n.dataset.mid, text: JSON.parse(n._renderSignature)[0]})));
    if (JSON.stringify(stored) !== JSON.stringify(restored)) throw Error('Persisted message IDs/text changed after reload');
    await page.evaluate(n => sessionStorage.setItem('v5992-next', String(n)), index + 1);
    return {scope: 'AUTHENTICATED_E2E_LOCAL_REAL_AGENT', name, query, seconds: (Date.now() - start) / 1000,
      http_status: response.status(), content_type: response.headers()['content-type'], job: job || null,
      job_state: status?.status || null, job_mode: status?.modo || null, outcome: status?.usados?.research_outcome || null,
      synthesis_llm: status?.sintese?.llm || false, chat_result_id: status?.chat_result_id || null,
      assistant_messages: after.length, reload_preserved: true, source_cards: sources, links, media_cards: media,
      public_answer: after.at(-1), page_errors: errors};
  } finally { page.removeListener('pageerror', onError); }
}
