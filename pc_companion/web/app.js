'use strict';
const $ = id => document.getElementById(id);
let token = '', current = 'overview', snapshot, offset = 0, more = false, searchSequence = 0, logs = [], searchTimer;
let updating = false, seenUpdateResult = '';
const pageScroll = {};
const bytes = n => n == null ? 'Calculando…' : new Intl.NumberFormat('pt-BR', {maximumFractionDigits:1}).format(n / 1024 ** (n >= 1024**3 ? 3 : n >= 1024**2 ? 2 : n >= 1024 ? 1 : 0)) + ' ' + (n >= 1024**3 ? 'GB' : n >= 1024**2 ? 'MB' : n >= 1024 ? 'KB' : 'B');
const message = text => { $('notice').textContent = text; };
async function api(path, body) {
  const response = await fetch(path, {headers:{'X-Vexx-Token': token, ...(body ? {'Content-Type':'application/json'} : {})}, ...(body ? {method:'POST',body:JSON.stringify(body)} : {})});
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Não foi possível concluir.');
  return data;
}
function go(page) {
  if (!['overview','pc','cleaner','projects','network','logs','ai'].includes(page)) return;
  pageScroll[current] = $('main-content').scrollTop;
  current = page;
  for (const view of document.querySelectorAll('[data-view]')) view.hidden = view.dataset.view !== page;
  for (const b of document.querySelectorAll('nav [data-page]')) {
    if (b.dataset.page === page) b.setAttribute('aria-current','page'); else b.removeAttribute('aria-current');
  }
  if (window.vexxWorkspace) window.vexxWorkspace.enter(page).catch(showError);
  if (page === 'logs') loadLogs().catch(showError);
  $('main-content').scrollTop = pageScroll[page] || 0;
}
function showError(err) { message(err.message || 'Ocorreu uma falha. Tente novamente.'); }
function render(data) {
  snapshot = data;
  const s = data.system, c = data.connection, i = data.index;
  renderUpdate(data.update);
  if (s.name) {
    $('host-name').textContent = '· ' + s.name;
    $('cpu').textContent = s.cpu_percent + '%'; $('cpu-bar').value = s.cpu_percent;
    $('cores').textContent = s.cpu_cores + ' processadores lógicos';
    $('ram').textContent = bytes(s.ram.used); $('ram-bar').value = s.ram.percent;
    $('ram-detail').textContent = s.ram.percent + '% de ' + bytes(s.ram.total);
    $('disk').textContent = s.disks[0] ? bytes(s.disks[0].free) : 'Indisponível';
    $('disk-detail').textContent = s.disks[0] ? 'livres em ' + s.disks[0].path + ' · ' + bytes(s.disks[0].total) + ' no total' : 'Nenhuma unidade disponível';
    $('uptime').textContent = Math.floor(s.uptime / 3600) + 'h ' + Math.floor(s.uptime % 3600 / 60) + 'min';
    $('battery').textContent = s.battery ? 'Bateria ' + s.battery.percent + '% · ' + (s.battery.plugged ? 'na tomada' : 'fora da tomada') : s.os;
    $('agent-memory').textContent = 'Aplicativo: ' + bytes(s.agent_rss) + ' de RAM · sensores a cada 3s';
    $('network-overview').textContent = s.adapters.map(a=>a.name).join(', ') || 'Nenhuma interface ativa';
    $('download').textContent = bytes(s.network.download) + '/s'; $('upload').textContent = bytes(s.network.upload) + '/s';
    const fragment = document.createDocumentFragment();
    for (const a of s.adapters) { const p = document.createElement('p'); p.textContent = a.name + ' · ' + a.addresses.join(' · ') + (a.speed_mbps > 0 ? ' · ' + a.speed_mbps + ' Mbps' : ''); fragment.append(p); }
    $('adapters').replaceChildren(fragment);
    $('ssid').textContent = s.ssid ? 'Wi-Fi conectado: ' + s.ssid : 'Nome Wi-Fi indisponível. As interfaces acima são detectadas pelo sistema.';
  }
  $('connection-badge').textContent = c.online ? 'Conectado' : data.linked ? 'Reconectando' : 'Sem vínculo';
  $('pair-form').hidden = data.linked && !c.relink_required;
  if (data.relay && document.activeElement !== $('relay-url')) $('relay-url').value = data.relay;
  if (data.nick && !$('pair-nick').value) $('pair-nick').value = data.nick;
  $('ai-mode-label').textContent = data.ai?.enabled ? (data.ai.model || 'Escolha um modelo na aba IA') : 'Ações locais. Dados reais.';
  $('connection-copy').textContent = c.pending ? 'Sua conta pediu acesso. Confira e autorize neste computador.' : data.linked ? 'Este PC está vinculado à sua conta. A sessão remota precisa da sua permissão local.' : 'No site Vexx AI, abra Meu PC e crie seu nick e PIN. Informe os mesmos dados abaixo.';
  if (data.linked && c.error) $('connection-copy').textContent = c.error;
  $('access-hint').textContent = c.approved ? (c.permanent_control ? 'Acesso permanente ativo · ' : 'Acesso autorizado por até uma hora · ') + (c.control_allowed ? 'visualização, mouse e teclado.' : 'somente visualização.') : 'Acesso pausado. Autorize por uma hora ou ative o controle permanente.';
  $('allow-view').disabled = !c.online; $('allow-control').disabled = !c.online; $('allow-permanent').disabled = !data.linked || c.permanent_control;
  $('pause-access').textContent = c.permanent_control ? 'Revogar acesso permanente' : 'Pausar acesso';
  $('pause-access').disabled = !c.approved && !c.pending; $('unlink').hidden = !data.linked;
  $('index-count').textContent = i.count.toLocaleString('pt-BR') + ' entradas';
  const status = i.error || (i.paused ? 'Indexação pausada' : i.running ? 'Indexando em segundo plano' : 'Índice pronto') + ' · ' + i.count.toLocaleString('pt-BR') + ' entradas · ' + i.skipped + ' inacessíveis';
  $('index-overview').textContent = status; $('index-status').textContent = status;
  $('index-roots').textContent = i.roots.join(' · ');
  $('index-toggle').textContent = i.paused ? 'Retomar índice' : 'Pausar índice';
  if (data.monitor_error) message(data.monitor_error);
}
function renderUpdate(update) {
  if (!update) return;
  const b = $('update-button');
  b.classList.toggle('available', update.available);
  b.disabled = update.checking || update.applying;
  $('update-label').textContent = update.applying ? 'Atualizando…' : update.checking ? 'Verificando…' : update.available ? 'Atualizar' : 'Verificar versão';
  b.title = update.available ? 'Atualizar Vexx PC para ' + update.latest : 'Versão ' + update.current + ' · verificar atualizações';
  b.setAttribute('aria-label', b.title);
  $('app-version').textContent = 'Vexx PC · ' + update.current;
  if (update.error) { updating = false; message(update.error); }
  if (update.last_result && ['failed','complete'].includes(update.last_result.state)) {
    const key = JSON.stringify(update.last_result);
    if (key !== seenUpdateResult) {seenUpdateResult = key;message(update.last_result.state === 'failed' ? update.last_result.message : 'Vexx PC atualizado para ' + update.current + '.');}
  }
  if (update.applying) { updating = true; message('Baixando e verificando a atualização. O Vexx PC será reaberto; seu vínculo e seus arquivos serão preservados.'); }
}
$('update-button').onclick = async () => {
  const button = $('update-button');button.disabled = true;
  try {
    if (snapshot?.update?.available) {
      const update = await api('/api/update/apply', {});renderUpdate(update);
    } else {
      const update = await api('/api/update/check', {});renderUpdate(update);
      if (!update.error) message(update.available ? 'Nova versão ' + update.latest + ' disponível. Clique no ícone de atualizar para instalar.' : 'Seu Vexx PC já está na versão mais recente: ' + update.current + '.');
      if (snapshot) snapshot.update = update;
    }
  } catch (err) {showError(err);} finally {if (!updating)button.disabled = false;}
};
async function refresh() { if (document.hidden || !token) return; render(await api('/api/status')); if(current==='logs')await loadLogs(); }
async function act(action, extras = {}) { await api('/api/action',{action,...extras}); await refresh(); }
async function search() { if(window.vexxWorkspace)return window.vexxWorkspace.search(); }
async function loadLogs(){ logs=(await api('/api/logs')).items; filterLogs(); }
function filterLogs(){const q=$('log-filter').value.toLocaleLowerCase();$('log-output').textContent=logs.filter(l=>l.message.toLocaleLowerCase().includes(q)).map(l=>l.time+'  '+l.message).join('\n') || 'Nenhum evento para mostrar.';}
function bubble(text,user=false){
  const host=$('chat-messages'),nearBottom=host.scrollHeight-host.scrollTop-host.clientHeight<45;
  const div=document.createElement('div');div.className='bubble'+(user?' user':'');div.textContent=text;host.append(div);
  while(host.children.length>80)host.firstElementChild.remove();
  if(nearBottom||user)host.scrollTop=host.scrollHeight;
}
async function prompt(text){bubble(text,true);const data=await api('/api/copilot',{text});bubble(data.reply);if(data.search){$('file-query').value=data.search;offset=0;window.vexxWorkspace?.setSearch();go('pc');}else if(data.page)go(data.page);await refresh();}
for(const b of document.querySelectorAll('[data-page]')) b.addEventListener('click',()=>go(b.dataset.page));
for(const b of document.querySelectorAll('[data-go]')) b.addEventListener('click',()=>go(b.dataset.go));
for(const b of document.querySelectorAll('[data-prompt]')) b.addEventListener('click',()=>prompt(b.dataset.prompt).catch(showError));
$('pair-form').addEventListener('submit',async e=>{e.preventDefault();const b=e.submitter;b.disabled=true;try{await api('/api/pair',Object.fromEntries(new FormData(e.target)));e.target.elements.pin.value='';message('PC vinculado. Aguardando conexão segura…');await refresh();}catch(err){showError(err);}finally{b.disabled=false;}});
$('allow-permanent').onclick=()=>{if(confirm('Permitir visualização, mouse e teclado permanentemente para a conta vinculada? O acesso continuará autorizado ao reabrir o aplicativo. Para cancelar, use Revogar acesso permanente ou desvincule o PC.'))act('allow',{control:true,permanent:true}).catch(showError);};
$('allow-view').onclick=()=>act('allow').catch(showError);
$('allow-control').onclick=()=>{if(confirm('Permitir que os aparelhos conectados à sua conta vejam a tela e controlem mouse e teclado deste PC por uma hora?'))act('allow',{control:true}).catch(showError);};
$('pause-access').onclick=()=>act('pause').catch(showError);
$('unlink').onclick=()=>{if(confirm('Desvincular este computador da sua conta? O acesso será pausado.'))act('unlink').catch(showError);};
$('shutdown').onclick=()=>{if(confirm('Encerrar Vexx PC e pausar todo acesso remoto?'))api('/api/action',{action:'shutdown'}).then(()=>{token='';message('Vexx PC encerrado. Você pode fechar esta janela.');}).catch(showError);};
$('index-toggle').onclick=()=>act(snapshot?.index.paused?'index_resume':'index_pause').catch(showError);
$('index-refresh').onclick=()=>act('index_refresh').then(()=>{message('Índice atualizando em segundo plano.');return search();}).catch(showError);
$('search-form').onsubmit=e=>{e.preventDefault();offset=0;search().catch(showError);};
$('file-query').oninput=()=>{clearTimeout(searchTimer);searchSequence++;searchTimer=setTimeout(()=>{offset=0;search().catch(showError);},220);};
$('file-kind').onchange=()=>{offset=0;search().catch(showError);};
$('previous-page').onclick=()=>{offset=Math.max(0,offset-60);search().catch(showError);};
$('next-page').onclick=()=>{if(more){offset+=60;search().catch(showError);}};
$('log-filter').oninput=filterLogs;$('logs-refresh').onclick=()=>loadLogs().catch(showError);
$('logs-export').onclick=()=>{const blob=new Blob([logs.map(l=>l.time+' '+l.message).join('\n')],{type:'text/plain;charset=utf-8'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='vexx-pc-logs.txt';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
$('chat-form').onsubmit=async e=>{e.preventDefault();const text=$('chat-input').value.trim();if(!text)return;e.submitter.disabled=true;$('chat-input').value='';try{await prompt(text);}catch(err){showError(err);}finally{e.submitter.disabled=false;}};
async function boot(){const r=await fetch('/api/bootstrap');if(!r.ok)throw new Error('Reabra pelo atalho Vexx PC.');token=(await r.json()).token;await refresh();loadAI(await api('/api/ai/config'));setInterval(()=>refresh().catch(err=>{if(!updating)showError(err);}),3000);}
boot().catch(showError);

function loadAI(data){
  $('ai-provider').value=data.provider;$('ai-url').value=data.base_url;$('ai-model').value=data.model;
  $('ai-key').value='';$('ai-clear-key').checked=false;
  $('ai-key').placeholder=data.key_set?'Chave salva · deixe vazio para manter':'Opcional para serviços locais';
  $('ai-status').textContent=data.enabled?'Configuração salva neste computador.':'Comandos locais ativos, sem provedor de IA.';
}
$('ai-provider').onchange=()=>{
  const defaults={ollama:'http://127.0.0.1:11434',hermes:'http://127.0.0.1:8645/v1',openai:'https://api.openai.com/v1'};
  $('ai-url').value=defaults[$('ai-provider').value]||'';$('ai-model').value='';$('ai-key').value='';
  $('ai-key').placeholder='Informe uma chave se o serviço exigir';$('ai-models').replaceChildren();
};
async function saveAI(){
  const data=Object.fromEntries(new FormData($('ai-form')));data.clear_key=$('ai-clear-key').checked;
  const result=await api('/api/ai/config',data);loadAI(result);return result;
}
$('ai-form').onsubmit=async e=>{e.preventDefault();e.submitter.disabled=true;try{await saveAI();message('Configuração de IA salva.');await refresh();}catch(err){showError(err);}finally{e.submitter.disabled=false;}};
$('ai-test').onclick=async()=>{
  const b=$('ai-test');b.disabled=true;$('ai-status').textContent='Testando o serviço…';
  try{await saveAI();const result=await api('/api/ai/test',{});$('ai-models').replaceChildren(...result.models.map(model=>{const o=document.createElement('option');o.value=model;return o;}));$('ai-status').textContent='Conectado · '+result.models.length+' modelos disponíveis. Escolha o modelo e salve.';}
  catch(err){$('ai-status').textContent=err.message;}finally{b.disabled=false;}
};
