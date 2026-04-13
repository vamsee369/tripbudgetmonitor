const CACHE_NAME = "tripbudget-v4"; // increment version when updating
const STATIC_ASSETS = [
    "/",                         // home page
    "/static/manifest.json",
    "/static/css/style.css",
    "/static/js/main.js",
    "/static/images/logo.png",
    "/static/trip/images/icon-192x192.png",  // PWA icon
    "/static/trip/images/icon-512x512.png",  // PWA icon
    // add any other static files you want to pre-cache
];

// Install: pre-cache static assets
self.addEventListener("install", (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS))
    );
    self.skipWaiting();
});

// Activate: clean old caches
self.addEventListener("activate", (event) => {
    event.waitUntil(
        caches.keys().then((keys) =>
            Promise.all(
                keys.map((key) => {
                    if (key !== CACHE_NAME) return caches.delete(key);
                })
            )
        )
    );
    self.clients.claim();
});

// Fetch: handle requests
self.addEventListener("fetch", (event) => {
    if (event.request.method !== "GET") return;

    const requestURL = new URL(event.request.url);

    // 1️⃣ Handle API requests (dynamic caching)
    if (requestURL.pathname.startsWith("/api/")) {
        event.respondWith(
            caches.match(event.request).then((cached) => {
                return cached || fetch(event.request).then((response) => {
                    return caches.open(CACHE_NAME).then((cache) => {
                        cache.put(event.request, response.clone());
                        return response;
                    });
                }).catch(() => {
                    // Return empty array if offline
                    return new Response(JSON.stringify([]), {
                        headers: { "Content-Type": "application/json" }
                    });
                });
            })
        );
        return;
    }

    // 2️⃣ Handle HTML pages (dynamic caching)
    if (event.request.destination === "document") {
        event.respondWith(
            caches.match(event.request).then((cachedResponse) => {
                if (cachedResponse) return cachedResponse;

                return fetch(event.request)
                    .then((response) => {
                        caches.open(CACHE_NAME).then((cache) => {
                            cache.put(event.request, response.clone());
                        });
                        return response;
                    })
                    .catch(() => caches.match("/")); // fallback to home
            })
        );
        return;
    }

    // 3️⃣ Handle other static assets (CSS, JS, images) - cache first
    event.respondWith(
        caches.match(event.request).then((cachedResponse) => {
            return cachedResponse || fetch(event.request).then((response) => {
                if (response.status === 200 && event.request.destination !== "document") {
                    caches.open(CACHE_NAME).then((cache) => {
                        cache.put(event.request, response.clone());
                    });
                }
                return response;
            }).catch(() => cachedResponse);
        })
    );
});