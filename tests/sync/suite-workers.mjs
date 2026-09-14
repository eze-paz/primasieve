// Writers that are NOT the file tools: run_python (pyodide) and walios.
//
// Both write into the same OPFS the sync engine owns, and each announces itself
// through a DIFFERENT channel. That divergence is the root of the "a whole git
// clone got deleted" class of bug documented at the top of dbx-syncstate.js, so
// each channel gets its own test.
//
//   pyodide-worker.js : forward-to-page -> sw-opfs-changed  (no owner stamp)
//                       forward-to-page -> opfs-deleted-by-python
//                       forward-to-page -> worker-hydrated   (a download: clean)
//   walios bridge     : _waliosWireOpfs -> sw-opfs-changed  (owner stamped)
//                       and, for the standalone /walios page,
//                       SandpieDbxSyncState.markDirty() directly
import { connectedWorld, settleDeletes } from './harness.mjs';

const tick = () => new Promise((r) => setTimeout(r, 5));

export async function run(t) {
  t.group('pyodide (run_python) writes');

  // run_python writes a file, then posts the batch of written paths.
  {
    const w = await connectedWorld();
    w.FS.set('out/plot.png', 'PNGDATA');
    w.MT.set('out/plot.png', w.now);
    w.relay({ type: 'forward-to-page', payload: { type: 'sw-opfs-changed', paths: ['out/plot.png'] } });
    t.ok(!!w.ledger()['out/plot.png'], 'python write is marked dirty via sw-opfs-changed');
    await w.sync();
    t.ok(w.cloudText('out/plot.png') === 'PNGDATA', 'python-written file reaches Dropbox', w.cloudText('out/plot.png'));
  }

  // A batch write (several paths in one message) — the real shape at
  // pyodide-worker.js writtenPaths.
  {
    const w = await connectedWorld();
    const paths = ['out/a.csv', 'out/b.csv', 'out/nested/c.csv'];
    for (const p of paths) { w.FS.set(p, 'data:' + p); w.MT.set(p, w.now); }
    w.relay({ type: 'forward-to-page', payload: { type: 'sw-opfs-changed', paths } });
    await w.sync();
    const missing = paths.filter((p) => w.cloudText(p) !== 'data:' + p);
    t.ok(missing.length === 0, 'a batch of python writes all reach Dropbox', missing);
  }

  // os.remove inside python -> opfs-deleted-by-python -> cloud delete.
  {
    const w = await connectedWorld({ cloud: { 'out/old.csv': 'stale' }, files: { 'out/old.csv': 'stale' } });
    await w.sync();
    t.ok(w.cloudHas('out/old.csv'), 'precondition: present in cloud');
    w.FS.delete('out/old.csv');
    w.relay({ type: 'forward-to-page', payload: { type: 'opfs-deleted-by-python', paths: ['out/old.csv'] } });
    await settleDeletes(w);
    t.ok(!w.cloudHas('out/old.csv'), 'python deletion propagates to Dropbox');
  }

  // A python write that never announces itself is an orphan today.
  {
    const w = await connectedWorld();
    w.writeUnmarked('out/silent.txt', 'written but unannounced');
    await w.sync();
    t.known(w.localHas('out/silent.txt') || w.cloudHas('out/silent.txt'),
      'an unannounced python write survives a sync',
      'current behaviour: deleted as an orphan by Pass 2.');
  }

  t.group('walios writes');

  // The in-app walios bridge stamps an owner and posts the same message.
  {
    const w = await connectedWorld();
    w.FS.set('work/build.log', 'compiled ok');
    w.MT.set('work/build.log', w.now);
    w.relay({ type: 'forward-to-page', payload: { type: 'sw-opfs-changed', paths: ['work/build.log'], owner: 'agent-9' } });
    t.ok(!!w.ledger()['work/build.log'], 'walios bridge write is marked dirty');
    await w.sync();
    t.ok(w.cloudText('work/build.log') === 'compiled ok', 'walios-written file reaches Dropbox', w.cloudText('work/build.log'));
  }

  // The standalone /walios page marks through the shared ledger module.
  {
    const w = await connectedWorld();
    w.writeViaLedgerApi('work/notes.md', 'from the terminal');
    t.ok(!!w.ledger()['work/notes.md'], 'SandpieDbxSyncState.markDirty records the write');
    await w.sync();
    t.ok(w.cloudText('work/notes.md') === 'from the terminal',
      'a file marked through the shared ledger uploads', w.cloudText('work/notes.md'));
  }

  // Many files at once — the `git clone` shape from the dbx-syncstate.js header.
  {
    const w = await connectedWorld();
    const paths = [];
    for (let i = 0; i < 25; i++) paths.push('repo/src/file' + i + '.js');
    for (const p of paths) w.writeViaLedgerApi(p, '// ' + p);
    await w.sync();
    const gone = paths.filter((p) => !w.localHas(p));
    const unsent = paths.filter((p) => !w.cloudHas(p));
    t.ok(gone.length === 0, 'a 25-file clone is not deleted locally', gone.slice(0, 5));
    t.ok(unsent.length === 0, 'a 25-file clone is fully uploaded', unsent.slice(0, 5));
  }

  // Unmarked walios writes: the original bug, still reproducible.
  {
    const w = await connectedWorld();
    for (let i = 0; i < 5; i++) w.writeUnmarked('repo2/f' + i + '.js', 'x');
    await w.sync();
    const survived = [0, 1, 2, 3, 4].filter((i) => w.localHas('repo2/f' + i + '.js'));
    t.known(survived.length === 5,
      'unmarked shell writes survive a sync',
      'current behaviour: all 5 deleted as orphans — the documented walios bug.');
  }

  t.group('hydration must not be mistaken for a local edit');

  // worker-hydrated = "this came FROM the cloud". It must not be re-uploaded,
  // and must not be deleted either.
  {
    const w = await connectedWorld({ cloud: { 'docs/manual.md': 'cloud copy' } });
    await w.sync();
    w.FS.set('docs/manual.md', 'cloud copy');
    w.MT.set('docs/manual.md', w.now);
    w.relay({ type: 'forward-to-page', payload: { type: 'worker-hydrated', paths: ['docs/manual.md'] } });
    await tick();
    const before = w.CALLS.filter((c) => c.url.includes('/upload')).length;
    await w.sync();
    const after = w.CALLS.filter((c) => c.url.includes('/upload')).length;
    t.ok(after === before, 'a hydrated file is not re-uploaded', { before, after });
    t.ok(w.localHas('docs/manual.md'), 'a hydrated file is not deleted');
  }
}
