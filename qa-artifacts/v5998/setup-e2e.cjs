async page => {
  await page.evaluate(()=>{
    sessionStorage.setItem('research-qa-config',JSON.stringify({version:'v5998',inference_policy:'configured-free-only-no-paid-fallback',cases:[
      ['technical','Pesquisa profunda sobre como usar Math.hypot, qual a sintaxe, comportamento e valor retornado.'],
      ['full-new','Pesquisa profunda sobre como funciona Array.prototype.flat, qual a sintaxe, comportamento, valor retornado e limitações.'],
      ['images','Pesquise imagens da Ponte Estaiada de São Paulo.'],
      ['cancel','Pesquisa profunda sobre armazenamento de energia térmica e limitações.']
    ]}));
    sessionStorage.setItem('v5992-next','0');
  });
  return {scope:'V5998_REAL_AGENT_QA',cases:4};
}
