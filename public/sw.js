const VERSION = 'VEXX-shell-research-cards-20261028-9';
const SHELL = ['/', '/index.html', '/styles.css', '/interface.css', '/app.js', '/workspace.js', '/organize.js', '/jdui.js', '/remote.js', '/remote-setup.html', '/model3d-schema.js', '/manifest.webmanifest', '/icon-192.png', '/icon-512.png', '/trust.css', '/sobre', '/privacidade', '/termos', '/seguranca', '/contato'];
const MODEL3D_ASSETS = new Set(['/model3d-viewer.js', '/model3d-education.js', '/vendor/three-engine.js', '/models/demo-cube.glb', '/models/preview.svg']);
self.addEventListener('install', evt => {
  evt.waitUntil(caches.open(VERSION).then(cache => cache.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', evt => {
  evt.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k !== VERSION).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', evt => {
  const url = new URL(evt.request.url);
  if (evt.request.method !== 'GET' || url.origin !== location.origin || url.pathname.startsWith('/api/')) return;
  const cacheKey = MODEL3D_ASSETS.has(url.pathname) ? url.pathname : evt.request;
  // Only cache public, versioned application shell. Never intercept private API calls.
  evt.respondWith(fetch(evt.request).then(res => {
    if (res.ok) { const clone = res.clone(); caches.open(VERSION).then(cache => cache.put(cacheKey, clone)); }
    return res;
  }).catch(() => caches.match(cacheKey)));
});
