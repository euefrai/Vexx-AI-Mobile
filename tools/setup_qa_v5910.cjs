async page => {
  if (!page.url().startsWith('http://127.0.0.1:')) throw Error('Disposable QA only');
  await page.evaluate(()=>{
    sessionStorage.setItem('research-qa-config',JSON.stringify({version:'v5910',inference_policy:'configured-free-only-no-paid-fallback',cases:[
      ['hello','Oi, tudo bem?'],
      ['normal','Pesquise quem escreveu Vidas Secas e em que ano foi publicado.'],
      ['company','Pesquisa profunda sobre quem fundou a WEG, em que ano e quais produtos ela fabrica.'],
      ['comparison','Pesquisa profunda sobre compare Nikon Z f e Nikon Z8 quanto ao peso com bateria e cartão e bateria utilizada.'],
      ['news','Pesquise notícias de Feira de Santana nos últimos sete dias, sem misturar Salvador.'],
      ['scarce','Pesquisa profunda sobre quantas pessoas entraram ontem na Biblioteca Pública do Estado da Bahia, segundo registro público.'],
      ['full','Pesquisa profunda sobre as causas e consequências da Revolução dos Cravos e divergências entre fontes históricas.'],
      ['images','Pesquise imagens da Ponte Estaiada de São Paulo.'],
      ['cancel','Pesquisa profunda sobre armazenamento de energia térmica e limitações.']
    ]}));
    sessionStorage.setItem('v5992-next','0');
  });
  return {cases:9};
}
