// ─────────────────────────────────────────────────────────────────────────────
// TripBudgetMonitor Service Worker
// Strategy:
//   • Read-only pages  → Network-first, cache fallback (served offline)
//   • Write pages      → Network-only (never cached, show offline page if down)
//   • Static assets    → Cache-first, network fallback
//   • API/AJAX         → Network-first, cached JSON fallback
// ─────────────────────────────────────────────────────────────────────────────

const CACHE_NAME = "tripbudget-v9";

// Static files pre-cached at install time
const PRECACHE_ASSETS = [
  "/static/manifest.json",
  "/static/trip/images/icon-192x192-v2.png",
  "/static/trip/images/icon-512x512-v2.png",
];

// ── URL Classification ────────────────────────────────────────────────────────

/**
 * Pages that mutate the database — never cache, never serve offline.
 * Matched by exact path or regex pattern.
 */
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
  /^\/admin\//,
];

/**
 * Read-only pages — cache with Network-first strategy so offline works.
 */
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
      // Pre-cache static assets (non-fatal if one fails)
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

      // Pre-cache the offline fallback page
      try {
        const offlineRes = await fetch("/offline/");
        if (offlineRes.ok) await cache.put("/offline/", offlineRes);
      } catch (e) {
        console.warn("[SW] could not cache offline page:", e);
      }

      // Pre-cache the home page
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

// ── Fetch ─────────────────────────────────────────────────────────────────────

self.addEventListener("fetch", (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Only intercept same-origin requests
  if (url.origin !== self.location.origin) return;

  // Never intercept non-GET requests (POST/PUT/DELETE go straight to network)
  if (request.method !== "GET") return;

  const { pathname } = url;

  // ── 1. AJAX / heatmap data endpoints → Network-first, cached JSON fallback
  if (
    pathname.startsWith("/api/") ||
    pathname.endsWith("/heatmap-ajax/")
  ) {
    event.respondWith(networkFirstJSON(request));
    return;
  }

  // ── 2. HTML page requests
  if (request.destination === "document") {
    if (isWritePage(pathname)) {
      // Write pages → pure network; if offline show the offline page
      event.respondWith(networkOnlyWithOfflineFallback(request));
    } else if (isReadPage(pathname)) {
      // Read pages → network-first, update cache, serve stale if offline
      event.respondWith(networkFirstPage(request));
    } else {
      // Unknown page → same as read page (safe default)
      event.respondWith(networkFirstPage(request));
    }
    return;
  }

  // ── 3. Static assets (JS, CSS, images, fonts) → Cache-first
  event.respondWith(cacheFirstAsset(request));
});

// ── Strategy Helpers ──────────────────────────────────────────────────────────

/**
 * Network-first for HTML read pages.
 * On success: update cache silently.
 * On failure: serve cached version or /offline/.
 */
async function networkFirstPage(request) {
  const cache = await caches.open(CACHE_NAME);
  try {
    const networkResponse = await fetch(request);
    if (networkResponse.ok) {
      // Clone before consuming — store fresh copy in cache
      cache.put(request, networkResponse.clone());
    }
    return networkResponse;
  } catch {
    // Offline — try exact URL first, then homepage, then offline page
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

/**
 * Network-only for write pages.
 * If offline, show /offline/ — never a stale write form.
 */
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

/**
 * Cache-first for static assets (CSS, JS, images).
 * Falls back to network, then caches any fresh response.
 */
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
    // Truly offline and not cached — nothing we can do for assets
    return new Response("", { status: 408 });
  }
}

/**
 * Network-first for JSON/AJAX endpoints.
 * Falls back to last cached response, then empty array.
 */
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

/**
 * Inline minimal offline HTML in case even /offline/ isn't cached yet.
 */
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