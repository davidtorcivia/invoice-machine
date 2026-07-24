// Deliberate no-op service worker. Do not delete.
//
// This app registers no service worker. The file exists so that any browser
// still holding a previously-registered worker fetches this one, takes control
// immediately, and caches nothing. Deleting it would make the browser's update
// check 404, which leaves the OLD worker active and serving stale assets
// indefinitely.
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', () => self.clients.claim());
