// Service worker do CWD Leads.
// Guarda só a "casca" do app (tela, estilo, script e ícones) para abrir rápido
// e mostrar a tela mesmo sem internet. NUNCA guarda respostas da /api/: a
// política da Places API não permite guardar os dados do Google.

const VERSAO = "cwd-leads-v1";
const CASCA = [
  "/",
  "/estilo.css",
  "/app.js",
  "/manifest.webmanifest",
  "/cwd-logo.png",
  "/favicon.png",
  "/icone-192.png",
  "/google-maps-logo.svg",
];

self.addEventListener("install", (evento) => {
  evento.waitUntil(
    caches.open(VERSAO).then((cache) => cache.addAll(CASCA)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (evento) => {
  evento.waitUntil(
    caches
      .keys()
      .then((nomes) => Promise.all(nomes.filter((nome) => nome !== VERSAO).map((nome) => caches.delete(nome))))
      .then(() => self.clients.claim())
  );
});

// Rede primeiro (sempre a versão mais nova); sem internet, usa a casca guardada.
self.addEventListener("fetch", (evento) => {
  const url = new URL(evento.request.url);
  const naCasca = CASCA.includes(url.pathname);
  const ehPagina = evento.request.mode === "navigate";
  if (evento.request.method !== "GET" || url.origin !== location.origin) return;
  if (url.pathname.startsWith("/api/") || !(naCasca || ehPagina)) return;

  evento.respondWith(
    fetch(evento.request)
      .then((resposta) => {
        if (resposta.ok && naCasca) {
          const copia = resposta.clone();
          caches.open(VERSAO).then((cache) => cache.put(url.pathname, copia));
        }
        return resposta;
      })
      .catch(() => caches.match(ehPagina ? "/" : url.pathname))
  );
});
