// sw.js - Utilitarios Hub Service Worker
const CACHE_NAME = 'utilitarios-cache-v1.2.0';

self.addEventListener('install', (event) => {
    self.skipWaiting();
});

self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((keys) => {
            return Promise.all(
                keys.map((key) => {
                    if (key !== CACHE_NAME) {
                        return caches.delete(key);
                    }
                })
            );
        }).then(() => self.clients.claim())
    );
});

self.addEventListener('fetch', (event) => {
    const url = new URL(event.request.url);

    // Documentos HTML, navegacao e checagem de versao: Sempre da rede sem cache
    if (
        event.request.mode === 'navigate' ||
        event.request.destination === 'document' ||
        url.pathname.endsWith('.html') ||
        url.pathname.endsWith('version.json') ||
        url.pathname.endsWith('/')
    ) {
        event.respondWith(
            fetch(event.request, { cache: 'no-store' }).catch(() => {
                return caches.match(event.request);
            })
        );
        return;
    }

    // Demais recursos: Network first
    event.respondWith(
        fetch(event.request)
            .then((response) => {
                if (response.ok && event.request.method === 'GET') {
                    const clone = response.clone();
                    caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
                }
                return response;
            })
            .catch(() => caches.match(event.request))
    );
});
