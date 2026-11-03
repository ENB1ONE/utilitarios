// purevoid/sw.js - PureVoid Service Worker com atualizacao forcada
const CACHE_NAME = 'purevoid-cache-v1.3.0';

// Força o Service Worker a ativar imediatamente sem esperar fechar as abas
self.addEventListener('install', (event) => {
    self.skipWaiting();
});

// Reivindica controle imediato de todas as abas e instâncias PWA
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

// Gerenciamento de Fetch
self.addEventListener('fetch', (event) => {
    const url = new URL(event.request.url);

    // Documentos HTML, navegacao e checagem de versao NUNCA devem vir de cache antigo
    if (
        event.request.mode === 'navigate' ||
        event.request.destination === 'document' ||
        url.pathname.endsWith('.html') ||
        url.pathname.endsWith('version.json') ||
        url.pathname.endsWith('/purevoid/') ||
        url.pathname.endsWith('/purevoid')
    ) {
        event.respondWith(
            fetch(event.request, { cache: 'no-store' }).catch(() => {
                return caches.match(event.request);
            })
        );
        return;
    }

    // Demais recursos (icones, assets estaticos): Network first com fallback para cache
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
