async page => {
  if (!page.url().startsWith('http://127.0.0.1:')) throw Error('Disposable localhost QA only');
  const message=page.locator('.message.ai').last();
  const cards=message.locator('.jdui-srccard');
  await cards.first().waitFor({state:'visible'});
  const links=await cards.locator('a').evaluateAll(nodes=>nodes.map(a=>({text:a.innerText,url:a.href,target:a.target})));
  const sourceText=await cards.allInnerTexts();
  const expected=links.filter(l=>l.url.startsWith('https://developer.mozilla.org/'));
  if (!expected.length)throw Error('Real source link missing');
  const popup=page.waitForEvent('popup');
  await cards.locator('a').filter({hasText:expected[0].text}).first().click();
  const opened=await popup;await opened.waitForLoadState('domcontentloaded');
  const openedUrl=opened.url();await opened.close();
  if (!openedUrl.startsWith('https://developer.mozilla.org/'))throw Error('Unexpected source destination');
  const connectionBefore=await page.getByRole('textbox',{name:'Mensagem',exact:true}).isEnabled();
  await page.context().setOffline(true);
  let offlineRejected=false;
  try {
    offlineRejected=await page.evaluate(async()=>{try {await fetch('/api/health');return false;}catch{return true;}});
  } finally {await page.context().setOffline(false);}
  const restored=await page.evaluate(async()=>(await fetch('/api/health')).status);
  return {scope:'REAL_CHROME_SEEDED_PUBLIC_SOURCE_DELIVERY',source_cards:await cards.count(),
    links,source_text:sourceText,opened_url:openedUrl,network_failure_observed:offlineRejected,
    health_after_reconnect:restored,composer_enabled_before_offline:connectionBefore,
    limits:['Fetch rejection is a transport negative test; no claim that every offline UI flow was exercised.']};
}
