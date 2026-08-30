/* Service worker CASA ONE — minimal et sur.
   Cache uniquement les ressources statiques (cache-first) ; toutes les pages
   dynamiques/authentifiees passent par le reseau (jamais mises en cache). */
const CACHE = 'casaone-static-v1';

self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (e) => e.waitUntil(self.clients.claim()));

self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url);
  if (e.request.method === 'GET' && url.pathname.startsWith('/static/')) {
    e.respondWith(
      caches.open(CACHE).then((c) =>
        c.match(e.request).then((hit) =>
          hit || fetch(e.request).then((resp) => {
            if (resp && resp.ok) c.put(e.request, resp.clone());
            return resp;
          })
        )
      )
    );
  }
  // Sinon : comportement reseau par defaut (pas d'interception).
});
