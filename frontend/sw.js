const CACHE_NAME = 'amigopet-pwa-v13-env-config';
const APP_SHELL = [
  '/',
  '/passeador',
  '/manifest.webmanifest',
  '/static/styles.css?v=login-persistente-v3',
  '/static/config.js?v=env-config-v1',
  '/static/app.js?v=login-persistente-v3',
  '/static/walker.js?v=login-persistente-v3',
  '/static/pwa.js?v=login-persistente-v3',
  '/static/assets/amigopet-icon.svg',
  '/static/assets/logo.png'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => cache.addAll(APP_SHELL))
      .then(() => self.skipWaiting())
      .catch(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(
      keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))
    )).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const request = event.request;
  const url = new URL(request.url);

  if (request.method !== 'GET') return;
  if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/ws')) return;
  if (url.pathname.endsWith('.js') || url.pathname.endsWith('.css')) {
    event.respondWith(fetch(request, { cache: 'no-store' }).catch(() => caches.match(request)));
    return;
  }

  event.respondWith(
    fetch(request)
      .then((response) => {
        const copy = response.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(request, copy)).catch(() => {});
        return response;
      })
      .catch(() => caches.match(request).then((cached) => cached || caches.match('/')))
  );
});

self.addEventListener('message', (event) => {
  const data = event.data || {};
  if (data.type === 'SHOW_NOTIFICATION' && self.registration?.showNotification) {
    self.registration.showNotification(data.title || 'AmigoPet', {
      body: data.body || 'Nova atualização no AmigoPet.',
      icon: '/static/assets/amigopet-icon.svg',
      badge: '/static/assets/amigopet-icon.svg',
      tag: data.tag || 'amigopet-update',
      renotify: true,
      requireInteraction: Boolean(data.requireInteraction),
      silent: Boolean(data.silent),
      data: { url: data.url || '/' }
    });
  }
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const targetUrl = event.notification?.data?.url || '/';
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
      for (const client of clientList) {
        if ('focus' in client) {
          client.navigate(targetUrl);
          return client.focus();
        }
      }
      if (clients.openWindow) return clients.openWindow(targetUrl);
    })
  );
});
