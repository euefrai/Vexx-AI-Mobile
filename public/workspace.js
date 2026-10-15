/* Account-scoped, offline-first project and chat metadata. No message text here. */
(function (global) {
  'use strict';
  const key = r => r.kind + ':' + r.id;
  const newer = (a, b) => !b || a.updated_at > b.updated_at ||
    (a.updated_at === b.updated_at && a.change_id > b.change_id);
  function create(options) {
    let owner = null, cache = new Map(), loading = null, syncing = false, timer;
    const prefix = uid => 'workspace:' + uid + ':';
    const request = req => new Promise((resolve, reject) => {
      req.onsuccess = () => resolve(req.result); req.onerror = () => reject(req.error);
    });
    async function load() {
      const uid = options.getUid();
      if (owner === uid) return;
      if (loading) { await loading; return load(); }
      loading = (async () => {
        const db = options.getDb();
        if (!db) return;
        const rows = await request(db.transaction('meta', 'readonly').objectStore('meta').getAll());
        cache = new Map(rows.filter(r => r.k.startsWith(prefix(uid))).map(r => [key(r.v), r.v]));
        owner = uid;
      })();
      try { await loading; } finally { loading = null; }
    }
    async function merge(records, uid) {
      if (uid !== options.getUid()) return;
      const db = options.getDb(), tx = db.transaction('meta', 'readwrite'), store = tx.objectStore('meta');
      const done = new Promise((resolve, reject) => {
        tx.oncomplete = resolve; tx.onerror = () => reject(tx.error); tx.onabort = () => reject(tx.error);
      });
      // Read inside this write transaction, so another browser tab cannot be overwritten
      // using an obsolete in-memory snapshot.
      for (const r of records) {
        if (!r || !['project', 'chat'].includes(r.kind) || typeof r.id !== 'string' ||
            typeof r.title !== 'string' || typeof r.updated_at !== 'string' || typeof r.change_id !== 'string') continue;
        const k = prefix(uid) + key(r);
        const old = await request(store.get(k));
        const winner = newer(r, old && old.v) ? r : old.v;
        if (winner === r) store.put({k, v: r});
        cache.set(key(winner), winner);
      }
      await done;
    }
    function schedule() {
      clearTimeout(timer);
      timer = setTimeout(() => sync(), 600);
    }
    async function change(kind, id, patch) {
      await load();
      const current = cache.get(kind + ':' + id);
      const latest = Math.max(Date.now(), ...[...cache.values()].map(r => Date.parse(r.updated_at) + 1));
      const r = Object.assign({kind, id, title: 'Nova conversa', project_id: '', pinned: false,
        archived: false, deleted: false}, current, patch, {
        updated_at: new Date(latest).toISOString(), change_id: crypto.randomUUID()
      });
      r.title = r.title.trim().replace(/\s+/g, ' ').slice(0, 80);
      if (!r.title) throw Error('Informe um nome');
      await merge([r], options.getUid());
      options.onStatus('Organização salva neste aparelho');
      schedule();
      return r;
    }
    async function trackSession(s) {
      await load();
      if ((s.owner || 'local') !== options.getUid()) return;
      const old = cache.get('chat:' + s.id);
      const patch = {title: s.title || 'Nova conversa', project_id: s.project_id || '',
        pinned: !!s.pinned, archived: !!s.archived};
      if (!old || Object.keys(patch).some(k => old[k] !== patch[k])) await change('chat', s.id, patch);
    }
    async function sync() {
      if (syncing || !options.canSync()) return;
      syncing = true;
      const uid = options.getUid();
      try {
        // Reload to include writes made by another tab before this sync.
        owner = null;
        await load();
        const snapshot = [...cache.values()];
        for (let i = 0; i < Math.max(snapshot.length, 1); i += 100) {
          const result = await options.api('/api/workspace/sync', {method: 'POST',
            body: JSON.stringify({records: snapshot.slice(i, i + 100)})});
          if (uid !== options.getUid()) return;
          await merge(result.records || [], uid);
        }
        options.onStatus('Projetos sincronizados com o PC');
        await options.onSync();
      } catch (_) {
        options.onStatus('Organização salva aqui · sincronização pendente');
      } finally { syncing = false; }
    }
    return {load, change, trackSession, sync,
      get: (kind, id) => cache.get(kind + ':' + id),
      list: kind => [...cache.values()].filter(r => r.kind === kind && !r.deleted),
      overlay: s => {
        const meta = cache.get('chat:' + s.id);
        return Object.assign({}, s, meta || {}, {updated_at:
          meta && meta.updated_at > (s.updated_at || '') ? meta.updated_at : s.updated_at});
      }};
  }
  global.VexxWorkspace = {create, newer};
})(typeof window === 'undefined' ? globalThis : window);
