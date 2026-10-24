'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const panels = ['overview','agents','users','research','models','audit'];
  let csrf = '', uid = '', logged = false, pending = null, expiry = null;
  const text = (tag, value, cls) => { const el=document.createElement(tag); el.textContent=String(value ?? 'Não disponível'); if(cls)el.className=cls; return el; };
  const notice = (value,error=false) => { $('notice').textContent=value; $('notice').dataset.error=String(error); };
  async function api(path, body) {
    const options={credentials:'same-origin',cache:'no-store',headers:{'X-CSRF-Token':csrf}};
    if(body!==undefined){options.method='POST';options.headers['Content-Type']='application/json';options.body=JSON.stringify(body);}
    const res=await fetch(path,options); const data=await res.json().catch(()=>({}));
    if(!res.ok){const err=new Error(typeof data.detail==='string'?data.detail:'Não foi possível completar a operação');err.status=res.status;throw err;}return data;
  }
  function lock(message='Confirme novamente sua senha para continuar.') {
    clearTimeout(expiry); $('console').hidden=true; panels.forEach(id=>$(id).replaceChildren());
    $('confirmDialog').open && $('confirmDialog').close();pending=null;$('confirmName').value='';
    $('authCard').hidden=false;$('usernameRow').hidden=logged;$('authHelp').textContent=logged?'Confirme a senha desta conta. A autorização expira em 10 minutos.':'Use a mesma conta do Vexx AI.';
    $('switchAccount').hidden=!logged;$('authSubmit').textContent=logged?'Autorizar console':'Entrar';$('password').value='';notice(message);
  }
  function card(title, entries) {
    const block=text('div','', 'card');block.append(text('h2',title));const dl=document.createElement('dl');
    entries.forEach(([k,v])=>dl.append(text('dt',k),text('dd',v)));block.append(dl);return block;
  }
  function table(headers, rows) {
    const wrap=text('div','', 'table-wrap');wrap.tabIndex=0;wrap.setAttribute('role','region');wrap.setAttribute('aria-label',headers.join(', '));
    const t=document.createElement('table'),head=document.createElement('thead'),hr=document.createElement('tr');headers.forEach(h=>{const th=text('th',h);th.scope='col';hr.append(th);});head.append(hr);t.append(head);
    const body=document.createElement('tbody');rows.forEach(row=>{const tr=document.createElement('tr');row.forEach(value=>{const td=document.createElement('td');if(value instanceof Node)td.append(value);else td.textContent=String(value??'—');tr.append(td);});body.append(tr);});t.append(body);wrap.append(t);return wrap;
  }
  function render(data, accounts, events) {
    panels.forEach(id=>$(id).replaceChildren());
    const grid=text('div','', 'grid');[['Contas',data.accounts.total],['Administradores',data.accounts.admins],['Ativas e aprovadas',data.accounts.active],['Pesquisas ativas',Object.entries(data.research.statuses).filter(([state])=>!['concluida','falhou','cancelada','interrompida','pausada'].includes(state)).reduce((total,[,count])=>total+count,0)]].forEach(([label,value])=>{const m=text('div','', 'metric');m.append(text('span',label),text('strong',value));grid.append(m);});$('overview').append(grid,card('Conexão', [['PC Agent',data.agent.connected?'Conectado':'Desconectado'],['Backend',/^[a-f0-9]{12,}$/i.test(data.backend||'')?data.backend.slice(0,12):data.backend],['Relay',data.relay],['Erros recentes','Não disponíveis neste resumo']]));
    $('agents').append(card('Agente conectado', [['Papel',data.agent.role],['PID',data.agent.pid],['Estado',data.agent.state],['Uptime',data.agent.uptime_s==null?null:data.agent.uptime_s+' s'],['RAM',data.agent.ram_mb==null?null:data.agent.ram_mb+' MB'],['CPU acumulada',data.agent.cpu_time_s==null?null:data.agent.cpu_time_s+' s']]));
    $('agents').append(text('p','Este painel não encerra processos nem executa comandos no computador. Outros serviços locais não são inventariados pelo relay.'));
    const people=accounts.users||[];const activeAdmins=people.filter(u=>u.role==='admin'&&u.status==='ativo'&&u.aprovado).length;
    const rows=people.map(user=>{const actions=text('div','', 'actions');[['Papel','role'],[user.status==='bloqueado'?'Desbloquear':'Bloquear','status'],['Revogar sessões','sessions'],['Limites','limits']].forEach(([label,action])=>{const b=text('button',label);b.type='button';b.setAttribute('aria-label',label+': '+user.username);b.disabled=(action==='role'||action==='status')&&(user.uid===uid||user.uid==='local'||(user.role==='admin'&&user.status==='ativo'&&activeAdmins<=1));b.addEventListener('click',()=>confirm(user,action));actions.append(b);});return [user.username,user.display,user.role,user.status,user.created_at,user.last_seen||'Não registrada',actions];});
    $('users').append(text('h2','Usuários'),rows.length?table(['Username','Nome','Papel','Status','Criação','Última atividade','Ações'],rows):text('p','Nenhuma conta disponível.'));
    const research=data.research;const rate=research.read_rate==null?'Sem fontes registradas':(100*research.read_rate).toFixed(1)+'%';
    $('research').append(card('Cobertura de leitura',[['Fontes registradas',research.sources],['Fontes marcadas como lidas',research.read_sources],['Taxa de leitura',rate]]),card('Estados dos jobs',Object.entries(research.statuses)),card('Resultado das investigações',Object.entries(research.outcomes)),text('p','Job concluído não significa síntese validada. A taxa usa flags de leitura; não mede suporte científico das afirmações.'));
    $('models').append(card('Inferência',[['Modelo configurado',data.model.configured],['Disponibilidade','Não verificada nesta consulta'],['Estado',data.model.inference],['Circuit breaker','Não informado pelo provedor'],['Rate limit','Não informado pelo provedor']]));
    const providers=Object.entries(data.providers||{}).map(([name,p])=>[name,p.chamadas,p.ok,p.vazio,JSON.stringify(p.erros||{})]);$('models').append(providers.length?table(['Fonte','Chamadas','Sucesso','Vazio','Códigos de erro'],providers):text('p','Nenhuma métrica de fonte registrada neste processo.'));
    $('audit').append(text('h2','Eventos administrativos'),events.events?.length?table(['Horário','Ator','Ação','Alvo'],events.events.map(e=>[e.ts,e.actor,e.action,e.target])):text('p','Nenhum evento registrado.'));
    $('authCard').hidden=true;$('console').hidden=false;notice('Acesso administrativo autorizado.');
    clearTimeout(expiry);expiry=setTimeout(()=>lock('Autorização expirada. Confirme sua senha.'),Math.max(0,Number(data.admin_expires_in)||0)*1000);
  }
  async function load(first) {
    $('console').classList.add('loading');$('refresh').disabled=true;notice('Carregando dados do PC Agent…');
    try {
      const data=first||await api('/api/admin/overview');
      const results=await Promise.allSettled([api('/api/admin/users'),api('/api/admin/audit')]);
      const failed=results.find(r=>r.status==='rejected');if(failed)throw failed.reason;
      render(data,results[0].value,results[1].value);
    } catch(err){if(err.status===401){logged=false;csrf='';uid='';}lock(err.message);notice(err.message,true);}
    finally{$('console').classList.remove('loading');$('refresh').disabled=false;}
  }
  async function init() {
    try {const session=await api('/api/session');csrf=session.csrf;uid=session.uid;logged=true;await api('/api/admin/access');const data=await api('/api/admin/overview');await load(data);}
    catch(err){if(err.status===401){logged=false;csrf='';uid='';}lock(err.status===401?'Entre com sua conta para continuar.':err.message);if(err.status!==401)notice(err.message,true);}
  }
  $('switchAccount').addEventListener('click',async()=>{try{await api('/api/logout',{});logged=false;csrf='';uid='';lock('Entre com outra conta.');}catch(err){notice(err.message,true);}});
  $('authForm').addEventListener('submit',async event=>{
    event.preventDefault();$('authSubmit').disabled=true;
    try {
      if(!logged){const session=await api('/api/login',{username:$('username').value,password:$('password').value});csrf=session.csrf;uid=session.uid;logged=true;$('password').value='';await api('/api/admin/access');lock();$('password').focus();return;}
      await api('/api/admin/reauth',{password:$('password').value});$('password').value='';await load();
    }catch(err){$('password').value='';lock(err.message);notice(err.message,true);}finally{$('authSubmit').disabled=false;}
  });
  function confirm(user,action) {
    pending={user,action};$('confirmTitle').textContent=action==='role'?'Alterar papel':action==='status'?'Alterar status':action==='sessions'?'Revogar sessões':'Alterar limites';
    $('confirmDescription').textContent=user.username+' · '+(action==='role'?'Novo papel: '+(user.role==='admin'?'user':'admin'):action==='status'?'Novo status: '+(user.status==='ativo'?'bloqueado':'ativo'):'A alteração será registrada na auditoria.');
    $('limitFields').hidden=action!=='limits';$('confirmName').value='';$('hourLimit').value=String(user.max_ai_hora??0);$('parallelLimit').value=String(user.max_ia_simult??0);$('confirmDialog').showModal();$('confirmName').focus();
  }
  $('cancelChange').addEventListener('click',()=>$('confirmDialog').close());
  $('confirmForm').addEventListener('submit',async event=>{
    event.preventDefault();if(!pending||$('confirmName').value!==pending.user.username){$('confirmName').setCustomValidity('Digite o username exato.');$('confirmName').reportValidity();return;}
    $('applyChange').disabled=true;const {user,action}=pending;let body={uid:user.uid};
    if(action==='role')body.role=user.role==='admin'?'user':'admin';
    if(action==='status')body.status=user.status==='ativo'?'bloqueado':'ativo';
    if(action==='limits'){body.max_ai_hora=Number($('hourLimit').value);body.max_ia_simult=Number($('parallelLimit').value);}
    try{await api('/api/admin/users/'+action,body);$('confirmDialog').close();pending=null;await load();}
    catch(err){notice(err.message,true);if(err.status===401||err.status===403)lock(err.message);}finally{$('applyChange').disabled=false;}
  });
  $('confirmName').addEventListener('input',()=>$('confirmName').setCustomValidity(''));
  $('refresh').addEventListener('click',()=>load());$('leave').addEventListener('click',async()=>{try{await api('/api/admin/leave',{});lock('Console bloqueado.');}catch(err){lock(err.message);}});
  const tabs=[...document.querySelectorAll('[data-tab]')];
  function select(tab){tabs.forEach(b=>{const selected=b===tab;b.setAttribute('aria-selected',String(selected));b.tabIndex=selected?0:-1;$(b.dataset.tab).hidden=!selected;});}
  tabs.forEach((tab,index)=>{tab.addEventListener('click',()=>select(tab));tab.addEventListener('keydown',event=>{let next;if(event.key==='ArrowRight')next=(index+1)%tabs.length;if(event.key==='ArrowLeft')next=(index+tabs.length-1)%tabs.length;if(event.key==='Home')next=0;if(event.key==='End')next=tabs.length-1;if(next!==undefined){event.preventDefault();select(tabs[next]);tabs[next].focus();}});});
  init();
})();
