'use strict';
(() => {
  const pc={mode:'browse',folder:'',offset:0,more:false,selected:new Map(),items:[],seq:0};
  const clean={mode:'files',offset:0,more:false,selected:new Map(),items:[],seq:0};
  let pending=null,runId='',runsSignature='',logText='',projectBusy=false,searchTimer=0;
  const main=$('main-content'),dialog=$('review-dialog');
  const el=(tag,text,className)=>{const node=document.createElement(tag);if(text!=null)node.textContent=text;if(className)node.className=className;return node;};
  const button=(text,fn)=>{const b=el('button',text);b.type='button';b.onclick=()=>Promise.resolve(fn()).catch(showError);return b;};
  const date=value=>{if(!value)return '—';const d=new Date(typeof value==='number'?value*1000:String(value).replace(/^(\d{4})(\d\d)(\d\d)$/,'$1-$2-$3'));return Number.isNaN(d.getTime())?'—':d.toLocaleDateString('pt-BR');};
  const keyOf=item=>item.id||item.path;
  function selectedBar(state,prefix){
    const count=state.selected.size,total=[...state.selected.values()].reduce((s,i)=>s+(i.size||0),0);
    $(prefix+'-selection').hidden=!count;$(prefix+'-selection-count').textContent=count+' arquivos · '+bytes(total)+' selecionados';
    const check=$(prefix==='files'?'files-select-page':'clean-select-page');
    const eligible=state.items.filter(i=>!i.directory&&i.removable!==false);
    check.checked=eligible.length>0&&eligible.every(i=>state.selected.has(keyOf(i)));check.indeterminate=!check.checked&&eligible.some(i=>state.selected.has(keyOf(i)));
  }
  function clear(state,prefix){state.selected.clear();selectedBar(state,prefix);}
  function rowList(items,tbody,state,prefix){
    state.items=items;const fragment=document.createDocumentFragment();
    for(const item of items){
      const row=el('tr');row.classList.toggle('selected',state.selected.has(keyOf(item)));
      const pick=el('td'),check=el('input');check.type='checkbox';check.checked=state.selected.has(keyOf(item));check.disabled=!!item.directory||item.removable===false;
      check.setAttribute('aria-label','Selecionar '+(item.name||item.path));
      check.onchange=()=>{if(check.checked&&state.selected.size>=100){check.checked=false;message('Selecione no máximo 100 arquivos por operação.');return;}if(check.checked)state.selected.set(keyOf(item),item);else state.selected.delete(keyOf(item));row.classList.toggle('selected',check.checked);selectedBar(state,prefix);};pick.append(check);
      const name=el('td'),label=item.name||item.path.split(/[\\/]/).pop();
      if(item.directory){const b=button('▸ '+label,()=>openFolder(item.path));b.className='file-name';name.append(b);}else name.append(el('b',label));
      name.append(el('small',item.path));if(item.removed)name.append(el('small','Removido em '+date(item.removed)));
      const size=el('td',bytes(item.size)+(item.directory&&item.size!=null?' indexados':''));size.setAttribute('aria-label','Tamanho: '+size.textContent);
      const modified=el('td',date(item.modified)),actions=el('td');
      if(!item.id){
        actions.append(button('Copiar caminho',()=>navigator.clipboard.writeText(item.path).then(()=>message('Caminho copiado.'))));
        if(item.directory||/\.(py|html?|m?js|cjs)$/i.test(item.path)||/(?:^|[\\/])(?:package\.json|vexx-project\.json|pyproject\.toml)$/i.test(item.path))actions.append(button('▷ Iniciar…',()=>inspectProject(item.path)));
      }else actions.append(button('Restaurar',()=>reviewFiles('restore',[item.id])));
      row.append(pick,name,size,modified,actions);fragment.append(row);
    }
    if(!items.length){const row=el('tr'),cell=el('td','Nenhum item para mostrar. Revise o filtro ou atualize o índice.');cell.colSpan=5;row.append(cell);fragment.append(row);}
    $(tbody).replaceChildren(fragment);selectedBar(state,prefix);
  }
  async function loadPC(){
    const seq=++pc.seq;
    try{
      let data;
      if(pc.mode==='browse')data=await api('/api/files/browse?'+new URLSearchParams({path:pc.folder,offset:pc.offset,sort:$('file-sort').value}));
      else data=await api('/api/search?'+new URLSearchParams({q:$('file-query').value,kind:$('file-kind').value,sort:$('file-sort').value,offset:pc.offset}));
      if(seq!==pc.seq)return;pc.more=data.more;
      if(pc.mode==='browse'){pc.folder=data.path;$('folder-path').value=pc.folder;$('files-location').textContent=pc.folder||'Raízes locais';$('folder-run').hidden=!pc.folder;$('files-up').disabled=!pc.folder;pc.parent=data.parent;}
      else{$('files-location').textContent='Pesquisa em todo o índice';$('folder-run').hidden=true;}
      $('search-summary').textContent=data.hint||(pc.mode==='browse'?(data.partial?'Pasta muito grande: mostrando uma parte. Use o índice para pesquisar.':'Navegação direta · '+data.items.length+' itens nesta página'):(data.items.length+' resultados nesta página · '+data.ms+' ms · tamanhos do último índice'));
      rowList(data.items,'file-results',pc,'files');$('previous-page').disabled=!pc.offset;$('next-page').disabled=!pc.more;$('page-number').textContent='Página '+(pc.offset/60+1);
      if(typeof updateSearchClear==='function')updateSearchClear();
    }catch(error){
      if(seq===pc.seq)$('search-summary').textContent='Não foi possível pesquisar agora. Tente novamente.';
      throw error;
    }
  }
  async function openFolder(path){clear(pc,'files');pc.mode='browse';pc.folder=path;pc.offset=0;$('file-query').value='';if(typeof updateSearchClear==='function')updateSearchClear();if(state.current!=='pc')go('pc');else await loadPC();window.scrollTo({top:0,behavior:'instant'});}
  async function searchPC(){pc.mode='search';return loadPC();}
  async function loadClean(){
    const seq=++clean.seq;let data;
    $('clean-filter-panel').hidden=clean.mode!=='files';$('clean-restore').hidden=clean.mode!=='trash';$('manage-apps').hidden=clean.mode!=='apps';$('clean-remove').textContent=clean.mode==='trash'?'Revisar exclusão definitiva →':'Revisar remoção →';
    for(const mode of ['files','apps','trash'])$('clean-'+mode).setAttribute('aria-pressed',String(clean.mode===mode));
    $('clean-head').hidden=clean.mode==='apps';
    if(clean.mode==='apps'){
      data=await api('/api/apps');if(seq!==clean.seq)return;
      const fragment=document.createDocumentFragment();
      for(const app of data.items){const row=el('tr');row.append(el('td','—'));const name=el('td');name.append(el('b',app.name),el('small',app.publisher+' · '+app.version));row.append(name,el('td',app.size?bytes(app.size)+' estimados':'Não informado'),el('td',date(app.installed)));const actions=el('td');actions.append(button('Gerenciar no Windows',()=>api('/api/apps/manage',{})));row.append(actions);fragment.append(row);}
      $('clean-results').replaceChildren(fragment);$('clean-summary').textContent=data.supported?data.items.length+' aplicativos · maior tamanho estimado primeiro. A remoção usa os assistentes do Windows.':'A lista de aplicativos instalados está disponível no Windows.';
      clean.items=[];clean.more=false;selectedBar(clean,'clean');
    }else if(clean.mode==='trash'){
      data=await api('/api/files/trash?offset='+clean.offset);if(seq!==clean.seq)return;
      $('clean-summary').textContent=data.count+' arquivos na Lixeira · '+bytes(data.size)+' ainda ocupados em disco. Restaurar não sobrescreve arquivos existentes.';
      rowList(data.items,'clean-results',clean,'clean');clean.more=!!data.more;
    }else{
      data=await api('/api/search?'+new URLSearchParams({q:$('clean-query').value,kind:$('clean-kind').value,sort:$('clean-sort').value,min_size:$('clean-size').value,age_days:$('clean-age').value,offset:clean.offset}));
      if(seq!==clean.seq)return;clean.more=data.more;
      $('clean-summary').textContent=data.hint||(data.items.length+' resultados nesta página · '+data.ms+' ms. Datas e tamanhos são do último índice; a revisão confere os arquivos novamente.');
      rowList(data.items,'clean-results',clean,'clean');
    }
    $('clean-prev').disabled=!clean.offset;$('clean-next').disabled=!clean.more;$('clean-page').textContent='Página '+(clean.offset/60+1);
  }
  function showReview(title,summary,note){
    $('review-title').textContent=title;$('review-summary').textContent=summary;$('review-note').textContent=note;$('review-items').replaceChildren();$('review-error').textContent='';
    $('review-word').value='';$('review-prepare').checked=false;$('review-word-row').hidden=true;$('review-prepare-row').hidden=true;$('review-confirm').disabled=false;
    if(!dialog.open)dialog.showModal();
  }
  async function reviewFiles(mode,items){
    const plan=await api('/api/files/prepare',{mode,items});pending={kind:'files',plan};
    showReview(mode==='purge'?'Excluir definitivamente?':mode==='restore'?'Restaurar arquivos':'Mover para a Lixeira Vexx',plan.count+' arquivos · '+bytes(plan.size),mode==='purge'?'Esta exclusão é definitiva e não permite restaurar pela Lixeira Vexx.':'Os caminhos e arquivos serão conferidos outra vez. Nenhum item foi processado ainda.');
    for(const item of plan.items){const row=el('div',null,'review-item');row.append(el('div',item.path),el('small',bytes(item.size)));$('review-items').append(row);}
    $('review-word-row').hidden=mode!=='purge';$('review-confirm').textContent=mode==='purge'?'Excluir definitivamente':mode==='restore'?'Restaurar':'Mover para a Lixeira';
    if(mode==='purge')$('review-confirm').disabled=true;
  }
  async function inspectProject(path){
    const plan=await api('/api/projects/inspect',{path});pending={kind:'project',plan};
    showReview('Revisar início do projeto',plan.root,plan.notice+' Fechar o Vexx PC encerra os processos que ele iniciou.');
    for(const text of [...plan.blockers,...plan.warnings])$('review-items').append(el('p',text,'hint'));
    for(const service of plan.services){const row=el('div',null,'review-item');row.append(el('h3',service.name),el('div','Pasta: '+service.cwd));
      for(const command of service.prepare)row.append(el('small','Preparação'),el('code',command.map(a=>JSON.stringify(a)).join(' ')));
      row.append(el('small','Iniciar'),el('code',service.command.map(a=>JSON.stringify(a)).join(' ')));
      if(service.script)row.append(el('small','Script do projeto: '+service.script));if(service.port)row.append(el('small','Porta local: '+service.port));$('review-items').append(row);
    }
    const needs=plan.services.some(s=>s.prepare.length);$('review-prepare-row').hidden=!needs;$('review-confirm').textContent=needs?'Preparar e iniciar':'Iniciar projeto';$('review-confirm').disabled=!!plan.blockers.length||needs;
  }
  function confirmState(){if(!pending)return;if(pending.kind==='project')$('review-confirm').disabled=!!pending.plan.blockers.length||pending.plan.services.some(s=>s.prepare.length)&&!$('review-prepare').checked;else $('review-confirm').disabled=pending.plan.mode==='purge'&&$('review-word').value!=='EXCLUIR';}
  $('review-word').oninput=confirmState;$('review-prepare').onchange=confirmState;
  $('review-confirm').onclick=async()=>{
    if(!pending)return;const task=pending;$('review-confirm').disabled=true;
    try{
      if(task.kind==='project'){
        const result=await api('/api/projects/start',{token:task.plan.token,prepare:$('review-prepare').checked});runId=result.id;dialog.close();go('projects');message('Projeto enviado. Acompanhe o andamento e os logs na aba Projetos.');
      }else{
        const result=await api('/api/files/execute',{token:task.plan.token,confirmation:$('review-word').value});
        for(const state of [pc,clean])for(const [key,item] of state.selected)if(result.done.includes(item.path))state.selected.delete(key);
        dialog.close();message(result.done.length+' arquivos processados'+(result.failed.length?' · '+result.failed.length+' pendentes. Confira permissões, conflitos ou arquivos em uso.':'.'));
        if(state.current==='pc')await loadPC();if(state.current==='cleaner')await loadClean();await refresh();
      }
      pending=null;
    }catch(error){$('review-error').textContent=error.message+' Feche esta revisão e analise a seleção novamente.';}
  };
  for(const id of ['review-close','review-cancel'])$(id).onclick=()=>{dialog.close();pending=null;};
  dialog.addEventListener('cancel',()=>{pending=null;});
  async function projectStatus(){
    if(projectBusy||state.current!=='projects'||document.hidden)return;projectBusy=true;
    try{
      const data=await api('/api/projects/status?'+new URLSearchParams({id:runId}));const signature=JSON.stringify(data.items.map(r=>({...r,logs:[]})));
      if(signature!==runsSignature){
        runsSignature=signature;const fragment=document.createDocumentFragment();
        if(!data.items.length)fragment.append(el('p','Ainda não há projetos iniciados nesta sessão.','hint'));
        for(const run of [...data.items].reverse()){
          const card=el('article',null,'project-card');const title=el('div',null,'section-title');title.append(el('h2',run.root.split(/[\\/]/).pop()),el('span',({preparing:'Preparando',starting:'Iniciando',running:'Em execução',stopped:'Parado',failed:'Falha',completed:'Concluído'})[run.state]||run.state,'badge'));card.append(title,el('p',run.root,'hint'));
          for(const service of run.services){const row=el('div',null,'service-row');row.append(el('div',service.name+' · PID '+service.pid));if(service.url){const link=el('a',service.url);link.href=service.url;link.target='_blank';link.rel='noopener';row.append(link);}card.append(row);}
          if(run.processes?.length)card.append(el('p','Processos vinculados: '+run.processes.map(p=>p.name+' ('+p.pid+')').join(' · '),'hint'));
          const actions=el('div',null,'actions');actions.append(button('Ver logs',()=>{runId=run.id;logText='';return projectStatus();}));
          if(['preparing','starting','running'].includes(run.state))actions.append(button('Parar processos',()=>api('/api/projects/stop',{id:run.id}).then(projectStatus)));
          card.append(actions);fragment.append(card);
        }
        $('project-runs').replaceChildren(fragment);
      }
      const selected=data.items.find(r=>r.id===runId);$('project-log-panel').hidden=!selected;
      if(selected){const value=selected.logs.join('\n');if(value!==logText){const host=$('project-logs'),bottom=host.scrollHeight-host.scrollTop-host.clientHeight<35;host.textContent=value||'Aguardando saída do processo…';if(bottom)host.scrollTop=host.scrollHeight;logText=value;}$('project-log-title').textContent='Logs · '+selected.root.split(/[\\/]/).pop();}
    }finally{projectBusy=false;}
  }
  function selectPage(state,prefix,checked){for(const item of state.items){if(item.directory||item.removable===false)continue;if(checked&&state.selected.size<100)state.selected.set(keyOf(item),item);else if(!checked)state.selected.delete(keyOf(item));}rowList(state.items,prefix==='files'?'file-results':'clean-results',state,prefix);}
  $('files-select-page').onchange=e=>selectPage(pc,'files',e.target.checked);$('clean-select-page').onchange=e=>selectPage(clean,'clean',e.target.checked);
  $('files-clear').onclick=()=>{clear(pc,'files');loadPC().catch(showError);};$('clean-clear').onclick=()=>{clear(clean,'clean');loadClean().catch(showError);};
  $('files-remove').onclick=()=>reviewFiles('trash',[...pc.selected.keys()]).catch(showError);
  $('clean-remove').onclick=()=>reviewFiles(clean.mode==='trash'?'purge':'trash',[...clean.selected.keys()]).catch(showError);$('clean-restore').onclick=()=>reviewFiles('restore',[...clean.selected.keys()]).catch(showError);
  for(const mode of ['files','apps','trash'])$('clean-'+mode).onclick=()=>{clear(clean,'clean');clean.mode=mode;clean.offset=0;loadClean().catch(showError);};
  $('manage-apps').onclick=()=>api('/api/apps/manage',{}).catch(showError);
  $('clean-form').onsubmit=e=>{e.preventDefault();clear(clean,'clean');clean.offset=0;loadClean().catch(showError);};
  $('clean-prev').onclick=()=>{clean.offset=Math.max(0,clean.offset-60);loadClean().catch(showError);};$('clean-next').onclick=()=>{clean.offset+=60;loadClean().catch(showError);};
  $('files-roots').onclick=()=>openFolder('').catch(showError);$('files-up').onclick=()=>openFolder(pc.parent||'').catch(showError);
  $('files-pick').onclick=()=>api('/api/files/pick-folder',{}).then(data=>{if(data.path)return openFolder(data.path);}).catch(showError);
  $('folder-form').onsubmit=e=>{e.preventDefault();openFolder($('folder-path').value).catch(showError);};$('folder-run').onclick=()=>inspectProject(pc.folder).catch(showError);
  $('search-form').onsubmit=e=>{e.preventDefault();clear(pc,'files');pc.offset=0;searchPC().catch(showError);};
  $('file-query').oninput=()=>{clearTimeout(searchTimer);pc.seq++;searchTimer=setTimeout(()=>{clear(pc,'files');pc.offset=0;searchPC().catch(showError);},260);};
  $('file-kind').onchange=()=>{clear(pc,'files');pc.offset=0;searchPC().catch(showError);};$('file-sort').onchange=()=>{pc.offset=0;loadPC().catch(showError);};
  $('previous-page').onclick=()=>{pc.offset=Math.max(0,pc.offset-60);loadPC().catch(showError);};$('next-page').onclick=()=>{pc.offset+=60;loadPC().catch(showError);};
  $('project-form').onsubmit=e=>{e.preventDefault();inspectProject($('project-path').value).catch(showError);};
  $('project-logs-copy').onclick=()=>navigator.clipboard.writeText($('project-logs').textContent).then(()=>message('Logs copiados.')).catch(showError);
  window.vexxWorkspace={search:searchPC,setSearch:()=>{pc.mode='search';pc.offset=0;$('files-location').textContent='Pesquisa em todo o índice';},clearSearch:()=>openFolder(pc.folder||''),enter:async page=>{if(page==='pc')await loadPC();if(page==='cleaner')await loadClean();if(page==='projects')await projectStatus();}};
  setInterval(()=>projectStatus().catch(showError),2000);
  let desktopClosed=localStorage.getItem('vexx-chat')==='closed',drawerOpen=false;
  function chatLayout(){const small=matchMedia('(max-width:1240px)').matches;document.body.classList.toggle('chat-collapsed',!small&&desktopClosed);document.body.classList.toggle('chat-open',small&&drawerOpen);$('chat-backdrop').hidden=!(small&&drawerOpen);$('chat-toggle').setAttribute('aria-expanded',String(small?drawerOpen:!desktopClosed));const modal=small&&drawerOpen;main.inert=modal;document.querySelector('nav').inert=modal;$('copilot-panel').setAttribute('role',small?'dialog':'complementary');if(modal)$('copilot-panel').setAttribute('aria-modal','true');else $('copilot-panel').removeAttribute('aria-modal');}
  function chatClose(){if(matchMedia('(max-width:1240px)').matches)drawerOpen=false;else{desktopClosed=true;localStorage.setItem('vexx-chat','closed');}chatLayout();$('chat-toggle').focus();}
  $('chat-toggle').onclick=()=>{if(matchMedia('(max-width:1240px)').matches)drawerOpen=!drawerOpen;else{desktopClosed=!desktopClosed;localStorage.setItem('vexx-chat',desktopClosed?'closed':'open');}chatLayout();if(drawerOpen||!desktopClosed)$('chat-input').focus();};
  $('chat-close').onclick=chatClose;$('chat-backdrop').onclick=chatClose;
  document.addEventListener('keydown',e=>{if(!drawerOpen||dialog.open)return;if(e.key==='Escape'){e.preventDefault();chatClose();}if(e.key==='Tab'){const focus=[...$('copilot-panel').querySelectorAll('button,textarea,a,input')].filter(n=>!n.disabled&&n.getClientRects().length);if(!focus.length)return;if(e.shiftKey&&document.activeElement===focus[0]){e.preventDefault();focus.at(-1).focus();}else if(!e.shiftKey&&document.activeElement===focus.at(-1)){e.preventDefault();focus[0].focus();}}});
  addEventListener('resize',chatLayout);chatLayout();
})();
