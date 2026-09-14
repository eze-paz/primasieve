// What happens to files across a page reload.
//
// world.reload() rebuilds every module over the SAME OPFS, localStorage and
// cloud — exactly what an F5 does. The invariant under test is simple and must
// hold before and after the refactor:
//
//   a file the model created is never silently lost by reloading.
import { connectedWorld } from './harness.mjs';

const tick = () => new Promise((r) => setTimeout(r, 5));
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
    t.ok(w.cloudText('artifacts/keep.html') === 'durable', 'synced file still in Dropbox after reload', w.cloudText('artifacts/keep.html'));
    t.ok(w.localText('artifacts/keep.html') === 'durable', 'synced file still local after reload', w.localText('artifacts/keep.html'));
  }

  // ── the risky case: written but NEVER synced before the reload ──
  {
    let w = await connectedWorld();
    await w.tools.tool_write_file({ path: 'artifacts/unsynced.html', content: 'not yet pushed' }, CTX);
    t.ok(!w.cloudHas('artifacts/unsynced.html'), 'precondition: not uploaded yet');
    t.ok(w.ledger()['artifacts/unsynced.html'], 'precondition: marked dirty in the ledger');

    w = w.reload();
    w.seedTokens();
    t.ok(w.localHas('artifacts/unsynced.html'), 'unsynced file survives the reload locally');
    t.ok(!!w.ledger()['artifacts/unsynced.html'], 'dirty mark survives the reload (localStorage)');

    await w.sync();
    t.ok(w.cloudText('artifacts/unsynced.html') === 'not yet pushed',
      'first sync after reload uploads the unsynced file', w.cloudText('artifacts/unsynced.html'));
  }

  // ── pre-reload flush pushes outstanding work ──
  {
    const w = await connectedWorld();
    await w.tools.tool_write_file({ path: 'artifacts/flushed.html', content: 'flush me' }, CTX);
    await w.flushBeforeReload({ timeoutMs: 2000 });
    await tick();
    t.ok(w.cloudText('artifacts/flushed.html') === 'flush me',
      'flushBeforeReload uploads dirty files before the refresh', w.cloudText('artifacts/flushed.html'));
  }

  // ── THE DATA-LOSS CASE: the dirty mark never landed ──
  // Reproduces the artifacts/ disappearance: a tool wrote the file, the
  // sw-opfs-changed relay did not reach dropbox.js, so the ledger has no entry.
  // Pass 2 then treats the file as an orphan ("in OPFS, not in cloud, no
  // record") and deletes it — the model's work is gone with no trace.
  {
    let w = await connectedWorld();
    w.relayBroken = true;
    await w.tools.tool_write_file({ path: 'artifacts/lost.html', content: 'precious work' }, CTX);
    w.relayBroken = false;
    t.ok(w.localHas('artifacts/lost.html'), 'precondition: file written to OPFS');
    t.ok(!w.ledger()['artifacts/lost.html'], 'precondition: no ledger entry (relay dropped)');

    w = w.reload();
    w.seedTokens();
    await w.sync();

    t.known(w.localHas('artifacts/lost.html') || w.cloudHas('artifacts/lost.html'),
      'a written file with no dirty mark is NOT destroyed by sync',
      'current behaviour: Pass 2 deletes it as an orphan. The refactor must make an\n          '
      + 'untracked local file an upload candidate, never a deletion candidate.');
  }

  // ── a file the cloud legitimately lost should still not vanish if dirty ──
  {
    let w = await connectedWorld();
    await w.tools.tool_write_file({ path: 'artifacts/dirty.html', content: 'v1' }, CTX);
    await w.sync();
    // another device deletes it; locally we have newer unsynced edits
    w.cloudDel('/sandpie/artifacts/dirty.html');
    await w.tools.tool_edit_file({ path: 'artifacts/dirty.html', old_str: 'v1', new_str: 'v2' }, CTX);

    w = w.reload();
    w.seedTokens();
    await w.sync();
    t.ok(w.localHas('artifacts/dirty.html'),
      'locally-edited file is kept even when the cloud copy is gone', [...w.FS.keys()]);
  }

  // ── repeated reloads must be idempotent ──
  {
    let w = await connectedWorld();
    await w.tools.tool_write_file({ path: 'artifacts/stable.html', content: 'same' }, CTX);
    await w.sync();
    for (let i = 0; i < 3; i++) { w = w.reload(); w.seedTokens(); await w.sync(); }
    t.ok(w.localText('artifacts/stable.html') === 'same' && w.cloudText('artifacts/stable.html') === 'same',
      'three reload+sync cycles leave the file untouched', [w.localText('artifacts/stable.html'), w.cloudText('artifacts/stable.html')]);
  }
}
