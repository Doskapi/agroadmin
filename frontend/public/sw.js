// Service worker: guarda la "cáscara" de la app (HTML, JS, CSS, íconos) para que abra rápido y se pueda
// instalar en el celular. NUNCA guarda respuestas de /api: los datos siempre vienen del servidor.
const CACHE = "agro-v1";
const BASE = ["/", "/manifest.webmanifest", "/icons/icon-192.png"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(BASE)));
  self.skipWaiting();
});

self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k)))));
  self.clients.claim();
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin || url.pathname.startsWith("/api/")) return;

  if (e.request.mode === "navigate") {
    // Primero la red (para tener siempre la última versión); sin conexión, la copia guardada
    e.respondWith(
      fetch(e.request)
        .then((r) => {
          const copia = r.clone();
          caches.open(CACHE).then((c) => c.put("/", copia));
          return r;
        })
        .catch(() => caches.match("/")),
    );
    return;
  }

  if (url.pathname.startsWith("/assets/") || url.pathname.startsWith("/icons/")) {
    // Los archivos de /assets llevan un hash en el nombre: si está guardado, es el correcto
    e.respondWith(
      caches.match(e.request).then((guardado) =>
        guardado || fetch(e.request).then((r) => {
          const copia = r.clone();
          caches.open(CACHE).then((c) => c.put(e.request, copia));
          return r;
        })),
    );
  }
});
