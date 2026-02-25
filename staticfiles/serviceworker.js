const CACHE_NAME = "tripbudget-v1";

const urlsToCache = [
    "/",
];

// Install event
self.addEventListener("install", function (event) {
    event.waitUntil(
        caches.open(CACHE_NAME).then(function (cache) {
            return cache.addAll(urlsToCache);
        })
    );
});

// Fetch event (Network first, fallback to cache)
self.addEventListener("fetch", function (event) {
    event.respondWith(
        fetch(event.request)
            .then(function (response) {
                return caches.open(CACHE_NAME).then(function (cache) {
                    cache.put(event.request, response.clone());
                    return response;
                });
            })
            .catch(function () {
                return caches.match(event.request);
            })
    );
});