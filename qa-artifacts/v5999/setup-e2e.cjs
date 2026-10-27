async page => {
 await page.evaluate(()=>{
  sessionStorage.setItem('research-qa-config',JSON.stringify({version:'v5999',inference_policy:'configured-free-only-no-paid-fallback',cases:[
   ['technical','Pesquisa profunda sobre qual é o peso da Nikon Z f com bateria e cartão e qual bateria utiliza.'],
   ['multifacet','Pesquisa profunda sobre como usar Object.entries, qual a sintaxe, comportamento e valor retornado.'],
   ['table-numbers','Pesquisa profunda sobre qual o peso da Nikon Z8 com bateria e cartão e qual bateria utiliza.'],
   ['insufficient','Pesquisa profunda sobre quantas pessoas entraram ontem na Biblioteca Pública do Estado da Bahia, segundo registro público.'],
   ['deep-flow','Pesquisa profunda sobre como usar sqlite3.connect, qual a sintaxe, comportamento, valor retornado e limitações.'],
   ['images','Pesquise imagens da Ponte Estaiada de São Paulo.'],
   ['cancel','Pesquisa profunda sobre armazenamento de energia térmica e limitações.']
  ]}));sessionStorage.setItem('v5992-next','0');
 });
 return {cases:7,scope:'Disposable authenticated real-agent QA'};
}
