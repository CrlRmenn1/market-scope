// Persistent tile cache for the map.
//
// The app's map is bounded to a fixed area (Panabo City), so the total
// number of distinct tiles even at high zoom is small and finite - unlike a
// general-purpose world map, caching every tile the user has ever seen is
// cheap and genuinely feasible here. This only intercepts OSM raster tile
// requests; every other request (API calls, the app shell, JS/CSS) passes
// through untouched, straight to the network as normal.
//
// Strategy: cache-first. Map tiles for a given z/x/y are effectively
// immutable, so once a tile is cached there's no need to ever re-fetch it.

const TILE_CACHE_NAME = 'marketscope-tiles-v1';
const TILE_HOST_PATTERN = /^https:\/\/[abc]\.tile\.openstreetmap\.org\//;
const MAX_CACHED_TILES = 3000; // generous for a bounded city-scale map

self.addEventListener('install', () => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter((key) => key.startsWith('marketscope-tiles-') && key !== TILE_CACHE_NAME)
            .map((key) => caches.delete(key))
        )
      )
      .then(() => self.clients.claim())
  );
});

async function trimCache(cache, maxEntries) {
  const keys = await cache.keys();
  const excess = keys.length - maxEntries;
  if (excess <= 0) return;
  // Cache.keys() returns entries in insertion order, so the oldest additions
  // come first - a reasonable approximation of LRU without extra bookkeeping.
  for (let i = 0; i < excess; i++) {
    await cache.delete(keys[i]);
  }
}

self.addEventListener('fetch', (event) => {
  const { request } = event;
  if (request.method !== 'GET' || !TILE_HOST_PATTERN.test(request.url)) {
    return; // not a tile request - let the browser handle it normally
  }

  event.respondWith(
    caches.open(TILE_CACHE_NAME).then(async (cache) => {
      const cached = await cache.match(request);
      if (cached) return cached;

      const response = await fetch(request);
      if (response && response.ok) {
        cache.put(request, response.clone());
        event.waitUntil(trimCache(cache, MAX_CACHED_TILES));
      }
      return response;
    })
  );
});
