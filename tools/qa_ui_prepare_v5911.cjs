async page => {
  if (!page.url().startsWith('http://127.0.0.1:')) throw Error('Disposable localhost QA only');
  if (await page.locator('#loginOverlay').isVisible()) {
    await page.getByRole('textbox', {name:'Usuário',exact:true}).fill('alice');
    await page.getByRole('textbox', {name:'Senha',exact:true}).fill('qa-password-long-5981');
    await page.getByRole('button', {name:'Entrar ↗',exact:true}).click();
    await page.locator('#loginOverlay').waitFor({state:'hidden'});
  }
  await page.evaluate(()=>sessionStorage.setItem('research-qa-config',JSON.stringify({version:'v5911'})));
  await page.getByRole('button',{name:/^Pesquisa profunda sobre quem fundou a WEG/}).waitFor({state:'visible'});
  return {scope:'EXISTING_QA_CHATS_NO_NEW_INFERENCE'};
}
