// Run with playwright-cli run-code, against preview_research_cards.py only.
async (page) => {
  const assert = (value, message) => { if (!value) throw Error(message); };
  assert((await page.title()).includes('QA isolado'), 'Refusing a non-QA page');
  const errors = []; page.on('pageerror', error => errors.push(String(error)));
  page.on('console', message => { if(message.type()==='error') errors.push(message.text()); });
  await page.evaluate(async () => {
    const tx=db.transaction(UISTATE,'readwrite'); const done=txDone(tx);
    tx.objectStore(UISTATE).clear(); await done; localStorage.removeItem('qa-owner');
  });
  await page.emulateMedia({reducedMotion:'no-preference'});
  await page.reload(); await page.waitForFunction(() => window.qa?.ready);
  const sources = page.locator('.jdui-research-sources');
  const cards = sources.locator('.jdui-srccard:visible');
  assert(await cards.count() === 4, 'Four controlled source records');
  await sources.getByRole('button', {name:'Com leitura (2)', exact:true}).click();
  assert(await cards.count() === 2, 'Read filter includes partial, excludes blocked');
  await sources.locator('summary').click();
  await page.getByRole('button', {name:'Tabela', exact:true}).click();
  await page.waitForFunction(() => Object.keys(jduiDirty).length === 0);
  await page.reload(); await page.waitForFunction(() => window.qa?.ready);
  assert(await cards.count() === 2, 'Read filter survives IndexedDB reload');
  assert(await sources.locator('details').getAttribute('open') !== null, 'Source details survive reload');
  assert(await page.locator('.jdui-product-comparison .jdui-scrollx').isVisible(), 'Comparison view survives reload');
  await page.locator('#owner').selectOption('qa-b');
  await page.waitForFunction(() => document.querySelector('[aria-label="Filtrar fontes"] button').getAttribute('aria-pressed') === 'true');
  assert(await cards.count() === 4, 'Account B does not inherit account A filters');
  await sources.getByRole('button', {name:'Sem leitura (2)', exact:true}).click();
  await page.waitForFunction(() => Object.keys(jduiDirty).length === 0);
  await page.locator('#owner').selectOption('qa-a');
  await page.waitForFunction(() => document.querySelector('[aria-label="Filtrar fontes"] button:nth-child(2)').getAttribute('aria-pressed') === 'true');
  assert(await cards.count() === 2, 'Account A retained its own state');
  await sources.getByRole('button', {name:'Comparar fontes', exact:true}).click();
  let prompt = await page.evaluate(() => qa.prompts.at(-1));
  assert(prompt.includes('example.org/warranty') && prompt.includes('example.net/model-b'), 'Follow-up has explicit source URLs');
  assert(!prompt.includes('example.com/pending') && prompt.includes('Leitura parcial'), 'Follow-up respects filter and partial scope');
  await page.evaluate(() => qa.online=false);
  await sources.getByRole('button', {name:'Criar resumo', exact:true}).click();
  assert(await page.evaluate(() => qa.prompts.length) === 1, 'Offline action sends nothing');
  assert((await sources.getByRole('status').innerText()).includes('Conecte'), 'Offline feedback');
  await page.evaluate(() => {qa.online=true;qa.fail=true;});
  await sources.getByRole('button', {name:'Criar resumo', exact:true}).click();
  assert((await sources.getByRole('status').innerText()).includes('Tente novamente'), 'Send failure has retry feedback');
  await page.evaluate(() => {qa.fail=false;qa.pending=true;});
  const summarize = sources.getByRole('button', {name:'Criar resumo', exact:true});
  await summarize.click();
  assert(await summarize.isDisabled(), 'Pending action blocks double click');
  await page.evaluate(() => {qa.pending=false;qa.release();});
  await page.waitForFunction(() => !document.querySelector('.jdui-research-next [aria-busy]'));
  await sources.getByRole('button', {name:'Todas (4)', exact:true}).click();
  await sources.getByRole('button', {name:'Analisar fonte', exact:true}).first().click();
  prompt = await page.evaluate(() => qa.prompts.at(-1));
  assert(prompt.includes('Analise esta fonte:') && prompt.includes('https://example.org/warranty'), 'Source analysis uses exact URL');
  await page.getByRole('button', {name:'Por produto', exact:true}).click();
  const negativeCases = await page.evaluate(() => {
    const render = (items, component='productcompare') => {
      const raw={version:JDUI.version,blocks:[{type:'ui',component,props:{items}}]};
      const validated=JDUI.validateMessage(raw);if(!validated.ok)throw Error(validated.erros.join(';'));
      const root=document.createElement('div');JDUI.mount(root,[validated.msg],{});return root;
    };
    const a={nome:'A',preco:'R$ 100',preco_valor:100,moeda:'BRL'};
    const b={nome:'B',preco:'$ 50',preco_valor:50,moeda:'USD'};
    const mixed=render([a,b]),unknown=render([a,{nome:'Sem preço'}]);
    const empty=render([{titulo:'Sem link',leitura:'FOUND'}, {titulo:'Outra prévia',leitura:'FOUND'}],'sources');
    empty.querySelectorAll('button')[1].click();
    const unsafe=render([{titulo:'<img src=x onerror=alert(1)>',url:'javascript:alert(1)'}],'sources');
    return {mixed:!mixed.querySelector('.win,.is-lowest'), unknown:!unknown.querySelector('.win,.is-lowest'),
      empty:!empty.querySelector('.jdui-research-empty').hidden && [...empty.querySelectorAll('.jdui-srccard')].every(e=>e.hidden),
      safe:!unsafe.querySelector('img,a') && unsafe.textContent.includes('<img src=x')};
  });
  assert(negativeCases.mixed && negativeCases.unknown, 'Different currencies and missing prices cannot create a winner');
  assert(negativeCases.empty && negativeCases.safe, 'Empty filters and unsafe model content have safe rendering');
  const geometry=[];
  for(const width of [320,390,1280]) {
    await page.setViewportSize({width,height:900});
    for(const view of ['Por produto','Tabela']) {
      await page.getByRole('button',{name:view,exact:true}).click();
      const sizes=await page.evaluate(()=>({viewport:innerWidth,document:document.documentElement.scrollWidth,
        cards:[...document.querySelectorAll('.jdui-srccard:not([hidden])')].map(e=>Math.round(e.getBoundingClientRect().width))}));
      assert(sizes.document<=width+1, 'Horizontal page overflow at '+width+' / '+view);
      geometry.push({width,view,...sizes});
    }
    await page.getByRole('button',{name:'Por produto',exact:true}).click();
    await page.screenshot({path:'output/playwright/research-cards-'+width+'.png',fullPage:true});
  }
  await page.setViewportSize({width:1280,height:900});
  await page.evaluate(()=>document.documentElement.style.zoom='2');
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'No overflow at 200% zoom');
  await page.evaluate(()=>document.documentElement.style.zoom='1');
  const filters=sources.getByRole('button',{name:'Com leitura (2)',exact:true});
  await filters.focus();await page.keyboard.press('Enter');
  assert(await cards.count()===2,'Keyboard activates source filter');
  await page.emulateMedia({reducedMotion:'reduce'});
  await page.waitForFunction(()=>matchMedia('(prefers-reduced-motion: reduce)').matches);
  assert(await filters.evaluate(e=>getComputedStyle(e).transitionDuration.split(',').every(v=>parseFloat(v)<0.001)),'Reduced motion');
  assert(errors.length===0,'Browser errors: '+errors.join(';'));
  return {scope:'ISOLATED_BROWSER_CONTROLLED_DATA_ACTUAL_JDUI_AND_INDEXEDDB_NO_MODEL_OR_RELAY',
    passed:true,geometry,consoleErrors:errors,checks:['filters','reload','account-isolation','follow-up-context',
      'offline','retry','pending-send','currency-ranking','mobile','zoom','keyboard','reduced-motion']};
}
