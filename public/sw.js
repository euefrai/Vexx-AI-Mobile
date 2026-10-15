const VERSION = 'VEXX-shell-v0.8-mobile-drawer';
const SHELL = ['/', '/index.html', '/styles.css', '/interface.css', '/app.js', '/workspace.js', '/organize.js', '/jdui.js', '/manifest.webmanifest', '/icon-192.png', '/icon-512.png'];
self.addEventListener('install', evt => {
  evt.waitUntil(caches.open(VERSION).then(cache => cache.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', evt => {
  evt.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k !== VERSION).map(k => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener('fetch', evt => {
  const url = new URL(evt.request.url);
  if (evt.request.method !== 'GET' || url.origin !== location.origin || url.pathname.startsWith('/api/')) return;
  // Only cache public, versioned application shell. Never intercept private API calls.
  evt.respondWith(fetch(evt.request).then(res => {
    if (res.ok) { const clone = res.clone(); caches.open(VERSION).then(cache => cache.put(evt.request, clone)); }
    return res;
  }).catch(() => caches.match(evt.request)));
});
