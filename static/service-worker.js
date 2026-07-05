const CACHE_NAME = "tripbudget-v5"; // incremented

const STATIC_ASSETS = [
    "/",
    "/offline/",                              // ✅ cache the offline page
    "/static/manifest.json",
    "/static/trip/images/icon-192x192-v2.png",
    "/static/trip/images/icon-512x512-v2.png",
];

// Install: pre-cache static assets including offline page
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

    // 1️⃣ API requests — network first, empty fallback if offline
    if (requestURL.pathname.startsWith("/api/")) {
        event.respondWith(
            caches.match(event.request).then((cached) => {
                return cached || fetch(event.request).then((response) => {
                    return caches.open(CACHE_NAME).then((cache) => {
                        cache.put(event.request, response.clone());
                        return response;
                    });
                }).catch(() => {
                    return new Response(JSON.stringify([]), {
                        headers: { "Content-Type": "application/json" }
                    });
                });
            })
        );
        return;
    }

    // 2️⃣ HTML pages — network first, show offline page if failed
    if (event.request.destination === "document") {
        event.respondWith(
            fetch(event.request)
                .then((response) => {
                    // cache every page the user visits
                    caches.open(CACHE_NAME).then((cache) => {
                        cache.put(event.request, response.clone());
                    });
                    return response;
                })
                .catch(() => {
                    // offline — try the cached version of this page first
                    return caches.match(event.request).then((cached) => {
                        if (cached) return cached;
                        // no cached version → show offline page
                        return caches.match("/offline/");
                    });
                })
        );
        return;
    }

    // 3️⃣ Static assets (CSS, JS, images) — cache first
    event.respondWith(
        caches.match(event.request).then((cachedResponse) => {
            return cachedResponse || fetch(event.request).then((response) => {
                if (response.status === 200) {
                    caches.open(CACHE_NAME).then((cache) => {
                        cache.put(event.request, response.clone());
                    });
                }
                return response;
            }).catch(() => cachedResponse);
        })
    );
});