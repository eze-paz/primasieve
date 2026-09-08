// Single source of truth for the Dropbox access token.
//
// Consumed by BOTH modules/dropbox.js (the app's sync provider) and
// /walios/terminal.html (which hands the token to walios/opfs-worker.js so the
// shell can list and hydrate cloud-only files). It had drifted: dropbox.js
// refreshed an expired token, terminal.html read `access_token` straight out of
// localStorage and never looked at `expires_at`. An access token lives ~4h, so
// the walios page was usually holding a dead one -- and opfs-worker hides every
// cloud-only file when it has no usable token, which is why a directory full of
// dehydrated files listed EMPTY.
//
// Plain classic script on purpose, like modules/walios-backend.js: the consumers
// include a classic Worker and a plain <script> tag, neither of which can
// `import`, so this assigns onto the global instead of exporting.

(function (g) {
  'use strict';

  const TOKENS_KEY = 'dbxfull-tokens';
  const SKEW_MS = 60000;          // refresh a minute early, as dropbox.js always has
  const TOKEN_URL = 'https://api.dropboxapi.com/oauth2/token';

  function read() {
    try { return JSON.parse(localStorage.getItem(TOKENS_KEY) || 'null'); } catch { return null; }
  }
  function write(t) {
    try { localStorage.setItem(TOKENS_KEY, JSON.stringify(t)); } catch {}
  }
  function fresh(t) {
    return !!(t && t.access_token && t.expires_at && Date.now() < t.expires_at - SKEW_MS);
  }

  // One refresh at a time: two callers (the app's sync and the walios page) can ask
  // at once, and a second POST would spend the refresh_token race for nothing.
  let inflight = null;

  // Returns a usable access token, refreshing when the stored one is stale.
  // THROWS when Dropbox is not connected or the refresh fails -- callers decide
  // whether that is fatal; the point is that nobody silently proceeds with a
  // dead token and reads the result as "no files".
  //
  // `fetchImpl` lets dropbox.js pass its own dbxFetch (throttling + 429 backoff);
  // anything else gets plain fetch, which is right for a single token call.
  async function accessToken({ fetchImpl } = {}) {
    const stored = read();
    if (!stored) throw new Error('Dropbox not connected');
    if (fresh(stored)) return stored.access_token;
    if (!stored.refresh_token || !stored.app_key) throw new Error('Dropbox token expired and cannot be refreshed (reconnect in sandpie)');
    if (inflight) return inflight;
    const f = fetchImpl || ((u, i) => fetch(u, i));
    inflight = (async () => {
      const body = new URLSearchParams({ grant_type: 'refresh_token', refresh_token: stored.refresh_token, client_id: stored.app_key });
      const res = await f(TOKEN_URL, {
        method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, body: body.toString(),
      });
      if (!res.ok) throw new Error('Token refresh failed: ' + await res.text());
      const data = await res.json();
      // Re-read: another tab may have rewritten the record while this was in flight.
      const cur = read() || stored;
      cur.access_token = data.access_token;
      cur.expires_at = Date.now() + data.expires_in * 1000;
      write(cur);
      return data.access_token;
    })();
    try { return await inflight; } finally { inflight = null; }
  }

  // Never throws: for callers that want to carry on without cloud files but must
  // still be able to SAY that is what happened.
  async function tryAccessToken(opts) {
    try { return { token: await accessToken(opts), error: null }; }
    catch (e) { return { token: null, error: (e && e.message) || String(e) }; }
  }

  // How long the current token has left, so a long-lived page can re-push before
  // it dies instead of waiting for the next failure.
  function msUntilStale() {
    const t = read();
    if (!t || !t.expires_at) return 0;
    return Math.max(0, t.expires_at - SKEW_MS - Date.now());
  }

  g.SandpieDbxToken = { TOKENS_KEY, read, fresh, accessToken, tryAccessToken, msUntilStale };
})(typeof self !== 'undefined' ? self : globalThis);
