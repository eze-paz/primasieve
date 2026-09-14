// Run the app's real Dropbox sync inside the standalone /walios/ page.
//
// walios writes into the SAME OPFS root the app syncs. When it is opened from the
// sandpie app the app's dropbox.js is already running and owns sync. Opened on its
// own, nothing did: files the shell wrote were marked dirty and then sat there until
// the user happened to open sandpie. This boots the actual sync engine here instead —
// modules/core.js (the Sandpie host), modules/opfs.js, modules/dropbox.js, unchanged
// and in the same order sandpie.html loads them. No second implementation of sync,
// which is the whole point: a copy would drift, and the drift is what broke this
// area twice already (the token, then the ledger).
//
// Exactly one syncer at a time, enforced with a Web Lock:
//   - the app takes 'sandpie-dbx-sync' with steal:true, so it ALWAYS wins;
//   - this page takes it with ifAvailable, so it only syncs when nobody else does,
//     and stands down the moment the app steals it.

(function () {
  'use strict';

  const LOCK = 'sandpie-dbx-sync';

  // Already inside the app (walios embedded in a sandpie tab): dropbox.js is live,
  // there is nothing to boot and two engines in one document would fight.
  if (window.Sandpie) return;
  if (!navigator.locks) { console.warn('[walios-sync] no Web Locks — not starting sync (cannot guarantee a single writer)'); return; }

  // core.js reaches for these when a sync finishes. In the app they redraw the file
  // list and the conversation list; there is no such UI here, so they are no-ops
  // rather than stubs that pretend to do something. (isGenerating and SandpieTokens
  // are already typeof-guarded in core.js, so they need nothing.)
  window.refreshFileList = window.refreshFileList || (() => {});
  window.refreshConversationList = window.refreshConversationList || (() => {});
  // core.js intercepts F5 / Ctrl-R to flush before a reload. Ctrl-R belongs to the
  // shell here (history search), so opt out of that interception.
  window.SANDPIE_NO_RELOAD_INTERCEPT = true;
  // We hold 'sandpie-dbx-sync' ourselves; dropbox.js must not steal it from us when
  // we are the ones booting it (it would look like the app taking over, and we would
  // stand down from our own engine).
  window.SANDPIE_SYNC_LOCK_HELD = true;

  const load = (src) => new Promise((res, rej) => {
    const s = document.createElement('script');
    s.src = src; s.async = false;          // preserve order: core.js needs opfs
    s.onload = () => res(src);
    s.onerror = () => rej(new Error('failed to load ' + src));
    document.head.appendChild(s);
  });

  async function boot() {
    // Same order as sandpie.html: opfs first (core.js's Sandpie.opfs getter reads
    // the `opfs` global), then the host, then the provider.
    await load('/modules/opfs.js?v=53');
    await load('/modules/core.js?v=13');
    await load('/modules/dropbox.js?v=88');
    const sp = window.Sandpie && window.Sandpie.syncProvider && window.Sandpie.syncProvider();
    if (!sp) throw new Error('dropbox.js did not register a sync provider');
    if (!sp.isConnected || !sp.isConnected()) {
      console.info('[walios-sync] Dropbox is not connected in this browser — nothing to sync');
      return;
    }
    console.info('[walios-sync] no sandpie app tab is open: this terminal runs Dropbox sync itself');
    try { await sp.sync(); } catch (e) { console.warn('[walios-sync] first sync failed:', (e && e.message) || e); }
  }

  // Hold the lock for as long as this page is the syncer. The promise never settles
  // on its own; it rejects (AbortError) if the app steals the lock, which is the
  // signal to stand down — the app is authoritative and is now doing the syncing.
  navigator.locks.request(LOCK, { ifAvailable: true }, async (lock) => {
    if (!lock) { console.info('[walios-sync] the sandpie app (or another tab) owns Dropbox sync, so this tab does not start a second engine. The terminal works normally; what the shell writes is synced by that tab.'); return; }
    await boot();
    await new Promise(() => {});
  }).catch((e) => {
    if (e && e.name === 'AbortError') { console.info('[walios-sync] the sandpie app took over Dropbox sync; the terminal keeps working, its writes are synced by the app.'); return; }
    console.warn('[walios-sync] not syncing:', (e && e.message) || e);
  });
})();
