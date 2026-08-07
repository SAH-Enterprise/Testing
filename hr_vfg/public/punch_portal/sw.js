const CACHE = "punch-portal-v3";
const ASSETS = [
	"/punch_portal?v=3",
	"/assets/hr_vfg/punch_portal/punch_portal.css?v=3",
	"/assets/hr_vfg/punch_portal/punch_portal.js?v=3",
	"/assets/hr_vfg/punch_portal/manifest.webmanifest",
	"/assets/hr_vfg/punch_portal/icon.svg",
];

self.addEventListener("install", (event) => {
	event.waitUntil(
		caches
			.open(CACHE)
			.then((cache) => cache.addAll(ASSETS))
			.then(() => self.skipWaiting())
	);
});

self.addEventListener("activate", (event) => {
	event.waitUntil(
		caches
			.keys()
			.then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
			.then(() => self.clients.claim())
	);
});

self.addEventListener("fetch", (event) => {
	const url = new URL(event.request.url);
	// Always hit network for API and versioned JS/CSS so machine status stays fresh.
	if (
		url.pathname.startsWith("/api/") ||
		url.pathname.endsWith("punch_portal.js") ||
		url.pathname.endsWith("punch_portal.css") ||
		url.pathname === "/punch_portal"
	) {
		event.respondWith(
			fetch(event.request).catch(() => caches.match(event.request))
		);
		return;
	}
	event.respondWith(
		caches.match(event.request).then((cached) => cached || fetch(event.request))
	);
});
