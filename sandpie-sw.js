// sandpie-sw.js — Service Worker for sandpie-sw.html.
//
// Owns the upstream LLM fetch + buffered SSE drain so the page can survive
// being frozen by Chrome's energy-saver tab freezing (Chrome 133+, kicks in
// ~5 min hidden + silent). While the page is frozen, the SW is NOT — as
// long as a fetch handler is in flight, the SW stays alive and keeps
// pulling bytes into an internal ReadableStream queue. When the page
// unfreezes, its reader picks up the buffered chunks and catches up.
//
// Wire diagram:
//   page  ──fetch("./sandpie-stream", {body:{url,headers,body}})──>  SW
//                                                                     │
//   page  <──Response(ReadableStream)──────────────────────────────── SW
//                                                                     │
//                                       SW eagerly drains upstream ───┘
//                                       into the stream's queue,
//                                       decoupling consumer pace
//                                       from producer pace.
//
// Lifecycle:
//   - skipWaiting on install + clients.claim on activate so an updated
//     SW takes over the page on next reload without a stale-tab dance.
//   - All other fetches fall through to the network (no caching, no
//     interception).

const STREAM_PATHS = new Set(['/sandpie-stream', '/public/sdk/sandpie-stream']);

self.addEventListener('install', () => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);
  // Match by pathname suffix so the SW works whether scoped at root
  // (`/sandpie-stream`) or under `/public/sdk/` (`/public/sdk/sandpie-stream`).
  // Anything else passes through to the network unchanged.
  if (!url.pathname.endsWith('/sandpie-stream')) return;
  event.respondWith(proxyStream(event.request));
});

async function proxyStream(req) {
  let payload;
  try {
    payload = await req.json();
  } catch (e) {
    return new Response('sandpie-sw: bad request body (' + e.message + ')', {
      status: 400,
      headers: { 'Content-Type': 'text/plain' },
    });
  }
  const { url, headers, body } = payload || {};
  if (!url) {
    return new Response('sandpie-sw: missing "url" in request body', {
      status: 400,
      headers: { 'Content-Type': 'text/plain' },
    });
  }

  // Open the upstream stream. AbortController lets us cancel upstream
  // when the page reader is cancelled (page navigated away, user hit
  // Stop, etc.).
  const upstreamCtl = new AbortController();
  let upstreamRes;
  try {
    upstreamRes = await fetch(url, {
      method: 'POST',
      headers: headers || { 'Content-Type': 'application/json' },
      body: typeof body === 'string' ? body : JSON.stringify(body || {}),
      signal: upstreamCtl.signal,
    });
  } catch (e) {
    return new Response('sandpie-sw: upstream fetch failed: ' + (e && e.message || e), {
      status: 502,
      headers: { 'Content-Type': 'text/plain' },
    });
  }

  if (!upstreamRes.ok) {
    // Forward the upstream error verbatim so the page sees the same
    // status + body it would have without the SW in the middle.
    const text = await upstreamRes.text().catch(() => '');
    return new Response(text, {
      status: upstreamRes.status,
      headers: { 'Content-Type': upstreamRes.headers.get('Content-Type') || 'text/plain' },
    });
  }

  const upstreamReader = upstreamRes.body.getReader();

  // Decouple producer from consumer: we eagerly drain upstream into the
  // controller's queue regardless of whether the page is currently
  // reading. That way a frozen page tab doesn't apply TCP backpressure
  // upstream — bytes keep flowing and the LLM finishes its work even if
  // the user has been on another tab for a minute.
  const stream = new ReadableStream({
    start(controller) {
      (async () => {
        try {
          while (true) {
            const { done, value } = await upstreamReader.read();
            if (done) { controller.close(); break; }
            controller.enqueue(value);
          }
        } catch (e) {
          // Surface upstream errors to the page reader.
          try { controller.error(e); } catch (_) {}
        }
      })();
    },
    cancel() {
      // Page closed its reader (Stop button, navigation, etc.) — cancel
      // upstream so we don't keep its slot occupied on the LLM side.
      try { upstreamCtl.abort(); } catch (_) {}
      try { upstreamReader.cancel(); } catch (_) {}
    },
  });

  return new Response(stream, {
    status: 200,
    headers: {
      'Content-Type': upstreamRes.headers.get('Content-Type') || 'text/event-stream',
      'Cache-Control': 'no-store',
    },
  });
}
