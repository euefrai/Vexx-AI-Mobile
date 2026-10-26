async page => {
  if (!page.url().startsWith('http://127.0.0.1:')) throw Error('Local QA only');
  await page.evaluate(()=>{
    sessionStorage.setItem('research-qa-config',JSON.stringify({version:'v5997',inference_policy:'configured-free-model-no-paid-fallback',cases:[
      ['technical','Pesquisa profunda sobre como usar Object.assign, qual sua sintaxe, comportamento e valor retornado. Use documentação original.'],
      ['company','Pesquisa profunda sobre quando a WEG foi fundada, quem a fundou e quais produtos fabrica.'],
      ['history','Pesquisa profunda sobre as causas e consequências da Revolta da Chibata.'],
      ['local-news','Pesquisa profunda sobre notícias de saúde em Irecê, Bahia, nos últimos sete dias.'],
      ['scarce','Pesquisa profunda sobre quantas pessoas visitaram o Museu Histórico de Jequié ontem, se existir registro público.'],
      ['multisource','Pesquisa profunda sobre como Array.prototype.toSorted funciona, qual a sintaxe e como difere de Array.prototype.sort quanto à alteração do array original. Use documentação original e compare os comportamentos.']
    ]}));
    sessionStorage.setItem('v5992-next','0');
  });
  return {cases:6,scope:'AUTONOMOUS_AUTHENTICATED_NO_SEEDED_URLS'};
}