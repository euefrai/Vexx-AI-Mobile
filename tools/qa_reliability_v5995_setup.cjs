async page => {
  if (!page.url().startsWith('http://127.0.0.1:')) throw Error('Disposable localhost QA only');
  await page.evaluate(() => {
    sessionStorage.setItem('research-qa-config', JSON.stringify({
      version: 'v5995', inference_policy: 'configured-free-model-no-paid-fallback', cases: [
        ['technical', 'Pesquisa profunda sobre como funciona WebAssembly.Table.grow, qual a sintaxe, o valor retornado e as limitações. Use documentação original e diferencie o tamanho anterior do tamanho final.'],
        ['company', 'Pesquisa profunda sobre quem fundou a Intel, em que ano e quais produtos fabrica. Use fontes originais e indique aspectos não confirmados.'],
        ['cancel', 'Pesquisa profunda sobre armazenamento de energia térmica, aplicações industriais e limitações atuais.']
      ]
    }));
    sessionStorage.setItem('v5992-next','0');
  });
  return {configured:3,scope:'AUTONOMOUS_DISCOVERY_PUBLIC_QUESTIONS_NO_SEEDED_URLS'};
}
