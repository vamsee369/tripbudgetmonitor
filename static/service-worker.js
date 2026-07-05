const CACHE_NAME = "tripbudget-v6";

// Only pre-cache files guaranteed to return 200 — no Django views here
const STATIC_ASSETS = [
    "/static/manifest.json",
    "/static/trip/images/icon-192x192-v2.png",
    "/static/trip/images/icon-512x512-v2.png",
];

// Install: pre-cache only static files, cache offline page separately
self.addEventListener("install", (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then(async (cache) => {
            // cache static assets
            await cache.addAll(STATIC_ASSETS);

            // cache offline page separately so one failure doesn't break everything
            try {
                const offlineRes = await fetch("/offline/");
                if (offlineRes.ok) await cache.put("/offline/", offlineRes);
            } catch (e) {}

            // cache home page separately
            try {
                const homeRes = await fetch("/");
                if (homeRes.ok) await cache.put("/", homeRes);
            } catch (e) {}
        })
    );
    self.skipWaiting();
});

// Activate: clean old caches
self.addEventListener("activate", (event) => {
    event.waitUntil(
        caches.keys().then((keys) =>
            Promise.all(keys.map((key) => {
                if (key !== CACHE_NAME) return caches.delete(key);
            }))
        )
    );
    self.clients.claim();
});

// Fetch: handle requests
self.addEventListener("fetch", (event) => {
    if (event.request.method !== "GET") return;

    const requestURL = new URL(event.request.url);

    // 1️⃣ API requests — network first, empty JSON fallback if offline
    if (requestURL.pathname.startsWith("/api/")) {
        event.respondWith(
            fetch(event.request).then((response) => {
                caches.open(CACHE_NAME).then((cache) => cache.put(event.request, response.clone()));
                return response;
            }).catch(() =>
                caches.match(event.request).then((cached) =>
                    cached || new Response(JSON.stringify([]), {
                        headers: { "Content-Type": "application/json" }
                    })
                )
            )
        );
        return;
    }

    // 2️⃣ HTML pages — network first, offline page fallback
    if (event.request.destination === "document") {
        event.respondWith(
            fetch(event.request)
                .then((response) => {
                    // cache every page the user successfully visits
                    if (response.ok) {
                        caches.open(CACHE_NAME).then((cache) => cache.put(event.request, response.clone()));
                    }
                    return response;
                })
                .catch(() =>
                    // offline — try cached version of this exact page first
                    caches.match(event.request).then((cached) =>
                        cached || caches.match("/offline/")
                    )
                )
        );
        return;
    }

    // 3️⃣ Static assets — cache first, network fallback
    event.respondWith(
        caches.match(event.request).then((cachedResponse) =>
            cachedResponse || fetch(event.request).then((response) => {
                if (response.status === 200) {
                    caches.open(CACHE_NAME).then((cache) => cache.put(event.request, response.clone()));
                }
                return response;
            }).catch(() => cachedResponse)
        )
    );
});