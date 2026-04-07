const CACHE = 'brewhome-v4';

// Assets précachés à l'installation — garantis offline dès le premier chargement
const PRECACHE = [
  '/',
  '/manifest.json',
  '/static/favicon.png',
  '/static/favicon-32.png',
  '/static/icon-192.png',
  '/static/icon-512.png',
  '/static/js/chart.umd.min.js',
  // CSS
  '/static/fonts/fa/all.min.css',
  '/static/fonts/google/fonts.css',
  // FontAwesome webfonts
  '/static/fonts/fa/webfonts/fa-solid-900.woff2',
  '/static/fonts/fa/webfonts/fa-regular-400.woff2',
  '/static/fonts/fa/webfonts/fa-brands-400.woff2',
  '/static/fonts/fa/webfonts/fa-v4compatibility.woff2',
  // Google fonts (Inter + Montserrat)
  '/static/fonts/google/QGYsz_wNahGAdqQ43Rh_c6Dpp_k.woff2',
  '/static/fonts/google/QGYsz_wNahGAdqQ43Rh_cqDpp_k.woff2',
  '/static/fonts/google/QGYsz_wNahGAdqQ43Rh_fKDp.woff2',
  '/static/fonts/google/nuFiD-vYSZviVYUb_rj3ij__anPXDTLYgFE_.woff2',
  '/static/fonts/google/nuFiD-vYSZviVYUb_rj3ij__anPXDTPYgFE_.woff2',
  '/static/fonts/google/nuFiD-vYSZviVYUb_rj3ij__anPXDTjYgFE_.woff2',
  '/static/fonts/google/nuFiD-vYSZviVYUb_rj3ij__anPXDTzYgA.woff2',
];

self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE).then(c => c.addAll(PRECACHE)).catch(() => {})
  );
  self.skipWaiting();
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', e => {
  const url = e.request.url;
  // API — toujours réseau, jamais de cache
  if (url.includes('/api/')) return;
  if (e.request.method !== 'GET') return;

  if (e.request.destination === 'document') {
    // App shell : network-first → le cache sert de fallback offline
    e.respondWith(
      fetch(e.request)
        .then(resp => {
          if (resp && resp.status === 200) {
            caches.open(CACHE).then(c => c.put(e.request, resp.clone()));
          }
          return resp;
        })
        .catch(() => caches.match(e.request))
    );
    return;
  }

  // Assets statiques : cache-first, mise en cache dynamique si absent
  e.respondWith(
    caches.match(e.request).then(cached => {
      if (cached) return cached;
      return fetch(e.request).then(resp => {
        if (resp && resp.status === 200) {
          caches.open(CACHE).then(c => c.put(e.request, resp.clone()));
        }
        return resp;
      });
    })
  );
});
