// CURRENT SYNC-ENGINE INTERNALS — delete this file with the engine.
//
// Everything here asserts on machinery the full-Dropbox refactor removes: the
// dirty ledger, the dirty/clean state transitions, the pre-reload flush, and
// the "no state entry" bookkeeping. These are NOT contracts. They are here so
// that, while the engine still exists, a change to it is visible rather than
// silent — and so the other suites can stay free of implementation detail.
//
// When a step of the refactor deletes one of these mechanisms, delete its test
// with it. If an assertion here starts failing and you did NOT mean to change
// the engine, that is a real regression.
//
// The user-facing behaviour these mechanisms exist to deliver is asserted
// storage-neutrally in suite-session / suite-reload / suite-multidevice, and
// those must survive the refactor untouched.
import { connectedWorld } from './harness.mjs';

const CTX = { agentId: 'agent-1' };
const WS = '/sandpie/';

function loseLedger(w) {
  w.LSMAP.delete('dbxfull-sync-state');
  w.LSMAP.delete('dbxfull-cloud-index');
  w.LSMAP.delete('dbxfull-pending');
}

export async function run(t) {
  t.group('engine internals: the dirty ledger');

  // A tool write must reach the ledger through the sw-opfs-changed relay, or
  // nothing will ever upload it.
  {
    const w = await connectedWorld();
    await w.tools.tool_write_file({ path: 'artifacts/marked.html', content: 'x' }, CTX);
    const e = w.ledger()['artifacts/marked.html'];
    t.ok(!!e && e.syncedMtime === 0, 'a tool write lands in the ledger as dirty', e);
  }

  // A successful upload flips dirty -> clean, carrying the cloud rev.
  {
    const w = await connectedWorld();
    await w.tools.tool_write_file({ path: 'artifacts/clean.html', content: 'x' }, CTX);
    await w.sync();
    const e = w.ledger()['artifacts/clean.html'];
    t.ok(!!e && e.syncedMtime !== 0 && !!e.rev, 'an uploaded file is recorded clean with a rev', e);
  }

  // The dirty mark lives in localStorage, so it has to survive a reload or the
  // upload is lost with the page.
  {
    let w = await connectedWorld();
    await w.tools.tool_write_file({ path: 'artifacts/persist.html', content: 'x' }, CTX);
    w = w.reload();
    t.ok(!!w.ledger()['artifacts/persist.html'], 'the dirty mark survives a reload');
  }

  // The non-tool writers reach the same ledger by two different routes.
  {
    const w = await connectedWorld();
    w.FS.set('out/py.txt', 'p'); w.MT.set('out/py.txt', w.now);
    w.relay({ type: 'forward-to-page', payload: { type: 'sw-opfs-changed', paths: ['out/py.txt'] } });
    t.ok(!!w.ledger()['out/py.txt'], 'a python write is marked dirty via sw-opfs-changed');

    w.writeViaLedgerApi('work/sh.txt', 's');
    t.ok(!!w.ledger()['work/sh.txt'], 'a walios write is marked dirty via SandpieDbxSyncState.markDirty');
  }

  t.group('engine internals: pre-reload flush');

  {
    const w = await connectedWorld();
    await w.tools.tool_write_file({ path: 'artifacts/flushed.html', content: 'flush me' }, CTX);
    const r = await w.flushBeforeReload({ timeoutMs: 2000 });
    t.ok(r && r.ran !== false, 'flushBeforeReload runs when there is unsent work', r);
    t.ok(w.cloudText('artifacts/flushed.html') === 'flush me',
      'flushBeforeReload uploads dirty files before the refresh', w.cloudText('artifacts/flushed.html'));
  }

  // Nothing outstanding: the flush must not delay an ordinary refresh.
  {
    const w = await connectedWorld();
    await w.tools.tool_write_file({ path: 'artifacts/already.html', content: 'done' }, CTX);
    await w.sync();
    const r = await w.flushBeforeReload({ timeoutMs: 2000 });
    t.ok(r && r.ran === false, 'flushBeforeReload is a no-op when nothing is dirty', r);
  }

  t.group('engine internals: ledger loss');

  // Losing localStorage must not cause a mass re-upload. This is the regression
  // the comment in pushDirty warns about, and the reason "no state entry" is not
  // treated as dirty.
  {
    const w = await connectedWorld();
    for (let i = 0; i < 8; i++) await w.tools.tool_write_file({ path: `docs/f${i}.md`, content: 'body ' + i }, CTX);
    await w.sync();
    const before = w.CALLS.filter((c) => c.url.includes('/upload')).length;

    loseLedger(w);
    await w.sync();
    const after = w.CALLS.filter((c) => c.url.includes('/upload')).length;
    t.ok(after === before, 'a ledger loss does not re-upload files the cloud already has', { before, after });
  }

  // Ledger loss plus a delete made elsewhere: the file must not come back. This
  // is the assertion that ruled out "treat untracked local files as dirty".
  {
    const w = await connectedWorld();
    await w.tools.tool_write_file({ path: 'artifacts/elsewhere.html', content: 'obsolete' }, CTX);
    await w.sync();

    loseLedger(w);
    w.cloudDel(WS + 'artifacts/elsewhere.html');
    await w.sync();

    t.ok(!w.cloudHas('artifacts/elsewhere.html'),
      'a file deleted on another device is not resurrected after a ledger loss', w.where('artifacts/elsewhere.html'));
  }

  t.group('engine internals: dehydration');

  // A clean local copy whose cloud rev has moved on is dropped, so the next
  // open re-hydrates the new revision instead of serving stale bytes.
  {
    const w = await connectedWorld();
    await w.tools.tool_write_file({ path: 'artifacts/stale.html', content: 'ours' }, CTX);
    await w.sync();
    w.cloudPut(WS + 'artifacts/stale.html', 'theirs');
    await w.sync();
    t.ok(!w.localHas('artifacts/stale.html'), 'a superseded clean local copy is dropped', w.where('artifacts/stale.html'));
  }
}
