// ─────────────────────────────────────────────────────────────────────────────
// TripBudgetMonitor Service Worker  v10  (Offline Expense Sync)
// Strategy:
//   • Read-only pages  → Network-first, cache fallback (served offline)
//   • Write pages      → Network-only (never cached, show offline page if down)
//   • Static assets    → Cache-first, network fallback
//   • API/AJAX         → Network-first, cached JSON fallback
//   • Background Sync  → Notify clients to flush IndexedDB queue when online
// ─────────────────────────────────────────────────────────────────────────────

const CACHE_NAME = "tripbudget-v12";

// Static files pre-cached at install time
const PRECACHE_ASSETS = [
  "/static/manifest.json",
  "/static/trip/images/icon-192x192-v2.png",
  "/static/trip/images/icon-512x512-v2.png",
];

// ── URL Classification ────────────────────────────────────────────────────────

const WRITE_PAGE_PATTERNS = [
  /^\/make-trip\/?$/,
  /^\/login\/?$/,
  /^\/signup\/?$/,
  /^\/logout\/?$/,
  /^\/trip\/\d+\/edit\/?$/,
  /^\/trip\/\d+\/add-expense\/?$/,
  /^\/trip\/\d+\/access\/?$/,
  /^\/trip\/\d+\/export-pdf\/?$/,
  /^\/trip\/\d+\/ocr-receipt\/?$/,
  /^\/trip\/\d+\/settlement\/mark-paid\/?$/,
  /^\/trip\/\d+\/settlement\/unmark-paid\/\d+\/?$/,
  /^\/trip\/\d+\/sync-offline-expense\/?$/,
  /^\/admin\//,
];

const READ_PAGE_PATTERNS = [
  /^\/$/,
  /^\/trip-history\/?$/,
  /^\/trip-list\/?$/,
  /^\/offline\/?$/,
  /^\/loading\/?$/,
  /^\/trip\/\d+\/view-expenses\/?$/,
  /^\/trip\/\d+\/dashboard\/?$/,
  /^\/trip\/\d+\/analytics\/?$/,
  /^\/trip\/\d+\/split-bill\/?$/,
  /^\/trip\/\d+\/settlement\/?$/,
  /^\/trip\/\d+\/photos\/?$/,
];

function isWritePage(pathname) {
  return WRITE_PAGE_PATTERNS.some((p) => p.test(pathname));
}

function isReadPage(pathname) {
  return READ_PAGE_PATTERNS.some((p) => p.test(pathname));
}

// ── Install ───────────────────────────────────────────────────────────────────

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(async (cache) => {
      await Promise.all(
        PRECACHE_ASSETS.map(async (url) => {
          try {
            const res = await fetch(url, { cache: "no-cache" });
            if (res.ok) await cache.put(url, res);
            else console.warn("[SW] precache skipped:", url, res.status);
          } catch (e) {
            console.warn("[SW] precache failed:", url, e);
          }
        })
      );

      try {
        const offlineRes = await fetch("/offline/");
        if (offlineRes.ok) await cache.put("/offline/", offlineRes);
      } catch (e) {
        console.warn("[SW] could not cache offline page:", e);
      }

      try {
        const homeRes = await fetch("/");
        if (homeRes.ok) await cache.put("/", homeRes);
      } catch (e) {
        console.warn("[SW] could not cache home:", e);
      }
    })
  );
  self.skipWaiting();
});

// ── Activate ──────────────────────────────────────────────────────────────────

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys.map((key) => {
          if (key !== CACHE_NAME) {
            console.log("[SW] deleting old cache:", key);
            return caches.delete(key);
          }
        })
      )
    )
  );
  self.clients.claim();
});

// ── Background Sync ───────────────────────────────────────────────────────────

self.addEventListener("sync", (event) => {
  if (event.tag === "sync-offline-expenses") {
    event.waitUntil(notifyClientsToSync());
  }
});

async function notifyClientsToSync() {
  const clients = await self.clients.matchAll({
    type: "window",
    includeUncontrolled: true,
  });
  for (const client of clients) {
    client.postMessage({ type: "SYNC_OFFLINE_EXPENSES" });
  }
}

// ── Message from page ─────────────────────────────────────────────────────────

self.addEventListener("message", (event) => {
  if (event.data && event.data.type === "REGISTER_SYNC") {
    self.registration.sync
      .register("sync-offline-expenses")
      .catch(() => {
        // Background Sync not supported — page handles it via online event
      });
  }
});

// ── Fetch ─────────────────────────────────────────────────────────────────────

self.addEventListener("fetch", (event) => {
  const { request } = event;
  const url = new URL(request.url);

  if (url.origin !== self.location.origin) return;
  if (request.method !== "GET") return;

  const { pathname } = url;

  if (
    pathname.startsWith("/api/") ||
    pathname.endsWith("/heatmap-ajax/")
  ) {
    event.respondWith(networkFirstJSON(request));
    return;
  }

  if (request.destination === "document") {
    if (isWritePage(pathname)) {
      event.respondWith(networkOnlyWithOfflineFallback(request));
    } else if (isReadPage(pathname)) {
      event.respondWith(networkFirstPage(request));
    } else {
      event.respondWith(networkFirstPage(request));
    }
    return;
  }

  event.respondWith(cacheFirstAsset(request));
});

// ── Strategy Helpers ──────────────────────────────────────────────────────────

async function networkFirstPage(request) {
  const cache = await caches.open(CACHE_NAME);
  try {
    const networkResponse = await fetch(request);
    if (networkResponse.ok) {
      cache.put(request, networkResponse.clone());
    }
    return networkResponse;
  } catch {
    const cached =
      (await cache.match(request)) ||
      (await cache.match("/")) ||
      (await cache.match("/offline/"));
    return (
      cached ||
      new Response(offlineFallbackHTML(), {
        headers: { "Content-Type": "text/html" },
      })
    );
  }
}

async function networkOnlyWithOfflineFallback(request) {
  try {
    return await fetch(request);
  } catch {
    const cache = await caches.open(CACHE_NAME);
    const offlinePage = await cache.match("/offline/");
    return (
      offlinePage ||
      new Response(offlineFallbackHTML(), {
        headers: { "Content-Type": "text/html" },
      })
    );
  }
}

async function cacheFirstAsset(request) {
  const cache = await caches.open(CACHE_NAME);
  const cached = await cache.match(request);
  if (cached) return cached;

  try {
    const networkResponse = await fetch(request);
    if (networkResponse.status === 200) {
      cache.put(request, networkResponse.clone());
    }
    return networkResponse;
  } catch {
    return new Response("", { status: 408 });
  }
}

async function networkFirstJSON(request) {
  const cache = await caches.open(CACHE_NAME);
  try {
    const networkResponse = await fetch(request);
    if (networkResponse.ok) {
      cache.put(request, networkResponse.clone());
    }
    return networkResponse;
  } catch {
    const cached = await cache.match(request);
    return (
      cached ||
      new Response(JSON.stringify({ offline: true, data: [] }), {
        headers: { "Content-Type": "application/json" },
      })
    );
  }
}

function offlineFallbackHTML() {
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>Offline – TripBudget</title>
  <style>
    body{font-family:system-ui,sans-serif;background:#f0f4f8;display:flex;
         align-items:center;justify-content:center;min-height:100vh;margin:0}
    .card{background:#fff;border-radius:20px;padding:2.5rem 2rem;
          text-align:center;max-width:380px;box-shadow:0 8px 32px rgba(0,0,0,.08)}
    h1{color:#1f2937;margin:.75rem 0 .5rem}
    p{color:#6b7280;font-size:.9rem;line-height:1.6}
    button{margin-top:1.5rem;background:#6366f1;color:#fff;border:none;
           border-radius:10px;padding:.65rem 1.75rem;font-size:.95rem;
           font-weight:600;cursor:pointer}
  </style>
</head>
<body>
  <div class="card">
    <div style="font-size:3rem">📶</div>
    <h1>You're Offline</h1>
    <p>No internet connection. Reconnect to continue managing your trips.</p>
    <button onclick="location.reload()">Try Again</button>
  </div>
  <script>window.addEventListener('online',()=>location.reload())</script>
</body>
</html>`;
}
