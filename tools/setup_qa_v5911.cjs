async page => {
 if(!page.url().startsWith('http://127.0.0.1:'))throw Error('Loopback QA only');
 await page.evaluate(()=>{
  sessionStorage.setItem('research-qa-config',JSON.stringify({version:'v5911',inference_policy:'configured-free-only-no-paid-fallback',cases:[
   ['hello','Oi, tudo bem?'],
   ['factual','Pesquise quem escreveu Capitães da Areia e em que ano foi publicado.'],
   ['company','Pesquisa profunda sobre quem fundou a WEG, em que ano e quais produtos ela fabrica.'],
   ['history','Pesquisa profunda sobre as causas e consequências da Revolta da Vacina.'],
   ['news','Pesquise notícias de Teixeira de Freitas nos últimos sete dias.'],
   ['comparison','Pesquisa profunda sobre compare Nikon Z8 e Nikon Z f quanto ao peso com bateria e cartão e bateria utilizada.'],
   ['full','Pesquisa profunda sobre quem fundou a Adidas, em que ano foi fundada e quais produtos fabrica.'],
   ['images','Pesquise imagens da Ponte Estaiada de São Paulo.'],
   ['cancel','Pesquisa profunda sobre armazenamento de energia térmica e limitações.']
  ]}));sessionStorage.setItem('v5992-next','0');
 });return {cases:9};
}
