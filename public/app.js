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
let storageGeneration = 0;
let workspace = null;
let csrf = '';
let authenticated = false;
let authEpoch = 0;
let authBusy = false;
let pcOnline = false;
let busy = false;
let toastTimer;
let aiAbort = null;
const aiRequests = new Set();
const aiQueue = [];
let aiQueueRunning = false;
let aiStartT = 0;
let aiFirstTokenT = 0;
let genTimer = null;
let modelsLoadedAt = 0;
let rafPending = null;
let rafText = '';
let rafReplyId = '';
let streamDraft = null;
let messagesRenderVersion = 0;
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
  const desktop = window.innerWidth >= 900;
  open = desktop || open;
  drawer.classList.toggle('open', open);
  drawer.setAttribute('aria-hidden', open ? 'false' : 'true');
  drawer.inert = !open;
  document.querySelector('.main-col').inert = open && !desktop;
  $('drawerOpen').setAttribute('aria-expanded', String(open));
  scrim.hidden = desktop || !open;
}
$('drawerOpen').addEventListener('click', () => { setDrawer(true); $('drawerClose').focus(); });
function closeDrawer() { setDrawer(false); if (window.innerWidth < 900) $('drawerOpen').focus(); }
$('drawerClose').addEventListener('click', closeDrawer);
scrim.addEventListener('click', closeDrawer);
window.matchMedia('(min-width:900px)').addEventListener('change', e => setDrawer(e.matches));
document.addEventListener('keydown', e => {
  if (window.innerWidth >= 900 || !drawer.classList.contains('open') || $('organizeDialog').open) return;
  if (e.key === 'Escape') { e.preventDefault(); closeDrawer(); }
  if (e.key === 'Tab') {
    const items = [...drawer.querySelectorAll('button,input,select,summary')].filter(el => !el.disabled && el.getClientRects().length);
    const first = items[0], last = items[items.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  }
});
function fitViewport() {
  document.documentElement.style.setProperty('--app-height', Math.round(window.visualViewport?.height || window.innerHeight) + 'px');
}
window.visualViewport?.addEventListener('resize', fitViewport);
window.addEventListener('resize', fitViewport);
fitViewport();

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
  if (!chat) { $('chatTitle').textContent = {desktop:'Meu PC',activity:'Atividades',estudos:'Estudos',settings:'Ajustes e conta',documents:'Documentos',research:'Pesquisas'}[tab] || 'Vexx AI'; $('chatSubtitle').textContent = 'Seu espaço pessoal'; }
  $('suggestions').style.display = chat ? 'flex' : 'none';
  document.querySelector('.composer-hint').style.display = chat ? 'flex' : 'none';
  if (tab === 'activity') renderTimeline();
  if (tab === 'estudos') renderEstudos();
  if (tab === 'research') renderPesquisas();
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
  const generation = storageGeneration, owner = currentUid;
  try {
    const rows = await reqPromise(db.transaction(UISTATE, 'readonly').objectStore(UISTATE).getAll());
    if (generation !== storageGeneration || owner !== currentUid) return;
    rows.forEach(r => {
      if (r && typeof r.k === 'string' && want.has(r.k.split('#')[0])
          && (r.owner || 'local') === currentUid) jduiStateCache[r.k] = r.state || {};
    });
  } catch (_) {}
}
function jduiCtx(row) {
  const contextOwner = currentUid;
  const contextGeneration = storageGeneration;
  return {
    messageId: row.id,
    conversationId: row.conversation_id,
    ownerId: contextOwner,
    api: (endpoint, options) => api(endpoint, options),
    queueLearn: (endpoint, body) => queueLearn(endpoint, body),
    download: (name, mime, text) => downloadFile(name, mime, text),
    online: () => authenticated && pcOnline && navigator.onLine,
    markdown: (t) => renderMarkdown(String(t).replace(/```jdui[\s\S]*?(```|$)/gi, '')),
    loadState: (key) => jduiStateCache[row.id + '#' + key],
    saveState: (key, st) => {
      if (currentUid !== contextOwner || contextGeneration !== storageGeneration) return;
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
  const generation = storageGeneration;
  const pending = { ...jduiDirty };
  try {
    const tx = db.transaction(UISTATE, 'readwrite');
    const done = txDone(tx);
    const st = tx.objectStore(UISTATE);
    Object.values(pending).forEach(r => st.put(r));
    await done;
    Object.keys(pending).forEach(k => { if (jduiDirty[k] === pending[k]) delete jduiDirty[k]; });
  } catch (_) {}
  if (generation !== storageGeneration) return;
  clearTimeout(jduiSyncTimer);
  jduiSyncTimer = setTimeout(syncJduiStates, 4000);
}
async function syncJduiStates() {
  if (!authenticated || !pcOnline || !db) return;
  const owner = currentUid;
  const generation = storageGeneration;
  try {
    const rows = (await reqPromise(db.transaction(UISTATE, 'readonly').objectStore(UISTATE).getAll()))
      .filter(r => (r.owner || 'local') === currentUid);
    for (let i = 0; i < rows.length; i += 100) {
      if (generation !== storageGeneration || owner !== currentUid || !authenticated) return;
      await api('/api/ui-state', { method: 'POST', body: JSON.stringify({ states: rows.slice(i, i + 100) }) });
    }
    let stateCursor = '';
    const stateCursors = new Set();
    do {
    const remote = await api('/api/ui-state' + (stateCursor ? '?cursor=' + encodeURIComponent(stateCursor) : ''));
    if (generation !== storageGeneration || owner !== currentUid || !authenticated) return;
    const tx = db.transaction(UISTATE, 'readwrite');
    const done = txDone(tx);
    const store = tx.objectStore(UISTATE);
    for (const r of remote.states || []) {
      try {
        const have = await reqPromise(store.get(r.k));
        if (!have || (r.updated_at || '') >= (have.updated_at || '')) {
          store.put(Object.assign({}, r, { owner: currentUid }));
          jduiStateCache[r.k] = r.state || {};
        }
      } catch (_) {}
    }
    await done;
    stateCursor = remote.next_cursor || '';
    if (stateCursor && stateCursors.has(stateCursor)) throw Error('Cursor de estado repetido');
    stateCursors.add(stateCursor);
    } while (stateCursor);
    if (!aiAbort) await renderMessages();
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
async function messageById(id) {
  if (!db) return null;
  return reqPromise(db.transaction(STORE, 'readonly').objectStore(STORE).get(id));
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
  storageGeneration++;
  clearTimeout(jduiSyncTimer);
  jduiSyncTimer = null;
  jduiDirty = {};
  if (workspace) workspace.reset();
  const tx = db.transaction([STORE, SESSIONS, SAVED, UISTATE, META], 'readwrite');
  const done = txDone(tx);
  tx.objectStore(STORE).clear(); tx.objectStore(SESSIONS).clear(); tx.objectStore(SAVED).clear();
  tx.objectStore(UISTATE).clear(); tx.objectStore(META).clear();
  jduiStateCache = {};
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
async function putSession(s, track = true) {
  const tx = db.transaction(SESSIONS, 'readwrite');
  const d = txDone(tx);
  const row = s.owner ? s : Object.assign({}, s, { owner: currentUid });
  tx.objectStore(SESSIONS).put(row);
  await d;
  if (workspace && track) await workspace.trackSession(row);
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
  // Keep intentionally empty chats (including projects); only infer missing titles.
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
async function touchSession(id, hint, activityAt, track = true) {
  const list = await ownSessions();
  const now = activityAt || new Date().toISOString();
  let s = list.find(x => x.id === id);
  if (!s) s = { id, title: hint || 'Nova conversa', created_at: now, updated_at: now, inferred: !!activityAt };
  else { s.updated_at = now > (s.updated_at || '') ? now : s.updated_at; if (s.title === 'Nova conversa' && hint) s.title = hint; }
  await putSession(s, track);
}
function titleFrom(t) { return String(t || '').replace(/\s+/g, ' ').trim().slice(0, 44) || 'Nova conversa'; }

/* ----- Markdown rico e seguro ----- */
const ESC_DIV = document.createElement('div');
function escapeHtml(t) { ESC_DIV.textContent = t; return ESC_DIV.innerHTML; }
function rotuloUrl(u) {
  try {
    const p = new URL(String(u));
    const caminho = (p.pathname || '').replace(/\/$/, '');
    const curto = caminho.length > 32 ? caminho.slice(0, 29) + '...' : caminho;
    return p.hostname.replace(/^www\./, '') + curto;
  } catch (_) { return String(u).length > 44 ? String(u).slice(0, 41) + '...' : String(u); }
}
function inlineFmt(s, sources = {}) {
  const tokens = [];
  const keep = html => '\u0001INLINE' + (tokens.push(html) - 1) + '\u0001';
  s = s.replace(/`([^`\n]+)`/g, (_, code) => keep('<code>' + code + '</code>'));
  s = s.replace(/!\[([^\]]{0,120})\]\(([^)\s]+)\)/g, (m, alt, url) => {
    const u = validUrl(url);
    if (!u) return esc(m);
    // V5.7 F4: serviço de placeholder (loremflickr) é imagem falsa
    // e instável no chat (pisca entre falha e recarga e derruba o
    // scroll) — não renderiza.
    if (/^(?:www\.)?loremflickr\.com$/i.test(new URL(u).hostname)) return '';
    return keep('<img class="chat-img" loading="lazy" decoding="async" referrerpolicy="no-referrer" alt="' + alt + '" src="' + esc(u.replace(/&amp;/g, '&')) + '" />');
  });
  s = s.replace(/\[([^\]]+)\]\((https?:[^)\s]+)\)/g, (m, t, u) => keep('<a href="' + esc(u.replace(/&amp;/g, '&')) + '" target="_blank" rel="noopener noreferrer">' + t + '</a>'));
  s = s.replace(/\[(S\d+)\]/gi, (m, id) => sources[id.toUpperCase()]
    ? keep('<a class="citation" href="' + esc(sources[id.toUpperCase()]) + '" target="_blank" rel="noopener noreferrer" aria-label="Fonte ' + id.toUpperCase() + '">' + m + '</a>') : m);
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
    return pre + '<a href="' + u + '" title="' + esc(u) + '" target="_blank" rel="noopener noreferrer">' + esc(rotuloUrl(u)) + '</a>' + suf;
  });
  return s.replace(/\u0001INLINE(\d+)\u0001/g, (_, n) => tokens[Number(n)] || '');
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
// SVG is an image document: never insert model markup into the application DOM.
function renderSvg(raw) {
  const clean = sanitizeSvg(raw);
  return clean ? '<div class="svg-art"><img alt="Ilustração SVG" src="data:image/svg+xml;charset=utf-8,' + encodeURIComponent(clean).replace(/'/g, '%27') + '"></div>' : '<p>[desenho vazio]</p>';
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
      if (!close) return '\nPreparando conteúdo interativo…\n';
      try {
        const r = JDUI.validateMessage(JSON.parse(body));
        if (r.ok) return '\x00JDUI' + (pendingJdui.push(r.msg) - 1) + '\x00';
      } catch (_) { /* cai no descarte */ }
      return '\nNão foi possível apresentar este conteúdo interativo.\n';
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
  const sources = {};
  const formatInline = value => inlineFmt(value, sources);
  let refsHtml = '';
  const refM = src.match(/\n(?:#{1,6}\s*)?((Fontes|Refer[eê]ncias|Sources)\s*:?[\s\S]*)$/i);
  let refBody = '';
  if (refM) { refBody = refM[1]; src = src.slice(0, refM.index); }
  else {
    const lines = src.split('\n');
    const tail = lines.slice(-6).join('\n');
    if (/https?:\/\//.test(tail) && /fonte|http|\[https/i.test(tail)) { /* deixa inline */ }
  }
  if (refBody) {
    refBody.split('\n').forEach(line => {
      const id = line.match(/\[(S\d+)\]/i), url = line.match(/https?:\/\/[^\s<>\)]+/);
      if (id && url) sources[id[1].toUpperCase()] = validUrl(url[0].replace(/[.,;]+$/, ''));
    });
    const items = escapeHtml(refBody).split('\n').map(l => l.trim()).filter(Boolean);
    const lis = items.slice(1).map(l => {
      return '<div class="reference-item">' + formatInline(l.replace(/^[-*]\s+/, '')) + '</div>';
    }).join('');
    refsHtml = '<div class="refs"><strong>Fontes e referências</strong>' + (lis || '<span>' + (items[0] || '') + '</span>') + '</div>';
  }
  const html = [];
  const lines = escapeHtml(src).split('\n');
  let list = null, bq = [], table = [];
  function flushList() { if (list) { html.push(list.tag === 'ol' ? '<ol>' + list.items.map(i => '<li>' + formatInline(i) + '</li>').join('') + '</ol>' : '<ul>' + list.items.map(i => '<li>' + formatInline(i) + '</li>').join('') + '</ul>'); list = null; } }
  function flushBq() { if (bq.length) { html.push('<blockquote>' + bq.map(formatInline).join('<br>') + '</blockquote>'); bq = []; } }
  function flushTable() {
    if (table.length >= 2) {
      const cells = line => line.trim().replace(/^\|/, '').replace(/\|$/, '').split(/(?<!\\)\|/).map(c => c.trim().replace(/\\\|/g, '|'));
      const head = cells(table[0]);
      const rows = table.slice(2).map(cells);
      html.push('<div class="table-wrap"><table><thead><tr>' + head.map(c => '<th>' + formatInline(c) + '</th>').join('') + '</tr></thead><tbody>' + rows.map(r => '<tr>' + r.map(c => '<td>' + formatInline(c) + '</td>').join('') + '</tr>').join('') + '</tbody></table></div>');
    } else if (table.length) { table.forEach(t => html.push('<p>' + formatInline(t) + '</p>')); }
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
      html.push('<div class="widget"><div class="widget-bar"><span>Prévia HTML · scripts desativados</span>'
        + '<button class="widget-code-btn" data-widget="' + wi + '" type="button">Ver código</button></div>'
        + '<iframe class="widget-frame" sandbox="" loading="lazy" title="Prévia HTML do Vexx" srcdoc="' + srcdocEsc('<meta http-equiv="Content-Security-Policy" content="default-src &#39;none&#39;; img-src https: data:; style-src &#39;unsafe-inline&#39;">' + wcode) + '"></iframe>'
        + '<pre class="widget-code" data-widget-code="' + wi + '" hidden><code>' + esc(wcode) + '</code></pre></div>');
      continue;
    }
    const svgPh = ln.match(/ SVG(\d+) /);
    if (svgPh && svgs[Number(svgPh[1])] !== undefined) {
      flushList(); flushBq(); flushTable();
      html.push(renderSvg(svgs[Number(svgPh[1])]));
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
    const heading = t.match(/^(#{1,4})\s+(.+)/);
    if (heading) {
      flushList(); flushBq();
      const tag = heading[1].length === 1 ? 'h2' : heading[1].length === 2 ? 'h3' : 'h4';
      html.push('<' + tag + '>' + formatInline(heading[2]) + '</' + tag + '>');
      continue;
    }
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
    html.push('<p>' + formatInline(t) + '</p>');
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
let chatStick = true;   // só acompanha o fim se o usuário está no fim
let lastScrollTop = 0;
function nearBottom(el) { return el.scrollHeight - el.scrollTop - el.clientHeight < 120; }
function scrollChat(force) {
  if (force) chatStick = true;
  if (chatStick) conversation.scrollTop = conversation.scrollHeight;
}
conversation.addEventListener('scroll', () => {
  const st = conversation.scrollTop;
  if (st < lastScrollTop - 2) chatStick = false;   // rolagem para cima desarma
  else if (conversation.scrollHeight - st - conversation.clientHeight < 24) chatStick = true;
  lastScrollTop = st;
  $('scrollFab').hidden = nearBottom(conversation);
});
$('scrollFab').addEventListener('click', () => scrollChat(true));
// Imagens do chat: o CSP do app bloqueia onerror inline, então o fallback é
// um listener de captura (error nao borbulha). Falha vira aviso clicavel e
// mudanças de altura fora da tela são compensadas para o texto não "pular".
function marcarImagensChat(raiz) {
  if (!raiz || !raiz.querySelectorAll) return;
  raiz.querySelectorAll('img.chat-img').forEach(img => {
    if (!img.dataset.ciAltura) img.dataset.ciAltura = String(Math.round(img.getBoundingClientRect().height));
  });
}
function ancorarAltura(antes, depois) {
  const delta = depois.height - antes.height;
  if (!delta) return;
  if (chatStick) { conversation.scrollTop = conversation.scrollHeight; return; }
  const caixa = conversation.getBoundingClientRect();
  if (depois.bottom <= caixa.top + 4) conversation.scrollTop += delta;
}
function imagemChatFalhou(img) {
  if (img.dataset.ciFalhou === '1') return;
  if (/^http:\/\//i.test(img.src) && img.dataset.ciHttps !== '1') {
    img.dataset.ciHttps = '1';   // CSP permite só https: tenta o upgrade antes de desistir
    img.src = img.src.replace(/^http:\/\//i, 'https://');
    return;
  }
  img.dataset.ciFalhou = '1';
  const antes = img.getBoundingClientRect();
  const chip = document.createElement('span');
  chip.className = 'image-unavailable';
  chip.append('🖼️ imagem indisponível');
  if (/^https?:/i.test(img.src)) {
    chip.append(' — ');
    const a = document.createElement('a');
    a.href = img.src; a.target = '_blank'; a.rel = 'noopener noreferrer';
    a.textContent = 'abrir link';
    chip.appendChild(a);
  }
  img.replaceWith(chip);
  ancorarAltura(antes, chip.getBoundingClientRect());
}
conversation.addEventListener('error', e => {
  const img = e.target;
  if (img && img.tagName === 'IMG' && img.classList.contains('chat-img') && img.isConnected) imagemChatFalhou(img);
}, true);
conversation.addEventListener('load', e => {
  const img = e.target;
  if (!img || img.tagName !== 'IMG' || !img.classList.contains('chat-img')) return;
  const depois = img.getBoundingClientRect();
  const antes = { height: Number(img.dataset.ciAltura || '0') };
  img.dataset.ciAltura = String(Math.round(depois.height));
  ancorarAltura(antes, depois);
}, true);

function appendMessage(row) {
  if (streamDraft && streamDraft.id === row.id && streamDraft.owner === currentUid) {
    row = { ...row, text: streamDraft.text || row.text };
  }
  const type = row.role === 'assistant' ? 'ai' : 'user';
  const wrap = document.createElement('div');
  wrap.className = 'message ' + type + (row.status === 'failed' ? ' failed' : '');
  wrap.dataset.mid = row.id;
  wrap._renderOwner = currentUid;
  wrap._renderSignature = JSON.stringify([row.text, row.status, row.model]);
  if (type === 'ai') { const ic = document.createElement('div'); ic.className = 'bubble-avatar'; ic.textContent = 'v.'; ic.setAttribute('aria-hidden', 'true'); wrap.appendChild(ic); }
  const content = document.createElement('div'); content.className = 'message-content';
  if (type === 'ai') { const s = document.createElement('div'); s.className = 'sender'; s.textContent = 'Vexx'; content.appendChild(s); }
  const bubble = document.createElement('div'); bubble.className = 'bubble';
  if (row.status === 'generating') {
    bubble.innerHTML = renderMarkdown(row.text) || '<span class="stream-placeholder" aria-hidden="true">···</span>';
    content.appendChild(bubble);
  } else {
    bubble.innerHTML = renderMarkdown(row.text)
      || (row.status === 'failed'
        ? '<p>Sem resposta da IA desta vez — toque em <strong>Tentar novamente</strong> abaixo. 🔄</p>'
        : '<p>…</p>');
    content.appendChild(bubble);
  }
  marcarImagensChat(bubble);
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
  }
  content.appendChild(meta);
  wrap.appendChild(content);
  conversation.appendChild(wrap);
}
function paintStreaming(replyId, text) {
  const el = conversation.querySelector('[data-mid="' + replyId + '"] .bubble');
  if (!el) { takeJduiSlots(); return; }
  if (!el._streamProse) {
    el._streamProse = document.createElement('div');
    el._streamComponents = document.createElement('div');
    el.replaceChildren(el._streamProse, el._streamComponents);
  }
  el._streamProse.innerHTML = renderMarkdown(text) || '<span class="stream-placeholder" aria-hidden="true">···</span>';
  marcarImagensChat(el._streamProse);
  const jslots = takeJduiSlots();
  const signature = JSON.stringify(jslots);
  // Keep mounted controls and their focus while only the surrounding prose changes.
  if (signature !== el._jduiSignature && typeof JDUI !== 'undefined') {
    el._jduiSignature = signature;
    el._streamComponents.replaceChildren();
    allMessages().then(rows => {
      const row = rows.find(m => m.id === replyId);
      if (row && el.isConnected && el._jduiSignature === signature) {
        try { JDUI.mount(el._streamComponents, jslots, jduiCtx(row)); } catch (_) {}
      }
    });
  }
  scrollChat(false);
}
function schedulePaint(replyId, text) {
  streamDraft = {id:replyId, text, owner:currentUid};
  rafReplyId = replyId; rafText = text;
  if (rafPending) return;
  rafPending = requestAnimationFrame(() => { rafPending = null; paintStreaming(rafReplyId, rafText); });
}

async function renderMessages() {
  if (!db) return;
  const version = ++messagesRenderVersion, selected = activeConversation, owner = currentUid;
  const all = ownRows(await allMessages());
  const rows = all.filter(m => m.conversation_id === activeConversation);
  await preloadJduiStates(rows.map(m => m.id));
  if (version !== messagesRenderVersion || selected !== activeConversation || owner !== currentUid) return;
  const stick = nearBottom(conversation);
  // Preserve unchanged 3D surfaces during sync; rebuilding them interrupts GPU loads and interaction.
  const retained3d = new Map(Array.from(conversation.querySelectorAll('.message'))
    .filter(node => node._renderOwner === currentUid && node.querySelector('.model3d'))
    .map(node => [node.dataset.mid, node]));
  conversation.replaceChildren();
  conversation.classList.toggle('is-empty', rows.length === 0);
  const header = document.createElement('div'); header.className = 'chat-date';
  const date = rows.length ? new Date(rows[0].created_at) : new Date();
  header.textContent = date.toLocaleDateString('pt-BR', {day:'numeric', month:'long'});
  conversation.appendChild(header);
  if (!rows.length) {
    const w = document.createElement('div'); w.className = 'empty-chat';
    w.innerHTML = '<span class="welcome-mark" aria-hidden="true">v.</span><p>Seu espaço para pensar e criar.</p><h1>O que vamos fazer hoje?</h1><small>Converse, estude ou organize suas ideias em projetos.</small>';
    conversation.appendChild(w);
  } else {
    const idsAssist = rows.filter(m => m.role === 'assistant' && m.status === 'synced').map(m => m.id);
    lastAssistantId = idsAssist.length ? idsAssist[idsAssist.length - 1] : '';
    rows.forEach(row => {
      const node = retained3d.get(row.id);
      if (node && node._renderSignature === JSON.stringify([row.text, row.status, row.model])) {
        // The authoritative timestamp arrives after SSE; it does not change the scene.
        const time = node.querySelector('.msg-time');
        if (time) time.textContent = fmtTime(row.created_at);
        conversation.appendChild(node);
      }
      else appendMessage(row);
    });
  }
  const temTroca = rows.length > 0;
  if (!$('page-chat').hidden) $('suggestions').style.display = temTroca ? 'none' : 'flex';
  if (stick) conversation.scrollTop = conversation.scrollHeight;
  const pending = all.filter(m => m.role === 'user' && m.status === 'pending').length;
  $('pendingCount').textContent = pending + ' pendente' + (pending === 1 ? '' : 's');
  $('syncCounter').textContent = String(pending);
  $('statTasks').textContent = String(all.length);
  $('statSessions').textContent = String(sessionsCache.length || new Set(all.map(m => m.conversation_id)).size || 1);
  const cur = sessionsCache.find(s => s.id === activeConversation);
  if ($('page-chat').hidden) return;
  $('chatTitle').textContent = cur ? cur.title : 'Nova conversa';
  const project = cur && workspace && workspace.get('project', cur.project_id);
  $('chatSubtitle').textContent = (project ? project.title : 'Sem projeto') + (cur?.archived ? ' · Arquivada' : '') + (rows.length ? ' · ' + rows.length + (rows.length === 1 ? ' mensagem' : ' mensagens') : '');
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
    d.innerHTML = '<div class="timeline-icon"><svg class="icon"><use href="#i-chat"/></svg></div><div><strong>' + esc((m.role === 'assistant' ? 'Lucas' : 'Você') + ' · ' + (m.status || '')) + '</strong><p>' + esc(String(m.text || '').slice(0, 120)) + '</p><small>' + esc(fmtTime(m.created_at)) + '</small></div>';
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
  $('estAcertos').textContent = r.respostas ? (r.acertos || 0) + '/' + r.respostas : '—';
  $('estItens').textContent = r.itens_plano ? (r.itens_feitos || 0) + '/' + r.itens_plano : '—';
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
  if (t === 'adaptive_round_evaluated') return 'Avaliando lacunas e novas evidências…';
  if (t === 'source_reused') return 'Reutilizando fontes já lidas…';
  if (t === 'source_irrelevant') return 'Fonte sem correspondência; seguindo a pesquisa…';
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
  if (researchJob && researchJob.controller) researchJob.controller.abort();
  if (researchJob && researchJob.timer) clearTimeout(researchJob.timer);
  if (researchJob && researchJob.statusTimer) clearInterval(researchJob.statusTimer);
  window._researchLast = jobId;
  try { localStorage.setItem('vexx-research-active:' + currentUid, JSON.stringify({ id: jobId, owner: currentUid, at: Date.now() })); } catch (_) {}
  researchJob = { id: jobId, seq: 0, vistos: new Set(), inicio: Date.now(), timer: null };
  const active = researchJob;
  // A stream may stay open without delivering the terminal event after reconnect.
  active.statusTimer = setInterval(() => {
    if (researchJob !== active || active.statusPending) return;
    active.statusPending = true;
    researchPollHTTP().catch(() => {}).finally(() => { active.statusPending = false; });
  }, 5000);
  $('researchBar').hidden = false;
  $('researchPanel').hidden = true;
  $('researchToggle').setAttribute('aria-expanded', 'false');
  $('researchSteps').replaceChildren();
  $('researchSources').replaceChildren();
  const view = $('researchView');
  if (view) { view.replaceChildren(); view.hidden = true; delete view.dataset.job; }
  const viewToggle = $('researchViewToggle');
  if (viewToggle) viewToggle.setAttribute('aria-expanded', 'false');
  const fill = $('researchProgressFill');
  if (fill) fill.style.width = '0%';
  researchAtualizaExport(jobId);
  researchFiltroAtual = 'all';
  researchAplicaFiltro();
  $('researchLabel').textContent = 'Pesquisando...';
  researchPoll();
}
let researchRestoring = false;
async function researchResumeSaved() {
  if (researchJob || researchRestoring || !authenticated || !pcOnline) return;
  const owner = currentUid;
  const epoch = authEpoch;
  const key = 'vexx-research-active:' + owner;
  let saved;
  try { saved = JSON.parse(localStorage.getItem(key) || 'null'); } catch (_) { return; }
  if (!saved) return;
  if (saved.owner !== owner || !Number.isFinite(saved.at) || !/^rj-[a-z0-9]+$/.test(saved.id || '') || Date.now() - saved.at > 86400000) {
    try { localStorage.removeItem(key); } catch (_) {} return;
  }
  researchRestoring = true;
  try {
    await api('/api/research/status?job_id=' + encodeURIComponent(saved.id));
    if (authenticated && currentUid === owner && authEpoch === epoch && !researchJob) researchAttach(saved.id);
  } catch (error) {
    if (error.status === 404) { try { localStorage.removeItem(key); } catch (_) {} }
  } finally { researchRestoring = false; }
}
function researchJobIdAtual() {
  return (researchJob && researchJob.id) || window._researchLast || '';
}
function researchAtualizaExport(jobId) {
  const id = jobId || researchJobIdAtual();
  if (!id || !/^[A-Za-z0-9_-]{2,64}$/.test(id)) return;
  const base = '/api/research/export?job_id=' + encodeURIComponent(id) + '&formato=';
  [['researchExportMd', 'md'], ['researchExportCsv', 'csv'],
    ['researchExportJson', 'json']].forEach(pair => {
    const a = $(pair[0]);
    if (!a) return;
    a.href = base + pair[1];
    a.hidden = false;
  });
}
function researchAtualizaProgresso(s) {
  const fill = $('researchProgressFill');
  if (!fill) return;
  const etapas = (s && Array.isArray(s.etapas)) ? s.etapas : [];
  const feitas = etapas.filter(e => e.status === 'feita').length;
  const pct = etapas.length ? Math.round(feitas / etapas.length * 100) : 0;
  fill.style.width = pct + '%';
  const bar = fill.parentElement;
  if (bar) {
    bar.setAttribute('role', 'progressbar');
    bar.setAttribute('aria-valuenow', String(pct));
    bar.setAttribute('aria-valuemin', '0');
    bar.setAttribute('aria-valuemax', '100');
    bar.setAttribute('aria-label', 'Progresso da pesquisa: ' + feitas + ' de ' + etapas.length + ' etapas');
  }
}
async function renderPesquisas() {
  const box = $('researchJobList');
  if (!box) return;
  box.replaceChildren();
  box.textContent = 'Carregando pesquisas…';
  try {
    const r = await api('/api/research/jobs');
    const jobs = Array.isArray(r.jobs) ? r.jobs : [];
    box.replaceChildren();
    if (!jobs.length) {
      box.textContent = 'Nenhuma pesquisa salva ainda. Peça uma investigação no chat.';
      return;
    }
    const ROT = { criada: 'criada', em_andamento: 'em andamento', pausada: 'pausada',
      concluida: 'conclu?da', interrompida: 'interrompida', cancelada: 'cancelada',
      falhou: 'falhou' };
    jobs.forEach(job => {
      const card = document.createElement('div');
      card.className = 'doc-item';
      const strong = document.createElement('strong');
      strong.textContent = job.objetivo || 'Pesquisa sem objetivo';
      card.appendChild(strong);
      const meta = document.createElement('small');
      meta.textContent = [ROT[job.status] || job.status || '', job.modo || '',
        job.atualizado_em || job.criado_em || ''].filter(Boolean).join(' · ');
      card.appendChild(meta);
      const acts = document.createElement('div');
      acts.className = 'doc-actions';
      const abrir = document.createElement('button');
      abrir.type = 'button'; abrir.className = 'subtle-button'; abrir.textContent = 'Abrir';
      abrir.addEventListener('click', () => researchWorkspaceAbrir(job.id));
      acts.appendChild(abrir);
      const chat = document.createElement('button');
      chat.type = 'button'; chat.className = 'subtle-button'; chat.textContent = 'Acompanhar no chat';
      chat.addEventListener('click', () => { researchAttach(job.id); navigate('chat'); });
      acts.appendChild(chat);
      card.appendChild(acts);
      box.appendChild(card);
    });
  } catch (_) {
    box.replaceChildren();
    box.textContent = 'Não foi possível carregar as pesquisas. Verifique a conexão com o PC.';
  }
}
function researchWorkspaceExporta(id) {
  if (!id || !/^[A-Za-z0-9_-]{2,64}$/.test(id)) return;
  const base = '/api/research/export?job_id=' + encodeURIComponent(id) + '&formato=';
  [['researchWorkspaceExportMd', 'md'], ['researchWorkspaceExportCsv', 'csv'],
    ['researchWorkspaceExportJson', 'json']].forEach(pair => {
    const a = $(pair[0]);
    if (!a) return;
    a.href = base + pair[1];
    a.hidden = false;
  });
}
async function researchWorkspaceAbrir(id) {
  const lista = $('researchJobList');
  const painel = $('researchWorkspace');
  const view = $('researchWorkspaceView');
  const titulo = $('researchWorkspaceTitle');
  if (!lista || !painel || !view || !titulo || !id) return;
  lista.hidden = true; painel.hidden = false;
  titulo.textContent = 'Carregando pesquisa…';
  view.replaceChildren();
  researchWorkspaceExporta(id);
  try {
    const st = await api('/api/research/status?job_id=' + encodeURIComponent(id));
    const resumo = (st && st.resumo) || {};
    titulo.textContent = resumo.objetivo || 'Pesquisa';
    const r = await api('/api/research/view?job_id=' + encodeURIComponent(id));
    view.replaceChildren();
    if (!r || !r.message || typeof JDUI === 'undefined') throw new Error('sem visão');
    JDUI.mount(view, [r.message], { markdown: renderMarkdown });
  } catch (_) {
    titulo.textContent = 'Pesquisa';
    view.replaceChildren();
    const p = document.createElement('p');
    p.className = 'settings-note';
    p.textContent = 'Não foi possível montar a visão estruturada. O plano e as fontes continuam disponíveis no chat.';
    view.appendChild(p);
  }
}
async function researchCarregaView(force) {
  const box = $('researchView');
  const id = researchJobIdAtual();
  if (!box || !id) return;
  if (!force && box.dataset.job === id && box.hasChildNodes()) { box.hidden = false; return; }
  box.hidden = false;
  box.replaceChildren();
  box.textContent = 'Carregando visão estruturada…';
  try {
    const r = await api('/api/research/view?job_id=' + encodeURIComponent(id));
    if (!r || !r.message || typeof JDUI === 'undefined') throw new Error('sem visão');
    box.replaceChildren();
    JDUI.mount(box, [r.message], { markdown: renderMarkdown });
    box.dataset.job = id;
  } catch (_) {
    box.replaceChildren();
    const p = document.createElement('p');
    p.className = 'jdui-source';
    p.textContent = 'Visão estruturada indisponível. Use a linha do tempo e as fontes consultadas; nenhum dado foi inventado.';
    box.appendChild(p);
  }
}
function researchStop() {
  $('researchBar').hidden = true;
  try { localStorage.removeItem('vexx-research-active:' + currentUid); } catch (_) {}
  if (researchJob && researchJob.timer) clearTimeout(researchJob.timer);
  if (researchJob && researchJob.statusTimer) clearInterval(researchJob.statusTimer);
  if (researchJob && researchJob.controller) researchJob.controller.abort();
  researchJob = null;
}
function researchItem(icon, title, desc) {
  return '<div class="timeline-icon"><svg class="icon"><use href="#' + icon + '"/></svg></div>'
    + '<div><strong>' + esc(title) + '</strong>'
    + (desc ? '<p>' + esc(desc) + '</p>' : '') + '</div>';
}
async function researchPoll() {
  if (!researchJob) return;
  const active = researchJob;
  if (Date.now() - researchJob.inicio > 10 * 60 * 1000) { researchStop(); return; }
  // V4.7: SSE push em tempo real; qualquer falha cai no polling (fallback).
  try {
    await researchPollSSE();
  } catch (_) {
    if (researchJob !== active) return;
    await researchPollHTTP();
  }
  if (researchJob === active) researchJob.timer = setTimeout(researchPoll, 2000);
}
async function researchPollSSE() {
  const active = researchJob;
  if (!active) return;
  active.controller = new AbortController();
  const res = await fetch('/api/research/stream?job_id=' + encodeURIComponent(researchJob.id)
    + '&apos_seq=' + researchJob.seq,
    { headers: { Accept: 'text/event-stream', 'X-CSRF-Token': csrf }, credentials: 'same-origin', signal: active.controller.signal });
  if (!res.ok || !res.body) throw new Error('SSE indisponível (' + res.status + ')');
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = '';
  for (;;) {
    if (researchJob !== active) { try { await reader.cancel(); } catch (_) {} return; }
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
      if (tipo !== 'research' || researchJob !== active) continue;
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
  const active = researchJob;
  if (!active) return;
  const r = await api('/api/research/status?job_id=' + encodeURIComponent(researchJob.id)
    + '&apos_seq=' + researchJob.seq);
  if (researchJob !== active) return;
  (r.eventos || []).forEach(ev => researchRecebe(ev));
  const s = r.resumo || {};
  researchPintaResumo(s);
  if (RESEARCH_FIM.indexOf(s.status) >= 0) {
    $('researchLabel').textContent = s.status === 'concluida'
      ? 'Pesquisa concluída: ' + (s.evidencias || 0) + ' evidências.'
      : 'Pesquisa ' + s.status + '.';
    researchCarregaFontes();
    researchAtualizaExport(s.id || researchJob.id);
    const view = $('researchView');
    if (view && !view.hidden) researchCarregaView(true);
    researchStop();
  }
}
function researchRecebe(ev) {
  if (!researchJob || (ev.job_id && ev.job_id !== researchJob.id) || researchJob.vistos.has(ev.seq)) return;
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
    window._researchResumo = s;
    researchAtualizaProgresso(s);
    const etapas = Array.isArray(s.etapas) ? s.etapas : [];
    const feitas = etapas.filter(e => e.status === 'feita').length;
    const total = etapas.length;
    const fim = RESEARCH_FIM.indexOf(s.status) >= 0;
    $('researchLabel').textContent = fim
      ? 'Pesquisa ' + s.status + ': ' + (s.evidencias || 0) + ' evidências.'
      : 'Pesquisando...' + (total ? ' (' + feitas + '/' + total + ')' : '');
    if (s.id) researchAtualizaExport(s.id);
    return;
  }
  if (ultimo) $('researchLabel').textContent = researchFase(ultimo);
}
function researchFinal(ev) {
  if (!researchJob) return;
  const active = researchJob;
  const id = researchJob.id;
  api('/api/research/status?job_id=' + encodeURIComponent(id) + '&apos_seq=0')
    .then(r => {
      if (researchJob !== active) return;
      researchPintaResumo(r.resumo || {});
      researchAtualizaExport((r.resumo && r.resumo.id) || id);
      const view = $('researchView');
      if (view && !view.hidden) researchCarregaView(true);
    })
    .catch(() => {})
    .finally(() => {
      if (researchJob !== active) return;
      const s = $('researchLabel');
      if (s && /Pesquisand/.test(s.textContent)) s.textContent = 'Pesquisa concluída. Ver detalhes.';
      researchCarregaFontes();
      researchStop();
    });
}
async function researchCarregaFontes() {
  if (!$('researchPanel') || $('researchPanel').hidden) return;
  const id = researchJobIdAtual();
  if (!id) return;
  try {
    const r = await api('/api/research/evidence?job_id=' + encodeURIComponent(id));
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
      const acesso = e.access_state === 'metadata_only' ? 'somente metadados'
        : (e.texto_lido ? 'texto lido' : (e.access_state === 'snippet_only' ? 'trecho' : 'origem'));
      const sm = document.createElement('small');
      sm.textContent = [e.dominio || '', e.status || '', acesso].filter(Boolean).join(' · ');
      wrap.appendChild(sm);
      if (e.trecho) {
        const p = document.createElement('p');
        p.textContent = String(e.trecho).slice(0, 320);
        wrap.appendChild(p);
      }
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
  if (!p.hidden) { researchCarregaFontes(); researchAtualizaExport(); }
});
const researchWorkspaceBack = $('researchWorkspaceBack');
if (researchWorkspaceBack) researchWorkspaceBack.addEventListener('click', () => {
  const painel = $('researchWorkspace');
  const lista = $('researchJobList');
  if (painel) painel.hidden = true;
  if (lista) lista.hidden = false;
  renderPesquisas();
});
const researchViewToggle = $('researchViewToggle');
if (researchViewToggle) researchViewToggle.addEventListener('click', () => {
  const box = $('researchView');
  if (!box) return;
  const abrir = box.hidden;
  box.hidden = !abrir;
  researchViewToggle.setAttribute('aria-expanded', abrir ? 'true' : 'false');
  if (abrir) researchCarregaView(false);
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
  const res = await fetch(endpoint, { method: options.method || 'GET', body: options.body, headers: Object.assign(headers, options.headers || {}), credentials: 'same-origin', cache: 'no-store', signal: options.signal });
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
  const epoch = authEpoch;
  if (PREVIEW_MODE) { authenticated = true; $('loginOverlay').hidden = true; return; }
  try {
    const s = await api('/api/session');
    if (epoch !== authEpoch || authBusy) return;  // login/cadastro mais novo venceu a corrida
    csrf = s.csrf; authenticated = true; $('loginOverlay').hidden = true;
    if (aplicarSessao(s) === false) return;
  } catch (_) {
    if (epoch !== authEpoch || authBusy || authenticated) return;
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
  e.preventDefault(); ++authEpoch; authBusy = true;
  const btn = $('loginButton'); btn.disabled = true; $('loginError').textContent = '';
  try {
    const r = await api('/api/login', { method: 'POST', body: JSON.stringify({ username: $('loginUser').value, password: $('loginPassword').value }) });
    $('loginPassword').value = ''; csrf = r.csrf; authenticated = true;
    $('loginOverlay').hidden = true;
    if (aplicarSessao(r) === false) return;
    await checkStatus(); showToast('Conectado');
  } catch (err) { $('loginError').textContent = err.message || 'Não foi possível entrar'; }
  finally { authBusy = false; btn.disabled = false; }
});
$('logoutButton').addEventListener('click', async () => {
  stopAI();
  try { await api('/api/logout', { method: 'POST' }); } catch (_) { showToast('O PC não confirmou a saída. Reconecte e tente novamente.'); return; }
  ++authEpoch;
  researchStop();
  authenticated = false; csrf = ''; pcOnline = false; $('loginOverlay').hidden = false;
  $('loginPassword').value = ''; $('regPassword').value = ''; $('regPassword2').value = '';
  $('loginError').textContent = ''; $('regError').textContent = '';
  $('registerForm').hidden = true; $('loginForm').hidden = false; $('loginBack').hidden = true;
  pintarPerfil('Offline', '', 'user', false);
  updateConnection(); showToast('Sessão encerrada');
});

/* ----- Auth config + register flow ----- */
let authConfig = { modo: 'fechado', exigir_aprovacao: true, agent_online: false };
async function fetchAuthConfig() {
  try { authConfig = await api('/api/auth/config'); }
  catch (_) { authConfig = { modo: 'fechado', exigir_aprovacao: true, agent_online: false }; }
  const inviteWrap = $('regInviteWrap');
  const showRegister = $('showRegister');
  const availability = $('registerAvailability');
  if (inviteWrap && showRegister && availability) {
    if (authConfig.modo === 'convite') {
      inviteWrap.hidden = false;
    } else {
      inviteWrap.hidden = true;
    }
    const offline = authConfig.agent_online !== true;
    showRegister.hidden = authConfig.modo === 'fechado' && !offline;
    availability.hidden = !offline;
    availability.textContent = offline
      ? 'Conecte o computador com o agente JULIA para criar contas e entrar com elas.'
      : '';
    if (authConfig.modo === 'fechado' && !offline) {
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
  ++authEpoch; authBusy = true;
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
  finally { authBusy = false; btn.disabled = false; }
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
      await researchResumeSaved();
      const conf = await syncAndRefresh();
      await loadModels(false);
      renderDocs();
      for (const m of conf.filter(m => m.want_ai && m.role === 'user')) requestAI(m);
      // puxa respostas prontas de outras sessões? tenta IA para pendentes recentes
      const all = ownRows(await allMessages());
      const pend = all.filter(m => m.role === 'user' && m.want_ai && m.status === 'synced' && !all.find(x => x.id === m.id + '-r1')).slice(-3);
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
  const owner = currentUid;
  const generation = storageGeneration;
  const conf = [];
  try {
    // Resolve names and project membership before importing message-only history.
    // Otherwise a fresh device could publish an inferred title over a real edit.
    const workspaceReady = workspace ? await workspace.sync() : false;
    if (generation !== storageGeneration || owner !== currentUid || !authenticated) return [];
    for (let guard = 0; guard < 5 && pcOnline; guard++) {
      const rem = ownRows(await allMessages()).filter(m => m.role === 'user' && m.status === 'pending').slice(0, 100);
      if (generation !== storageGeneration || owner !== currentUid || !authenticated) return [];
      if (!rem.length) break;
      const clean = rem.map(m => ({ id: m.id, conversation_id: m.conversation_id, origin: 'mobile', role: 'user', text: m.text, created_at: m.created_at }));
      const r = await api('/api/sync', { method: 'POST', body: JSON.stringify({ messages: clean }) });
      if (generation !== storageGeneration || owner !== currentUid || !authenticated) return [];
      const ok = new Set(r.confirmed_ids || []);
      if (!ok.size) break;
      const batch = rem.filter(m => ok.has(m.id));
      await storeMessages(batch.map(m => ({ id: m.id, conversation_id: m.conversation_id, origin: 'mobile', role: 'user', text: m.text, created_at: m.created_at, status: 'synced', want_ai: true, owner })));
      conf.push(...batch);
    }
    const conversations = new Map();
    let historyCursor = '';
    const historyCursors = new Set();
    do {
    const remote = await api('/api/messages' + (historyCursor ? '?cursor=' + encodeURIComponent(historyCursor) : ''));
    if (generation !== storageGeneration || owner !== currentUid || !authenticated) return [];
    const adds = [];
    for (const m of remote.messages || []) {
      if (!m || typeof m.id !== 'string' || typeof m.text !== 'string' || m.origin !== 'mobile') continue;
      const cid = m.conversation_id || activeConversation;
      if (isDeleted(cid)) continue; // excluída: não ressuscita
      adds.push({ id: m.id, conversation_id: cid, origin: 'mobile', role: m.role === 'assistant' ? 'assistant' : 'user', text: m.text, created_at: m.created_at, status: 'synced', model: m.model || '', owner });
    }
    await storeMessages(adds);
    for (const m of adds) {
      const summary = conversations.get(m.conversation_id) || {first: null, last: ''};
      if (m.role === 'user' && (!summary.first || m.created_at < summary.first.created_at)) summary.first = m;
      if (m.created_at > summary.last) summary.last = m.created_at;
      conversations.set(m.conversation_id, summary);
    }
    historyCursor = remote.next_cursor || '';
    if (historyCursor && historyCursors.has(historyCursor)) throw Error('Cursor de histórico repetido');
    historyCursors.add(historyCursor);
    } while (historyCursor);
    for (const [conv, summary] of conversations) {
      if (generation !== storageGeneration || owner !== currentUid || !authenticated) return [];
      await touchSession(conv, summary.first ? titleFrom(summary.first.text) : undefined, summary.last, workspaceReady);
    }
    await renderSessions($('sessionSearch').value);
    if (!aiAbort) await renderMessages();
    syncJduiStates();
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
let modelCatalog = { models: [], providers: [] };
let modelLoadVersion = 0;
let providerMutation = false;
function providerLabel(pid) {
  const p = (modelCatalog.providers || []).find(x => x.id === pid);
  return p ? p.label : pid;
}
function providerFlag(pid, campo) {
  const p = (modelCatalog.providers || []).find(x => x.id === pid);
  return !!(p && p[campo]);
}
function isConfigured(pid) {
  if (pid === 'hermes') return true;
  return providerFlag(pid, 'configured') && !providerFlag(pid, 'auth_error');
}
function providerOf(id) {
  const mapa = modelCatalog.itemProvider || {};
  if (mapa[id]) return mapa[id];
  const i = String(id || '').indexOf('/');
  if (i > 0) {
    const pref = id.slice(0, i).toLowerCase();
    if ((modelCatalog.providers || []).some(p => p.id === pref)) return pref;
  }
  return 'hermes';
}
function modelGroup(id) {
  const pid = providerOf(id);
  if (String(id).endsWith(':free')) return 0;
  return pid !== 'hermes' && isConfigured(pid) ? 1 : 2;
}
function fillModels(filter) {
  const sel = $('modelSelect');
  const cur = modeloAtivo() || modelCatalog.default || '';
  sel.replaceChildren();
  const q = (filter || '').trim().toLowerCase();
  const ids = [...new Set(modelCatalog.models || [])].filter(id => !q ||
    id.toLowerCase().includes(q) || providerLabel(providerOf(id)).toLowerCase().includes(q));
  ids.sort((a, b) => modelGroup(a) - modelGroup(b) ||
    providerLabel(providerOf(a)).localeCompare(providerLabel(providerOf(b)), 'pt-BR') || a.localeCompare(b));
  const groups = new Map();
  for (const id of ids) {
    const pid = providerOf(id), rank = modelGroup(id), pronto = isConfigured(pid);
    const recusada = providerFlag(pid, 'auth_error');
    const key = rank + ':' + pid;
    if (!groups.has(key)) {
      const g = document.createElement('optgroup');
      g.label = ['Grátis', 'Suas API keys', 'Outros'][rank] + ' · ' + providerLabel(pid) +
        (pronto ? '' : recusada ? ' · chave recusada' : ' · sem chave');
      groups.set(key, g); sel.appendChild(g);
    }
    const o = document.createElement('option');
    o.value = id;
    o.textContent = pid !== 'hermes' && id.startsWith(pid + '/') ? id.slice(pid.length + 1) : id;
    o.title = id; o.disabled = !pronto;
    groups.get(key).appendChild(o);
  }
  // Filtering must not silently select a different model than the one sent.
  sel.value = cur;
  const selected = $('modelSelected');
  if (selected) selected.textContent = cur ? 'Selecionado: ' + cur : 'Escolha um modelo';
  const info = $('modelResults');
  if (info) info.textContent = ids.length ? ids.length + ' modelos · grátis, suas chaves e outros' : 'Nenhum modelo encontrado. Tente outra busca ou atualize a lista.';
  return cur;
}
async function loadModels(force) {
  if (!authenticated || !pcOnline) { $('aiStatus').textContent = pcOnline ? 'IA: conectado' : 'IA: desconectado'; return false; }
  if (providerMutation && !force) return false;
  if (!force && Date.now() - modelsLoadedAt < 300000) return true;
  const version = ++modelLoadVersion, owner = currentUid;
  try {
    const r = await api('/api/ai/models');
    if (version !== modelLoadVersion || owner !== currentUid || !authenticated) return false;
    modelsLoadedAt = Date.now();
    modelCatalog = { models: r.models || [], providers: r.providers || [], default: r.default || '',
      itemProvider: Object.fromEntries((r.items || []).map(i => [i.id, i.provider])) };
    const cur = fillModels($('modelSearch') ? $('modelSearch').value : '');
    if (!modeloAtivo() && r.default) localStorage.setItem('julia-model', r.default);
    const escolhido = modeloAtivo() || r.default || '?';
    const pid = providerOf(escolhido);
    const aviso = (pid !== 'hermes' && !isConfigured(pid))
      ? (providerFlag(pid, 'auth_error') ? ' · chave recusada no PC' : ' · sem chave no PC') : '';
    $('aiStatus').textContent = (isConfigured(pid) ? 'Modelo selecionado · ' : 'Modelo indisponível · ') + escolhido + aviso;
    return true;
  } catch (_) { if (version === modelLoadVersion) $('aiStatus').textContent = 'IA: sem resposta do PC'; return false; }
}
$('modelSearch') && $('modelSearch').addEventListener('input', e => { fillModels(e.target.value); });
$('modelSelect').addEventListener('change', e => {
  if (!e.target.value || !isConfigured(providerOf(e.target.value))) return;
  localStorage.setItem('julia-model', e.target.value);
  $('aiStatus').textContent = 'IA pronta · ' + e.target.value;
  $('modelSelected').textContent = 'Selecionado: ' + e.target.value;
});
$('modelRefresh') && $('modelRefresh').addEventListener('click', async () => {
  const b = $('modelRefresh');
  b.disabled = true;
  const ok = await loadModels(true);
  b.disabled = false;
  showToast(ok ? 'Lista de modelos atualizada' : 'Não consegui atualizar a lista agora');
});
function abrirSeletorDeModelo() {
  setDrawer(true);
  const det = document.querySelector('.drawer-connection');
  if (det) det.open = true;
  const alvo = $('modelSelect') || $('modelSearch');
  if (alvo) {
    if (alvo.scrollIntoView) alvo.scrollIntoView({ block: 'nearest' });
    try { alvo.focus({ preventScroll: true }); } catch (_) { alvo.focus(); }
  }
}
$('popModelRow') && $('popModelRow').addEventListener('click', () => { $('statusPop').hidden = true; abrirSeletorDeModelo(); });
$('popModelRow') && $('popModelRow').addEventListener('keydown', e => {
  if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); $('statusPop').hidden = true; abrirSeletorDeModelo(); }
});

/* ----- Provedores de IA: chaves ficam SÓ no PC (nunca aqui no app) ----- */
function providerChipInfo(p) {
  if (!p.configured) return { texto: 'Sem chave', classe: '' };
  if (p.auth_error) return { texto: 'Chave recusada no PC', classe: 'warn' };
  return { texto: 'Chave salva', classe: 'ok' };
}
function providerSourceHint(p) {
  if (p.source === 'arquivo') return 'Salva neste PC — troque ou remova aqui.';
  if (p.source === 'sistema') return 'Definida fora do app (variável do sistema). Salvar aqui passa a valer.';
  return '';
}
function providersError(msg) {
  const erro = $('providersError');
  if (!erro) { showToast(msg); return; }
  erro.textContent = msg;
  erro.hidden = false;
}
function renderProviders() {
  const alvo = $('providersList');
  if (!alvo || providerMutation) return;
  const drafts = new Map([...alvo.querySelectorAll('.provider-row')].map(row => [row.dataset.provider, row.querySelector('input')?.value || '']));
  alvo.replaceChildren();
  const provs = (modelCatalog.providers || []).filter(p => p && p.id !== 'hermes');
  if (!provs.length) {
    const vazio = document.createElement('p');
    vazio.className = 'provider-vazio';
    vazio.textContent = 'Sem resposta do PC agora. Use "Atualizar lista de modelos".';
    alvo.appendChild(vazio);
    return;
  }
  for (const p of provs) {
    const row = document.createElement('div');
    row.className = 'provider-row';
    row.dataset.provider = p.id;
    const top = document.createElement('div');
    top.className = 'provider-top';
    const nome = document.createElement('strong');
    nome.textContent = p.label || p.id;
    const chipInfo = providerChipInfo(p);
    const chip = document.createElement('span');
    chip.className = 'provider-chip' + (chipInfo.classe ? ' ' + chipInfo.classe : '');
    chip.textContent = chipInfo.texto;
    top.append(nome, chip);
    row.appendChild(top);
    const dica = providerSourceHint(p);
    if (dica) {
      const fonte = document.createElement('span');
      fonte.className = 'provider-source';
      fonte.textContent = dica;
      row.appendChild(fonte);
    }
    const form = document.createElement('form');
    form.className = 'provider-form';
    const entrada = document.createElement('input');
    entrada.type = 'password';
    entrada.autocomplete = 'off';
    entrada.value = drafts.get(p.id) || '';
    entrada.maxLength = 400;
    entrada.enterKeyHint = 'done';
    entrada.spellcheck = false;
    entrada.placeholder = p.configured ? 'Trocar a chave…' : 'Colar a chave…';
    entrada.setAttribute('aria-label', 'Chave de ' + (p.label || p.id));
    const salvar = document.createElement('button');
    salvar.type = 'submit';
    salvar.className = 'subtle-button';
    salvar.textContent = 'Salvar';
    form.addEventListener('submit', e => { e.preventDefault(); salvarChaveProvedor(p.id, entrada, salvar); });
    form.append(entrada, salvar);
    row.appendChild(form);
    if (p.configured && !p.auth_error) {
      const escolher = document.createElement('button');
      escolher.type = 'button'; escolher.className = 'provider-remove';
      escolher.textContent = 'Escolher modelo deste provedor';
      escolher.addEventListener('click', () => {
        $('providersDialog').close();
        $('modelSearch').value = p.label || p.id;
        fillModels($('modelSearch').value); abrirSeletorDeModelo();
      });
      row.appendChild(escolher);
    }
    if (p.source === 'arquivo') {
      const remover = document.createElement('button');
      remover.type = 'button';
      remover.className = 'provider-remove';
      remover.textContent = 'Remover chave deste PC';
      remover.addEventListener('click', () => removerChaveProvedor(p.id, remover));
      row.appendChild(remover);
    }
    alvo.appendChild(row);
  }
}
function providerPending(pending) {
  providerMutation = pending;
  $('providersRefresh').disabled = pending;
  $('providersList').querySelectorAll('input, button').forEach(el => { el.disabled = pending; });
}
function applyProviderResult(pid, result) {
  if (!result.ok || result.provider !== pid) throw new Error('O PC não confirmou a alteração da chave.');
  const provider = modelCatalog.providers.find(p => p.id === pid);
  if (provider) Object.assign(provider, { configured: result.configured, source: result.source, auth_error: false });
  ++modelLoadVersion; modelsLoadedAt = 0;
  fillModels($('modelSearch').value);
}
async function salvarChaveProvedor(pid, entrada, botao) {
  if (providerMutation) return;
  const valor = String(entrada.value || '').trim();
  if (valor.length < 8) { providersError('Cole a chave completa do provedor (mínimo 8 caracteres).'); entrada.focus(); return; }
  ++modelLoadVersion;
  providerPending(true); botao.textContent = 'Salvando…';
  $('providersError').hidden = true; $('providersNotice').textContent = '';
  try {
    const result = await api('/api/providers', { method: 'POST', body: JSON.stringify({ provider: pid, action: 'set', key: valor }) });
    if (!result.configured) throw new Error('O PC não confirmou que a chave foi salva.');
    applyProviderResult(pid, result);
    entrada.value = ''; /* a chave nunca fica guardada na tela */
    $('providersNotice').textContent = 'Chave de ' + providerLabel(pid) + ' salva no PC. O campo fica vazio por segurança. Escolha um modelo deste provedor para usá-la.';
    const refreshed = await loadModels(true);
    if (!refreshed) $('providersNotice').textContent += ' Não foi possível atualizar os modelos agora; tente Atualizar lista de modelos.';
    else if (providerFlag(pid, 'auth_error')) providersError('A chave foi salva, mas ' + providerLabel(pid) + ' recusou o acesso. Confira a chave e as permissões no provedor.');
  } catch (e) {
    providersError((e && e.message) || 'Não consegui salvar a chave');
  } finally { providerPending(false); renderProviders(); }
}
async function removerChaveProvedor(pid, botao) {
  if (providerMutation) return;
  ++modelLoadVersion;
  providerPending(true); botao.textContent = 'Removendo…';
  $('providersError').hidden = true; $('providersNotice').textContent = '';
  try {
    const result = await api('/api/providers', { method: 'POST', body: JSON.stringify({ provider: pid, action: 'del' }) });
    applyProviderResult(pid, result);
    $('providersNotice').textContent = result.configured ? 'Chave do app removida. A chave definida no sistema continua ativa.' : 'Chave removida deste PC.';
    if (!await loadModels(true)) $('providersNotice').textContent += ' Atualize a lista de modelos quando a conexão voltar.';
  } catch (e) {
    providersError((e && e.message) || 'Não consegui remover a chave');
  } finally { providerPending(false); renderProviders(); }
}
async function abrirProvedores() {
  const d = $('providersDialog');
  if (!d) return;
  renderProviders();
  if (!d.open) d.showModal();
  if (await loadModels(false)) renderProviders();
}
$('providersOpen') && $('providersOpen').addEventListener('click', () => abrirProvedores());
$('popProvidersRow') && $('popProvidersRow').addEventListener('click', () => { $('statusPop').hidden = true; abrirProvedores(); });
$('popProvidersRow') && $('popProvidersRow').addEventListener('keydown', e => {
  if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); $('statusPop').hidden = true; abrirProvedores(); }
});
$('providersClose') && $('providersClose').addEventListener('click', () => $('providersDialog').close());
$('providersDialog') && $('providersDialog').addEventListener('click', e => { if (e.target === $('providersDialog')) $('providersDialog').close(); });
$('providersRefresh') && $('providersRefresh').addEventListener('click', async () => {
  const b = $('providersRefresh');
  b.disabled = true;
  const ok = await loadModels(true);
  b.disabled = false;
  renderProviders();
  showToast(ok ? 'Lista de modelos atualizada' : 'Não consegui atualizar a lista agora');
});

/* ----- IA com streaming rápido ----- */
function setGenBar(on, label) {
  $('genBar').hidden = !on;
  if (label) $('genLabel').textContent = label;
}
function tickGen() {
  $('genLabel').textContent = aiFirstTokenT ? 'Respondendo…' : 'Preparando resposta…';
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
  const placeQuestion = /\b(perto|pr[oó]xim[oa]s?|na minha cidade|onde estou|localiza[cç][aã]o|clima|tempo (em|agora|hoje)|como (est[aá]|t[aá]) o tempo|temperatura|chover|chovendo|previs[aã]o|restaurante|farm[aá]cia|hospital|loja|tr[aâ]nsito|endere[cç]o|pontos tur[ií]sticos|lugares)\b/i.test(text || '');
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
function requestAI(userRow, options = {}) {
  if (!authenticated || (!pcOnline && !options.immediate) || !navigator.onLine || !db) {
    return Promise.resolve();
  }
  const replyId = userRow.id + '-r1';
  options = { ...options, owner: currentUid };
  if (aiRequests.has(replyId)) return Promise.resolve();
  aiRequests.add(replyId);
  const timing = {
    queuedAt: performance.now(),
    workerStartedAt: 0,
    sentAt: options.sentAt,
    storedAt: options.storedAt,
    requestStartedAt: 0,
    responseHeadersAt: 0,
    firstDeltaAt: 0,
    finishedAt: 0
  };
  return new Promise((resolve, reject) => {
    aiQueue.push({ userRow, options, timing, resolve, reject });
    pumpAIQueue();
  });
}
function pumpAIQueue() {
  if (aiQueueRunning) return;
  const item = aiQueue.shift();
  if (!item) return;
  aiQueueRunning = true;
  runAIRequest(item.userRow, item.options, item.timing)
    .then(item.resolve, item.reject)
    .finally(() => {
      aiQueueRunning = false;
      pumpAIQueue();
    });
}
async function runAIRequest(userRow, options, timing) {
  const replyId = userRow.id + '-r1';
  timing.workerStartedAt = performance.now();
  if (!authenticated || !navigator.onLine || !db || options.owner !== currentUid) {
    aiRequests.delete(replyId);
    return;
  }
  let existingReply;
  try { existingReply = await messageById(replyId); }
  catch (err) { aiRequests.delete(replyId); throw err; }
  if (existingReply && (existingReply.status === 'synced' || existingReply.status === 'generating')) {
    aiRequests.delete(replyId);
    return;
  }
  const ph = { id: replyId, conversation_id: userRow.conversation_id, origin: 'mobile', role: 'assistant', text: existingReply?.text || '', created_at: existingReply?.created_at || new Date().toISOString(), status: 'generating', model: modeloAtivo(), owner: options.owner };
  try { await storeMessages([ph]); } catch (_) { aiRequests.delete(replyId); return; }
  aiStartT = Date.now(); aiFirstTokenT = 0;
  setGenBar(true, 'Preparando resposta…');
  clearInterval(genTimer); genTimer = setInterval(tickGen, 500);
  const ctx = aiLocalContext(userRow.text || '');
  const sceneContext = typeof globalThis.getModel3DContext === 'function' ? globalThis.getModel3DContext(options.owner,userRow.conversation_id) : null;
  if (sceneContext) ctx.scene_state = JSON.stringify(sceneContext);
  const qs = new URLSearchParams(Object.assign({
    message_id: userRow.id, conversation_id: userRow.conversation_id,
    model: modeloAtivo(), memory: memoryOn() ? '1' : '0',
    text: userRow.text || '', created_at: userRow.created_at || ''
  }, ctx));
  aiAbort = new AbortController();
  let cur = '';
  let terminal = false, lastSeq = -1, savedAt = 0;
  const saveReply = (text, status, extra = {}) => storeMessages([{ ...ph, text, status, ...extra }]);
  function finalText(d) {
    if (d.reply_id && d.reply_id !== replyId) throw new Error('Identificador de resposta inconsistente');
    const text = d.response_text || cur;
    if (typeof text !== 'string' || !text.trim()) throw new Error('Resposta vazia da IA');
    return text;
  }
  try {
    timing.requestStartedAt = performance.now();
    const streamRequest = fetch('/api/ai/stream', { method: 'POST', body: JSON.stringify({ ...Object.fromEntries(qs), memory: memoryOn() ? 1 : 0 }), headers: { Accept: 'text/event-stream', 'Content-Type': 'application/json', 'X-CSRF-Token': csrf }, credentials: 'same-origin', signal: aiAbort.signal });
    if (typeof options.onStarted === 'function') Promise.resolve(options.onStarted()).catch(() => {});
    if (userRow.conversation_id === activeConversation) {
      renderMessages().catch(() => showToast('Não foi possível atualizar a conversa.'));
    }
    const res = await streamRequest;
    timing.responseHeadersAt = performance.now();
    if (!res.ok || !res.body) throw new Error('IA indisponível (' + res.status + ')');
    const reader = res.body.getReader();
    const dec = new TextDecoder();
    let buf = '';
    let lastEvt = Date.now();
    const stall = setInterval(() => { if (Date.now() - lastEvt > 75000 && aiAbort) aiAbort.abort(); }, 5000);
    try {
      stream: for (;;) {
        const read = await reader.read();
        if (read.done) break;
        buf += dec.decode(read.value, { stream: true });
        lastEvt = Date.now(); // SSE comments are keepalives too.
        let boundary;
        while ((boundary = /\r?\n\r?\n/.exec(buf))) {
          const idx = boundary.index;
          const evt = buf.slice(0, idx); buf = buf.slice(idx + boundary[0].length);
          let tipo = '', dados = '';
          for (const ln of evt.split(/\r?\n/)) {
            if (ln.startsWith('event:')) tipo = ln.slice(6).trim();
            else if (ln.startsWith('data:')) dados += (dados ? '\n' : '') + ln.slice(5).trim();
          }
          if (!tipo) continue;
          lastEvt = Date.now();
          let d = {};
          try { d = JSON.parse(dados); } catch (_) { continue; }
          if (tipo === 'delta') {
            if (Number.isInteger(d.seq) && d.seq > 0) {
              if (d.seq <= lastSeq) continue;
              if (lastSeq > 0 && d.seq !== lastSeq + 1) throw new Error('Conexão interrompida entre trechos da resposta');
              lastSeq = d.seq;
            }
            if (!aiFirstTokenT) {
              aiFirstTokenT = Date.now();
              timing.firstDeltaAt = performance.now();
              tickGen();
            }
            cur += d.trecho || '';
            schedulePaint(replyId, cur);
            if (Date.now() - savedAt >= 1000) {
              await saveReply(cur, 'generating'); savedAt = Date.now();
            }
          } else if (tipo === 'done') {
            if (rafPending) { cancelAnimationFrame(rafPending); rafPending = null; }
            const secs = Math.round((Date.now() - aiStartT) / 100) / 10;
            cur = finalText(d);
            await saveReply(cur, 'synced', {model: d.model || ph.model, latency_s: secs});
            terminal = true; break stream;
          } else if (tipo === 'cancelled') {
            cur = d.partial || cur;
            await saveReply(cur, 'failed');
            terminal = true; break stream;
          } else if (tipo === 'error') {
            if (d.codigo !== 'sem_mensagem') throw new Error(d.error || 'IA indisponível');
            const syncResult = await api('/api/sync', { method: 'POST', signal: aiAbort.signal, body: JSON.stringify({
              messages: [{
                id: userRow.id, conversation_id: userRow.conversation_id,
                origin: 'mobile', role: 'user', text: userRow.text || '',
                created_at: userRow.created_at || ''
              }]
            }) });
            if (!(syncResult.confirmed_ids || []).includes(userRow.id)) {
              throw new Error('A mensagem não foi confirmada pelo computador.');
            }
            const fb = await api('/api/ai', { method: 'POST', signal: aiAbort.signal, body: JSON.stringify({
              message_id: userRow.id, conversation_id: userRow.conversation_id,
              model: modeloAtivo(), memory: memoryOn() ? 1 : 0,
              text: userRow.text || '', created_at: userRow.created_at || '', ...ctx
            }) });
            if (!fb.response_text || !fb.response_text.trim()) {
              throw new Error('Resposta vazia da IA');
            }
            cur = finalText(fb);
            const secs = Math.round((Date.now() - aiStartT) / 100) / 10;
            await saveReply(cur, 'synced', {model: fb.model || ph.model, latency_s: secs});
            console.warn('[chat-timing] sincronização de compatibilidade antes do retry da IA',
              userRow.id.slice(-8));
            terminal = true; break stream;
          }
        }
      }
      if (!terminal && cur) throw new Error('Conexão encerrada antes de concluir. O texto parcial foi salvo.');
      if (!terminal && !cur) {
        const check = (await allMessages()).find(m => m.id === replyId);
        if (!check || check.status === 'generating') {
          // Stream veio vazio: tenta a resposta completa uma vez antes de falhar.
          try {
            const fb = await api('/api/ai', { method: 'POST', signal: aiAbort.signal, body: JSON.stringify({
              message_id: userRow.id, conversation_id: userRow.conversation_id,
              model: modeloAtivo(), memory: memoryOn() ? 1 : 0,
              text: userRow.text || '', created_at: userRow.created_at || '', ...ctx
            }) });
            if (fb.response_text && fb.response_text.trim()) {
              cur = finalText(fb);
              const secs = Math.round((Date.now() - aiStartT) / 100) / 10;
              await saveReply(cur, 'synced', {model: fb.model || ph.model, latency_s: secs});
            } else throw new Error('Resposta vazia da IA');
          } catch (e2) { throw new Error('Resposta vazia da IA'); }
        }
      }
    } finally { clearInterval(stall); await reader.cancel().catch(() => {}); }
  } catch (err) {
    const inter = aiAbort && aiAbort.signal.aborted;
    const motivo = (err && err.message) ? err.message : 'tente de novo';
    const kept = cur || ((await allMessages()).find(m => m.id === replyId) || {}).text || '';
    await saveReply(kept || (inter ? '' : 'Não consegui responder: ' + motivo), 'failed');
    showToast(inter ? 'Interrompido. Toque para retomar.' : 'IA falhou: ' + motivo);
  } finally {
    timing.finishedAt = performance.now();
    console.info('[chat-timing]', JSON.stringify({
      message_id: userRow.id.slice(-8),
      local_save_ms: timing.sentAt && timing.storedAt ? Math.round(timing.storedAt - timing.sentAt) : null,
      queue_wait_ms: timing.workerStartedAt ? Math.round(timing.workerStartedAt - timing.queuedAt) : null,
      preflight_ms: timing.requestStartedAt && timing.workerStartedAt ? Math.round(timing.requestStartedAt - timing.workerStartedAt) : null,
      response_headers_ms: timing.requestStartedAt && timing.responseHeadersAt ? Math.round(timing.responseHeadersAt - timing.requestStartedAt) : null,
      first_delta_ms: timing.requestStartedAt && timing.firstDeltaAt ? Math.round(timing.firstDeltaAt - timing.requestStartedAt) : null,
      total_ms: timing.sentAt ? Math.round(timing.finishedAt - timing.sentAt) : null
    }));
    aiRequests.delete(replyId);
    aiAbort = null;
    streamDraft = null;
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
    if (pre) copyText(pre.textContent, 'Código copiado');
    return;
  }
  const mc = e.target.closest('[data-copy]');
  if (mc) {
    const mid = mc.dataset.copy;
    copyMessage(mid);
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
      copyMessage(mid);
    } else if (mi.dataset.act === 'save' || mi.dataset.act === 'share'
        || mi.dataset.act === 'download' || mi.dataset.act === 'print') {
      const printWindow = mi.dataset.act === 'print' ? window.open('', '_blank') : null;
      allMessages().then(async rows => {
        const row = rows.find(m => m.id === mid);
        if (!row) { if (printWindow) printWindow.close(); return; }
        const title = String(row.text || '').split(/\r?\n/, 1)[0].replace(/^#+\s*/, '').slice(0, 80) || 'Resposta de Lucas';
        if (mi.dataset.act === 'save') {
          try {
            await saveItem({ title, text: row.text || '', message_id: row.id, conversation_id: row.conversation_id });
            showToast('Resposta salva neste aparelho.');
          } catch (_) { showToast('Não foi possível salvar a resposta.'); }
        } else if (mi.dataset.act === 'share') await shareText(title, row.text || '', true);
        else if (mi.dataset.act === 'download') {
          const filename = title.replace(/[^\w\- ]+/g, '').trim().slice(0, 40) || 'resposta-lucas';
          downloadFile(filename + '.txt', 'text/plain', row.text || '');
          showToast('Resposta baixada em TXT.');
        } else {
          openPrintWindow(title, '<article><strong>Lucas</strong><pre>' + esc(row.text || '') + '</pre></article>', printWindow);
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
  const sentAt = performance.now();
  const row = { id: newId(), conversation_id: activeConversation, origin: 'mobile', role: 'user', text: value, created_at: new Date().toISOString(), status: 'pending', want_ai: true };
  try {
    await storeMessages([row]);
    const storedAt = performance.now();
    if (authenticated && navigator.onLine) {
      requestAI(row, { immediate: true, onStarted: syncAndRefresh, sentAt, storedAt })
        .catch(err => showToast('IA falhou: ' + (err.message || 'tente de novo')));
    } else showToast('Salvo no celular');
    await touchSession(row.conversation_id, titleFrom(value));
    if (activeConversation === row.conversation_id && messageInput.value.trim() === value) {
      messageInput.value = ''; autoresize(); $('charCount').textContent = '';
    }
    await renderSessions($('sessionSearch').value);
    await renderMessages();
    scrollChat(true);
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
  if (window.innerWidth < 900) setDrawer(false);
  messageInput.focus();
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
async function copyText(text, successMessage = 'Copiado') {
  const value = String(text == null ? '' : text);
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(value);
      showToast(successMessage);
      return true;
    }
  } catch (_) { /* Try the browser's legacy copy path below. */ }
  const active = document.activeElement;
  const selection = window.getSelection();
  const ranges = selection ? Array.from({length: selection.rangeCount}, (_, i) => selection.getRangeAt(i).cloneRange()) : [];
  const caret = active && typeof active.selectionStart === 'number'
    ? [active.selectionStart, active.selectionEnd, active.selectionDirection] : null;
  const field = document.createElement('textarea');
  field.value = value;
  field.readOnly = true;
  field.style.cssText = 'position:fixed;top:0;left:0;opacity:0;pointer-events:none;font-size:16px';
  let copied = false;
  try {
    document.body.appendChild(field);
    field.focus({preventScroll: true});
    field.select();
    field.setSelectionRange(0, value.length);
    copied = typeof document.execCommand === 'function' && document.execCommand('copy');
  } catch (_) { /* Show a useful failure instead of leaving the button silent. */ }
  finally {
    field.remove();
    if (selection && ranges.length) {
      selection.removeAllRanges();
      ranges.forEach(range => selection.addRange(range));
    }
    if (active && active.isConnected) {
      active.focus({preventScroll: true});
      if (caret) active.setSelectionRange(...caret);
    }
  }
  showToast(copied ? successMessage : 'Não foi possível copiar. Selecione o texto e copie manualmente.');
  return !!copied;
}
async function copyMessage(id) {
  try {
    const row = await messageById(id);
    if (!row || (row.owner || 'local') !== currentUid) {
      showToast('Mensagem indisponível para copiar.');
      return;
    }
    await copyText(row.text);
  } catch (_) { showToast('Não foi possível ler a mensagem para copiar.'); }
}
async function shareText(title, text, allowShare) {
  const payload = String(text || '');
  if (allowShare && navigator.share) {
    try { await navigator.share({ title, text: payload }); return; }
    catch (err) {
      if (err && err.name === 'AbortError') return;
    }
  }
  await copyText(payload, allowShare ? 'Copiado para compartilhar.' : 'Copiado');
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
    const text = rows.map(m => (m.role === 'assistant' ? 'Lucas' : 'Você') + ' · ' +
      fmtTime(m.created_at) + '\n' + String(m.text || '')).join('\n\n');
    downloadFile(title + '.txt', 'text/plain', text);
  } else if (fmt === 'csv') {
    const quote = value => {
      let text = String(value == null ? '' : value);
      if (/^[=+\-@]/.test(text)) text = "'" + text;
      return '"' + text.replace(/"/g, '""') + '"';
    };
    const csv = [['Autor', 'Data e hora', 'Mensagem'], ...rows.map(m => [
      m.role === 'assistant' ? 'Lucas' : 'Você', m.created_at || '', m.text || ''
    ])].map(row => row.map(quote).join(',')).join('\r\n');
    downloadFile(title + '.csv', 'text/csv', '\uFEFF' + csv);
  } else {
    let md = '# ' + title + '\n\n_Exportado do Vexx AI em ' + new Date().toLocaleString('pt-BR') + '_\n\n';
    rows.forEach(m => {
      md += (m.role === 'assistant' ? '## ✦ Lucas' : '## Você') + ' · ' + fmtTime(m.created_at) + '\n\n' + String(m.text || '') + '\n\n---\n\n';
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
  const cards = rows.map(m => '<article><strong>' + esc(m.role === 'assistant' ? 'Lucas' : 'Você') +
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
  const text = rows.map(m => (m.role === 'assistant' ? 'Lucas' : 'Você') + ': ' + (m.text || '')).join('\n\n');
  const session = (await ownSessions()).find(s => s.id === activeConversation);
  await shareText((session && session.title) || 'Conversa com Lucas', text, true);
});
$('clearCache').addEventListener('click', async () => {
  if (!window.confirm('Apagar todo o cache? Esta ação não pode ser desfeita.')) return;
  await clearStorage();
  if (workspace) workspace.reset();
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
  const uploadConversation = activeConversation;
  $('attachButton').disabled = true;
  $('uploadStatus').hidden = false;
  $('uploadStatus').textContent = 'Enviando e lendo ' + f.name + '…';
  try {
    const fd = new FormData();
    fd.append('file', f, f.name);
    fd.append('conversation_id', uploadConversation);
    const res = await fetch('/api/docs/upload', { method: 'POST', body: fd, headers: { 'X-CSRF-Token': csrf }, credentials: 'same-origin' });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || ('Erro ' + res.status));
    const row = { id: newId(), conversation_id: uploadConversation, origin: 'mobile', role: 'user', text: '📎 Anexei o documento "' + data.name + '" (' + data.chars + ' caracteres em ' + data.chunks + ' trechos).', created_at: new Date().toISOString(), status: 'pending', want_ai: false };
    await storeMessages([row]);
    await touchSession(uploadConversation, titleFrom(f.name));
    await syncAndRefresh();
    await renderSessions($('sessionSearch').value);
    await renderMessages();
    await renderDocs();
    scrollChat(true);
    showToast('Documento lido. Peça resumo, tópicos ou pergunte sobre ele.');
  } catch (err) { showToast('Falha no upload: ' + (err.message || '')); }
  finally { $('attachButton').disabled = false; $('uploadStatus').hidden = true; }
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
    if (!docs.length) { box.innerHTML = '<div class="doc-empty">Nenhum documento ainda. Abra uma conversa e use o botão + para anexar.</div>'; return; }
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
let historySearchVersion = 0;
async function searchHistory() {
  const version = ++historySearchVersion;
  const generation = storageGeneration, owner = currentUid;
  const isCurrent = () => version === historySearchVersion && generation === storageGeneration && owner === currentUid;
  const box = $('historyResults');
  if (!box) return;
  const query = String($('historySearch').value || '').trim().toLocaleLowerCase('pt-BR');
  box.replaceChildren();
  if (query.length < 2) return;
  if (!db) { box.textContent = 'Histórico local indisponível.'; return; }
  const all = ownRows(await allMessages());
  if (!isCurrent()) return;
  const matches = all.filter(m => String(m.text || '').toLocaleLowerCase('pt-BR').includes(query))
    .slice(-50).reverse();
  if (!matches.length) {
    const empty = document.createElement('div'); empty.className = 'doc-empty';
    empty.textContent = 'Nenhuma mensagem encontrada no histórico deste aparelho.';
    box.appendChild(empty);
    return;
  }
  const titles = new Map((await ownSessions()).map(s => [s.id, s.title || 'Conversa']));
  if (!isCurrent()) return;
  matches.forEach(m => {
    const row = document.createElement('button'); row.type = 'button'; row.className = 'history-result';
    const head = document.createElement('strong');
    head.textContent = (titles.get(m.conversation_id) || 'Conversa') + ' · ' +
      (m.role === 'assistant' ? 'Lucas' : 'Você') + ' · ' + fmtTime(m.created_at);
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
let savedItemsRenderVersion = 0;
async function paintSavedItems() {
  const version = ++savedItemsRenderVersion;
  const generation = storageGeneration, owner = currentUid;
  const box = $('savedItems');
  if (!box) return;
  box.replaceChildren();
  const items = await savedItems();
  if (version !== savedItemsRenderVersion || generation !== storageGeneration || owner !== currentUid) return;
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
    for (const s of await ownSessions()) {
      if (!s.inferred || workspace.get('chat', s.id)) await workspace.trackSession(s);
    }
    await migrateV1();
    const rows = await allMessages();
    const presas = ownRows(rows).filter(m => m.status === 'generating');
    if (presas.length) await storeMessages(presas.map(m => ({ ...m, status: 'failed' })));
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
