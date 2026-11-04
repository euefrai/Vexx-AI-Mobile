'use strict';
(() => {
  const $ = id => document.getElementById(id);
  let csrf = '', expiryTimer;
  async function request(path, method='GET') {
    const response = await fetch(path,{method,headers:{'X-CSRF-Token':csrf}});
    const data = await response.json();
    if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'Não foi possível concluir.');
    return data;
  }
  async function state() {
    const data=await request('/api/companion/status');
    $('companion-device').textContent=data.linked ? data.active ? 'Computador: '+data.name+' · '+(data.online?'conectado':'offline') : 'Vínculo revogado. Gere outro código para conectar novamente.' : 'Nenhum computador vinculado.';
    $('companion-unlink').hidden=!data.active;
  }
  $('companion-generate').onclick=async()=>{
    $('companion-generate').disabled=true;
    try{
      const data=await request('/api/companion/pair','POST');
      $('companion-code').textContent='Código: '+data.code+' · endereço: '+location.origin+' · válido por 3 minutos';
      clearTimeout(expiryTimer);expiryTimer=setTimeout(()=>{$('companion-code').textContent='Código expirado. Gere outro para vincular.';},data.expires_in*1000);
    }catch(e){$('companion-code').textContent=e.message;}finally{$('companion-generate').disabled=false;}
  };
  $('companion-unlink').onclick=async()=>{
    if(!confirm('Desvincular seu computador e revogar a credencial de acesso?'))return;
    try{await request('/api/companion/unlink','POST');clearTimeout(expiryTimer);$('companion-code').textContent='Computador desvinculado.';await state();}catch(e){$('companion-code').textContent=e.message;}
  };
  (async()=>{
    try{
      const session=await request('/api/session');
      if(!session.authenticated)throw new Error('Entre na sua conta no Vexx AI para gerar o código.');
      csrf=session.csrf;$('companion-account').textContent='Conta: '+session.user;$('companion-generate').disabled=false;
      await state();
      setInterval(()=>{if(!document.hidden)state().catch(e=>{$('companion-device').textContent=e.message;});},10000);
    }catch(e){$('companion-account').textContent=e.message;}
  })();
})();
