async page => {
 await page.evaluate(()=>{
 sessionStorage.setItem('research-qa-config',JSON.stringify({version:'v5997',inference_policy:'public-images-and-cancellation-no-paid-fallback',cases:[['images','Pesquise imagens da Ponte Estaiada de São Paulo.'],['cancel','Pesquisa profunda sobre armazenamento de energia térmica e limitações.']]}));
 sessionStorage.setItem('v5992-next','0');
 });
 return {cases:2};
}