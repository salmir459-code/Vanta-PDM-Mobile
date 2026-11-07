// Vanta PDM Mobil – Service Worker
// Hält die App-Dateien vor, damit sie schnell und auch ohne Netz startet.
// Google-Anmeldung und Drive gehen immer direkt ins Netz.
const STAND = "vanta-2026-11-07-stueckliste";
const DATEIEN = ["./", "index.html", "config.js", "manifest.webmanifest",
  "icon-192.png", "icon-512.png", "icon-maskable-192.png",
  "icon-maskable-512.png", "apple-touch-icon.png", "favicon-32.png"];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(STAND).then(c => c.addAll(DATEIEN)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== STAND).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});
self.addEventListener("fetch", e => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin) return;   // Google: nie anfassen
  const seite = e.request.mode === "navigate" || url.pathname.endsWith("/index.html") || url.pathname.endsWith("/config.js");
  if (seite) {
    // Netz zuerst, damit Updates sofort ankommen; ohne Netz der gespeicherte Stand
    e.respondWith(fetch(e.request).then(r => {
      const kopie = r.clone(); caches.open(STAND).then(c => c.put(e.request, kopie)); return r;
    }).catch(() => caches.match(e.request).then(r => r || caches.match("index.html"))));
  } else {
    e.respondWith(caches.match(e.request).then(r => r || fetch(e.request)));
  }
});
