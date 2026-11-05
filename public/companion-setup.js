"use strict";
(() => {
  const $ = id => document.getElementById(id);
  if (!$('companion-identity-form')) return;
  let csrf='', user='', configured=false, busy=false, identityLoaded=false;
  async function request(path,method='GET',body) {
    const response=await fetch(path,{method,headers:{'X-CSRF-Token':csrf,...(body?{'Content-Type':'application/json'}:{})},...(body?{body:JSON.stringify(body)}:{})});
    const data=await response.json();
    if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'Não foi possível concluir.');
    return data;
  }
  function notice(text){$('companion-identity-state').textContent=text;}
  async function status(){
    const data=await request('/api/companion/status');
    $('companion-device').textContent=data.linked?(data.active?'Computador: '+data.name+' · '+(data.online?'conectado':'offline'):'Computador desvinculado. Conecte o aplicativo com seu nick e PIN.'):'Nenhum computador vinculado.';
    $('companion-unlink').hidden=!data.active;
  }
  async function credentials(){
    const data=await request('/api/companion/identity');configured=data.configured;identityLoaded=true;$('companion-editor').open=!configured;
    $('companion-nick').value=data.nick||'';$('companion-pin').value='';
    $('companion-delete').hidden=!configured;
    $('companion-pin').placeholder=configured?'PIN salvo · digite para trocar':'6 a 12 números';
    notice(configured?'Nick salvo: '+data.nick+' · PIN definido, sem prazo de expiração.':'Crie seu nick e PIN para conectar o aplicativo.');
  }
  async function session(){
    if(busy)return;
    try{
      const data=await request('/api/session');
      const next=data.authenticated?String(data.user):'';csrf=data.csrf||'';
      $('companion-save').disabled=!next;
      $('companion-account').textContent=next?'Conta: '+next:'Entre na sua conta Vexx AI para criar ou alterar o nick e PIN.';
      if(next!==user){user=next;configured=false;identityLoaded=false;$('companion-nick').value='';$('companion-pin').value='';$('companion-delete').hidden=true;$('companion-unlink').hidden=true;$('companion-device').textContent='';notice('');}
      if(user&&!identityLoaded)await credentials();
      if(user)await status();
    }catch(e){notice(e.message);}
  }
  $('companion-identity-form').onsubmit=async e=>{
    e.preventDefault();if(!user||busy)return;
    if(configured&&!confirm('Salvar novas credenciais desconecta o computador atual. Continuar?'))return;
    busy=true;$('companion-save').disabled=true;
    try{await request('/api/companion/identity','POST',{nick:$('companion-nick').value.trim(),pin:$('companion-pin').value});await credentials();await status();notice('Nick e PIN salvos. Use os mesmos dados no aplicativo Vexx PC.');}
    catch(e){notice(e.message);}finally{busy=false;$('companion-save').disabled=!user;}
  };
  $('companion-delete').onclick=async()=>{
    if(!user||busy||!confirm('Apagar seu nick e PIN e desconectar o computador atual?'))return;
    busy=true;try{await request('/api/companion/identity','DELETE');await credentials();await status();notice('Nick e PIN apagados. O computador foi desconectado.');}catch(e){notice(e.message);}finally{busy=false;}
  };
  $('companion-unlink').onclick=async()=>{
    if(!confirm('Desvincular o computador? Seu nick e PIN serão mantidos.'))return;
    try{await request('/api/companion/unlink','POST');await status();notice('Computador desvinculado. Nick e PIN mantidos.');}catch(e){notice(e.message);}
  };
  session();setInterval(()=>{if(!document.hidden)session();},10000);
})();
