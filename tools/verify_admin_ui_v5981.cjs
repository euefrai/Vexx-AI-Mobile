async page => {
  const out='qa-artifacts/v5981';
  const metrics=[];let alerts=0;let errors=[];
  page.on('dialog',async dialog=>{alerts++;await dialog.dismiss();});
  page.on('pageerror',error=>errors.push(error.message));
  await page.getByLabel('Usuário',{exact:true}).fill('alice');
  await page.getByLabel('Senha',{exact:true}).fill('qa-password-long-5981');
  await page.getByRole('button',{name:'Entrar',exact:true}).click();
  await page.getByRole('button',{name:'Autorizar console',exact:true}).waitFor();
  await page.getByLabel('Senha',{exact:true}).fill('qa-password-long-5981');
  await page.getByRole('button',{name:'Autorizar console',exact:true}).click();
  await page.getByRole('tab',{name:'Visão geral',exact:true}).waitFor();
  await page.reload();await page.getByRole('tab',{name:'Visão geral',exact:true}).waitFor();
  for (const width of [1280,390,320]) {
    await page.setViewportSize({width,height:900});
    await page.getByRole('tab',{name:'Visão geral',exact:true}).click();
    await page.screenshot({path:`${out}/admin-${width}.png`,fullPage:true});
    await page.getByRole('tab',{name:'Usuários',exact:true}).click();
    const data=await page.evaluate(()=>({width:innerWidth,root:document.documentElement.scrollWidth,
         table:document.querySelector('#users .table-wrap').scrollWidth}));
    if(data.root>data.width)throw Error('Page overflow '+JSON.stringify(data));metrics.push(data);
    if(!(await page.getByText('<svg/onload=alert(1)>',{exact:true}).isVisible()))throw Error('XSS fixture missing');
    if(await page.locator('svg[onload]').count())throw Error('Unsafe user HTML executed');
    if(width===390)await page.screenshot({path:`${out}/admin-users-390.png`,fullPage:true});
  }
  await page.evaluate(()=>document.body.style.zoom='2');
  const zoom=await page.evaluate(()=>({width:innerWidth,root:document.documentElement.scrollWidth}));
  if(zoom.root>zoom.width)throw Error('Zoom overflow');
  await page.screenshot({path:`${out}/admin-zoom-200.png`,fullPage:true});
  await page.evaluate(()=>document.body.style.zoom='1');
  const tab=page.getByRole('tab',{name:'Usuários',exact:true});await tab.focus();await page.keyboard.press('ArrowRight');
  if(await page.getByRole('tab',{name:'Pesquisas',exact:true}).getAttribute('aria-selected')!=='true')throw Error('Keyboard navigation');
  await tab.click();
  await page.getByRole('button',{name:'Limites: bob',exact:true}).click();
  await page.getByLabel('Respostas por hora (0 = sem limite)',{exact:true}).fill('20');
  await page.getByLabel('Respostas simultâneas (0 = sem limite)',{exact:true}).fill('2');
  await page.getByLabel('Digite o username da conta para confirmar',{exact:true}).fill('bob');
  await page.getByRole('button',{name:'Confirmar',exact:true}).click();
  await page.getByRole('dialog').waitFor({state:'hidden'});
  await page.getByRole('button',{name:'Revogar sessões: bob',exact:true}).click();
  await page.getByRole('button',{name:'Cancelar',exact:true}).click();
  await page.getByRole('dialog').waitFor({state:'hidden'});
  await page.getByRole('link',{name:'Voltar ao chat',exact:true}).click();
  await page.locator('#loginOverlay').waitFor({state:'hidden'});
  await page.getByRole('textbox',{name:'Mensagem',exact:true}).fill('/admin');
  await page.getByRole('button',{name:'Enviar',exact:true}).click();
  await page.waitForURL('**/admin');await page.getByRole('tab',{name:'Visão geral',exact:true}).waitFor();
  await page.getByRole('button',{name:'Bloquear console',exact:true}).click();
  await page.getByRole('button',{name:'Autorizar console',exact:true}).waitFor();
  if(await page.locator('#console').isVisible())throw Error('Lock did not clear private content');
  const report={scope:'Real Chrome + actual local FastAPI/PC Agent WSS + temporary SQLite, QA accounts; no production admin deployment',
      metrics,zoom,alerts,page_errors:errors,reload:true,keyboard:true,xss_escaped:true,
      limits_confirmed:true,cancel_dialog:true,chat_admin_navigation:true,locked:true};
  if(alerts||errors.length)throw Error(JSON.stringify(report));
  return report;
}
