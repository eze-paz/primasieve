// What happens to files across a page reload.
//
// world.reload() rebuilds every module over the SAME OPFS, localStorage and
// cloud — exactly what an F5 does. The invariant under test is simple and must
// hold before and after the full-Dropbox refactor:
//
//   a file the model created is never silently lost by reloading.
//
// Assertions use readBack()/readable(), never localHas(), because after the
// refactor a project file lives only in Dropbox and having no local copy is
// correct rather than a failure. The ledger mechanics that currently deliver
// this are asserted in suite-engine.mjs, which dies with the engine.
import { connectedWorld } from './harness.mjs';

const CTX = { agentId: 'agent-1' };

export async function run(t) {
  t.group('reload: survival of written files');

  // ── clean case: written, synced, then reloaded ──
  {
    let w = await connectedWorld();
    await w.tools.tool_write_file({ path: 'artifacts/keep.html', content: 'durable' }, CTX);
    await w.sync();

    w = w.reload();
    w.seedTokens();
    await w.sync();
    t.ok(w.readBack('artifacts/keep.html') === 'durable',
      'a file written before a reload is still readable after it', w.where('artifacts/keep.html'));
    t.ok(w.cloudText('artifacts/keep.html') === 'durable',
      'and it is in Dropbox, not only on this device', w.cloudText('artifacts/keep.html'));
  }

  // ── the risky case: the reload happens right after the write ──
  // Today the upload has not run yet and the file is carried across the reload
  // by OPFS plus the dirty ledger. After the refactor it is already in Dropbox
  // before the reload. Either way the work must come back.
  {
    let w = await connectedWorld();
    await w.tools.tool_write_file({ path: 'artifacts/unsynced.html', content: 'not yet pushed' }, CTX);

    w = w.reload();
    w.seedTokens();
    t.ok(w.readBack('artifacts/unsynced.html') === 'not yet pushed',
      'work written immediately before a reload survives it', w.where('artifacts/unsynced.html'));

    await w.sync();
    t.ok(w.cloudText('artifacts/unsynced.html') === 'not yet pushed',
      'and reaches Dropbox once the app is running again', w.cloudText('artifacts/unsynced.html'));
  }

  // ── THE DATA-LOSS CASE: the dirty mark never landed ──
  // Reproduces the artifacts/ disappearance: a tool wrote the file, the
  // sw-opfs-changed relay did not reach dropbox.js, so the ledger has no entry.
  // Pass 2 then treats the file as an orphan ("in OPFS, not in cloud, no
  // record") and deletes it — the model's work is gone with no trace.
  //
  // The refactor removes the premise: a Zone B write IS the upload, so there is
  // no window in which a file exists only locally and unrecorded.
  {
    let w = await connectedWorld();
    w.relayBroken = true;
    await w.tools.tool_write_file({ path: 'artifacts/lost.html', content: 'precious work' }, CTX);
    w.relayBroken = false;
    t.ok(w.readable('artifacts/lost.html'), 'precondition: the tool reported success and the bytes exist');

    w = w.reload();
    w.seedTokens();
    await w.sync();

    t.known(w.readBack('artifacts/lost.html') === 'precious work',
      'a written file is never destroyed by a later sync',
      'current behaviour: with no ledger entry, cleanup Pass 2 deletes it as an orphan.');
  }

  // ── a file the cloud lost must not take our newer edit with it ──
  {
    let w = await connectedWorld();
    await w.tools.tool_write_file({ path: 'artifacts/dirty.html', content: 'v1' }, CTX);
    await w.sync();
    w.cloudDel('/sandpie/artifacts/dirty.html');     // another device deletes it
    await w.tools.tool_edit_file({ path: 'artifacts/dirty.html', old_str: 'v1', new_str: 'v2' }, CTX);

    w = w.reload();
    w.seedTokens();
    await w.sync();
    t.ok(w.readBack('artifacts/dirty.html') === 'v2',
      'an edit made after a remote delete is still readable', w.where('artifacts/dirty.html'));
  }

  // ── repeated reloads must be idempotent ──
  {
    let w = await connectedWorld();
    await w.tools.tool_write_file({ path: 'artifacts/stable.html', content: 'same' }, CTX);
    await w.sync();
    for (let i = 0; i < 3; i++) { w = w.reload(); w.seedTokens(); await w.sync(); }
    t.ok(w.readBack('artifacts/stable.html') === 'same' && w.cloudText('artifacts/stable.html') === 'same',
      'three reload cycles leave the file untouched', [w.readBack('artifacts/stable.html'), w.cloudText('artifacts/stable.html')]);
  }
}
