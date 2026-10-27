async page => {
  if (!page.url().startsWith('http://127.0.0.1:')) throw Error('Loopback QA only');
  await page.route('https://example.org/qa-focus.svg',route=>route.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="80" height="80"><rect width="80" height="80" fill="teal"/></svg>'}));
  await page.evaluate(()=>{
    document.getElementById('qa-focus-root')?.remove();
    const host=document.createElement('section');host.id='qa-focus-root';document.body.appendChild(host);
    const msg=JDUI.validateMessage({version:'JULIA-ui-message/v1',blocks:[{type:'ui',component:'media',props:{items:[{type:'image',title:'Controle de foco QA',url:'https://example.org/qa-focus.svg'}]}}]});
    if (!msg.ok) throw Error(msg.erros.join(';'));
    window.__qaRemount=()=>{host.replaceChildren();JDUI.mount(host,[msg.msg],{ownerId:'qa',conversationId:'qa-focus',messageId:'qa-focus-message'});};
    window.__qaRemount();
  });
  const opener=page.locator('#qa-focus-root .jdui-media-zoom');
  await opener.click();
  await page.keyboard.press('Escape');
  await page.locator('.jdui-image-dialog').waitFor({state:'detached'});
  const normal=await opener.evaluate(n=>n===document.activeElement);
  await opener.click();
  await page.evaluate(()=>{window.__qaOldOpener=document.querySelector('#qa-focus-root .jdui-media-zoom');window.__qaRemount();});
  await page.keyboard.press('Escape');
  await page.locator('.jdui-image-dialog').waitFor({state:'detached'});
  const remount=await opener.evaluate(n=>n===document.activeElement);
  const detached=await page.evaluate(()=>!window.__qaOldOpener.isConnected);
  await page.locator('#qa-focus-root').evaluate(n=>n.remove());
  if (!normal || !remount || !detached) throw Error('Gallery focus regression: '+JSON.stringify({normal,remount,detached}));
  return {scope:'REAL_CHROME_CONTROLLED_ASSET_AND_REMOUNT',normal,remount,old_opener_detached:detached};
}
