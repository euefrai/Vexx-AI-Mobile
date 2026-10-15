/* Julia Mobile v0.3: fullscreen chat + drawer + sessions + shared memory + rich markdown + fast streaming. */
'use strict';
const $ = id => document.getElementById(id);
const composer = $('composer');
const messageInput = $('messageInput');
const conversation = $('conversation');
const toast = $('toast');
const DB_NAME = 'julia-mobile-cache-v2';
const DB_OLD = 'julia-mobile-cache-v1';
const STORE = 'messages';
const SESSIONS = 'sessions';
const PREVIEW_MODE = location.protocol === 'file:';
let db = null;
let workspace = null;
let csrf = '';
let authenticated = false;
let pcOnline = false;
let busy = false;
let toastTimer;
let aiAbort = null;
let aiStartT = 0;
let aiFirstTokenT = 0;
let genTimer = null;
let modelsLoadedAt = 0;
let rafPending = null;
let rafText = '';
let rafReplyId = '';
let sessionsCache = [];
let activeConversation = null;
try { activeConversation = localStorage.getItem('julia-active-conversation') || newId(); } catch (_) { activeConversation = newId(); }
try { localStorage.setItem('julia-active-conversation', activeConversation); } catch (_) {}

function newId() { return crypto.randomUUID ? crypto.randomUUID() : (Date.now().toString(36) + Math.random().toString(36).slice(2)); }
function showToast(m) { toast.textContent = m; toast.classList.add('show'); clearTimeout(toastTimer); toastTimer = setTimeout(() => toast.classList.remove('show'), 3200); }
function esc(s) { return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }
function validUrl(u) { try { const p = new URL(String(u).trim(), location.href); return (p.protocol === 'http:' || p.protocol === 'https:' || p.protocol === 'data:') ? p.href : ''; } catch (_) { return ''; } }
function fmtTime(iso) { try { const d = new Date(iso); return d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' }); } catch (_) { return ''; } }

/* ----- Drawer ----- */
const drawer = $('drawer'), scrim = $('drawerScrim');
function setDrawer(open) {
  drawer.classList.toggle('open', open);
  drawer.setAttribute('aria-hidden', open ? 'false' : 'true');
  scrim.hidden = window.innerWidth >= 900 ? true : !open;
}
$('drawerOpen').addEventListener('click', () => setDrawer(true));
$('drawerClose').addEventListener('click', () => setDrawer(false));
scrim.addEventListener('click', () => setDrawer(false));

/* ----- Nav ----- */
const navItems = [...document.querySelectorAll('.drawer-item')];
const pages = [...document.querySelectorAll('.page')];
function navigate(tab) {
  const page = $('page-' + tab);
  if (!page) return;
  pages.forEach(p => { const on = p === page; p.hidden = !on; p.classList.toggle('active', on); });
  navItems.forEach(n => n.classList.toggle('active', n.dataset.tab === tab));
  const chat = tab === 'chat';
  document.querySelector('.bottom-dock').hidden = !chat;
  $('chatOptions').hidden = !chat;
  composer.style.display = chat ? 'flex' : 'none';
  if (tab === 'documents') renderDocs();
  if (!chat) { $('chatTitle').textContent = {desktop:'Meu PC',activity:'Atividades',estudos:'Estudos',settings:'Ajustes e conta',documents:'Documentos'}[tab] || 'Vexx AI'; $('chatSubtitle').textContent = 'Seu espaço pessoal'; }
  $('suggestions').style.display = chat ? 'flex' : 'none';
  document.querySelector('.composer-hint').style.display = chat ? 'flex' : 'none';
  if (tab === 'activity') renderTimeline();
  if (tab === 'estudos') renderEstudos();
  if (tab === 'settings') { loadMemories(); paintSavedItems(); }
  if (tab === 'chat' || tab === 'estudos') learnSyncOutbox();
  if (tab === 'chat' && db) renderMessages();
}
navItems.forEach(n => n.addEventListener('click', () => {
  navigate(n.dataset.tab);
  if (n.dataset.scroll === 'memory') {
    const t = $('memoryTitle');
    if (t) setTimeout(() => t.scrollIntoView({ block: 'start' }), 60);
  }
  if (window.innerWidth < 900) setDrawer(false);
}));
$('drawerLogout').addEventListener('click', () => $('logoutButton').click());

/* ----- IndexedDB ----- */
function reqPromise(r) { return new Promise((res, rej) => { r.onsuccess = () => res(r.result); r.onerror = () => rej(r.error); }); }
function txDone(tx) { return new Promise((res, rej) => { tx.oncomplete = res; tx.onerror = () => rej(tx.error); tx.onabort = () => rej(tx.error || Error('cancelada')); }); }
const UISTATE = 'ui_state';
const META = 'meta';
const SAVED = 'saved_items';
function openDb() {
  return new Promise((resolve, reject) => {
    if (!('indexedDB' in window)) { reject(Error('IndexedDB indisponivel')); return; }
    const req = indexedDB.open(DB_NAME, 4);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE)) {
        const m = db.createObjectStore(STORE, { keyPath: 'id' });
        m.createIndex('created_at', 'created_at');
        m.createIndex('conversation_id', 'conversation_id');
      }
      if (!db.objectStoreNames.contains(SESSIONS)) db.createObjectStore(SESSIONS, { keyPath: 'id' });
      if (!db.objectStoreNames.contains(UISTATE)) db.createObjectStore(UISTATE, { keyPath: 'k' });
      if (!db.objectStoreNames.contains(META)) db.createObjectStore(META, { keyPath: 'k' });
      if (!db.objectStoreNames.contains(SAVED)) db.createObjectStore(SAVED, { keyPath: 'id' });
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}
/* ----- Estado JDUI (offline-first) ----- */
let jduiStateCache = {};
let jduiDirty = {};
let jduiSyncTimer = null;
async function preloadJduiStates(msgIds) {
  jduiStateCache = {};
  if (!db || !msgIds || !msgIds.length) return;
  const want = new Set(msgIds);
  try {
    const rows = await reqPromise(db.transaction(UISTATE, 'readonly').objectStore(UISTATE).getAll());
    rows.forEach(r => {
      if (r && typeof r.k === 'string' && want.has(r.k.split('#')[0])
          && (r.owner || 'local') === currentUid) jduiStateCache[r.k] = r.state || {};
    });
  } catch (_) {}
}
function jduiCtx(row) {
  return {
    messageId: row.id,
    api: (endpoint, options) => api(endpoint, options),
    queueLearn: (endpoint, body) => queueLearn(endpoint, body),
    download: (name, mime, text) => downloadFile(name, mime, text),
    online: () => authenticated && pcOnline && navigator.onLine,
    markdown: (t) => renderMarkdown(String(t).replace(/```jdui[\s\S]*?(```|$)/gi, '')),
    loadState: (key) => jduiStateCache[row.id + '#' + key],
    saveState: (key, st) => {
      const k = row.id + '#' + key;
      jduiStateCache[k] = st;
      jduiDirty[k] = { k, message_id: row.id, slot: key, state: st, updated_at: new Date().toISOString(), owner: currentUid };
      persistJduiSoon();
    },
    onChat: (text) => sendMessage(text)
  };
}
async function persistJduiSoon() {
  if (!db) return;
  try {
    const tx = db.transaction(UISTATE, 'readwrite');
    const done = txDone(tx);
    const st = tx.objectStore(UISTATE);
    Object.values(jduiDirty).forEach(r => st.put(r));
    jduiDirty = {};
    await done;
  } catch (_) {}
  clearTimeout(jduiSyncTimer);
  jduiSyncTimer = setTimeout(syncJduiStates, 4000);
}
async function syncJduiStates() {
  if (!authenticated || !pcOnline || !db) return;
  try {
    const rows = (await reqPromise(db.transaction(UISTATE, 'readonly').objectStore(UISTATE).getAll()))
      .filter(r => (r.owner || 'local') === currentUid);
    if (!rows.length) return;
    await api('/api/ui-state', { method: 'POST', body: JSON.stringify({ states: rows.slice(-300) }) });
    const remote = await api('/api/ui-state');
    const tx = db.transaction(UISTATE, 'readwrite');
    const done = txDone(tx);
    const store = tx.objectStore(UISTATE);
    for (const r of remote.states || []) {
      try {
        const have = await reqPromise(db.transaction(UISTATE, 'readonly').objectStore(UISTATE).get(r.k)).catch(() => null);
        if (!have || (r.updated_at || '') >= (have.updated_at || '')) {
          store.put(Object.assign({}, r, { owner: currentUid }));
          jduiStateCache[r.k] = r.state || {};
        }
      } catch (_) {}
    }
    await done;
    await renderMessages();
  } catch (_) { /* offline: tenta na próxima */ }
}
async function migrateV1() {
  try {
    const old = await new Promise((res, rej) => { const r = indexedDB.open(DB_OLD, 1); r.onsuccess = () => res(r.result); r.onerror = () => rej(r.error); });
    let rows = [];
    try { rows = await reqPromise(old.transaction(STORE, 'readonly').objectStore(STORE).getAll()); } catch (_) {}
    old.close();
    if (rows && rows.length) {
      const mine = await allMessages();
      if (!mine.length) await storeMessages(rows.map(m => ({ id: m.id, conversation_id: m.conversation_id, origin: 'mobile', role: m.role, text: m.text, created_at: m.created_at, status: m.status === 'synced' ? 'synced' : 'pending', model: m.model || '' })));
      const convs = [...new Set(rows.map(r => r.conversation_id))];
      for (const c of convs) await ensureSession(c);
    }
  } catch (_) {}
}
async function allMessages() {
  if (!db) return [];
  const rows = await reqPromise(db.transaction(STORE, 'readonly').objectStore(STORE).getAll());
  return rows.sort((a, b) => a.created_at.localeCompare(b.created_at) || a.id.localeCompare(b.id));
}
async function storeMessages(ms) {
  if (!db) throw Error('Armazenamento indisponivel');
  const tx = db.transaction(STORE, 'readwrite');
  const done = txDone(tx);
  const st = tx.objectStore(STORE);
  for (const m of ms) st.put(m.owner ? m : Object.assign({}, m, { owner: currentUid }));
  await done;
}
async function deleteMessagesOf(conv) {
  const tx = db.transaction(STORE, 'readwrite');
  const done = txDone(tx);
  const st = tx.objectStore(STORE);
  const rows = await reqPromise(st.getAll());
  for (const r of rows) if (r.conversation_id === conv) st.delete(r.id);
  await done;
}
async function clearStorage() {
  const tx = db.transaction([STORE, SESSIONS, SAVED], 'readwrite');
  const done = txDone(tx);
  tx.objectStore(STORE).clear(); tx.objectStore(SESSIONS).clear(); tx.objectStore(SAVED).clear();
  await done;
}
async function allSessions() {
  if (!db) return [];
  const rows = await reqPromise(db.transaction(SESSIONS, 'readonly').objectStore(SESSIONS).getAll()).catch(() => []);
  if (workspace) await workspace.load();
  const mine = rows.filter(s => (s.owner || 'local') === currentUid);
  const ids = new Set(mine.map(s => s.id));
  if (workspace) workspace.list('chat').forEach(r => {
    if (!ids.has(r.id)) mine.push(Object.assign({owner: currentUid, created_at: r.updated_at}, r));
  });
  return mine.map(s => workspace ? workspace.overlay(s) : s).filter(s => !s.deleted)
    .sort((a, b) => (b.updated_at || '').localeCompare(a.updated_at || ''));
}
async function putSession(s) {
  const tx = db.transaction(SESSIONS, 'readwrite');
  const d = txDone(tx);
  const row = s.owner ? s : Object.assign({}, s, { owner: currentUid });
  tx.objectStore(SESSIONS).put(row);
  await d;
  if (workspace) await workspace.trackSession(row);
}
async function ownSessions() {
  const all = await allSessions();
  return all.filter(s => (s.owner || 'local') === currentUid);
}
async function savedItems() {
  if (!db) return [];
  const rows = await reqPromise(db.transaction(SAVED, 'readonly').objectStore(SAVED).getAll());
  return rows.filter(r => (r.owner || 'local') === currentUid)
    .sort((a, b) => (b.saved_at || '').localeCompare(a.saved_at || ''));
}
async function saveItem(item) {
  if (!db) throw Error('Armazenamento local indisponível');
  const row = Object.assign({ id: newId(), saved_at: new Date().toISOString(), owner: currentUid }, item);
  const tx = db.transaction(SAVED, 'readwrite');
  const done = txDone(tx);
  tx.objectStore(SAVED).put(row);
  await done;
  return row;
}
/* ----- Conversa ativa resiliente (localStorage pode ser limpo sem levar o IndexedDB) ----- */
function lsGet(k) { try { return localStorage.getItem(k); } catch (_) { return null; } }
function lsSet(k, v) { try { localStorage.setItem(k, v); } catch (_) {} }
async function metaGet(k) {
  if (!db) return null;
  try { const r = await reqPromise(db.transaction(META, 'readonly').objectStore(META).get(k)); return r ? r.v : null; }
  catch (_) { return null; }
}
async function metaSet(k, v) {
  if (!db) return;
  try {
    const tx = db.transaction(META, 'readwrite');
    const d = txDone(tx);
    tx.objectStore(META).put({ k, v });
    await d;
  } catch (_) {}
}
/* ----- Tombstones: conversa excluída não ressuscita no próximo sync ----- */
let deletedConvs = new Set();
async function loadTombstones() {
  deletedConvs = new Set();
  if (!db) return;
  try {
    const rows = await reqPromise(db.transaction(META, 'readonly').objectStore(META).getAll());
    rows.forEach(r => { if (r && typeof r.k === 'string' && r.k.indexOf('deleted:') === 0) deletedConvs.add(r.k.slice(8)); });
  } catch (_) {}
}
const isDeleted = (id) => deletedConvs.has(id) || !!(workspace && workspace.get('chat', id)?.deleted);
async function tombstone(convId) {
  deletedConvs.add(convId);
  await metaSet('deleted:' + convId, new Date().toISOString());
}
function setActiveConversation(id) {
  activeConversation = id;
  lsSet('julia-active-conversation', id);
  metaSet('active-conversation', id);
}
async function resolveActiveConversation() {
  // 1) localStorage, se ainda apontar para sessão existente (e não excluída)
  const sessions = (await ownSessions()).filter(s => !isDeleted(s.id));
  const ids = new Set(sessions.map(s => s.id));
  const viaLs = lsGet('julia-active-conversation');
  if (viaLs && ids.has(viaLs)) return viaLs;
  // 2) espelho no IndexedDB
  const viaMeta = await metaGet('active-conversation');
  if (viaMeta && ids.has(viaMeta)) { lsSet('julia-active-conversation', viaMeta); return viaMeta; }
  // 3) sessão mais recente COM mensagens (cura "cada abertura vira chat novo")
  const all = ownRows(await allMessages()).filter(m => !isDeleted(m.conversation_id));
  const withMsgs = new Set(all.map(m => m.conversation_id));
  const ranked = sessions.filter(s => withMsgs.has(s.id))
    .sort((a, b) => (b.updated_at || '').localeCompare(a.updated_at || ''));
  if (ranked.length) return ranked[0].id;
  if (sessions.length) return sessions[0].id;
  // 4) último recurso: id novo
  return newId();
}
async function healSessions() {
  // titula sessões "Nova conversa" que já têm mensagens + apaga vazias órfãs
  try {
    const all = ownRows(await allMessages());
    const firstByConv = {};
    all.forEach(m => {
      if (m.role === 'user' && !firstByConv[m.conversation_id]) firstByConv[m.conversation_id] = m.text;
    });
    const sessions = await ownSessions();
    const counts = {};
    all.forEach(m => { counts[m.conversation_id] = (counts[m.conversation_id] || 0) + 1; });
    for (const s of sessions) {
      if (isDeleted(s.id)) continue;
      if (s.title === 'Nova conversa' && firstByConv[s.id]) {
        s.title = titleFrom(firstByConv[s.id]); s.updated_at = new Date().toISOString();
        await putSession(s);

      }
    }
  } catch (_) {}
}
async function delSession(id) { const tx = db.transaction(SESSIONS, 'readwrite'); const d = txDone(tx); tx.objectStore(SESSIONS).delete(id); await d; }
async function ensureSession(id, title) {
  const cur = await reqPromise(db.transaction(SESSIONS, 'readonly').objectStore(SESSIONS).get(id)).catch(() => null);
  if (cur && (cur.owner || 'local') === currentUid) return workspace ? workspace.overlay(cur) : cur;
  const now = new Date().toISOString();
  const s = { id, title: title || 'Nova conversa', created_at: now, updated_at: now };
  await putSession(s);
  return s;
}
async function touchSession(id, hint) {
  const list = await ownSessions();
  const now = new Date().toISOString();
  let s = list.find(x => x.id === id);
  if (!s) s = { id, title: hint || 'Nova conversa', created_at: now, updated_at: now };
  else { s.updated_at = now; if (s.title === 'Nova conversa' && hint) s.title = hint; }
  await putSession(s);
}
function titleFrom(t) { return String(t || '').replace(/\s+/g, ' ').trim().slice(0, 44) || 'Nova conversa'; }

/* ----- Markdown rico e seguro ----- */
const ESC_DIV = document.createElement('div');
function escapeHtml(t) { ESC_DIV.textContent = t; return ESC_DIV.innerHTML; }
function inlineFmt(s) {
  s = s.replace(/`([^`\n]+)`/g, '<code>$1</code>');
  s = s.replace(/!\[([^\]]{0,120})\]\(([^)\s]+)\)/g, (m, alt, url) => {
    const u = validUrl(url);
    if (!u) return esc(m);
    const seed = alt.toLowerCase().replace(/[^a-z0-9]+/g, '').slice(0, 20) || 'julia';
    return '<img class="chat-img" loading="lazy" alt="' + alt + '" src="' + u + '" '
      + 'onerror="this.onerror=null;this.src=\'https://picsum.photos/seed/' + seed + '/800/500\'" />';
  });
  s = s.replace(/\[([^\]]+)\]\((https?:[^)\s]+)\)/g, (m, t, u) => '<a href="' + esc(u) + '" target="_blank" rel="noopener noreferrer">' + t + '</a>');
  s = s.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  s = s.replace(/~~([^~]+)~~/g, '<del>$1</del>');
  s = s.replace(/(^|[^*\w])\*([^*\n]+)\*/g, '$1<em>$2</em>');
  // Autolink SÓ em texto puro: nunca dentro de tags/atributos já gerados
  // (img src, href, code, onerror). Prefixo válido: início, espaço ou '('.
  s = s.replace(/(^|[\s(])(https?:\/\/[^\s<\]\)]+)/g, (m, pre, url) => {
    const e = url.match(/[.,;:!?]+$/);
    let u = url, suf = '';
    if (e) { u = url.slice(0, -e[0].length); suf = e[0]; }
    if (!u) return m;
    return pre + '<a href="' + u + '" target="_blank" rel="noopener noreferrer">' + u + '</a>' + suf;
  });
  return s;
}
function srcdocEsc(s) {
  return String(s).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
function sanitizeSvg(raw) {
  let s = String(raw || '').slice(0, 30000);
  s = s.replace(/<script[\s\S]*?<\/script\s*>/gi, '');
  s = s.replace(/<\s*foreignobject[\s\S]*?<\s*\/\s*foreignobject\s*>/gi, '');
  s = s.replace(/<\s*(iframe|object|embed|form|video|audio)\b[^>]*>[\s\S]*?<\s*\/\s*\1\s*>/gi, '');
  s = s.replace(/<\s*(iframe|object|embed|form|video|audio)\b[^>]*\/?>/gi, '');
  s = s.replace(/\son[a-z]+\s*=\s*("[^"]*"|'[^']*'|[^\s>]+)/gi, '');
  s = s.replace(/((?:href|xlink:href)\s*=\s*")\s*javascript:[^"]*"/gi, '$1#"');
  s = s.replace(/((?:href|xlink:href)\s*=\s*')\s*javascript:[^']*'/gi, "$1#'");
  return s.trim();
}
let pendingJdui = [];
let duoEmitted = false;
let lastAssistantId = '';
let showArchived = false;
function takeJduiSlots() { const s = pendingJdui; pendingJdui = []; return s; }
async function delMessage(id) {
  if (!db) return;
  const tx = db.transaction(STORE, 'readwrite');
  const done = txDone(tx);
  tx.objectStore(STORE).delete(id);
  await done;
}
function renderMarkdown(text) {
  if (!text) return '';
  const blocks = [];
  pendingJdui = [];
  duoEmitted = false;
  const widgets = [];
  const svgs = [];
  let src = String(text).replace(/\r\n/g, '\n');
  // JDUI: fences fechados válidos viram slots (montados após innerHTML);
  // fence aberto (stream) vira aviso amigável; inválido fechado some.
  if (typeof JDUI !== 'undefined') {
    src = src.replace(/```jdui\s*\n([\s\S]*?)(```|$)/gi, (m, body, close) => {
      if (!close) return '\n[JDUI: montando interface…]\n';
      try {
        const r = JDUI.validateMessage(JSON.parse(body));
        if (r.ok) return '\x00JDUI' + (pendingJdui.push(r.msg) - 1) + '\x00';
      } catch (_) { /* cai no descarte */ }
      return '';
    });
  }
  // Mini-apps executáveis: ```widget-html ... ``` → iframe isolado (sandbox, sem acesso ao app).
  src = src.replace(/```widget-html\s*\n([\s\S]*?)(```|$)/g, (m, code) => {
    const clean = code.replace(/\n$/, '');
    if (clean.length > 24000) {
      const i = blocks.push({ lang: 'html', code: clean }) - 1;
      return ' CODE' + i + ' ';
    }
    const i = widgets.push(clean) - 1;
    return ' WIDGET' + i + ' ';
  });
  // Desenhos vetoriais: ```svg ... ``` → SVG inline sanitizado.
  src = src.replace(/```svg\s*\n([\s\S]*?)(```|$)/g, (m, code) => {
    const i = svgs.push(code.replace(/\n$/, '')) - 1;
    return ' SVG' + i + ' ';
  });
  src = src.replace(/```(\w*)\n([\s\S]*?)(```|$)/g, (m, lang, code) => {
    const i = blocks.push({ lang: (lang || '').slice(0, 20), code: code.replace(/\n$/, '') }) - 1;
    return ' CODE' + i + ' ';
  });
  let refsHtml = '';
  const refM = src.match(/\n((Fontes|Refer[eê]ncias|Sources)\s*:?[\s\S]*)$/i);
  let refBody = '';
  if (refM) { refBody = refM[1]; src = src.slice(0, refM.index); }
  else {
    const lines = src.split('\n');
    const tail = lines.slice(-6).join('\n');
    if (/https?:\/\//.test(tail) && /fonte|http|\[https/i.test(tail)) { /* deixa inline */ }
  }
  if (refBody) {
    const items = escapeHtml(refBody).split('\n').map(l => l.trim()).filter(Boolean);
    const lis = items.slice(1).map(l => {
      const m = l.match(/(https?:\/\/[^\s<]+)/);
      if (m) return '<a href="' + m[1] + '" target="_blank" rel="noopener noreferrer">' + l + '</a>';
      return '<span>' + l + '</span>';
    }).join('');
    refsHtml = '<div class="refs"><strong>FONTES / REFERENCIAS</strong>' + (lis || '<span>' + (items[0] || '') + '</span>') + '</div>';
  }
  const html = [];
  const lines = escapeHtml(src).split('\n');
  let list = null, bq = [], table = [];
  function flushList() { if (list) { html.push(list.tag === 'ol' ? '<ol>' + list.items.map(i => '<li>' + inlineFmt(i) + '</li>').join('') + '</ol>' : '<ul>' + list.items.map(i => '<li>' + inlineFmt(i) + '</li>').join('') + '</ul>'); list = null; } }
  function flushBq() { if (bq.length) { html.push('<blockquote>' + bq.map(inlineFmt).join('<br>') + '</blockquote>'); bq = []; } }
  function flushTable() {
    if (table.length >= 2) {
      const head = table[0].split('|').map(c => c.trim()).filter(c => c !== '');
      const rows = table.slice(2).map(r => r.split('|').map(c => c.trim()).filter(c => c !== ''));
      html.push('<div class="table-wrap"><table><thead><tr>' + head.map(c => '<th>' + inlineFmt(c) + '</th>').join('') + '</tr></thead><tbody>' + rows.map(r => '<tr>' + r.map(c => '<td>' + inlineFmt(c) + '</td>').join('') + '</tr>').join('') + '</tbody></table></div>');
    } else if (table.length) { table.forEach(t => html.push('<p>' + inlineFmt(t) + '</p>')); }
    table = [];
  }
  for (const raw of lines) {
    const ln = raw.trimEnd();
    const t = ln.trim();
    const codePh = ln.match(/ CODE(\d+) /);
    if (codePh) {
      flushList(); flushBq(); flushTable();
      const bn = Number(codePh[1]);
      const b = blocks[bn];
      let duoQi = -1;
      if (typeof JDUI !== 'undefined' && JDUI.quizFromCode && (b.lang === '' || /^(py|python)$/i.test(b.lang || ''))) {
        const hasQuiz = pendingJdui.some(function (m) { return (m.blocks || []).some(function (x) { return x.component === 'quiz'; }); });
        if (!hasQuiz) {
          try {
            const qm = JDUI.quizFromCode(b.code);
            if (qm) { duoQi = pendingJdui.push(qm) - 1; duoEmitted = true; }
          } catch (_) {}
        }
      }
      if (duoQi >= 0) {
        html.push('<div class="jdui-duo"><div class="jdui-tabbar"><button class="jdui-tab on" data-duo="ui" type="button">Interface</button><button class="jdui-tab" data-duo="code" type="button">C&#243;digo</button></div>'
          + '<div class="jdui-slot" data-jdui="' + duoQi + '"></div>'
          + '<div class="codeblock" hidden><span class="code-lang">' + esc(b.lang || 'code') + '</span><button class="code-copy" data-code="' + bn + '" type="button">Copiar</button><pre><code>' + esc(b.code) + '</code></pre></div></div>');
      } else {
        html.push('<div class="codeblock"><span class="code-lang">' + esc(b.lang || 'code') + '</span><button class="code-copy" data-code="' + bn + '" type="button">Copiar</button><pre><code>' + esc(b.code) + '</code></pre></div>');
      }
      continue;
    }
    const wPh = ln.match(/ WIDGET(\d+) /);
    if (wPh && widgets[Number(wPh[1])] !== undefined) {
      flushList(); flushBq(); flushTable();
      const wi = Number(wPh[1]);
      const wcode = widgets[wi];
      html.push('<div class="widget"><div class="widget-bar"><span>▶ Mini app interativo</span>'
        + '<button class="widget-code-btn" data-widget="' + wi + '" type="button">Ver código</button></div>'
        + '<iframe class="widget-frame" sandbox="allow-scripts" loading="lazy" title="Mini app da Júlia" srcdoc="' + srcdocEsc(wcode) + '"></iframe>'
        + '<pre class="widget-code" data-widget-code="' + wi + '" hidden><code>' + esc(wcode) + '</code></pre></div>');
      continue;
    }
    const svgPh = ln.match(/ SVG(\d+) /);
    if (svgPh && svgs[Number(svgPh[1])] !== undefined) {
      flushList(); flushBq(); flushTable();
      const clean = sanitizeSvg(svgs[Number(svgPh[1])]);
      html.push(clean ? '<div class="svg-art">' + clean + '</div>' : '<p>[desenho vazio]</p>');
      continue;
    }
    const jPh = ln.match(/\x00JDUI(\d+)\x00/);
    if (jPh && pendingJdui[Number(jPh[1])]) {
      flushList(); flushBq(); flushTable();
      html.push('<div class="jdui-slot" data-jdui="' + Number(jPh[1]) + '"></div>');
      continue;
    }
    if (/^\|.*\|$/.test(t) && t.includes('|')) {
      if (/^\|?[\s:|-]+\|?[\s:|.-]*$/.test(t) && table.length === 1) { table.push(t); continue; }
      if (table.length === 0) { flushList(); flushBq(); table.push(t); continue; }
      table.push(t); continue;
    } else if (table.length) flushTable();
    if (/^(#{1,4})\s+(.+)/.test(t)) { flushList(); flushBq(); const m = t.match(/^(#{1,4})\s+(.+)/); html.push('<h3>' + inlineFmt(m[2]) + '</h3>'); continue; }
    if (/^(-{3,}|\*{3,}|_{3,})$/.test(t)) { flushList(); flushBq(); html.push('<hr>'); continue; }
    if (/^&gt;/.test(ln) || /^>/.test(t)) { flushList(); bq.push(t.replace(/^(&gt;|>)\s?/, '')); continue; }
    else if (bq.length) flushBq();
    const ol = t.match(/^(\d+)[.)]\s+(.+)/);
    const ul = t.match(/^[-*•]\s+(.+)/);
    if (ol) { if (!list || list.tag !== 'ol') { flushList(); list = { tag: 'ol', items: [] }; } list.items.push(ol[2]); continue; }
    if (ul) { if (!list || list.tag !== 'ul') { flushList(); list = { tag: 'ul', items: [] }; } list.items.push(ul[1]); continue; }
    if (list) flushList();
    if (!t) { html.push(''); continue; }
    const imgOnly = t.match(/^<img class="chat-img"[\s\S]*\/>$/);
    if (imgOnly) { html.push(t); continue; }
    html.push('<p>' + inlineFmt(t) + '</p>');
  }
  flushList(); flushBq(); flushTable();
  if (typeof JDUI !== 'undefined' && JDUI.quizFromText && !duoEmitted) {
    const hasQuiz = pendingJdui.some(function (m) { return (m.blocks || []).some(function (x) { return x.component === 'quiz'; }); });
    if (!hasQuiz) {
      try {
        const semCodigo = String(text).replace(/```[\s\S]*?(```|$)/g, ' ');
        const qm = JDUI.quizFromText(semCodigo);
        if (qm) {
          const qi = pendingJdui.push(qm) - 1;
          html.push('<div class="jdui-slot" data-jdui="' + qi + '"></div>');
        }
      } catch (_) {}
    }
  }
  // junta <p> seguidos sem vazio excessivo: mantem como estao
  return html.filter((h, i) => !(h === '' && html[i - 1] === '')).join('') + refsHtml;
}

/* ----- Render ----- */
function nearBottom(el) { return el.scrollHeight - el.scrollTop - el.clientHeight < 240; }
function scrollChat(force) {
  if (force || nearBottom(conversation)) conversation.scrollTop = conversation.scrollHeight;
}
conversation.addEventListener('scroll', () => { $('scrollFab').hidden = nearBottom(conversation); });
$('scrollFab').addEventListener('click', () => { conversation.scrollTop = conversation.scrollHeight; });

function appendMessage(row) {
  const type = row.role === 'assistant' ? 'ai' : 'user';
  const wrap = document.createElement('div');
  wrap.className = 'message ' + type + (row.status === 'failed' ? ' failed' : '');
  wrap.dataset.mid = row.id;
  if (type === 'ai') { const ic = document.createElement('div'); ic.className = 'bubble-avatar'; ic.textContent = '✦'; wrap.appendChild(ic); }
  const content = document.createElement('div'); content.className = 'message-content';
  if (type === 'ai') { const s = document.createElement('div'); s.className = 'sender'; s.textContent = 'Júlia'; content.appendChild(s); }
  const bubble = document.createElement('div'); bubble.className = 'bubble';
  if (row.status === 'generating') {
    bubble.innerHTML = '<span class="typing">digitando <span class="typing-indicator"><span class="typing-dot">•</span><span class="typing-dot">•</span><span class="typing-dot">•</span></span></span>';
    content.appendChild(bubble);
  } else {
    bubble.innerHTML = renderMarkdown(row.text)
      || (row.status === 'failed'
        ? '<p>Sem resposta da IA desta vez — toque em <strong>Tentar novamente</strong> abaixo. 🔄</p>'
        : '<p>…</p>');
    content.appendChild(bubble);
  }
  const jslots = takeJduiSlots();
  if (jslots.length && typeof JDUI !== 'undefined') {
    try {
      // V4.3 §12: patch in-place — blocos com update_of remontam a bolha alvo
      // com o ctx da mensagem ORIGINAL (estado preservado pelas mesmas chaves).
      const resto = [];
      jslots.forEach(slot => {
        const alvo = slot && slot.update_of;
        const elAlvo = (typeof alvo === 'string' && alvo)
          ? conversation.querySelector('[data-mid="' + alvo + '"] .bubble') : null;
        if (elAlvo) {
          elAlvo.querySelectorAll('.jdui-slot').forEach(s => s.remove());
          allMessages().then(rows => {
            const alvoRow = rows.find(m => m.id === alvo);
            if (alvoRow) { try { JDUI.mount(elAlvo, [slot], jduiCtx(alvoRow)); } catch (_) {} }
          });
        } else resto.push(slot);
      });
      if (resto.length) JDUI.mount(bubble, resto, jduiCtx(row));
    } catch (_) { /* fallback: só texto */ }
  }
  if (type === 'ai' && row.status !== 'generating') {
    // V4.5: resposta anuncia pesquisa agêntica → anexa o painel live (id real).
    const mj = /\(id (rj-[0-9a-f]+)\)/.exec(row.text || '');
    if (mj) { try { researchAttach(mj[1]); } catch (_) {} }
  }
  const meta = document.createElement('div'); meta.className = 'msg-meta';
  const tm = document.createElement('span'); tm.className = 'msg-time'; tm.textContent = fmtTime(row.created_at);
  meta.appendChild(tm);
  if (type === 'user') {
    const ack = document.createElement('span');
    ack.className = 'message-ack ' + (row.status === 'synced' ? 'synced' : 'pending');
    ack.textContent = row.status === 'synced' ? '✓ Sincronizado' : '◷ No celular';
    meta.appendChild(ack);
  } else {
    const mn = document.createElement('button'); mn.type = 'button'; mn.className = 'msg-menu-btn'; mn.dataset.menu = row.id;
    mn.textContent = '···'; mn.setAttribute('aria-label', 'Ações da mensagem'); mn.setAttribute('aria-haspopup', 'true');
    meta.appendChild(mn);
    if (row.status === 'failed') { const rt = document.createElement('button'); rt.type = 'button'; rt.className = 'message-retry'; rt.textContent = 'Tentar novamente'; meta.appendChild(rt); }

    // Rede de segurança: prometeu imagem mas não renderizou nenhuma.
    if (row.status !== 'generating' && !bubble.querySelector('img')
        && /\[?mostrando[^\n]{0,80}imagem|aqui est[áa][^\n]{0,80}imagem|exibindo[^\n]{0,80}imagem/i.test(row.text || '')) {
      const rb = document.createElement('button'); rb.type = 'button'; rb.className = 'message-retry';
      rb.textContent = '🖼️ A imagem não apareceu — gerar de novo';
      rb.dataset.imgRetry = row.id;
      content.appendChild(rb);
    }
  }
  content.appendChild(meta);
  wrap.appendChild(content);
  conversation.appendChild(wrap);
}
function paintStreaming(replyId, text) {
  const el = conversation.querySelector('[data-mid="' + replyId + '"] .bubble');
  if (!el) { takeJduiSlots(); return; }
  el.innerHTML = renderMarkdown(text) || '<span class="typing">digitando …</span>';
  const jslots = takeJduiSlots();
  // Remonta componentes só quando surgem novos slots (evita reconstruir a cada delta).
  if (jslots.length && jslots.length !== el._jduiN && typeof JDUI !== 'undefined') {
    el._jduiN = jslots.length;
    allMessages().then(rows => {
      const row = rows.find(m => m.id === replyId);
      if (row) { try { JDUI.mount(el, jslots, jduiCtx(row)); } catch (_) {} }
    });
  }
  scrollChat(false);
}
function schedulePaint(replyId, text) {
  rafReplyId = replyId; rafText = text;
  if (rafPending) return;
  rafPending = requestAnimationFrame(() => { rafPending = null; paintStreaming(rafReplyId, rafText); });
}

async function renderMessages() {
  if (!db) return;
  const all = ownRows(await allMessages());
  const rows = all.filter(m => m.conversation_id === activeConversation);
  await preloadJduiStates(rows.map(m => m.id));
  const stick = nearBottom(conversation);
  conversation.replaceChildren();
  conversation.classList.toggle('is-empty', rows.length === 0);
  const header = document.createElement('div'); header.className = 'chat-date';
  header.textContent = (sessionsCache.find(s => s.id === activeConversation)?.title || 'CONVERSA') + ' · HOJE';
  conversation.appendChild(header);
  if (!rows.length) {
    const w = document.createElement('div'); w.className = 'empty-chat';
    w.innerHTML = '<span class="welcome-mark" aria-hidden="true">v.</span><p>Seu espaço para pensar e criar.</p><h1>O que vamos fazer hoje?</h1><small>Converse, estude ou organize suas ideias em projetos.</small>';
    conversation.appendChild(w);
  } else {
    const idsAssist = rows.filter(m => m.role === 'assistant' && m.status === 'synced').map(m => m.id);
    lastAssistantId = idsAssist.length ? idsAssist[idsAssist.length - 1] : '';
    rows.forEach(appendMessage);
  }
  const temTroca = rows.some(m => m.role === 'user');
  if (!$('page-chat').hidden) $('suggestions').style.display = temTroca ? 'none' : 'flex';
  if (stick) conversation.scrollTop = conversation.scrollHeight;
  const pending = all.filter(m => m.status !== 'synced').length;
  $('pendingCount').textContent = pending + ' pendente' + (pending === 1 ? '' : 's');
  $('syncCounter').textContent = String(pending);
  $('statTasks').textContent = String(all.length);
  $('statSessions').textContent = String(sessionsCache.length || new Set(all.map(m => m.conversation_id)).size || 1);
  const cur = sessionsCache.find(s => s.id === activeConversation);
  $('chatTitle').textContent = cur ? cur.title : 'Nova conversa';
  const project = cur && workspace && workspace.get('project', cur.project_id);
  $('chatSubtitle').textContent = (project ? project.title : 'Sem projeto') + (cur?.archived ? ' · Arquivada' : '') + (rows.length ? ' · ' + rows.length + ' mensagens' : '');
}

$('archivedToggle').addEventListener('click', () => {
  showArchived = !showArchived;
  $('archivedToggle').setAttribute('aria-pressed', showArchived ? 'true' : 'false');
  $('archivedToggle').setAttribute('aria-label', showArchived ? 'Ocultar conversas arquivadas' : 'Mostrar conversas arquivadas');
  $('archivedToggle').title = showArchived ? 'Ocultar conversas arquivadas' : 'Mostrar conversas arquivadas';
  renderSessions($('sessionSearch').value);
});

async function renderTimeline() {
  const tl = $('timeline');
  if (!tl) return;
  const all = ownRows(await allMessages());
  tl.replaceChildren();
  const items = all.filter(m => !isDeleted(m.conversation_id)).slice(-6).reverse();
  if (!items.length) {
    tl.innerHTML = '<div class="timeline-item"><div class="timeline-icon"><svg class="icon"><use href="#i-sparkle"/></svg></div><div><strong>Pronto para explorar</strong><p>Envie a primeira mensagem no chat.</p><small>Agora · local</small></div></div>';
    return;
  }
  items.forEach(m => {
    const d = document.createElement('div'); d.className = 'timeline-item';
    d.innerHTML = '<div class="timeline-icon"><svg class="icon"><use href="#i-chat"/></svg></div><div><strong>' + esc((m.role === 'assistant' ? 'Júlia' : 'Você') + ' · ' + (m.status || '')) + '</strong><p>' + esc(String(m.text || '').slice(0, 120)) + '</p><small>' + esc(fmtTime(m.created_at)) + '</small></div>';
    tl.appendChild(d);
  });
}

/* ----- Fila offline educacional (V4.2.1 §4): outbox idempotente no SAVED ----- */
function learnOutboxKey(row) { return row && row.kind === 'learn-outbox'; }
async function learnOutbox() {
  if (!db) return [];
  const rows = await reqPromise(db.transaction(SAVED, 'readonly').objectStore(SAVED).getAll());
  return rows.filter(r => learnOutboxKey(r) && (r.owner || 'local') === currentUid)
    .sort((a, b) => (a.ts || '').localeCompare(b.ts || ''));
}
async function learnEnqueue(endpoint, body) {
  if (!db) throw Error('Armazenamento local indisponível');
  const row = { id: 'outbox-' + newId(), kind: 'learn-outbox', endpoint, body,
    ts: new Date().toISOString(), owner: currentUid, tries: 0 };
  const tx = db.transaction(SAVED, 'readwrite');
  const done = txDone(tx);
  tx.objectStore(SAVED).put(row);
  await done;
  return row;
}
async function learnOutboxDrop(id) {
  if (!db) return;
  const tx = db.transaction(SAVED, 'readwrite');
  const done = txDone(tx);
  tx.objectStore(SAVED).delete(id);
  await done;
}
async function learnSyncOutbox() {
  // Servidor corrige e valida; cliente nunca confia em pontuação local.
  // Conflito (tentativa finalizada/ausente → 404/409): descarta com registro.
  const pend = await learnOutbox();
  if (!pend.length || !navigator.onLine || !authenticated || !pcOnline) return { sent: 0, kept: pend.length };
  let sent = 0;
  for (const item of pend) {
    try {
      await api(item.endpoint, { method: 'POST', body: JSON.stringify(item.body) });
      await learnOutboxDrop(item.id);
      sent++;
    } catch (e) {
      if (e && (e.status === 404 || e.status === 409 || e.status === 422)) {
        await learnOutboxDrop(item.id); // conflito: não reenvia
      } else break; // rede/PC: mantém o resto para a próxima
    }
  }
  return { sent, kept: (await learnOutbox()).length };
}
async function queueLearn(endpoint, body) {
  // Tenta online; sem conexão, enfileira (resposta com ts do aparelho).
  try {
    return await api(endpoint, { method: 'POST', body: JSON.stringify(body) });
  } catch (e) {
    if (!navigator.onLine || !pcOnline || (e && e.status >= 500)) {
      await learnEnqueue(endpoint, body);
      learnSyncOutbox();
      return { queued: true };
    }
    throw e;
  }
}
/* ----- Meus Estudos (V4.2): progresso, planos e revisoes, com cache offline ----- */
function learnKey(name) { return 'learn:' + currentUid + ':' + name; }
async function learnCachePut(name, data) {
  if (!db) return;
  try {
    const tx = db.transaction(META, 'readwrite');
    const done = txDone(tx);
    tx.objectStore(META).put({ k: learnKey(name), v: { at: new Date().toISOString(), data } });
    await done;
  } catch (_) {}
}
async function learnCacheGet(name) {
  if (!db) return null;
  try {
    const rows = await reqPromise(db.transaction(META, 'readonly').objectStore(META).getAll());
    const hit = (rows || []).find(r => r && r.k === learnKey(name));
    return hit ? hit.v : null;
  } catch (_) { return null; }
}
async function learnData(name, url, online) {
  if (online) {
    try {
      const data = await api(url);
      await learnCachePut(name, data);
      return { data, cached: false, at: null };
    } catch (_) {}
  }
  const hit = await learnCacheGet(name);
  return { data: hit ? hit.data : null, cached: true, at: hit ? hit.at : null };
}
function estudosItem(icon, title, desc, small) {
  return '<div class="timeline-icon"><svg class="icon"><use href="#' + icon + '"/></svg></div>'
    + '<div><strong>' + esc(title) + '</strong>'
    + (desc ? '<p>' + esc(desc) + '</p>' : '')
    + (small ? '<small>' + esc(small) + '</small>' : '') + '</div>';
}
function estudosLista(id, rows) {
  const box = $(id);
  if (!box) return;
  box.replaceChildren();
  rows.forEach(html => {
    const d = document.createElement('div');
    d.className = 'timeline-item';
    d.innerHTML = html;
    box.appendChild(d);
  });
}
async function renderEstudos() {
  if (!$('estudosGrid') || !$('page-estudos')) return;
  const online = navigator.onLine && authenticated && pcOnline && !PREVIEW_MODE;
  const [stats, plans, due, mistakes, rec] = await Promise.all([
    learnData('stats', '/api/learn/stats', online),
    learnData('plans', '/api/learn/plans', online),
    learnData('due', '/api/learn/cards/due?limite=20', online),
    learnData('mistakes', '/api/learn/mistakes?limite=10', online),
    learnData('recommend', '/api/learn/recommend', online),
  ]);
  const aviso = $('estudosAviso');
  const at = [stats, plans, due, mistakes, rec].map(x => x.at).filter(Boolean).sort().pop();
  if (aviso) {
    const semDados = !stats.data && !plans.data;
    aviso.hidden = !semDados && !stats.cached;
    aviso.textContent = semDados
      ? 'Sem dados ainda — faça um quiz no chat para começar.'
      : 'Offline — mostrando dados salvos' + (at ? ' em ' + esc(at.slice(0, 16).replace('T', ' ')) : '') + '.';
  }
  const r = (stats.data && stats.data.resumo) || {};
  $('estProvas').textContent = r.concluidas || 0;
  $('estAcertos').textContent = (r.acertos || 0) + '/' + (r.respostas || 0);
  $('estItens').textContent = (r.itens_feitos || 0) + '/' + (r.itens_plano || 0);
  $('estDue').textContent = r.revisoes_pendentes || 0;
  estudosLista('estudosAssuntos', ((stats.data && stats.data.por_assunto) || []).map(p =>
    estudosItem('i-activity', (p.assunto || 'geral') + ' — ' + Math.round((p.taxa || 0) * 100) + '%',
      (p.acertos || 0) + ' acertos em ' + (p.total || 0) + ' respostas', null)));
  const recs = (rec.data && rec.data.recomendacoes) || [];
  estudosLista('estudosRecs', recs.length ? recs.map(x =>
    estudosItem('i-sparkle', x.detalhe || x.tipo, 'Base: dados reais do seu estudo', null))
    : [estudosItem('i-sparkle', 'Nada a recomendar ainda',
      (rec.data && rec.data.aviso) || 'Responda quizzes para receber sugestões.', null)]);
  estudosLista('estudosPlanos', ((plans.data && plans.data.planos) || []).map(p =>
    estudosItem('i-chat', p.titulo + ' — ' + (p.feitos || 0) + '/' + (p.total || 0),
      (p.assunto ? p.assunto + ' · ' : '') + (p.prazo_iso ? 'até ' + p.prazo_iso : 'sem prazo'), null)));
  estudosLista('estudosDue', ((due.data && due.data.cards) || []).slice(0, 20).map(c =>
    '<div class="timeline-icon"><svg class="icon"><use href="#i-refresh"/></svg></div>'
    + '<div><details><summary><strong>' + esc(c.frente || '') + '</strong>'
    + (c.assunto ? ' <small>' + esc(c.assunto) + '</small>' : '') + '</summary><p>'
    + esc(c.verso || '') + '</p></details></div>'));
  estudosLista('estudosErros', ((mistakes.data && mistakes.data.erradas) || []).map(e =>
    estudosItem('i-chat', e.enunciado || '',
      'Sua resposta: ' + (e.sua_resposta || '—'), e.assunto || null)));
}
/* ----- Live Research V4.5: telemetria real via polling (eventos do backend) ----- */
let researchJob = null;
const RESEARCH_FIM = ['concluida', 'cancelada', 'falhou', 'interrompida'];
function researchFase(ev) {
  const a = ev.agente || '', t = ev.tipo || '', s = ev.status || '';
  if (t === 'research_created' || t === 'plan_created') return 'Planejando…';
  if (t === 'plan_updated') return 'Replanejando…';
  if (t === 'research_completed') return 'Finalizado.';
  if (t === 'research_cancelled') return 'Interrompido.';
  if (t === 'research_failed') return 'Falhou.';
  if (t === 'source_opened') return s === 'falha' ? 'Fonte inacessível.' : 'Abrindo fontes…';
  if (t === 'extraction_completed' || t === 'evidence_registered' || t === 'evidence_linked') return 'Extraindo conteúdo…';
  if (t === 'source_dependency_detected') return 'Analisando fontes…';
  if (t === 'claim_identified') return 'Identificando afirmações…';
  if (t === 'claim_verified' || t === 'claim_verification_completed') return 'Verificando evidências…';
  if (t === 'contradiction_investigated') return 'Analisando contradições…';
  if (t === 'audit_started') return 'Auditando conclusões…';
  if (t === 'audit_completed') return 'Auditoria pronta.';
  if (a === 'search') return 'Pesquisando fontes…';
  if (a === 'analyst') return 'Analisando documentos…';
  if (a === 'checker' || a === 'auditor') return 'Verificando informações…';
  if (a === 'contradiction') return 'Analisando contradições…';
  if (a === 'synthesizer') return 'Gerando resposta…';
  return 'Pesquisando…';
}
function researchAttach(jobId) {
  if (!jobId || (researchJob && researchJob.id === jobId)) return;
  window._researchLast = jobId;
  researchJob = { id: jobId, seq: 0, vistos: new Set(), inicio: Date.now(), timer: null };
  $('researchBar').hidden = false;
  $('researchPanel').hidden = true;
  $('researchToggle').setAttribute('aria-expanded', 'false');
  $('researchSteps').replaceChildren();
  $('researchSources').replaceChildren();
  researchFiltroAtual = 'all';
  researchAplicaFiltro();
  $('researchLabel').textContent = 'Pesquisando…';
  researchPoll();
}
function researchStop() {
  if (researchJob && researchJob.timer) clearTimeout(researchJob.timer);
  researchJob = null;
}
function researchItem(icon, title, desc) {
  return '<div class="timeline-icon"><svg class="icon"><use href="#' + icon + '"/></svg></div>'
    + '<div><strong>' + esc(title) + '</strong>'
    + (desc ? '<p>' + esc(desc) + '</p>' : '') + '</div>';
}
async function researchPoll() {
  if (!researchJob) return;
  if (Date.now() - researchJob.inicio > 10 * 60 * 1000) { researchStop(); return; }
  // V4.7: SSE push em tempo real; qualquer falha cai no polling (fallback).
  try {
    await researchPollSSE();
  } catch (_) {
    await researchPollHTTP();
  }
  if (researchJob) researchJob.timer = setTimeout(researchPoll, 2000);
}
async function researchPollSSE() {
  const res = await fetch('/api/research/stream?job_id=' + encodeURIComponent(researchJob.id)
    + '&apos_seq=' + researchJob.seq,
    { headers: { Accept: 'text/event-stream', 'X-CSRF-Token': csrf }, credentials: 'same-origin' });
  if (!res.ok || !res.body) throw new Error('SSE indisponível (' + res.status + ')');
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = '';
  for (;;) {
    if (!researchJob) { try { await reader.cancel(); } catch (_) {} return; }
    const read = await reader.read();
    if (read.done) return;
    buf += dec.decode(read.value, { stream: true });
    let idx;
    while ((idx = buf.indexOf('\n\n')) >= 0) {
      const evt = buf.slice(0, idx); buf = buf.slice(idx + 2);
      let tipo = '', dados = '';
      for (const ln of evt.split('\n')) {
        if (ln.startsWith('event:')) tipo = ln.slice(6).trim();
        else if (ln.startsWith('data:')) dados += ln.slice(5).trim();
      }
      if (tipo !== 'research' || !researchJob) continue;
      let ev = null;
      try { ev = JSON.parse(dados); } catch (_) { continue; }
      if (ev && typeof ev.seq === 'number') researchRecebe(ev);
      if (ev && (ev.tipo === 'research_completed' || ev.tipo === 'research_failed'
        || ev.tipo === 'research_cancelled')) {
        try { await reader.cancel(); } catch (_) {}
        researchFinal(ev);
        return;
      }
    }
  }
}
async function researchPollHTTP() {
  const r = await api('/api/research/status?job_id=' + encodeURIComponent(researchJob.id)
    + '&apos_seq=' + researchJob.seq);
  (r.eventos || []).forEach(ev => researchRecebe(ev));
  const s = r.resumo || {};
  researchPintaResumo(s);
  if (RESEARCH_FIM.indexOf(s.status) >= 0) {
    $('researchLabel').textContent = s.status === 'concluida'
      ? 'Pesquisa concluída: ' + (s.evidencias || 0) + ' evidências.'
      : 'Pesquisa ' + s.status + '.';
    researchCarregaFontes();
    researchStop();
  }
}
function researchRecebe(ev) {
  if (!researchJob || researchJob.vistos.has(ev.seq)) return;
  researchJob.vistos.add(ev.seq);
  researchJob.seq = Math.max(researchJob.seq, ev.seq);
  const d = document.createElement('div');
  d.className = 'timeline-item';
  d.dataset.agente = ev.agente || '';
  d.dataset.tipo = ev.tipo || '';
  d.dataset.status = ev.status || '';
  d.innerHTML = researchItem('i-sparkle', researchFase(ev), ev.descricao || '');
  if (ev.meta && (ev.meta.trecho || ev.meta.url)) {
    const det = document.createElement('details');
    const sum = document.createElement('summary');
    sum.textContent = 'Ver evidência';
    det.appendChild(sum);
    if (ev.meta.trecho) {
      const p = document.createElement('p');
      p.textContent = String(ev.meta.trecho).slice(0, 300);
      det.appendChild(p);
    }
    if (ev.meta.url) {
      const a = document.createElement('a');
      a.href = ev.meta.url; a.target = '_blank'; a.rel = 'noopener noreferrer';
      a.textContent = 'Abrir fonte ↗';
      det.appendChild(a);
    }
    d.appendChild(det);
  }
  const box = $('researchSteps');
  box.appendChild(d);
  while (box.children.length > 30) box.firstChild.remove();
  researchAplicaFiltro();
  researchPintaResumo(null, ev);
}
let researchFiltroAtual = 'all';
function researchAplicaFiltro() {
  const box = $('researchSteps');
  if (!box) return;
  Array.prototype.forEach.call(box.children, el => {
    const a = el.dataset.agente || '', t = el.dataset.tipo || '', s = el.dataset.status || '';
    let mostra = researchFiltroAtual === 'all';
    if (researchFiltroAtual === 'search') mostra = a === 'search' || a === 'orchestrator';
    else if (researchFiltroAtual === 'source') mostra = a === 'analyst' || t === 'evidence_linked' || t === 'source_opened';
    else if (researchFiltroAtual === 'erros') mostra = s === 'falha' || s === 'alerta';
    el.style.display = mostra ? '' : 'none';
  });
}
document.querySelectorAll('#researchFilters button').forEach(b => b.addEventListener('click', () => {
  researchFiltroAtual = b.dataset.filtro || 'all';
  researchAplicaFiltro();
}));
function researchPintaResumo(s, ultimo) {
  s = s || null;
  if (s) {
    const feitas = (s.etapas || []).filter(e => e.status === 'feita').length;
    const total = (s.etapas || []).length;
    $('researchLabel').textContent = 'Pesquisando…' + (total ? ' (' + feitas + '/' + total + ')' : '');
    return;
  }
  if (ultimo) $('researchLabel').textContent = researchFase(ultimo);
}
function researchFinal(ev) {
  if (!researchJob) return;
  const id = researchJob.id;
  api('/api/research/status?job_id=' + encodeURIComponent(id) + '&apos_seq=0')
    .then(r => researchPintaResumo(r.resumo || {}))
    .catch(() => {})
    .finally(() => {
      const s = $('researchLabel');
      if (s && /Pesquisand/.test(s.textContent)) s.textContent = 'Pesquisa concluída. Ver detalhes.';
      researchCarregaFontes();
      researchStop();
    });
}
async function researchCarregaFontes() {
  if (!$('researchPanel') || $('researchPanel').hidden) return;
  try {
    const r = await api('/api/research/evidence?job_id=' + encodeURIComponent(
      (researchJob && researchJob.id) || window._researchLast || ''));
    const box = $('researchSources');
    box.replaceChildren();
    (r.evidencias || []).slice(0, 20).forEach(e => {
      const d = document.createElement('div');
      d.className = 'timeline-item';
      const ic = '<div class="timeline-icon"><svg class="icon"><use href="#i-chat"/></svg></div>';
      const a = document.createElement('a');
      a.href = e.url; a.target = '_blank'; a.rel = 'noopener noreferrer';
      a.textContent = e.titulo || e.dominio || e.url;
      const wrap = document.createElement('div');
      const st = document.createElement('strong');
      st.appendChild(a);
      wrap.appendChild(st);
      const sm = document.createElement('small');
      sm.textContent = (e.dominio || '') + ' · ' + (e.status || '');
      wrap.appendChild(sm);
      d.innerHTML = ic;
      d.appendChild(wrap);
      box.appendChild(d);
    });
  } catch (_) {}
}
$('researchToggle').addEventListener('click', () => {
  const p = $('researchPanel');
  p.hidden = !p.hidden;
  $('researchToggle').setAttribute('aria-expanded', p.hidden ? 'false' : 'true');
  if (!p.hidden) researchCarregaFontes();
});
$('researchCancel').addEventListener('click', async () => {
  if (!researchJob) return;
  try {
    await api('/api/research/cancel', { method: 'POST', body: JSON.stringify({ job_id: researchJob.id }) });
  } catch (_) {}
  $('researchLabel').textContent = 'Pesquisa cancelada.';
  researchStop();
});
$('researchResult').addEventListener('click', () => sendMessage('Mostra o resultado da pesquisa'));
$('researchPause').addEventListener('click', async () => {
  const id = (researchJob && researchJob.id) || window._researchLast;
  if (!id) return;
  const pausada = $('researchPause').textContent === 'Retomar';
  try {
    await api('/api/research/pause', { method: 'POST', body: JSON.stringify({ job_id: id, pausar: !pausada }) });
    $('researchPause').textContent = pausada ? 'Pausar' : 'Retomar';
    $('researchLabel').textContent = pausada ? 'Pesquisa retomada.' : 'Pesquisa pausada.';
    if (window._researchLast === id || (researchJob && researchJob.id === id)) researchPoll();
  } catch (_) {}
});
$('estudosRefresh').addEventListener('click', () => { renderEstudos(); learnSyncOutbox(); });

/* ----- Conexão / API ----- */
function memoryOn() { return $('memoryToggle').checked; }
$('memoryToggle').addEventListener('change', e => { localStorage.setItem('julia-memory', e.target.checked ? '1' : '0'); showToast(e.target.checked ? 'Memória entre chats ativada' : 'Memória entre chats pausada'); renderMessages(); });
if (localStorage.getItem('julia-memory') === '0') $('memoryToggle').checked = false;

function updateConnection() {
  const msg = PREVIEW_MODE ? 'Prévia local' : (!navigator.onLine ? 'Sem internet' : pcOnline ? 'PC conectado' : 'PC desconectado');
  $('connectionLabel').textContent = msg;
  $('connectionShort').textContent = pcOnline && navigator.onLine ? 'PC conectado' : 'Offline';
  $('statusButton').setAttribute('aria-label', 'Conexão: ' + msg);
  if (!pcOnline) $('aiStatus').textContent = 'PC desconectado';
  const on = pcOnline && navigator.onLine;
  $('statusButton').classList.toggle('online', on);
  document.querySelectorAll('#statusButton .status-dot, #popDot').forEach(d => {
    d.style.background = on ? 'var(--rose)' : '';
    d.style.boxShadow = on ? '0 0 0 3px var(--glow-rose)' : '';
  });
  $('popModel').textContent = modeloAtivo() || '—';
  $('popSync').textContent = $('syncCounter').textContent + ' pendentes'
    + (relayHa != null && relayHa >= 0 ? ' · agente há ' + relayHa + 's' : '');
  const dot = $('drawerDot'); if (dot) { dot.style.background = pcOnline ? '#ff2bd6' : '#5a5972'; }
  $('deviceStatus').textContent = pcOnline ? 'Online' : 'Offline';
  $('deviceStatus').classList.toggle('connected', pcOnline);
  $('deviceDetail').textContent = pcOnline ? 'Windows · Conectado' : 'Aguardando agente';
  $('memoryStatus').textContent = memoryOn() ? 'Ativada neste aparelho' : 'Pausada neste aparelho';
  $('syncStatusText').textContent = pcOnline ? 'PC disponível. Pendências serão sincronizadas.'
    : 'PC desconectado. Mensagens ficam no celular.' + (lastSyncErr ? ' ' + lastSyncErr : '');
}
let relayHa = null;
let lastSyncErr = '';
function marcaErroSync(msg) {
  try {
    lastSyncErr = 'Última falha ' + new Date().toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })
      + ' — ' + String(msg || 'sem resposta').slice(0, 90);
  } catch (_) { lastSyncErr = String(msg || '').slice(0, 90); }
}
$('statusButton').addEventListener('click', e => {
  e.stopPropagation();
  $('statusPop').hidden = !$('statusPop').hidden;
});
document.addEventListener('click', e => {
  if (!e.target.closest('#statusPop') && !e.target.closest('#statusButton')) $('statusPop').hidden = true;
  const mp = e.target.closest('.msg-menu-pop');
  if (!mp && !e.target.closest('[data-menu]')) document.querySelectorAll('.msg-menu-pop').forEach(p => p.remove());
});
async function api(endpoint, options) {
  options = options || {};
  const headers = { Accept: 'application/json' };
  if (options.body) headers['Content-Type'] = 'application/json';
  if (csrf && options.method && options.method !== 'GET') headers['X-CSRF-Token'] = csrf;
  const res = await fetch(endpoint, { method: options.method || 'GET', body: options.body, headers: Object.assign(headers, options.headers || {}), credentials: 'same-origin', cache: 'no-store' });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) { const err = new Error(typeof data.detail === 'string' ? data.detail : 'Erro HTTP ' + res.status); err.status = res.status; throw err; }
  return data;
}
let currentUid = 'local';
let currentRole = 'user';
try { currentUid = localStorage.getItem('julia-uid') || 'local'; } catch (_) {}
function pintarPerfil(display, username, role, online) {
  $('profileName').textContent = display || 'Conta';
  $('profileUser').textContent = username ? '@' + username : '@—';
  $('profileAvatar').textContent = (display || '?').trim().charAt(0).toUpperCase() || '✦';
  $('profileTag').textContent = online ? (role === 'admin' ? 'ADMIN' : 'ONLINE') : 'OFFLINE';
  const dp = $('drawerProfile');
  if (dp) {
    dp.querySelector('strong').textContent = display || 'Conta';
    dp.querySelector('small').textContent = username ? '@' + username : '';
    dp.querySelector('.profile-avatar').textContent = $('profileAvatar').textContent;
  }
}
function aplicarSessao(s) {
  // Troca de conta: recarrega para isolar caches (nunca mistura dados).
  const uid = s.uid || 'local';
  if (lsGet('julia-uid') && lsGet('julia-uid') !== uid) {
    lsSet('julia-uid', uid);
    location.reload();
    return false;
  }
  lsSet('julia-uid', uid);
  currentUid = uid;
  currentRole = s.role || 'user';
  pintarPerfil(s.user, s.username || '', currentRole, true);
  atualizarPerfilConta();
  return true;
}
async function atualizarPerfilConta() {
  if (!authenticated || PREVIEW_MODE || !navigator.onLine) return;
  try {
    const u = await api('/api/account');
    if (u && u.uid) {
      currentRole = u.role || currentRole;
      pintarPerfil(u.display || u.username, u.username || '', currentRole, true);
    }
  } catch (_) {}
}
function ownRows(rows) {
  return (rows || []).filter(m => (m.owner || 'local') === currentUid);
}
async function restoreSession() {
  if (PREVIEW_MODE) { authenticated = true; $('loginOverlay').hidden = true; return; }
  try {
    const s = await api('/api/session');
    csrf = s.csrf; authenticated = true; $('loginOverlay').hidden = true;
    if (aplicarSessao(s) === false) return;
  } catch (_) {
    authenticated = false; $('loginOverlay').hidden = false;
    pintarPerfil('Offline', '', 'user', false);
  }
  await fetchAuthConfig();
}
$('passToggle').addEventListener('click', () => {
  const inp = $('loginPassword');
  const show = inp.type === 'password';
  inp.type = show ? 'text' : 'password';
  $('passToggle').innerHTML = '<svg class="icon"><use href="#' + (show ? 'i-eye-off' : 'i-eye') + '"/></svg>';
  $('passToggle').setAttribute('aria-label', show ? 'Ocultar senha' : 'Mostrar senha');
  $('passToggle').setAttribute('aria-pressed', show ? 'true' : 'false');
});
$('loginForm').addEventListener('submit', async e => {
  e.preventDefault();
  const btn = $('loginButton'); btn.disabled = true; $('loginError').textContent = '';
  try {
    const r = await api('/api/login', { method: 'POST', body: JSON.stringify({ username: $('loginUser').value, password: $('loginPassword').value }) });
    $('loginPassword').value = ''; csrf = r.csrf; authenticated = true;
    $('loginOverlay').hidden = true;
    if (aplicarSessao(r) === false) return;
    await checkStatus(); showToast('Conectado');
  } catch (err) { $('loginError').textContent = err.message || 'Não foi possível entrar'; }
  finally { btn.disabled = false; }
});
$('logoutButton').addEventListener('click', async () => {
  try { await api('/api/logout', { method: 'POST' }); } catch (_) {}
  authenticated = false; csrf = ''; pcOnline = false; $('loginOverlay').hidden = false;
  $('loginPassword').value = ''; $('regPassword').value = ''; $('regPassword2').value = '';
  $('loginError').textContent = ''; $('regError').textContent = '';
  $('registerForm').hidden = true; $('loginForm').hidden = false; $('loginBack').hidden = true;
  pintarPerfil('Offline', '', 'user', false);
  updateConnection(); showToast('Sessão encerrada');
});

/* ----- Auth config + register flow ----- */
let authConfig = { modo: 'convite', exigir_aprovacao: true, agent_online: false };
async function fetchAuthConfig() {
  try { authConfig = await api('/api/auth/config'); }
  catch (_) { authConfig = { modo: 'convite', exigir_aprovacao: true, agent_online: false }; }
  const inviteWrap = $('regInviteWrap');
  const showRegister = $('showRegister');
  if (inviteWrap && showRegister) {
    if (authConfig.modo === 'convite') {
      inviteWrap.hidden = false;
    } else {
      inviteWrap.hidden = true;
    }
    if (authConfig.modo === 'fechado') {
      showRegister.style.display = 'none';
    } else {
      showRegister.style.display = '';
    }
  }
}
$('showRegister').addEventListener('click', () => {
  $('loginForm').hidden = true;
  $('registerForm').hidden = false;
  $('loginBack').hidden = false;
  $('regError').textContent = '';
});
$('showLogin').addEventListener('click', () => {
  $('registerForm').hidden = true;
  $('loginForm').hidden = false;
  $('loginBack').hidden = true;
  $('regError').textContent = '';
});
$('regPassToggle').addEventListener('click', () => {
  const inp = $('regPassword');
  const show = inp.type === 'password';
  inp.type = show ? 'text' : 'password';
  $('regPassToggle').innerHTML = '<svg class="icon"><use href="#' + (show ? 'i-eye-off' : 'i-eye') + '"/></svg>';
  $('regPassToggle').setAttribute('aria-label', show ? 'Ocultar senha' : 'Mostrar senha');
  $('regPassToggle').setAttribute('aria-pressed', show ? 'true' : 'false');
});
$('registerForm').addEventListener('submit', async e => {
  e.preventDefault();
  const btn = $('registerButton'); btn.disabled = true; $('regError').textContent = '';
  const pw1 = $('regPassword').value; const pw2 = $('regPassword2').value;
  if (pw1.length < 8) { $('regError').textContent = 'Senha precisa ter pelo menos 8 caracteres'; btn.disabled = false; return; }
  if (pw1 !== pw2) { $('regError').textContent = 'Senhas não coincidem'; btn.disabled = false; return; }
  try {
    const r = await api('/api/register', { method: 'POST', body: JSON.stringify({
      display: $('regDisplay').value, username: $('regUsername').value,
      password: pw1, invite: $('regInvite') ? $('regInvite').value : ''
    }) });
    $('regDisplay').value = ''; $('regUsername').value = ''; $('regPassword').value = '';
    $('regPassword2').value = ''; if ($('regInvite')) $('regInvite').value = '';
    if (r.status === 'pendente' || !r.csrf) {
      $('registerForm').hidden = true; $('loginForm').hidden = false; $('loginBack').hidden = true;
      showToast('Cadastro recebido! Aguarde aprovação para entrar.');
      return;
    }
    csrf = r.csrf; authenticated = true;
    $('loginOverlay').hidden = true;
    if (aplicarSessao(r) === false) return;
    showToast('Conta criada. Bem-vindo!');
    await checkStatus();
  } catch (err) { $('regError').textContent = err.message || 'Não foi possível cadastrar'; }
  finally { btn.disabled = false; }
});

/* ----- Conta: trocar senha + excluir (formulário inline, sem prompt) ----- */
$('changePwBtn').addEventListener('click', () => {
  if (currentUid === 'local') { showToast('Conta do proprietário: troque nas variáveis do servidor'); return; }
  if (!pcOnline) { showToast('PC offline — tente quando online'); return; }
  $('changePwForm').hidden = !$('changePwForm').hidden;
  $('pwError').textContent = '';
});
$('pwCancel').addEventListener('click', () => {
  $('changePwForm').hidden = true; $('pwAtual').value = ''; $('pwNova').value = ''; $('pwError').textContent = '';
});
$('pwSave').addEventListener('click', async () => {
  const nova = $('pwNova').value;
  if (nova.length < 8) { $('pwError').textContent = 'Nova senha: mínimo 8 caracteres'; return; }
  $('pwError').textContent = '';
  try {
    await api('/api/account/password', { method: 'POST', body: JSON.stringify({ atual: $('pwAtual').value, nova }) });
    $('changePwForm').hidden = true; $('pwAtual').value = ''; $('pwNova').value = '';
    showToast('Senha alterada');
  } catch (err) { $('pwError').textContent = err.message || 'Falha'; }
});
$('deleteAccountBtn').addEventListener('click', async () => {
  if (currentUid === 'local') { showToast('A conta do proprietário não se exclui por aqui'); return; }
  if (!pcOnline) { showToast('PC offline — tente quando online'); return; }
  if (!window.confirm('Excluir sua conta E todos os seus dados (conversas, memórias, documentos)? Sem volta!')) return;
  const senha = window.prompt('Digite sua senha para confirmar:');
  if (!senha) return;
  try {
    await api('/api/account/delete', { method: 'POST', body: JSON.stringify({ password: senha }) });
    showToast('Conta excluída');
    try { await api('/api/logout', { method: 'POST' }); } catch (_) {}
    location.reload();
  } catch (err) { showToast(err.message || 'Falha ao excluir'); }
});

async function checkStatus() {
  if (!authenticated || PREVIEW_MODE || !navigator.onLine) { pcOnline = false; updateConnection(); return; }
  try {
    const st = await api('/api/status');
    pcOnline = st.pc_online === true;
    if (typeof st.agente_ha === 'number') relayHa = st.agente_ha;
    try {
      const dg = await api('/api/diag');
      if (typeof dg.agente_ha === 'number') relayHa = dg.agente_ha;
    } catch (_) { /* diag é auxiliar; status já vale */ }
    updateConnection();
    if (pcOnline) {
      const conf = await syncAndRefresh();
      await loadModels(false);
      renderDocs();
      for (const m of conf.filter(m => m.want_ai && m.role === 'user')) requestAI(m);
      // puxa respostas prontas de outras sessões? tenta IA para pendentes recentes
      const all = ownRows(await allMessages());
      const pend = all.filter(m => m.role === 'user' && m.want_ai && m.status === 'synced' && !all.find(x => x.id === m.id + '-r1' && x.status === 'synced')).slice(-3);
      for (const m of pend) { if (!aiAbort) await requestAI(m); }
    }
  } catch (err) {
    pcOnline = false;
    if (err.status === 401) { authenticated = false; $('loginOverlay').hidden = false; }
    else marcaErroSync(err.status ? 'HTTP ' + err.status : 'rede?');
    updateConnection();
  }
}
async function syncAndRefresh() {
  if (busy || !authenticated || !pcOnline || !db) return [];
  busy = true;
  const conf = [];
  try {
    for (let guard = 0; guard < 5 && pcOnline; guard++) {
      const rem = ownRows(await allMessages()).filter(m => m.role === 'user' && m.status === 'pending').slice(0, 100);
      if (!rem.length) break;
      const clean = rem.map(m => ({ id: m.id, conversation_id: m.conversation_id, origin: 'mobile', role: 'user', text: m.text, created_at: m.created_at }));
      const r = await api('/api/sync', { method: 'POST', body: JSON.stringify({ messages: clean }) });
      const ok = new Set(r.confirmed_ids || []);
      if (!ok.size) break;
      const batch = rem.filter(m => ok.has(m.id));
      await storeMessages(batch.map(m => ({ id: m.id, conversation_id: m.conversation_id, origin: 'mobile', role: 'user', text: m.text, created_at: m.created_at, status: 'synced', want_ai: true })));
      conf.push(...batch);
    }
    const remote = await api('/api/messages');
    const adds = [];
    for (const m of remote.messages || []) {
      if (!m || typeof m.id !== 'string' || typeof m.text !== 'string' || m.origin !== 'mobile') continue;
      const cid = m.conversation_id || activeConversation;
      if (isDeleted(cid)) continue; // excluída: não ressuscita
      adds.push({ id: m.id, conversation_id: cid, origin: 'mobile', role: m.role === 'assistant' ? 'assistant' : 'user', text: m.text, created_at: m.created_at, status: 'synced', model: m.model || '' });
    }
    if (adds.length) {
      await storeMessages(adds);
      const convs = [...new Set(adds.map(a => a.conversation_id))];
      for (const c of convs) await touchSession(c);
    }
    await renderSessions($('sessionSearch').value);
    await renderMessages();
    syncJduiStates();
    if (workspace) await workspace.sync();
    return conf;
  } catch (err) {
    if (err.status === 503) pcOnline = false;
    if (err.status === 401) { authenticated = false; $('loginOverlay').hidden = false; }
    if (err.status && err.status !== 401) marcaErroSync('HTTP ' + err.status + ': ' + (err.message || ''));
    updateConnection();
    return conf;
  } finally { busy = false; }
}

/* ----- Modelos ----- */
function modeloAtivo() { return localStorage.getItem('julia-model') || ''; }
async function loadModels(force) {
  if (!authenticated || !pcOnline) { $('aiStatus').textContent = pcOnline ? 'IA: conectado' : 'IA: desconectado'; return; }
  if (!force && Date.now() - modelsLoadedAt < 300000) return;
  try {
    const r = await api('/api/ai/models');
    modelsLoadedAt = Date.now();
    const sel = $('modelSelect');
    const cur = modeloAtivo() || r.default || '';
    sel.replaceChildren();
    for (const id of r.models || []) { const o = document.createElement('option'); o.value = id; o.textContent = id; if (id === cur) o.selected = true; sel.appendChild(o); }
    if (cur && !(r.models || []).includes(cur)) { const o = document.createElement('option'); o.value = cur; o.textContent = cur + ' (salvo)'; o.selected = true; sel.appendChild(o); }
    if (!modeloAtivo() && r.default) localStorage.setItem('julia-model', r.default);
    $('aiStatus').textContent = 'IA pronta · ' + (modeloAtivo() || r.default || '?');
  } catch (_) { $('aiStatus').textContent = 'IA: Hermes indisponível'; }
}
$('modelSelect').addEventListener('change', e => { localStorage.setItem('julia-model', e.target.value); $('aiStatus').textContent = 'IA pronta · ' + e.target.value; });

/* ----- IA com streaming rápido ----- */
function setGenBar(on, label) {
  $('genBar').hidden = !on;
  if (label) $('genLabel').textContent = label;
}
function tickGen() {
  const s = Math.floor((Date.now() - aiStartT) / 1000);
  const ttft = aiFirstTokenT ? ' · 1º token ' + ((aiFirstTokenT - aiStartT) / 1000).toFixed(1) + 's' : '';
  $('genLabel').textContent = 'Júlia está escrevendo… ' + s + 's' + ttft;
}
function localContextKey(name) { return 'julia-context:' + currentUid + ':' + name; }
function aiLocalContext(text) {
  let timezone = '';
  try { timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || ''; } catch (_) {}
  const now = new Date();
  const offset = -now.getTimezoneOffset();
  const sign = offset >= 0 ? '+' : '-';
  const offsetText = sign + String(Math.floor(Math.abs(offset) / 60)).padStart(2, '0') +
    ':' + String(Math.abs(offset) % 60).padStart(2, '0');
  const localTime = new Date(now.getTime() - now.getTimezoneOffset() * 60000)
    .toISOString().slice(0, 19) + offsetText;
  const context = { local_time: localTime, timezone };
  const placeQuestion = /\b(perto|pr[oó]xim[oa]s?|na minha cidade|onde estou|localiza[cç][aã]o|clima|tempo em|previs[aã]o|restaurante|farm[aá]cia|hospital|loja|tr[aâ]nsito|endere[cç]o|pontos tur[ií]sticos|lugares)\b/i.test(text || '');
  if (!placeQuestion || !$('locationEnabled') || !$('locationEnabled').checked) return context;
  const city = String($('contextCity').value || '').trim().slice(0, 100);
  if (city) context.city = city;
  try {
    const saved = JSON.parse(localStorage.getItem(localContextKey('location')) || 'null');
    if (saved && Number.isFinite(saved.latitude) && Number.isFinite(saved.longitude)) {
      context.latitude = saved.latitude;
      context.longitude = saved.longitude;
    }
  } catch (_) {}
  return context;
}
async function requestAI(userRow) {
  if (!authenticated || !pcOnline || !db || aiAbort) return;
  const replyId = userRow.id + '-r1';
  const rows = await allMessages();
  const ja = rows.find(m => m.id === replyId);
  if (ja && (ja.status === 'synced' || ja.status === 'generating')) return;
  const ph = { id: replyId, conversation_id: userRow.conversation_id, origin: 'mobile', role: 'assistant', text: '', created_at: new Date().toISOString(), status: 'generating', model: modeloAtivo() };
  try { await storeMessages([ph]); } catch (_) { return; }
  if (userRow.conversation_id === activeConversation) await renderMessages();
  aiStartT = Date.now(); aiFirstTokenT = 0;
  setGenBar(true, 'Júlia está escrevendo… 0s');
  clearInterval(genTimer); genTimer = setInterval(tickGen, 500);
  const ctx = aiLocalContext(userRow.text || '');
  const qs = new URLSearchParams(Object.assign({
    message_id: userRow.id, conversation_id: userRow.conversation_id,
    model: modeloAtivo(), memory: memoryOn() ? '1' : '0',
    text: userRow.text || '', created_at: userRow.created_at || ''
  }, ctx));
  aiAbort = new AbortController();
  let cur = '';
  try {
    const res = await fetch('/api/ai/stream?' + qs.toString(), { headers: { Accept: 'text/event-stream', 'X-CSRF-Token': csrf }, credentials: 'same-origin', signal: aiAbort.signal });
    if (!res.ok || !res.body) throw new Error('IA indisponível (' + res.status + ')');
    const reader = res.body.getReader();
    const dec = new TextDecoder();
    let buf = '';
    let lastEvt = Date.now();
    const stall = setInterval(() => { if (Date.now() - lastEvt > 75000 && aiAbort) aiAbort.abort(); }, 5000);
    try {
      for (;;) {
        const read = await reader.read();
        if (read.done) break;
        buf += dec.decode(read.value, { stream: true });
        let idx;
        while ((idx = buf.indexOf('\n\n')) >= 0) {
          const evt = buf.slice(0, idx); buf = buf.slice(idx + 2);
          let tipo = '', dados = '';
          for (const ln of evt.split('\n')) {
            if (ln.startsWith('event:')) tipo = ln.slice(6).trim();
            else if (ln.startsWith('data:')) dados += ln.slice(5).trim();
          }
          if (!tipo) continue;
          lastEvt = Date.now();
          let d = {};
          try { d = JSON.parse(dados); } catch (_) { continue; }
          if (tipo === 'delta') {
            if (!aiFirstTokenT) { aiFirstTokenT = Date.now(); tickGen(); }
            cur += d.trecho || '';
            schedulePaint(replyId, cur);
          } else if (tipo === 'done') {
            if (rafPending) { cancelAnimationFrame(rafPending); rafPending = null; }
            const secs = Math.round((Date.now() - aiStartT) / 100) / 10;
            await storeMessages([{ id: replyId, conversation_id: userRow.conversation_id, origin: 'mobile', role: 'assistant', text: d.response_text || cur, created_at: new Date().toISOString(), status: 'synced', model: d.model || modeloAtivo(), latency_s: secs }]);
          } else if (tipo === 'cancelled') {
            await storeMessages([{ id: replyId, conversation_id: userRow.conversation_id, origin: 'mobile', role: 'assistant', text: d.partial || cur, created_at: new Date().toISOString(), status: 'failed', model: modeloAtivo() }]);
          } else if (tipo === 'error') throw new Error(d.error || 'IA indisponível');
        }
      }
      if (!cur) {
        const check = (await allMessages()).find(m => m.id === replyId);
        if (!check || check.status === 'generating') {
          // Stream veio vazio: tenta a resposta completa uma vez antes de falhar.
          try {
            const fb = await api('/api/ai', { method: 'POST', body: JSON.stringify({
              message_id: userRow.id, conversation_id: userRow.conversation_id,
              model: modeloAtivo(), memory: memoryOn() ? 1 : 0,
              text: userRow.text || '', created_at: userRow.created_at || '', ...ctx
            }) });
            if (fb.response_text && fb.response_text.trim()) {
              cur = fb.response_text;
              const secs = Math.round((Date.now() - aiStartT) / 100) / 10;
              await storeMessages([{ id: replyId, conversation_id: userRow.conversation_id, origin: 'mobile', role: 'assistant', text: cur, created_at: new Date().toISOString(), status: 'synced', model: fb.model || modeloAtivo(), latency_s: secs }]);
            } else throw new Error('Resposta vazia da IA');
          } catch (e2) { throw new Error('Resposta vazia da IA'); }
        }
      }
    } finally { clearInterval(stall); }
  } catch (err) {
    const inter = aiAbort && aiAbort.signal.aborted;
    const kept = cur || ((await allMessages()).find(m => m.id === replyId) || {}).text || '';
    await storeMessages([{ id: replyId, conversation_id: userRow.conversation_id, origin: 'mobile', role: 'assistant', text: kept, created_at: new Date().toISOString(), status: 'failed', model: modeloAtivo() }]);
    showToast(inter ? 'Interrompido. Toque para retomar.' : 'IA falhou: ' + (err.message || 'tente de novo'));
  } finally {
    aiAbort = null;
    clearInterval(genTimer);
    setGenBar(false);
    if (rafPending) { cancelAnimationFrame(rafPending); rafPending = null; }
    if (userRow.conversation_id === activeConversation) await renderMessages();
    await renderSessions($('sessionSearch').value);
  }
}
function stopAI() { if (aiAbort) aiAbort.abort(); }
$('stopGen').addEventListener('click', stopAI);
function toggleMsgMenu(btn) {
  const content = btn.closest('.message-content');
  const wasOpen = content.querySelector('.msg-menu-pop');
  document.querySelectorAll('.msg-menu-pop').forEach(p => p.remove());
  if (wasOpen) return;
  const mid = btn.dataset.menu || '';
  const wrap = btn.closest('.message');
  const failed = wrap && wrap.classList.contains('failed');
  const isLast = mid === lastAssistantId;
  const pop = document.createElement('div');
  pop.className = 'msg-menu-pop';
  pop.setAttribute('role', 'menu');
  const item = (act, label) => {
    const b = document.createElement('button');
    b.type = 'button'; b.dataset.act = act; b.textContent = label;
    b.setAttribute('role', 'menuitem');
    pop.appendChild(b);
  };
  item('copy', 'Copiar');
  if (!failed) {
    item('save', 'Salvar item neste aparelho');
    item('share', 'Compartilhar resposta');
    item('download', 'Baixar resposta em TXT');
    item('print', 'Imprimir / salvar resposta em PDF');
    item('regen', 'Regenerar resposta');
    if (isLast) item('cont', 'Continuar resposta');
  } else item('retry', 'Tentar novamente');
  content.appendChild(pop);
}
async function regenerateReply(userId) {
  if (!db || aiAbort) { if (aiAbort) showToast('Aguarde a geração atual'); return; }
  if (!pcOnline || !authenticated) { showToast('PC desconectado — tente quando online'); return; }
  const rows = await allMessages();
  const user = rows.find(m => m.id === userId);
  if (!user) return;
  try {
    await api('/api/ai/regenerate', { method: 'POST', body: JSON.stringify({ message_id: userId, conversation_id: user.conversation_id }) });
  } catch (err) { showToast('Falha ao reiniciar: ' + (err.message || '')); return; }
  await delMessage(userId + '-r1');
  if (user.conversation_id === activeConversation) await renderMessages();
  requestAI(user);
}
async function continueReply(userId) {
  if (!db || aiAbort) { if (aiAbort) showToast('Aguarde a geração atual'); return; }
  if (!pcOnline || !authenticated) { showToast('PC desconectado — tente quando online'); return; }
  const rows = await allMessages();
  const user = rows.find(m => m.id === userId);
  if (!user) return;
  setGenBar(true, 'Continuando…');
  try {
    const r = await api('/api/ai/continue', { method: 'POST', body: JSON.stringify({
      message_id: userId, conversation_id: user.conversation_id, model: modeloAtivo(),
      ...aiLocalContext(user.text || '')
    }) });
    await storeMessages([{ id: r.reply_id || (userId + '-r1'), conversation_id: user.conversation_id, origin: 'mobile', role: 'assistant', text: r.response_text, created_at: new Date().toISOString(), status: 'synced', model: r.model || modeloAtivo() }]);
    if (user.conversation_id === activeConversation) { await renderMessages(); scrollChat(true); }
  } catch (err) { showToast('Falha ao continuar: ' + (err.message || '')); }
  finally { setGenBar(false); }
}
conversation.addEventListener('click', e => {
  const duo = e.target.closest('[data-duo]');
  if (duo) {
    const wrap = duo.closest('.jdui-duo');
    if (wrap) {
      const showCode = duo.dataset.duo === 'code';
      wrap.querySelectorAll('[data-duo]').forEach(b => b.classList.toggle('on', b === duo));
      const slot = wrap.querySelector('.jdui-slot');
      const code = wrap.querySelector('.codeblock');
      if (slot) slot.hidden = showCode;
      if (code) code.hidden = !showCode;
    }
    return;
  }
  const wb = e.target.closest('.widget-code-btn');
  if (wb) {
    const wrap = wb.closest('.widget');
    const pre = wrap ? wrap.querySelector('.widget-code') : null;
    if (pre) {
      pre.hidden = !pre.hidden;
      wb.textContent = pre.hidden ? 'Ver código' : 'Ocultar código';
    }
    return;
  }
  const cp = e.target.closest('.code-copy');
  if (cp) {
    const pre = cp.parentElement.querySelector('code');
    if (pre && navigator.clipboard) navigator.clipboard.writeText(pre.innerText).then(() => showToast('Código copiado')).catch(() => showToast('Não foi possível copiar'));
    return;
  }
  const mc = e.target.closest('[data-copy]');
  if (mc) {
    const mid = mc.dataset.copy;
    allMessages().then(rows => {
      const r = rows.find(m => m.id === mid);
      if (r && navigator.clipboard) navigator.clipboard.writeText(r.text).then(() => showToast('Copiado')).catch(() => showToast('Não foi possível copiar'));
    });
    return;
  }
  const ir = e.target.closest('[data-img-retry]');
  if (ir) {
    const mid = ir.dataset.imgRetry || '';
    const uid = mid.endsWith('-r1') ? mid.slice(0, -3) : '';
    allMessages().then(rows => {
      const u = rows.find(m => m.id === uid);
      const tema = u ? u.text.replace(/\s+/g, ' ').trim().slice(0, 120) : 'pedida';
      sendMessage('Você disse que mostraria uma imagem sobre "' + tema + '" mas ela não apareceu. Responda agora SÓ com esta linha e nada mais: ![imagem](https://loremflickr.com/800/500/tema)');
    });
    return;
  }
  const mn = e.target.closest('[data-menu]');
  if (mn) { toggleMsgMenu(mn); return; }
  const mi = e.target.closest('.msg-menu-pop button');
  if (mi) {
    const wrap = mi.closest('.message');
    const mid = wrap ? wrap.dataset.mid : '';
    document.querySelectorAll('.msg-menu-pop').forEach(p => p.remove());
    if (!mid) return;
    if (mi.dataset.act === 'copy') {
      allMessages().then(rows => {
        const r = rows.find(m => m.id === mid);
        if (r && navigator.clipboard) navigator.clipboard.writeText(r.text).then(() => showToast('Copiado')).catch(() => showToast('Não foi possível copiar'));
      });
    } else if (mi.dataset.act === 'save' || mi.dataset.act === 'share'
        || mi.dataset.act === 'download' || mi.dataset.act === 'print') {
      const printWindow = mi.dataset.act === 'print' ? window.open('', '_blank') : null;
      allMessages().then(async rows => {
        const row = rows.find(m => m.id === mid);
        if (!row) { if (printWindow) printWindow.close(); return; }
        const title = String(row.text || '').split(/\r?\n/, 1)[0].replace(/^#+\s*/, '').slice(0, 80) || 'Resposta da Júlia';
        if (mi.dataset.act === 'save') {
          try {
            await saveItem({ title, text: row.text || '', message_id: row.id, conversation_id: row.conversation_id });
            showToast('Resposta salva neste aparelho.');
          } catch (_) { showToast('Não foi possível salvar a resposta.'); }
        } else if (mi.dataset.act === 'share') await shareText(title, row.text || '', true);
        else if (mi.dataset.act === 'download') {
          const filename = title.replace(/[^\w\- ]+/g, '').trim().slice(0, 40) || 'resposta-julia';
          downloadFile(filename + '.txt', 'text/plain', row.text || '');
          showToast('Resposta baixada em TXT.');
        } else {
          openPrintWindow(title, '<article><strong>Júlia</strong><pre>' + esc(row.text || '') + '</pre></article>', printWindow);
        }
      });
    } else if (mi.dataset.act === 'regen' || mi.dataset.act === 'cont' || mi.dataset.act === 'retry') {
      const uid = mid.endsWith('-r1') ? mid.slice(0, -3) : '';
      allMessages().then(rows => {
        const u = rows.find(m => m.id === (uid || mid));
        if (!u) return;
        if (mi.dataset.act === 'regen') regenerateReply(u.id);
        else if (mi.dataset.act === 'cont') continueReply(u.id);
        else requestAI(u);
      });
    }
    return;
  }
  const falha = e.target.closest('.message.failed');
  if (falha) {
    const mid = falha.dataset.mid || '';
    const uid = mid.endsWith('-r1') ? mid.slice(0, -3) : '';
    allMessages().then(rows => { const u = rows.find(m => m.id === uid); if (u) requestAI(u); });
  }
});

/* ----- Envio ----- */
function autoresize() { messageInput.style.height = 'auto'; messageInput.style.height = Math.min(messageInput.scrollHeight, 140) + 'px'; }
messageInput.addEventListener('input', () => {
  autoresize();
  const n = messageInput.value.length;
  $('charCount').textContent = n > 9000 ? n + ' / 10000' : '';
});
messageInput.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey && !e.isComposing && !window.matchMedia('(pointer: coarse)').matches) { e.preventDefault(); composer.requestSubmit(); } });
async function sendMessage(raw) {
  const value = String(raw || '').trim();
  if (!value) return;
  if (!db) { showToast('Cache local indisponível'); return; }
  if (value.length > 10000) { showToast('Mensagem muito longa'); return; }
  const row = { id: newId(), conversation_id: activeConversation, origin: 'mobile', role: 'user', text: value, created_at: new Date().toISOString(), status: 'pending', want_ai: true };
  try {
    await storeMessages([row]);
    await touchSession(activeConversation, titleFrom(value));
    messageInput.value = ''; autoresize(); $('charCount').textContent = '0 / 10000';
    await renderSessions($('sessionSearch').value);
    await renderMessages();
    scrollChat(true);
    if (pcOnline && authenticated) {
      const conf = await syncAndRefresh();
      if (conf.some(m => m.id === row.id)) requestAI(Object.assign({}, row, { status: 'synced' }));
      else {
        const cur = await allMessages();
        const synced = cur.find(m => m.id === row.id && m.status === 'synced');
        if (synced) requestAI(synced);
      }
    } else showToast('Salvo no celular');
    if (navigator.storage && navigator.storage.persist) navigator.storage.persist().catch(() => {});
  } catch (_) { showToast('Não foi possível salvar'); }
}
composer.addEventListener('submit', e => { e.preventDefault(); if (authenticated || PREVIEW_MODE) sendMessage(messageInput.value); else showToast('Faça login'); });
document.querySelectorAll('.suggestion').forEach(b => b.addEventListener('click', () => { messageInput.value = b.dataset.message; autoresize(); messageInput.focus(); }));
async function newChat(projectId = '') {
  if (!db) { showToast('Armazenamento local indisponível'); return; }
  if (typeof projectId !== 'string') projectId = '';
  setActiveConversation(newId());
  const session = await ensureSession(activeConversation);
  if (projectId) { session.project_id = projectId; await putSession(session); openProjects.add(projectId); }
  await renderSessions($('sessionSearch').value);
  await renderMessages();
  navigate('chat');
  messageInput.focus();
  if (window.innerWidth < 900) setDrawer(false);
  showToast(projectId ? 'Conversa criada no projeto' : 'Nova conversa');
}
$('newChatCta').addEventListener('click', newChat);
$('newChatTop').addEventListener('click', newChat);
$('sessionSearch').addEventListener('input', e => renderSessions(e.target.value));
$('syncNow').addEventListener('click', async () => { await checkStatus(); showToast(pcOnline ? 'Sincronizado' : 'PC desconectado'); });
function downloadFile(name, mime, text) {
  const blob = new Blob([text], { type: mime + ';charset=utf-8' });
  downloadBlob(name, blob);
}
function downloadBlob(name, blob) {
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = name;
  document.body.appendChild(a);
  a.click();
  setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
}
async function shareText(title, text, allowShare) {
  const payload = String(text || '');
  if (allowShare && navigator.share) {
    try { await navigator.share({ title, text: payload }); return; }
    catch (err) {
      if (err && err.name === 'AbortError') return;
    }
  }
  if (!navigator.clipboard || !navigator.clipboard.writeText) {
    showToast('Compartilhamento indisponível neste navegador.');
    return;
  }
  try { await navigator.clipboard.writeText(payload); showToast('Copiado para compartilhar.'); }
  catch (_) { showToast('Não foi possível copiar.'); }
}
async function exportConversation(fmt) {
  if (!db) { showToast('Cache indisponível'); return; }
  const rows = ownRows(await allMessages()).filter(m => m.conversation_id === activeConversation);
  const s = (await ownSessions()).find(x => x.id === activeConversation);
  const title = (s && s.title ? s.title : 'conversa').replace(/[^\w\- ]+/g, '').trim().slice(0, 40) || 'conversa';
  if (!rows.length) { showToast('Nada para exportar'); return; }
  if (fmt === 'json') {
    downloadFile(title + '.json', 'application/json', JSON.stringify({ title, exported_at: new Date().toISOString(), messages: rows }, null, 2));
  } else if (fmt === 'txt') {
    const text = rows.map(m => (m.role === 'assistant' ? 'Júlia' : 'Você') + ' · ' +
      fmtTime(m.created_at) + '\n' + String(m.text || '')).join('\n\n');
    downloadFile(title + '.txt', 'text/plain', text);
  } else if (fmt === 'csv') {
    const quote = value => {
      let text = String(value == null ? '' : value);
      if (/^[=+\-@]/.test(text)) text = "'" + text;
      return '"' + text.replace(/"/g, '""') + '"';
    };
    const csv = [['Autor', 'Data e hora', 'Mensagem'], ...rows.map(m => [
      m.role === 'assistant' ? 'Júlia' : 'Você', m.created_at || '', m.text || ''
    ])].map(row => row.map(quote).join(',')).join('\r\n');
    downloadFile(title + '.csv', 'text/csv', '\uFEFF' + csv);
  } else {
    let md = '# ' + title + '\n\n_Exportado da Júlia Mobile em ' + new Date().toLocaleString('pt-BR') + '_\n\n';
    rows.forEach(m => {
      md += (m.role === 'assistant' ? '## ✦ Júlia' : '## Você') + ' · ' + fmtTime(m.created_at) + '\n\n' + String(m.text || '') + '\n\n---\n\n';
    });
    downloadFile(title + '.md', 'text/markdown', md);
  }
  showToast('Exportado: ' + title);
}
async function exportXlsx() {
  if (!db) { showToast('Cache indisponível'); return; }
  const rows = ownRows(await allMessages()).filter(m => m.conversation_id === activeConversation);
  const session = (await ownSessions()).find(s => s.id === activeConversation);
  if (!rows.length) { showToast('Nada para exportar'); return; }
  if (rows.length > 500) { showToast('Esta conversa excede o limite de 500 mensagens para Excel.'); return; }
  try {
    const response = await fetch('/api/export/xlsx', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf },
      credentials: 'same-origin',
      body: JSON.stringify({
        title: (session && session.title) || 'Conversa',
        messages: rows.map(m => ({
          role: m.role, text: String(m.text || '').slice(0, 10000), created_at: m.created_at || ''
        }))
      })
    });
    if (!response.ok) throw new Error('Exportação indisponível (' + response.status + ')');
    downloadBlob('conversa.xlsx', await response.blob());
    showToast('Planilha Excel exportada.');
  } catch (err) { showToast(err.message || 'Falha ao exportar Excel.'); }
}
function openPrintWindow(title, contentHtml, printWindow) {
  printWindow = printWindow || window.open('', '_blank');
  if (!printWindow) { showToast('Permita a abertura de uma janela para imprimir ou salvar em PDF.'); return; }
  printWindow.document.open();
  printWindow.document.write('<!doctype html><html lang="pt-BR"><meta charset="utf-8"><title>' +
    esc(title) + '</title><style>' +
    'body{font:15px system-ui,sans-serif;max-width:850px;margin:32px auto;color:#172033}h1{font-size:24px}' +
    'article{border:1px solid #d9deea;border-radius:12px;padding:14px;margin:12px 0;break-inside:avoid}' +
    'strong{color:#5145cd}pre{font:inherit;white-space:pre-wrap;overflow-wrap:anywhere;margin-bottom:0}' +
    '@media print{body{margin:0 auto}article{border-color:#bbb}}</style><h1>' +
    esc(title) + '</h1>' + contentHtml + '</html>');
  printWindow.document.close();
  printWindow.focus();
  setTimeout(() => printWindow.print(), 250);
}
async function printConversation(printWindow) {
  if (!db) { if (printWindow) printWindow.close(); showToast('Cache indisponível'); return; }
  const rows = ownRows(await allMessages()).filter(m => m.conversation_id === activeConversation);
  if (!rows.length) { if (printWindow) printWindow.close(); showToast('Nada para imprimir'); return; }
  const session = (await ownSessions()).find(s => s.id === activeConversation);
  const cards = rows.map(m => '<article><strong>' + esc(m.role === 'assistant' ? 'Júlia' : 'Você') +
    ' · ' + esc(fmtTime(m.created_at)) + '</strong><pre>' + esc(m.text || '') + '</pre></article>').join('');
  openPrintWindow((session && session.title) || 'Conversa', cards, printWindow);
}
$('exportMd').addEventListener('click', () => exportConversation('md'));
$('exportJson').addEventListener('click', () => exportConversation('json'));
$('exportTxt').addEventListener('click', () => exportConversation('txt'));
$('exportCsv').addEventListener('click', () => exportConversation('csv'));
$('exportXlsx').addEventListener('click', exportXlsx);
$('exportPdf').addEventListener('click', () => printConversation(window.open('', '_blank')));
$('shareConversation').addEventListener('click', async () => {
  if (!db) { showToast('Cache indisponível'); return; }
  const rows = ownRows(await allMessages()).filter(m => m.conversation_id === activeConversation);
  if (!rows.length) { showToast('Nada para compartilhar'); return; }
  const text = rows.map(m => (m.role === 'assistant' ? 'Júlia' : 'Você') + ': ' + (m.text || '')).join('\n\n');
  const session = (await ownSessions()).find(s => s.id === activeConversation);
  await shareText((session && session.title) || 'Conversa com Júlia', text, true);
});
$('clearCache').addEventListener('click', async () => {
  if (!window.confirm('Apagar todo o cache? Esta ação não pode ser desfeita.')) return;
  await clearStorage();
  ['city', 'location', 'enabled'].forEach(key => {
    try { localStorage.removeItem(localContextKey(key)); } catch (_) {}
  });
  $('contextCity').value = '';
  $('locationEnabled').checked = false;
  $('locationStatus').textContent = 'Localização e dados locais apagados.';
  setActiveConversation(newId());
  await ensureSession(activeConversation);
  await renderSessions(''); await renderMessages(); showToast('Cache apagado');
});
$('attachButton').addEventListener('click', () => {
  if (!authenticated && !PREVIEW_MODE) { showToast('Faça login'); return; }
  if (!pcOnline) { showToast('PC desconectado — anexe quando online'); return; }
  $('fileInput').click();
});
$('fileInput').addEventListener('change', async e => {
  const f = e.target.files && e.target.files[0];
  e.target.value = '';
  if (!f) return;
  if (f.size > 15 * 1024 * 1024) { showToast('Arquivo maior que 15MB'); return; }
  showToast('Lendo ' + f.name + '…');
  try {
    const fd = new FormData();
    fd.append('file', f, f.name);
    fd.append('conversation_id', activeConversation);
    const res = await fetch('/api/docs/upload', { method: 'POST', body: fd, headers: { 'X-CSRF-Token': csrf }, credentials: 'same-origin' });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || ('Erro ' + res.status));
    const row = { id: newId(), conversation_id: activeConversation, origin: 'mobile', role: 'user', text: '📎 Anexei o documento "' + data.name + '" (' + data.chars + ' caracteres em ' + data.chunks + ' trechos).', created_at: new Date().toISOString(), status: 'pending', want_ai: false };
    await storeMessages([row]);
    await touchSession(activeConversation);
    await syncAndRefresh();
    await renderSessions($('sessionSearch').value);
    await renderMessages();
    await renderDocs();
    scrollChat(true);
    showToast('Documento lido. Peça resumo, tópicos ou pergunte sobre ele.');
  } catch (err) { showToast('Falha no upload: ' + (err.message || '')); }
});

/* ----- Documentos ----- */
async function renderDocs() {
  const box = $('docList');
  if (!box) return;
  if (!authenticated || !pcOnline) {
    box.innerHTML = '<div class="doc-empty">Documentos aparecem com o PC online.</div>';
    $('docCount').textContent = '0';
    return;
  }
  try {
    const r = await api('/api/docs');
    const docs = r.documents || [];
    $('docCount').textContent = String(docs.length);
    box.replaceChildren();
    if (!docs.length) { box.innerHTML = '<div class="doc-empty">Nenhum ainda. Toque em + para anexar.</div>'; return; }
    docs.slice(0, 20).forEach(d => {
      const el = document.createElement('div');
      el.className = 'doc-item';
      const t = document.createElement('div'); t.className = 't'; t.textContent = '📄 ' + d.name; t.title = d.name;
      const s = document.createElement('small'); s.textContent = d.chars + ' chars · ' + (d.tem_resumo ? 'resumido' : 'novo');
      const acts = document.createElement('div'); acts.className = 'doc-actions';
      const b1 = document.createElement('button'); b1.type = 'button'; b1.textContent = 'Resumo';
      const b2 = document.createElement('button'); b2.type = 'button'; b2.textContent = 'Tópicos';
      b1.addEventListener('click', () => docAction(d.doc_id, d.name, 'resumo', b1, b2));
      b2.addEventListener('click', () => docAction(d.doc_id, d.name, 'topicos', b1, b2));
      acts.appendChild(b1); acts.appendChild(b2);
      el.appendChild(t); el.appendChild(s); el.appendChild(acts);
      box.appendChild(el);
    });
  } catch (_) { box.innerHTML = '<div class="doc-empty">PC offline.</div>'; }
}
async function docAction(docId, name, kind, b1, b2) {
  b1.disabled = true; b2.disabled = true;
  showToast(kind === 'resumo' ? 'Resumindo ' + name + '…' : 'Extraindo tópicos de ' + name + '…');
  try {
    const r = await api('/api/docs/' + kind, { method: 'POST', body: JSON.stringify({ doc_id: docId }) });
    const txt = r.resumo || r.topicos || '';
    if (!txt.trim()) throw new Error('resposta vazia');
    const row = { id: newId(), conversation_id: activeConversation, origin: 'mobile', role: 'assistant',
      text: (kind === 'resumo' ? '📄 Resumo de ' + name + '\n\n' : '📑 Tópicos de ' + name + '\n\n') + txt,
      created_at: new Date().toISOString(), status: 'synced', model: modeloAtivo() };
    await storeMessages([row]);
    navigate('chat');
    await renderMessages();
    scrollChat(true);
  } catch (err) { showToast('Falha: ' + (err.message || '')); }
  finally { b1.disabled = false; b2.disabled = false; }
}

/* ----- Memória (ver, buscar, corrigir, confirmar, desativar) ----- */
let memoryCache = [];
async function loadMemories() {
  const box = $('memoryList');
  const pend = $('memoryPending');
  if (!box) return;
  if (!authenticated || !pcOnline) {
    box.innerHTML = '<div class="doc-empty">Memória aparece com o PC online.</div>';
    if (pend) pend.replaceChildren();
    return;
  }
  try {
    const [r, st] = await Promise.all([
      api('/api/memories/full'),
      api('/api/memory/settings').catch(() => ({ learning: true }))
    ]);
    memoryCache = r.memories || [];
    $('learningToggle').checked = st.learning !== false;
    paintMemories();
    loadEvents();
  } catch (_) { box.innerHTML = '<div class="doc-empty">PC offline.</div>'; }
}
function paintMemories() {
  const box = $('memoryList');
  const pend = $('memoryPending');
  const q = ($('memorySearch').value || '').toLowerCase();
  const pr = memoryCache.filter(m => m.status === 'pendente');
  pend.replaceChildren();
  if (pr.length) {
    const cap = document.createElement('div'); cap.className = 'memory-sub'; cap.textContent = 'AGUARDANDO SUA CONFIRMAÇÃO';
    pend.appendChild(cap);
    pr.forEach(m => {
      const row = document.createElement('div'); row.className = 'memory-row mem-pend';
      const v = document.createElement('span'); v.className = 'v'; v.textContent = m.value; v.title = m.value;
      const ok = document.createElement('button'); ok.type = 'button'; ok.className = 'mem-ok'; ok.textContent = '✓';
      ok.title = 'Confirmar e guardar';
      ok.addEventListener('click', async () => {
        try {
          await api('/api/memories/confirm', { method: 'POST' });
          await loadMemories(); showToast('Guardado!');
        } catch (_) { showToast('Falha ao confirmar'); }
      });
      const no = document.createElement('button'); no.type = 'button'; no.textContent = '✕'; no.title = 'Descartar';
      no.addEventListener('click', async () => {
        try {
          await api('/api/memories/' + encodeURIComponent(m.key), { method: 'DELETE' });
          await loadMemories(); showToast('Descartado');
        } catch (_) { showToast('Falha ao descartar'); }
      });
      row.appendChild(v); row.appendChild(ok); row.appendChild(no);
      pend.appendChild(row);
    });
  }
  box.replaceChildren();
  const ms = memoryCache.filter(m => m.status === 'confirmada'
    && (!q || (m.key + ' ' + m.value + ' ' + (m.assunto || '')).toLowerCase().includes(q)));
  if (!ms.length) { box.innerHTML = '<div class="doc-empty">' + (q ? 'Nada encontrado.' : 'Nada guardado. Diga "lembre-se que…".') + '</div>'; return; }
  ms.forEach(m => {
    const row = document.createElement('div'); row.className = 'memory-row';
    const badge = document.createElement('span'); badge.className = 'mem-tipo ' + (m.tipo || '');
    badge.textContent = m.tipo || 'fato';
    const k = document.createElement('span'); k.className = 'k'; k.textContent = m.key;
    const v = document.createElement('span'); v.className = 'v';
    v.textContent = m.value + (m.updated_at ? ' · ' + fmtTime(m.updated_at) : '');
    v.title = m.value + (m.assunto ? ' [' + m.assunto + ']' : '');
    const fix = document.createElement('button'); fix.type = 'button'; fix.className = 'fix'; fix.textContent = '✎'; fix.title = 'Corrigir';
    fix.addEventListener('click', async () => {
      const nv = window.prompt('Corrigir "' + m.key + '":', m.value);
      if (!nv || !nv.trim() || nv.trim() === m.value) return;
      try {
        await api('/api/memories/' + encodeURIComponent(m.key), { method: 'PUT', body: JSON.stringify({ value: nv.trim().slice(0, 500) }) });
        await loadMemories(); showToast('Corrigido!');
      } catch (_) { showToast('Falha ao corrigir'); }
    });
    const b = document.createElement('button'); b.type = 'button'; b.textContent = '✕'; b.title = 'Esquecer ' + m.key;
    b.addEventListener('click', async () => {
      if (!window.confirm('Esquecer "' + m.key + '" para sempre?')) return;
      try {
        const res = await fetch('/api/memories/' + encodeURIComponent(m.key), { method: 'DELETE', headers: { 'X-CSRF-Token': csrf }, credentials: 'same-origin' });
        if (!res.ok) throw new Error();
        await loadMemories(); showToast('Esquecido: ' + m.key);
      } catch (_) { showToast('Falha ao esquecer'); }
    });
    row.appendChild(badge); row.appendChild(k); row.appendChild(v); row.appendChild(fix); row.appendChild(b);
    box.appendChild(row);
  });
}
async function searchHistory() {
  const box = $('historyResults');
  if (!box) return;
  const query = String($('historySearch').value || '').trim().toLocaleLowerCase('pt-BR');
  box.replaceChildren();
  if (query.length < 2) return;
  if (!db) { box.textContent = 'Histórico local indisponível.'; return; }
  const all = ownRows(await allMessages());
  const matches = all.filter(m => String(m.text || '').toLocaleLowerCase('pt-BR').includes(query))
    .slice(-50).reverse();
  if (!matches.length) {
    const empty = document.createElement('div'); empty.className = 'doc-empty';
    empty.textContent = 'Nenhuma mensagem encontrada no histórico deste aparelho.';
    box.appendChild(empty);
    return;
  }
  const titles = new Map((await ownSessions()).map(s => [s.id, s.title || 'Conversa']));
  matches.forEach(m => {
    const row = document.createElement('button'); row.type = 'button'; row.className = 'history-result';
    const head = document.createElement('strong');
    head.textContent = (titles.get(m.conversation_id) || 'Conversa') + ' · ' +
      (m.role === 'assistant' ? 'Júlia' : 'Você') + ' · ' + fmtTime(m.created_at);
    const excerpt = document.createElement('span');
    const text = String(m.text || '').replace(/\s+/g, ' ');
    const at = text.toLocaleLowerCase('pt-BR').indexOf(query);
    excerpt.textContent = text.slice(Math.max(0, at - 55), Math.min(text.length, at + query.length + 100));
    row.append(head, excerpt);
    row.addEventListener('click', async () => {
      setActiveConversation(m.conversation_id);
      await renderSessions($('sessionSearch').value);
      await renderMessages();
      navigate('chat');
      const target = [...conversation.querySelectorAll('.message')].find(el => el.dataset.mid === m.id);
      if (target) { target.scrollIntoView({ behavior: 'smooth', block: 'center' }); target.classList.add('search-hit'); }
    });
    box.appendChild(row);
  });
}
async function paintSavedItems() {
  const box = $('savedItems');
  if (!box) return;
  box.replaceChildren();
  const items = await savedItems();
  if (!items.length) {
    const empty = document.createElement('div'); empty.className = 'doc-empty';
    empty.textContent = 'Nenhum item salvo neste aparelho.';
    box.appendChild(empty);
    return;
  }
  items.forEach(item => {
    const row = document.createElement('div'); row.className = 'saved-item';
    const title = document.createElement('strong'); title.textContent = item.title || 'Item salvo';
    const body = document.createElement('span'); body.textContent = String(item.text || '').slice(0, 180);
    const actions = document.createElement('div'); actions.className = 'export-row';
    const copy = document.createElement('button'); copy.type = 'button'; copy.className = 'subtle-button'; copy.textContent = 'Copiar';
    copy.addEventListener('click', () => shareText(item.title || 'Item salvo', item.text || '', false));
    const del = document.createElement('button'); del.type = 'button'; del.className = 'subtle-button danger-link'; del.textContent = 'Apagar';
    del.addEventListener('click', async () => {
      const tx = db.transaction(SAVED, 'readwrite'); const done = txDone(tx);
      tx.objectStore(SAVED).delete(item.id); await done; await paintSavedItems();
    });
    actions.append(copy, del); row.append(title, body, actions); box.appendChild(row);
  });
}
async function loadEvents() {
  const box = $('eventList');
  if (!box) return;
  try {
    const r = await api('/api/memory/events');
    const evs = r.events || [];
    box.replaceChildren();
    if (!evs.length) { box.innerHTML = '<div class="doc-empty">Nenhum evento. Diga "minha prova é dia 20/11".</div>'; return; }
    evs.forEach(e => {
      const row = document.createElement('div'); row.className = 'memory-row';
      const k = document.createElement('span'); k.className = 'k'; k.textContent = e.data_br;
      const v = document.createElement('span'); v.className = 'v'; v.textContent = e.titulo + ' (faltam ' + e.faltam + ' dias)';
      row.appendChild(k); row.appendChild(v);
      box.appendChild(row);
    });
  } catch (_) { box.innerHTML = '<div class="doc-empty">PC offline.</div>'; }
}
$('memoryRefresh').addEventListener('click', loadMemories);
$('memorySearch').addEventListener('input', paintMemories);
$('historySearch').addEventListener('input', searchHistory);
$('historySearch').addEventListener('search', searchHistory);
$('contextCity').value = lsGet(localContextKey('city')) || '';
$('locationEnabled').checked = lsGet(localContextKey('enabled')) === 'true';
$('locationStatus').textContent = $('locationEnabled').checked
  ? 'Ativado: localização enviada apenas em perguntas sobre lugares.'
  : 'Desligado: nenhuma localização será enviada.';
$('contextCity').addEventListener('input', e => {
  try { localStorage.setItem(localContextKey('city'), String(e.target.value || '').slice(0, 100)); } catch (_) {}
});
$('locationEnabled').addEventListener('change', e => {
  try { localStorage.setItem(localContextKey('enabled'), e.target.checked ? 'true' : 'false'); } catch (_) {}
  $('locationStatus').textContent = e.target.checked
    ? 'Ativado: localização enviada apenas em perguntas sobre lugares.'
    : 'Desligado: nenhuma localização será enviada.';
});
$('useCurrentLocation').addEventListener('click', () => {
  const status = $('locationStatus');
  if (!navigator.geolocation) { status.textContent = 'Este aparelho não oferece localização pelo navegador.'; return; }
  status.textContent = 'Aguardando permissão de localização…';
  navigator.geolocation.getCurrentPosition(position => {
    const coarse = {
      latitude: Math.round(position.coords.latitude * 100) / 100,
      longitude: Math.round(position.coords.longitude * 100) / 100
    };
    try {
      localStorage.setItem(localContextKey('location'), JSON.stringify(coarse));
      status.textContent = 'Local aproximado salvo neste aparelho. Ative a opção acima para usá-lo em perguntas sobre lugares.';
    } catch (_) { status.textContent = 'Não foi possível salvar o local neste aparelho.'; }
  }, error => {
    status.textContent = error.code === error.PERMISSION_DENIED
      ? 'Permissão negada. Você pode informar uma cidade manualmente.'
      : 'Não foi possível obter o local. Você pode informar uma cidade manualmente.';
  }, { enableHighAccuracy: false, timeout: 12000, maximumAge: 300000 });
});
$('clearLocation').addEventListener('click', () => {
  ['location', 'city'].forEach(key => {
    try { localStorage.removeItem(localContextKey(key)); } catch (_) {}
  });
  $('contextCity').value = '';
  $('locationEnabled').checked = false;
  try { localStorage.setItem(localContextKey('enabled'), 'false'); } catch (_) {}
  $('locationStatus').textContent = 'Localização apagada e desativada.';
});
function updateDeviceTimeStatus() {
  try {
    const now = new Date();
    const zone = Intl.DateTimeFormat().resolvedOptions().timeZone || 'fuso desconhecido';
    $('deviceTimeStatus').textContent = 'Agora: ' + now.toLocaleString('pt-BR') + ' · ' + zone;
  } catch (_) { $('deviceTimeStatus').textContent = ''; }
}
updateDeviceTimeStatus();
setInterval(updateDeviceTimeStatus, 60000);
$('learningToggle').addEventListener('change', async e => {
  try {
    await api('/api/memory/settings', { method: 'POST', body: JSON.stringify({ learning: e.target.checked }) });
    showToast(e.target.checked ? 'Aprendizado ativado' : 'Armazenamento pausado (explícitos valem)');
  } catch (_) { showToast('Falha ao salvar'); loadMemories(); }
});


/* ----- Remoto ----- */
let remoteEnabled = false, screenBusy = false, touchStart = null, touchMoved = false, longPressed = false, longTimer = null, lastMove = 0;
const desktopAtivo = () => !$('page-desktop').hidden;
async function pullScreen() {
  if (!authenticated || !pcOnline || !desktopAtivo() || !navigator.onLine || screenBusy) return;
  screenBusy = true;
  try {
    const r = await api('/api/screen?max_w=800&q=50');
    $('screenImg').src = 'data:image/jpeg;base64,' + r.imagem;
    remoteEnabled = r.remote_enabled === true;
    $('screenLabel').textContent = 'AO VIVO · ' + (r.ms || 0) + 'ms';
    $('screenNote').textContent = remoteEnabled ? 'Toque = clique, segurar = direito, arrastar = mover.' : 'Somente visualização. Ative JULIA_REMOTE=1 no PC.';
  } catch (err) {
    $('screenLabel').textContent = 'TELA INDISPONÍVEL';
    $('screenNote').textContent = err.status === 403 ? 'Sem autorização. Peça acesso ao administrador.'
      : err.status === 503 ? 'Agente sem suporte a tela: reinicie o agente.' : 'Falha ao buscar: ' + (err.message || 'Atualizar.');
  } finally { screenBusy = false; }
}
setInterval(pullScreen, 1500);
async function sendInput(cmd) {
  if (!remoteEnabled) { showToast('Controle desativado no PC (JULIA_REMOTE=1).'); return; }
  try { await api('/api/input', { method: 'POST', body: JSON.stringify(cmd) }); }
  catch (err) { showToast(err.message || 'Comando recusado'); }
}
function normPos(ev) {
  const r = $('remoteFrame').getBoundingClientRect();
  const t = ev.touches && ev.touches[0] ? ev.touches[0] : ev;
  return { x: Math.min(1, Math.max(0, (t.clientX - r.left) / r.width)), y: Math.min(1, Math.max(0, (t.clientY - r.top) / r.height)) };
}
function mostraPonteiro(p) {
  const f = $('remoteFrame').getBoundingClientRect();
  const el = $('remotePointer');
  el.style.display = 'block'; el.style.left = (p.x * f.width) + 'px'; el.style.top = (p.y * f.height) + 'px';
}
const frame = $('remoteFrame');
frame.addEventListener('touchstart', ev => {
  if (!desktopAtivo()) return;
  ev.preventDefault();
  const p = normPos(ev);
  touchStart = p; touchMoved = false; longPressed = false;
  mostraPonteiro(p); clearTimeout(longTimer);
  longTimer = setTimeout(() => { longPressed = true; sendInput(Object.assign({ kind: 'right' }, p)); }, 600);
}, { passive: false });
frame.addEventListener('touchmove', ev => {
  if (!touchStart) return;
  ev.preventDefault();
  const p = normPos(ev);
  mostraPonteiro(p);
  const rc = frame.getBoundingClientRect();
  const dx = (p.x - touchStart.x) * rc.width, dy = (p.y - touchStart.y) * rc.height;
  if (Math.hypot(dx, dy) > 12) {
    touchMoved = true; clearTimeout(longTimer);
    const agora = Date.now();
    if (agora - lastMove > 90) { lastMove = agora; sendInput(Object.assign({ kind: 'move' }, p)); }
  }
}, { passive: false });
frame.addEventListener('touchend', ev => {
  if (!touchStart) return;
  ev.preventDefault(); clearTimeout(longTimer);
  const p = touchStart; touchStart = null;
  if (!touchMoved && !longPressed) sendInput(Object.assign({ kind: 'click' }, p));
});
frame.addEventListener('click', ev => {
  if (!desktopAtivo() || ev.detail === 0) return;
  const p = normPos(ev); mostraPonteiro(p); sendInput(Object.assign({ kind: 'click' }, p));
});
$('keyboardButton').addEventListener('click', () => { const c = $('remoteKeys'); c.value = ''; c.focus(); showToast(remoteEnabled ? 'Digite: as teclas vão para o PC.' : 'Teclado desativado.'); });
$('remoteKeys').addEventListener('input', ev => {
  const v = ev.target.value;
  if (v.length > (ev.target._last || '').length && v.length) sendInput({ kind: 'text', text: v.slice(ev.target._last ? ev.target._last.length : 0) });
  ev.target._last = v;
});
$('remoteKeys').addEventListener('keydown', ev => {
  if (ev.key === 'Enter') { sendInput({ kind: 'key', key: 'enter' }); ev.target.value = ''; ev.target._last = ''; }
  else if (ev.key === 'Backspace' && !ev.target.value) sendInput({ kind: 'key', key: 'backspace' });
});
$('refreshButton').addEventListener('click', pullScreen);
$('touchMode').addEventListener('click', () => showToast('Toque, segurar, arrastar.'));
$('fullscreen').addEventListener('click', async () => {
  const el = $('remoteFrame');
  if (!document.fullscreenEnabled) { showToast('Tela cheia indisponível'); return; }
  try { if (document.fullscreenElement) await document.exitFullscreen(); else await el.requestFullscreen(); }
  catch (_) { showToast('Tela cheia não autorizada'); }
});
window.addEventListener('online', checkStatus);
window.addEventListener('offline', () => { pcOnline = false; updateConnection(); });
document.addEventListener('visibilitychange', () => { if (!document.hidden) checkStatus(); });
workspace = VexxWorkspace.create({
  getDb: () => db, getUid: () => currentUid,
  canSync: () => !!db && authenticated && pcOnline && navigator.onLine && !PREVIEW_MODE,
  api, onStatus: text => { $('workspaceStatus').textContent = text; },
  onSync: async () => {
    if (isDeleted(activeConversation)) { setActiveConversation(newId()); await ensureSession(activeConversation); }
    await renderSessions($('sessionSearch').value);
    if (!$('page-chat').hidden) await renderMessages();
  }
});
bindOrganizer();
setInterval(() => { if (!document.hidden) checkStatus(); }, 12000);
(async function init() {
  navigate('chat');
  setDrawer(window.innerWidth >= 900);
  try {
    db = await openDb();
    await workspace.load();
    await loadTombstones();
    for (const s of await ownSessions()) await workspace.trackSession(s);
    await migrateV1();
    const rows = await allMessages();
    const presas = rows.filter(m => m.status === 'generating');
    if (presas.length) await storeMessages(presas.map(m => ({ id: m.id, conversation_id: m.conversation_id, origin: 'mobile', role: m.role, text: m.text, created_at: m.created_at, status: 'failed', model: m.model || '' })));
    setActiveConversation(await resolveActiveConversation());
    await healSessions();
    await ensureSession(activeConversation);
    await renderSessions('');
    await renderMessages();
  } catch (_) { showToast('Cache local indisponível'); }
  autoresize();
  await restoreSession(); await fetchAuthConfig(); await checkStatus(); updateConnection();
  if ('serviceWorker' in navigator && location.protocol !== 'file:') navigator.serviceWorker.register('/sw.js').catch(() => {});
})();
