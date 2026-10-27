async page => {
  if(!page.url().startsWith('http://127.0.0.1:'))throw Error('Loopback QA only');
  await page.evaluate(()=>{
    sessionStorage.setItem('research-qa-config',JSON.stringify({version:'v5912',inference_policy:'configured-free-only-no-paid-fallback',cases:[
      ['company','Pesquisa profunda sobre quem fundou a WEG, em que ano foi fundada e quais produtos fabrica.'],
      ['independent','Pesquisa profunda sobre quem fundou a Gerdau, quando foi fundada e quais produtos fabrica.'],
      ['independent-two','Pesquisa profunda sobre quem fundou a Sega, em que ano foi fundada e quais produtos fabrica.'],
      ['independent-three','Pesquisa profunda sobre quem fundou a Natura, em que ano foi fundada e quais produtos fabrica.'],
      ['history','Pesquisa profunda sobre quais foram as causas e as consequências da Guerra do Contestado.'],
      ['technical','Pesquisa profunda sobre como usar Math.trunc, qual a sintaxe e qual o valor retornado.'],
      ['cancel','Pesquisa profunda sobre transmissão de energia elétrica e limitações.']
    ]}));
    sessionStorage.setItem('v5992-next','0');
  });return {cases:7};
}
