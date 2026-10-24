async page => {
  if(await page.locator('#loginOverlay').isVisible()){
    await page.getByRole('textbox',{name:'Usuário',exact:true}).fill('alice');
    await page.getByRole('textbox',{name:'Senha',exact:true}).fill('qa-password-long-5981');
    await page.locator('#loginButton').click();
    await page.locator('#loginOverlay').waitFor({state:'hidden'});
  }
  const query='Pesquisa profunda sobre notícias em Angola nos últimos sete dias';
  await page.getByRole('textbox',{name:'Mensagem',exact:true}).fill(query);
  await page.getByRole('button',{name:'Enviar',exact:true}).click();
  await page.locator('.message.ai').last().waitFor({state:'visible',timeout:15000});
  await page.locator('#stopGen').waitFor({state:'hidden',timeout:60000});
  const text=await page.locator('.message.ai').last().innerText();
  const job=(text.match(/id (rj-[a-z0-9]+)/)||[])[1];
  if(job)await page.evaluate(id=>sessionStorage.setItem('v5991-job',id),job);
  return {scope:'AUTHENTICATED_E2E_LOCAL_REAL_AGENT',query,job_id:job||null,answer:text.slice(0,500)};
}
