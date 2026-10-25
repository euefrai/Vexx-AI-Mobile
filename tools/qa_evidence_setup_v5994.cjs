async page => {
  if (!page.url().startsWith('http://127.0.0.1:')) throw Error('Disposable localhost QA only');
  const config = {version:'v5994',inference_policy:'single-authorized-free-model-attempt-no-paid-fallback',
    cases:[['company-order','Pesquisa profunda sobre quem fundou a Tramontina, em que ano e quais produtos ela fabrica, com evidências para cada aspecto.']]};
  await page.evaluate(value=>{
    sessionStorage.setItem('research-qa-config',JSON.stringify(value));
    sessionStorage.setItem('v5992-next','0');
  },config);
  return {configured:true,case_count:config.cases.length};
}
