// More than one device syncs the same Dropbox folder.
//
// This suite exists to constrain any "stop deleting local files" fix. The
// cleanup passes are not gratuitous: they are how a delete made on one device
// reaches the others. A fix that keeps untracked local files must not turn a
// remote delete into a resurrection, and must not re-upload a whole workspace
// when localStorage is lost (the regression pushDirty's comment warns about).
//
// "Another device" is modelled by mutating the cloud directly — which is
// literally what the other device's uploads and deletes do.
import { connectedWorld } from './harness.mjs';

const CTX = { agentId: 'agent-1' };
const WS = '/sandpie/';

// localStorage is per-device and disposable: cleared site data, a new browser
// profile, a quota eviction. OPFS can easily outlive it.
function loseLedger(w) {
  w.LSMAP.delete('dbxfull-sync-state');
  w.LSMAP.delete('dbxfull-cloud-index');
  w.LSMAP.delete('dbxfull-pending');
}

export async function run(t) {
  t.group('multi-device: deletes must propagate, not resurrect');

  // ── baseline: a delete on another device removes the local copy here ──
  {
    const w = await connectedWorld();
    await w.tools.tool_write_file({ path: 'artifacts/shared.html', content: 'v1' }, CTX);
    await w.sync();
    t.ok(w.localHas('artifacts/shared.html') && w.cloudHas('artifacts/shared.html'), 'precondition: synced on both sides');

    w.cloudDel(WS + 'artifacts/shared.html');          // the other device deletes it
    await w.sync();
    t.ok(!w.localHas('artifacts/shared.html'), 'a remote delete removes the local copy', [...w.FS.keys()]);
    t.ok(!w.cloudHas('artifacts/shared.html'), 'the remote delete is not undone by our sync');
  }

  // ── THE CONSTRAINT: remote delete + lost ledger must not resurrect ──
  // This is the case that makes "never delete a file with no ledger entry"
  // wrong. After localStorage is lost every local file is untracked, so that
  // rule would re-upload files the other device deliberately deleted.
  {
    const w = await connectedWorld();
    await w.tools.tool_write_file({ path: 'artifacts/deleted-elsewhere.html', content: 'obsolete' }, CTX);
    await w.sync();

    loseLedger(w);                                      // this device forgets everything
    w.cloudDel(WS + 'artifacts/deleted-elsewhere.html'); // other device deletes it
    await w.sync();

    t.ok(!w.cloudHas('artifacts/deleted-elsewhere.html'),
      'a file deleted on another device is NOT resurrected after a ledger loss',
      { cloud: w.cloudHas('artifacts/deleted-elsewhere.html'), local: w.localHas('artifacts/deleted-elsewhere.html') });
  }

  // ── losing the ledger must not trigger a mass re-upload ──
  // Dropbox already holds the correct copies; re-uploading every local file
  // churns the account and can clobber newer remote revisions.
  {
    const w = await connectedWorld();
    for (let i = 0; i < 8; i++) await w.tools.tool_write_file({ path: `docs/f${i}.md`, content: 'body ' + i }, CTX);
    await w.sync();
    const uploadsBefore = w.CALLS.filter((c) => c.url.includes('/upload')).length;

    loseLedger(w);
    await w.sync();
    const uploadsAfter = w.CALLS.filter((c) => c.url.includes('/upload')).length;

    t.ok(uploadsAfter === uploadsBefore,
      'a ledger loss does not re-upload files the cloud already has',
      { before: uploadsBefore, after: uploadsAfter });
  }

  // ── a remote delete must not beat a local unsynced edit ──
  {
    const w = await connectedWorld();
    await w.tools.tool_write_file({ path: 'artifacts/contested.html', content: 'v1' }, CTX);
    await w.sync();

    w.cloudDel(WS + 'artifacts/contested.html');        // other device deletes
    await w.tools.tool_edit_file({ path: 'artifacts/contested.html', old_str: 'v1', new_str: 'v2' }, CTX);  // we edit
    await w.sync();

    t.ok(w.localHas('artifacts/contested.html'),
      'an unsynced local edit survives a concurrent remote delete', [...w.FS.keys()]);
    t.ok(w.cloudText('artifacts/contested.html') === 'v2',
      'the surviving local edit is pushed back up', w.cloudText('artifacts/contested.html'));
  }

  // ── a file created on another device is not deleted from the cloud by us ──
  {
    const w = await connectedWorld();
    w.cloudPut(WS + 'artifacts/from-other-device.html', 'made elsewhere');
    await w.sync();
    t.ok(w.cloudHas('artifacts/from-other-device.html'),
      'a cloud-only file from another device is left alone', [...w.CLOUD.keys()].filter((k) => k.includes('other-device')));
  }

  t.group('multi-device: edits made elsewhere');

  // App metadata (sandpie/*) is EXEMPT: eagerly synced both ways, because
  // memory.js and pins.js read it straight from OPFS on every prompt build. A
  // memory written on the laptop has to reach the phone's local copy.
  {
    const w = await connectedWorld({ cloud: { 'sandpie/memory/fact.md': 'original' } });
    await w.sync();
    t.ok(w.localText('sandpie/memory/fact.md') === 'original', 'exempt file is pulled local on first sync', w.localText('sandpie/memory/fact.md'));

    w.cloudPut(WS + 'sandpie/memory/fact.md', 'edited on the other device');
    await w.sync();
    t.ok(w.localText('sandpie/memory/fact.md') === 'edited on the other device',
      'a remote edit to an exempt file updates the local copy', w.localText('sandpie/memory/fact.md'));
  }

  // A remote delete of an exempt file removes it locally too, or memory/pins
  // would keep serving content the user deleted on another device.
  {
    const w = await connectedWorld({ cloud: { 'sandpie/memory/gone.md': 'delete me' } });
    await w.sync();
    t.ok(w.localHas('sandpie/memory/gone.md'), 'precondition: pulled local');
    w.cloudDel(WS + 'sandpie/memory/gone.md');
    await w.sync();
    t.ok(!w.localHas('sandpie/memory/gone.md'), 'a remote delete of an exempt file removes the local copy');
  }

  // Project files are dehydratable: a remote edit is NOT downloaded eagerly, but
  // the stale local copy must be dropped so the next open re-hydrates the new
  // revision instead of serving old bytes forever.
  {
    const w = await connectedWorld();
    await w.tools.tool_write_file({ path: 'artifacts/doc.html', content: 'ours' }, CTX);
    await w.sync();
    t.ok(w.localText('artifacts/doc.html') === 'ours', 'precondition: local copy present');

    w.cloudPut(WS + 'artifacts/doc.html', 'newer, from the other device');
    await w.sync();
    t.ok(w.localText('artifacts/doc.html') !== 'ours',
      'a stale local copy is not kept once the cloud revision moves on', w.localText('artifacts/doc.html'));
    t.ok(w.cloudText('artifacts/doc.html') === 'newer, from the other device',
      'the other device’s revision is left intact in Dropbox', w.cloudText('artifacts/doc.html'));
  }

  // Concurrent edit. Ours is unsynced (dirty), theirs landed first. Dropbox is
  // last-write-wins; what must never happen is a merged or truncated file.
  {
    const w = await connectedWorld();
    await w.tools.tool_write_file({ path: 'artifacts/both.html', content: 'base' }, CTX);
    await w.sync();

    w.cloudPut(WS + 'artifacts/both.html', 'their version');
    await w.tools.tool_edit_file({ path: 'artifacts/both.html', old_str: 'base', new_str: 'our version' }, CTX);
    await w.sync();

    const cloud = w.cloudText('artifacts/both.html');
    t.ok(cloud === 'our version' || cloud === 'their version',
      'a concurrent edit resolves to one whole version, never a merge', cloud);
  }

  // A folder deleted elsewhere takes its descendants with it. Dropbox reports
  // only the folder, so the subtree has to be inferred locally.
  {
    const w = await connectedWorld();
    for (const n of ['a', 'b', 'c']) await w.tools.tool_write_file({ path: `proj/sub/${n}.txt`, content: n }, CTX);
    await w.sync();
    t.ok(['a', 'b', 'c'].every((n) => w.localHas(`proj/sub/${n}.txt`)), 'precondition: subtree synced');

    w.cloudDel(WS + 'proj/sub');
    await w.sync();
    const left = ['a', 'b', 'c'].filter((n) => w.localHas(`proj/sub/${n}.txt`));
    t.ok(left.length === 0, 'a folder deleted elsewhere removes the whole local subtree', left);
  }

  // A rename on another device arrives as delete + create.
  {
    const w = await connectedWorld();
    await w.tools.tool_write_file({ path: 'artifacts/before.html', content: 'renamed content' }, CTX);
    await w.sync();

    w.cloudDel(WS + 'artifacts/before.html');
    w.cloudPut(WS + 'artifacts/after.html', 'renamed content');
    await w.sync();

    t.ok(!w.localHas('artifacts/before.html'), 'the old name is gone locally');
    t.ok(w.cloudHas('artifacts/after.html'), 'the new name survives in Dropbox');
    t.ok(!w.cloudHas('artifacts/before.html'), 'our sync does not recreate the old name');
  }

  // Our own uploads echo back through the cursor. They must not be mistaken for
  // another device's changes and must not be re-downloaded or re-uploaded.
  {
    const w = await connectedWorld();
    await w.tools.tool_write_file({ path: 'artifacts/echo.html', content: 'mine' }, CTX);
    await w.sync();
    const uploads1 = w.CALLS.filter((c) => c.url.includes('/upload')).length;
    await w.sync();
    await w.sync();
    const uploads2 = w.CALLS.filter((c) => c.url.includes('/upload')).length;
    t.ok(uploads1 === uploads2, 'repeated syncs do not re-upload an unchanged file', { uploads1, uploads2 });
    t.ok(w.cloudText('artifacts/echo.html') === 'mine', 'content is stable across repeated syncs', w.cloudText('artifacts/echo.html'));
  }
}
