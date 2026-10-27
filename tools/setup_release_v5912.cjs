async page => {
  if(!page.url().startsWith('http://127.0.0.1:'))throw Error('Loopback QA only');
  await page.evaluate(()=>{
    sessionStorage.setItem('research-qa-config',JSON.stringify({version:'v5912',inference_policy:'configured-free-only-no-paid-fallback',cases:[
      ['gerdau','Pesquisa profunda sobre quem fundou a Gerdau, quando foi fundada e quais produtos fabrica.'],
      ['natura','Pesquisa profunda sobre quem fundou a Natura, em que ano foi fundada e quais produtos fabrica.'],
      ['company','Pesquisa profunda sobre quem fundou a WEG, em que ano foi fundada e quais produtos fabrica.'],
      ['new-company','Pesquisa profunda sobre quem fundou a Acer, quando foi fundada e quais produtos fabrica.']
    ]}));
    sessionStorage.setItem('v5992-next','0');
  });return {cases:4,scope:'ONE_ATTEMPT_PER_CASE_AFTER_REPRODUCED_FIXES'};
}
