/**
 * CryptoAlert Service Worker
 * 缓存静态资源，提供离线回退，支持应用更新
 */

const CACHE_NAME = 'cryptoalert-v1';
const STATIC_ASSETS = [
    '/',
    '/static/css/style.css?v=3.3',
    '/static/js/app.js?v=3.3',
    '/static/icons/icon.svg',
    '/manifest.json'
];

// 外部资源（字体等）
const EXTERNAL_ASSETS = [
    'https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap'
];

// ── Install ─────────────────────────────────────────
self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => {
            console.log('[SW] 缓存静态资源');
            return cache.addAll(STATIC_ASSETS);
        }).then(() => {
            // 跳过等待，立即激活
            return self.skipWaiting();
        })
    );
});

// ── Activate ────────────────────────────────────────
self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((cacheNames) => {
            return Promise.all(
                cacheNames
                    .filter((name) => name !== CACHE_NAME)
                    .map((name) => {
                        console.log('[SW] 清除旧缓存:', name);
                        return caches.delete(name);
                    })
            );
        }).then(() => {
            // 立即控制所有客户端
            return self.clients.claim();
        })
    );
});

// ── Fetch ───────────────────────────────────────────
self.addEventListener('fetch', (event) => {
    const url = new URL(event.request.url);

    // 跳过 WebSocket、API 请求和 socket.io 请求（始终走网络）
    if (
        event.request.url.includes('/socket.io/') ||
        event.request.url.includes('/api/') ||
        event.request.method !== 'GET'
    ) {
        return;
    }

    // 静态资源：缓存优先，回退到网络
    if (
        url.pathname.startsWith('/static/') ||
        url.pathname === '/' ||
        url.pathname === '/manifest.json'
    ) {
        event.respondWith(
            caches.match(event.request).then((cached) => {
                if (cached) {
                    // 后台更新缓存（stale-while-revalidate）
                    fetch(event.request).then((response) => {
                        if (response && response.ok) {
                            caches.open(CACHE_NAME).then((cache) => {
                                cache.put(event.request, response);
                            });
                        }
                    }).catch(() => {});
                    return cached;
                }
                return fetch(event.request).then((response) => {
                    if (response && response.ok) {
                        const responseClone = response.clone();
                        caches.open(CACHE_NAME).then((cache) => {
                            cache.put(event.request, responseClone);
                        });
                    }
                    return response;
                });
            })
        );
        return;
    }

    // 外部资源（字体 CDN 等）：网络优先，回退缓存
    event.respondWith(
        fetch(event.request)
            .then((response) => {
                if (response && response.ok) {
                    const responseClone = response.clone();
                    caches.open(CACHE_NAME).then((cache) => {
                        cache.put(event.request, responseClone);
                    });
                }
                return response;
            })
            .catch(() => {
                return caches.match(event.request);
            })
    );
});
