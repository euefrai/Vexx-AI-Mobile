/* Júlia Mobile v0.2: IndexedDB offline-first and safe acknowledgement-based sync.
   Real AI conversation and remote desktop are NOT implemented yet.
*/
'use strict';
const $ = id => document.getElementById(id);
const navItems = [...document.querySelectorAll('.nav-item')];
const pages = [...document.querySelectorAll('.page')];
const composer = $('composer');
const messageInput = $('messageInput');
const conversation = $('conversation');
const toast = $('toast');
const DB_NAME = 'julia-mobile-cache-v1';
const STORE = 'messages';
const PREVIEW_MODE = location.protocol === 'file:';
let db = null;
let csrf = '';
let authenticated = false;
let pcOnline = false;
let busy = false;
let toastTimer;
let aiAbort = null;
let modelsLoadedAt = 0;
let activeConversation = localStorage.getItem('julia-active-conversation') || newId();
localStorage.setItem('julia-active-conversation', activeConversation);

function newId() { return crypto.randomUUID ? crypto.randomUUID() : (Date.now().toString(36) + Math.random().toString(36).slice(2)); }
function showToast(message) { toast.textContent = message; toast.classList.add('show'); clearTimeout(toastTimer); toastTimer = setTimeout(() => toast.classList.remove('show'), 3200); }
function navigate(tab) {
  const page = $('page-' + tab);
  if (!page) return;
  pages.forEach(p => { const on = p === page; p.hidden = !on; p.classList.toggle('active', on); });
  navItems.forEach(n => { const on = n.dataset.tab === tab; n.classList.toggle('active', on); if (on) n.setAttribute('aria-current', 'page'); else n.removeAttribute('aria-current'); });
  composer.style.display = tab === 'chat' ? 'flex' : 'none';
  page.scrollTop = 0;
}
navItems.forEach(n => n.addEventListener('click', () => navigate(n.dataset.tab)));

function reqPromise(request) { return new Promise((resolve, reject) => { request.onsuccess = () => resolve(request.result); request.onerror = () => reject(request.error); }); }
function transactionDone(tx) { return new Promise((resolve, reject) => { tx.oncomplete = resolve; tx.onerror = () => reject(tx.error); tx.onabort = () => reject(tx.error || Error('Transação cancelada')); }); }
function openDb() {
  return new Promise((resolve, reject) => {
    if (!('indexedDB' in window)) { reject(Error('IndexedDB indisponível neste navegador')); return; }
    const req = indexedDB.open(DB_NAME, 1);
    req.onupgradeneeded = () => {
      const store = req.result.createObjectStore(STORE, { keyPath: 'id' });
      store.createIndex('created_at', 'created_at');
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}
async function allMessages() {
  if (!db) return [];
  const tx = db.transaction(STORE, 'readonly');
  const rows = await reqPromise(tx.objectStore(STORE).getAll());
  return rows.sort((a, b) => a.created_at.localeCompare(b.created_at) || a.id.localeCompare(b.id));
}
async function storeMessages(messages) {
  if (!db) throw Error('Armazenamento indisponível');
  const tx = db.transaction(STORE, 'readwrite');
  const done = transactionDone(tx);
  for (const msg of messages) tx.objectStore(STORE).put(msg);
  await done;
}
async function clearStorage() {
  const tx = db.transaction(STORE, 'readwrite');
  const done = transactionDone(tx);
  tx.objectStore(STORE).clear();
  await done;
}
function appendMessage(row) {
  const type = row.role === 'assistant' ? 'ai' : 'user';
  const wrapper = document.createElement('div');
  wrapper.className = 'message ' + type + (row.status === 'failed' ? ' failed' : '');
  wrapper.dataset.mid = row.id;
  if (type === 'ai') {
    const icon = document.createElement('div'); icon.className = 'bubble-avatar'; icon.textContent = '✦'; wrapper.appendChild(icon);
  }
  const content = document.createElement('div'); content.className = 'message-content';
  if (type === 'ai') { const sender = document.createElement('div'); sender.className = 'sender'; sender.textContent = 'Júlia'; content.appendChild(sender); }
  const bubble = document.createElement('div'); bubble.className = 'bubble';
  if (row.status === 'generating') {
    const t = document.createElement('span'); t.className = 'typing'; t.textContent = 'gerando resposta…'; bubble.appendChild(t);
    const stop = document.createElement('button'); stop.type = 'button'; stop.className = 'stop-gen'; stop.dataset.stop = row.id;
    stop.textContent = '■ Interromper'; content.appendChild(bubble); content.appendChild(stop);
  } else {
    bubble.textContent = row.text;
    content.appendChild(bubble);
  }
  if (type === 'user') {
    const ack = document.createElement('div');
    ack.className = 'message-ack ' + (row.status === 'synced' ? 'synced' : 'pending');
    ack.textContent = row.status === 'synced' ? '✓ Salva no computador' : '◷ Salva no celular · aguardando sincronização';
    content.appendChild(ack);
  } else if (row.status === 'failed') {
    const retry = document.createElement('div'); retry.className = 'message-retry';
    retry.textContent = 'Toque para tentar de novo'; content.appendChild(retry);
  } else if (row.model) {
    const meta = document.createElement('div'); meta.className = 'message-ack synced'; meta.textContent = row.model;
    content.appendChild(meta);
  }
  wrapper.appendChild(content); conversation.appendChild(wrapper);
}
function nearBottom(el) { return el.scrollHeight - el.scrollTop - el.clientHeight < 220; }
function scrollChat() {
  const page = $('page-chat');
  if (nearBottom(conversation) || nearBottom(page)) {
    conversation.scrollTop = conversation.scrollHeight;
    page.scrollTop = page.scrollHeight;
  }
}
async function renderMessages() {
  if (!db) return;
  const rows = (await allMessages()).filter(m => m.conversation_id === activeConversation);
  conversation.replaceChildren();
  const header = document.createElement('div'); header.className = 'chat-date'; header.textContent = 'HISTÓRICO DO CELULAR'; conversation.appendChild(header);
  if (!rows.length) {
    const welcome = document.createElement('div'); welcome.className = 'empty-chat';
    welcome.textContent = '✦ Suas mensagens ficam neste aparelho e serão enviadas para o SQLite do computador assim que ele estiver online.';
    conversation.appendChild(welcome);
  } else rows.forEach(appendMessage);
  conversation.scrollTop = conversation.scrollHeight;
  const pendingCount = (await allMessages()).filter(m => m.status !== 'synced').length;
  $('pendingCount').textContent = `${pendingCount} pendente${pendingCount === 1 ? '' : 's'}`;
  $('syncCounter').textContent = String(pendingCount);
}
function updateConnection() {
  const message = PREVIEW_MODE ? 'Prévia local' : (!navigator.onLine ? 'Sem internet' : pcOnline ? 'PC conectado' : 'PC desconectado');
  $('connectionLabel').textContent = message;
  $('statusButton').classList.toggle('online', pcOnline && navigator.onLine);
  $('deviceStatus').textContent = pcOnline ? 'Online' : 'Offline';
  $('deviceStatus').classList.toggle('connected', pcOnline);
  $('syncStatusText').textContent = pcOnline
    ? 'Computador disponível. Mensagens pendentes serão sincronizadas.'
    : 'O computador está desconectado. Suas mensagens continuam no celular.';
}
async function api(endpoint, options = {}) {
  const headers = { 'Accept': 'application/json', ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...(csrf && options.method && options.method !== 'GET' ? { 'X-CSRF-Token': csrf } : {}) };
  const res = await fetch(endpoint, { ...options, headers: { ...headers, ...options.headers }, credentials: 'same-origin', cache: 'no-store' });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) { const err = new Error(typeof data.detail === 'string' ? data.detail : `Erro HTTP ${res.status}`); err.status = res.status; throw err; }
  return data;
}
async function restoreSession() {
  if (PREVIEW_MODE) { authenticated = true; $('loginOverlay').hidden = true; showToast('Prévia local: apenas armazenamento no celular'); return; }
  try {
    const session = await api('/api/session');
    csrf = session.csrf; authenticated = true; $('loginOverlay').hidden = true;
  } catch (err) {
    authenticated = false;
    $('loginOverlay').hidden = false;
    if (!navigator.onLine) $('loginError').textContent = 'Sem internet. Para desbloqueio offline completo, será necessário um PIN local (próxima etapa).';
  }
}
$('loginForm').addEventListener('submit', async event => {
  event.preventDefault();
  const btn = $('loginButton'); btn.disabled = true; $('loginError').textContent = '';
  try {
    const credentials = { username: $('loginUser').value, password: $('loginPassword').value };
    const result = await api('/api/login', { method: 'POST', body: JSON.stringify(credentials) });
    $('loginPassword').value = ''; csrf = result.csrf; authenticated = true;
    $('loginOverlay').hidden = true;
    await checkStatus();
    showToast('Login realizado com sucesso');
  } catch (err) { $('loginError').textContent = err.message || 'Não foi possível entrar'; }
  finally { btn.disabled = false; }
});
$('logoutButton').addEventListener('click', async () => {
  try { await api('/api/logout', { method: 'POST' }); } catch (_) { /* session may be unavailable */ }
  authenticated = false; csrf = ''; pcOnline = false; $('loginOverlay').hidden = false;
  $('loginPassword').value = ''; updateConnection();
  showToast('Sessão encerrada. Cache local mantido neste aparelho.');
});
async function checkStatus() {
  if (!authenticated || PREVIEW_MODE || !navigator.onLine) { pcOnline = false; updateConnection(); return; }
  try {
    const status = await api('/api/status');
    pcOnline = status.pc_online === true;
    updateConnection();
    if (pcOnline) {
      const confirmados = await syncAndRefresh();
      await loadModels(false);
      for (const m of confirmados.filter(m => m.want_ai && m.role === 'user')) requestAI(m);
    }
  } catch (err) {
    pcOnline = false; updateConnection();
    if (err.status === 401) { authenticated = false; $('loginOverlay').hidden = false; }
  }
}
async function syncAndRefresh() {
  if (busy || !authenticated || !pcOnline || !db) return [];
  busy = true;
  const confirmados = [];
  try {
    while (pcOnline) {
      // Só mensagens do usuário entram no lote: placeholders de IA
      // (texto vazio/em geração) contaminavam o lote com 422 e nada
      // sincronizava. Respostas da IA vêm por /api/messages ou /api/ai.
      const remaining = (await allMessages()).filter(m => m.role === 'user' && m.status === 'pending').slice(0, 100);
      if (!remaining.length) break;
      const result = await api('/api/sync', { method: 'POST', body: JSON.stringify({ messages: remaining.map(({ status, want_ai, ...rest }) => rest) }) });
      const confirmed = new Set(result.confirmed_ids || []);
      if (!confirmed.size) break;
      const batch = remaining.filter(m => confirmed.has(m.id));
      await storeMessages(batch.map(m => ({ ...m, status: 'synced' })));
      confirmados.push(...batch);
    }
    const remote = await api('/api/messages');
    const local = new Map((await allMessages()).map(m => [m.id, m]));
    const additions = [];
    for (const message of remote.messages || []) {
      if (!message || typeof message.id !== 'string' || typeof message.text !== 'string' || message.origin !== 'mobile') continue;
      additions.push({ ...message, status: 'synced' });
    }
    if (additions.length) await storeMessages(additions);
    await renderMessages();
    return confirmados;
  } catch (err) {
    if (err.status === 503) pcOnline = false;
    if (err.status === 401) { authenticated = false; $('loginOverlay').hidden = false; }
    updateConnection();
    return confirmados;
  } finally { busy = false; }
}
function modeloAtivo() { return localStorage.getItem('julia-model') || ''; }
async function loadModels(forcar) {
  if (!authenticated || !pcOnline) { $('aiStatus').textContent = pcOnline ? 'IA: PC online' : 'IA: PC desconectado'; return; }
  if (!forcar && Date.now() - modelsLoadedAt < 300000) return;
  try {
    const r = await api('/api/ai/models');
    modelsLoadedAt = Date.now();
    const sel = $('modelSelect');
    const atual = modeloAtivo() || r.default || '';
    sel.replaceChildren();
    for (const id of r.models || []) {
      const o = document.createElement('option'); o.value = id; o.textContent = id;
      if (id === atual) o.selected = true;
      sel.appendChild(o);
    }
    if (atual && ![...(r.models || [])].includes(atual)) {
      const o = document.createElement('option'); o.value = atual; o.textContent = atual + ' (salvo)'; o.selected = true;
      sel.appendChild(o);
    }
    if (!modeloAtivo() && r.default) localStorage.setItem('julia-model', r.default);
    $('aiStatus').textContent = 'IA pronta · ' + (modeloAtivo() || r.default || '?');
  } catch (err) {
    $('aiStatus').textContent = 'IA: Hermes indisponível no PC';
  }
}
async function requestAI(userRow) {
  if (!authenticated || !pcOnline || !db || aiAbort) return;
  const replyId = userRow.id + '-r1';
  const ja = (await allMessages()).find(m => m.id === replyId);
  if (ja && (ja.status === 'synced' || ja.status === 'generating')) return;
  const placeholder = { id: replyId, conversation_id: userRow.conversation_id, origin: 'mobile',
    role: 'assistant', text: '', created_at: new Date().toISOString(), status: 'generating',
    model: modeloAtivo() };
  try { await storeMessages([placeholder]); } catch (_) { return; }
  await renderMessages();
  const qs = new URLSearchParams({ message_id: userRow.id,
    conversation_id: userRow.conversation_id, model: modeloAtivo() });
  aiAbort = new AbortController();
  let cur = '';
  const bubble = () => conversation.querySelector('[data-mid="' + replyId + '"] .bubble');
  try {
    const res = await fetch('/api/ai/stream?' + qs.toString(), {
      headers: { 'Accept': 'text/event-stream', 'X-CSRF-Token': csrf },
      credentials: 'same-origin', signal: aiAbort.signal });
    if (!res.ok || !res.body) throw new Error('IA indisponível (' + res.status + ')');
    const reader = res.body.getReader();
    const dec = new TextDecoder();
    let buf = '';
    let lastEvt = Date.now();
    let travou = false;
    const stall = setInterval(() => {
      if (Date.now() - lastEvt > 75000 && aiAbort) { travou = true; aiAbort.abort(); }
    }, 5000);
    try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let idx;
      while ((idx = buf.indexOf('\n\n')) >= 0) {
        const evt = buf.slice(0, idx); buf = buf.slice(idx + 2);
        let tipo = '', dados = '{}';
        for (const ln of evt.split('\n')) {
          if (ln.startsWith('event:')) tipo = ln.slice(6).trim();
          else if (ln.startsWith('data:')) dados += ln.slice(5).trim();
        }
        if (!tipo) continue; // ping/keepalive
        lastEvt = Date.now();
        let d = {};
        try { d = JSON.parse(dados); } catch (_) { continue; }
        if (tipo === 'delta') {
          cur += d.trecho || '';
          const el = bubble();
          if (el) el.textContent = cur;
          if (nearBottom(conversation)) conversation.scrollTop = conversation.scrollHeight;
        } else if (tipo === 'done') {
          await storeMessages([{ id: replyId, conversation_id: userRow.conversation_id,
            origin: 'mobile', role: 'assistant', text: d.response_text || cur,
            created_at: new Date().toISOString(), status: 'synced', model: d.model || modeloAtivo() }]);
        } else if (tipo === 'cancelled') {
          await storeMessages([{ id: replyId, conversation_id: userRow.conversation_id,
            origin: 'mobile', role: 'assistant', text: d.partial || cur,
            created_at: new Date().toISOString(), status: 'failed', model: modeloAtivo() }]);
        } else if (tipo === 'error') {
          throw new Error(d.error || 'IA indisponível');
        }
      }
    }
    } finally { clearInterval(stall); }
  } catch (err) {
    const interrompida = aiAbort && aiAbort.signal.aborted;
    await storeMessages([{ id: replyId, conversation_id: userRow.conversation_id,
      origin: 'mobile', role: 'assistant', text: cur,
      created_at: new Date().toISOString(), status: 'failed', model: modeloAtivo() }]);
    showToast(travou ? 'IA sem resposta há 75s. Verifique o agente/Hermes e toque para retomar.'
      : interrompida ? 'Geração interrompida. Toque na resposta para retomar.'
      : ('IA falhou: ' + (err.message || 'tente de novo')));
  } finally {
    aiAbort = null;
    await renderMessages();
  }
}
function stopAI() { if (aiAbort) aiAbort.abort(); }
conversation.addEventListener('click', event => {
  const stop = event.target.closest('[data-stop]');
  if (stop) { stopAI(); return; }
  const falha = event.target.closest('.message.failed');
  if (falha) {
    const mid = falha.dataset.mid || '';
    const uid = mid.endsWith('-r1') ? mid.slice(0, -3) : '';
    allMessages().then(rows => {
      const user = rows.find(m => m.id === uid);
      if (user) requestAI(user);
    });
  }
});
$('modelSelect').addEventListener('change', event => {
  localStorage.setItem('julia-model', event.target.value);
  $('aiStatus').textContent = 'IA pronta · ' + event.target.value;
});
async function sendMessage(raw) {
  const value = raw.trim(); if (!value) return;
  if (!db) { showToast('Este navegador não permitiu salvar o cache local'); return; }
  if (value.length > 10000) { showToast('Mensagem muito longa'); return; }
  const row = { id: newId(), conversation_id: activeConversation, origin: 'mobile', role: 'user',
    text: value, created_at: new Date().toISOString(), status: 'pending', want_ai: true };
  try {
    // Only clear the composer after a complete IndexedDB transaction.
    await storeMessages([row]); messageInput.value = ''; await renderMessages();
    if (pcOnline && authenticated) {
      const confirmados = await syncAndRefresh();
      if (confirmados.some(m => m.id === row.id)) requestAI({ ...row, status: 'synced' });
    } else showToast('Mensagem salva neste celular. Sincronização pendente.');
    if (navigator.storage?.persist) navigator.storage.persist().catch(() => {});
  } catch (err) {
    showToast('Não foi possível salvar a mensagem: verifique o armazenamento');
  }
}
composer.addEventListener('submit', e => { e.preventDefault(); if (authenticated) sendMessage(messageInput.value); });
document.querySelectorAll('.suggestion').forEach(b => b.addEventListener('click', () => sendMessage(b.dataset.message)));
$('resetChat').addEventListener('click', async () => {
  activeConversation = newId(); localStorage.setItem('julia-active-conversation', activeConversation);
  await renderMessages(); showToast('Nova conversa. As anteriores permanecem armazenadas.');
});
$('syncNow').addEventListener('click', async () => { await checkStatus(); showToast(pcOnline ? 'Sincronização conferida' : 'PC desligado ou sem conexão'); });
$('clearCache').addEventListener('click', async () => {
  if (!window.confirm('Apagar TODO o cache de mensagens neste celular, inclusive mensagens ainda não sincronizadas? Essa ação não pode ser desfeita.')) return;
  await clearStorage(); await renderMessages(); showToast('Cache local apagado');
});
$('attachButton').addEventListener('click', () => showToast('Anexos: previstos para a próxima etapa'));
$('statusButton').addEventListener('click', () => showToast(pcOnline ? 'Agente PC online' : 'Aguardando o agente local do Windows'));
$('keyboardButton').addEventListener('click', () => showToast('Controle remoto de teclado ainda não implementado'));
$('refreshButton').addEventListener('click', () => showToast('Transmissão remota ainda não implementada'));
$('touchMode').addEventListener('click', () => showToast('Controles remotos ainda não implementados'));
$('remoteFrame').addEventListener('click', event => {
  const bounds = event.currentTarget.getBoundingClientRect(); const pointer = $('remotePointer');
  pointer.style.display = 'block'; pointer.style.left = (event.clientX - bounds.left) + 'px'; pointer.style.top = (event.clientY - bounds.top) + 'px';
  showToast('Toque simulado — nenhum comando foi enviado');
});
$('fullscreen').addEventListener('click', async () => {
  const element = $('remoteFrame');
  if (!document.fullscreenEnabled) { showToast('Tela cheia indisponível'); return; }
  try { if (document.fullscreenElement) await document.exitFullscreen(); else await element.requestFullscreen(); }
  catch (_) { showToast('Tela cheia não autorizada'); }
});
window.addEventListener('online', checkStatus);
window.addEventListener('offline', () => { pcOnline = false; updateConnection(); });
document.addEventListener('visibilitychange', () => { if (!document.hidden) checkStatus(); });
setInterval(() => { if (!document.hidden) checkStatus(); }, 12000);
(async function init() {
  navigate('chat');
  try {
    db = await openDb();
    // Recupera interrupções: geração morta com o app fechado vira retry.
    const rows = await allMessages();
    const presas = rows.filter(m => m.status === 'generating');
    if (presas.length) await storeMessages(presas.map(m => ({ ...m, status: 'failed' })));
    await renderMessages();
  }
  catch (err) { showToast('Armazenamento local indisponível'); $('pendingCount').textContent = 'Cache indisponível'; }
  await restoreSession(); await checkStatus(); updateConnection();
  if ('serviceWorker' in navigator && location.protocol !== 'file:') {
    navigator.serviceWorker.register('/sw.js').catch(() => {});
  }
})();
