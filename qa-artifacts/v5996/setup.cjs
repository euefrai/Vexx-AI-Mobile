async page => {
 await page.evaluate(()=>{
 sessionStorage.setItem('research-qa-config',JSON.stringify({version:'v5996',inference_policy:'cancel-before-research-completion',cases:[['cancel','Pesquisa profunda sobre baterias térmicas e limitações.']]}));
 sessionStorage.setItem('v5992-next','0');
 });
 return {cases:1};
}