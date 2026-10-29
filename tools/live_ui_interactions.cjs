// Additional real UI checks on the existing disposable local QA conversation.
async (page) => {
  if(!/^http:\/\/127\.0\.0\.1:\d+\//.test(page.url()))throw Error('Local QA required');
  const errors=[];page.on('pageerror',e=>errors.push(String(e)));
  const order=page.getByRole('combobox',{name:'Ordenar produtos',exact:true}).first();
  await order.selectOption({label:'Nome A–Z'});
  const sorted=await order.inputValue();
  const references=page.locator('.jdui-provenance summary').first();
  await references.click();
  const referencesOpened=await references.locator('..').getAttribute('open')!==null;
  const sourceLinks=await references.locator('..').locator('a[href]').count();
  await page.setViewportSize({width:390,height:900});
  await page.getByRole('button',{name:'Abrir menu',exact:true}).click();
  await page.waitForFunction(()=>Math.abs(document.querySelector('.drawer').getBoundingClientRect().left)<1);
  const account=page.getByRole('button',{name:'Ajustes e conta',exact:true});
  const hit=await account.evaluate(el=>{
    const r=el.getBoundingClientRect();return el.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2));
  });
  await account.click();
  await page.getByRole('heading',{name:'Configurações.',exact:true}).waitFor({state:'visible'});
  const settingsVisible=await page.locator('#page-settings').isVisible();
  await page.waitForFunction(()=>document.querySelector('.drawer').getBoundingClientRect().right<=0);
  await page.screenshot({path:'output/real-ui/settings-390.png'});
  await page.getByRole('button',{name:'Abrir menu',exact:true}).click();
  await page.getByRole('button',{name:'Oi Lucas, explique em duas frases o que é um',exact:true}).first().click();
  await page.waitForFunction(()=>document.querySelector('#drawerOpen').getAttribute('aria-expanded')==='false');
  await page.reload();
  await page.getByRole('combobox',{name:'Ordenar produtos',exact:true}).first().waitFor({state:'attached'});
  const persisted=await page.getByRole('combobox',{name:'Ordenar produtos',exact:true}).first().inputValue();
  const first=page.locator('.jdui-pcard').first();
  await first.evaluate(el=>el.scrollIntoView({block:'start'}));
  const action=first.getByRole('link',{name:'Abrir oferta ↗',exact:true});
  const actionStyle=await action.evaluate(el=>{const s=getComputedStyle(el);return {color:s.color,background:s.backgroundImage};});
  await page.screenshot({path:'output/real-ui/interaction-390.png'});
  const geometry=[];
  for(const width of [320,390,1280]){
    await page.setViewportSize({width,height:900});
    await page.waitForFunction(()=>{const r=document.querySelector('.drawer').getBoundingClientRect();return innerWidth>=900 ? Math.abs(r.left)<1 : r.right<=0;});
    await page.locator('.jdui-title').first().evaluate(el=>el.scrollIntoView({block:'start'}));
    geometry.push(await page.evaluate(()=>({width:innerWidth,documentWidth:document.documentElement.scrollWidth,
      sidebarLeft:document.querySelector('.drawer').getBoundingClientRect().left})));
    await page.screenshot({path:'output/real-ui/chat-'+width+'.png',animations:'disabled'});
  }
  return {scope:'REAL_LOCAL_UI_INTERACTIONS',mobileMenuHit:hit,settingsVisible,
    referencesOpened,sourceLinks,sortBeforeReload:sorted,sortAfterReload:persisted,
    sortPersisted:sorted===persisted,actionStyle,geometry,errors};
}
