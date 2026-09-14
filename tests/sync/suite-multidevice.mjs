// More than one device syncs the same Dropbox folder.
//
// This suite exists to constrain any "stop deleting local files" fix. Deletion
// is not gratuitous: it is how a delete made on one device reaches the others.
// A fix that keeps untracked local files must not turn a remote delete into a
// resurrection.
//
// "Another device" is modelled by mutating the cloud directly — which is
// literally what the other device's uploads and deletes do.
//
// Assertions use readable()/readBack(), so they hold both now (where a project
// file is mirrored into OPFS) and after the refactor (where it lives only in
// Dropbox). The ledger-specific variants live in suite-engine.mjs.
//
// ONE DELIBERATE EXCEPTION: sandpie/* asserts on the LOCAL copy, because
// memory.js and pins.js read OPFS synchronously while building a prompt. For
// that subtree "it is in Dropbox" is not good enough, and the refactor keeps it
// eagerly synced for exactly this reason.
import { connectedWorld } from './harness.mjs';

const CTX = { agentId: 'agent-1' };
const WS = '/sandpie/';

export async function run(t) {
  t.group('multi-device: deletes must propagate, not resurrect');

  // ── baseline: a delete on another device takes effect here ──
  {
    const w = await connectedWorld();
    await w.tools.tool_write_file({ path: 'artifacts/shared.html', content: 'v1' }, CTX);
    await w.sync();
    t.ok(w.readable('artifacts/shared.html') && w.cloudHas('artifacts/shared.html'), 'precondition: synced on both sides');

    w.cloudDel(WS + 'artifacts/shared.html');          // the other device deletes it
    await w.sync();
    t.ok(!w.readable('artifacts/shared.html'), 'a remote delete takes effect on this device', w.where('artifacts/shared.html'));
    t.ok(!w.cloudHas('artifacts/shared.html'), 'and our sync does not undo it');
  }

  // ── a remote delete stays deleted across a reload ──
  {
    let w = await connectedWorld();
    await w.tools.tool_write_file({ path: 'artifacts/stays-gone.html', content: 'obsolete' }, CTX);
    await w.sync();
    w.cloudDel(WS + 'artifacts/stays-gone.html');
    await w.sync();

    w = w.reload();
    w.seedTokens();
    await w.sync();
    t.ok(!w.readable('artifacts/stays-gone.html'),
      'a file deleted elsewhere does not come back after a reload', w.where('artifacts/stays-gone.html'));
  }

  // ── a remote delete must not beat a local unsynced edit ──
  {
    const w = await connectedWorld();
    await w.tools.tool_write_file({ path: 'artifacts/contested.html', content: 'v1' }, CTX);
    await w.sync();

    w.cloudDel(WS + 'artifacts/contested.html');        // other device deletes
    await w.tools.tool_edit_file({ path: 'artifacts/contested.html', old_str: 'v1', new_str: 'v2' }, CTX);  // we edit
    await w.sync();

    t.ok(w.readBack('artifacts/contested.html') === 'v2',
      'an edit made after a concurrent remote delete survives', w.where('artifacts/contested.html'));
    t.ok(w.cloudText('artifacts/contested.html') === 'v2',
      'and is pushed back up', w.cloudText('artifacts/contested.html'));
  }

  // ── a file created on another device is not deleted from the cloud by us ──
  {
    const w = await connectedWorld();
    w.cloudPut(WS + 'artifacts/from-other-device.html', 'made elsewhere');
    await w.sync();
    t.ok(w.readBack('artifacts/from-other-device.html') === 'made elsewhere',
      'a file created on another device is readable here', w.where('artifacts/from-other-device.html'));
    t.ok(w.cloudHas('artifacts/from-other-device.html'), 'and is left intact in Dropbox');
  }

  t.group('multi-device: edits made elsewhere');

  // App metadata (sandpie/*) is EXEMPT: eagerly synced both ways, because
  // memory.js and pins.js read it straight from OPFS on every prompt build. A
  // memory written on the laptop has to reach the phone's LOCAL copy — asserting
  // on the local copy here is deliberate, not an oversight.
  {
    const w = await connectedWorld({ cloud: { 'sandpie/memory/fact.md': 'original' } });
    await w.sync();
    t.ok(w.localText('sandpie/memory/fact.md') === 'original',
      'an exempt file is pulled into OPFS, where the prompt builder reads it', w.where('sandpie/memory/fact.md'));

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

  // A project file edited elsewhere: reading it here must give the NEW content,
  // never the superseded local bytes. How that happens differs by architecture
  // (today the stale copy is dropped and re-hydrated on demand; after the
  // refactor there is no local copy at all), so assert on the read.
  {
    const w = await connectedWorld();
    await w.tools.tool_write_file({ path: 'artifacts/doc.html', content: 'ours' }, CTX);
    await w.sync();
    t.ok(w.readBack('artifacts/doc.html') === 'ours', 'precondition: our version is what we read');

    w.cloudPut(WS + 'artifacts/doc.html', 'newer, from the other device');
    await w.sync();
    t.ok(w.readBack('artifacts/doc.html') === 'newer, from the other device',
      'reading a file edited elsewhere gives the newer content', w.where('artifacts/doc.html'));
  }

  // Concurrent edit. Ours is unsynced, theirs landed first. Dropbox is
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
  // only the folder, so the subtree has to be handled explicitly.
  {
    const w = await connectedWorld();
    for (const n of ['a', 'b', 'c']) await w.tools.tool_write_file({ path: `proj/sub/${n}.txt`, content: n }, CTX);
    await w.sync();
    t.ok(['a', 'b', 'c'].every((n) => w.readable(`proj/sub/${n}.txt`)), 'precondition: subtree synced');

    w.cloudDel(WS + 'proj/sub');
    await w.sync();
    const left = ['a', 'b', 'c'].filter((n) => w.readable(`proj/sub/${n}.txt`));
    t.ok(left.length === 0, 'a folder deleted elsewhere removes the whole subtree', left);
  }

  // A rename on another device arrives as delete + create.
  {
    const w = await connectedWorld();
    await w.tools.tool_write_file({ path: 'artifacts/before.html', content: 'renamed content' }, CTX);
    await w.sync();

    w.cloudDel(WS + 'artifacts/before.html');
    w.cloudPut(WS + 'artifacts/after.html', 'renamed content');
    await w.sync();

    t.ok(!w.readable('artifacts/before.html'), 'the old name is gone', w.where('artifacts/before.html'));
    t.ok(w.readBack('artifacts/after.html') === 'renamed content', 'the new name is readable', w.where('artifacts/after.html'));
    t.ok(!w.cloudHas('artifacts/before.html'), 'our sync does not recreate the old name');
  }

  // Our own uploads echo back through the cursor. They must not be mistaken for
  // another device's changes and must not cause redundant traffic.
  {
    const w = await connectedWorld();
    await w.tools.tool_write_file({ path: 'artifacts/echo.html', content: 'mine' }, CTX);
    await w.sync();
    const uploads1 = w.CALLS.filter((c) => c.url.includes('/upload')).length;
    await w.sync();
    await w.sync();
    const uploads2 = w.CALLS.filter((c) => c.url.includes('/upload')).length;
    t.ok(uploads1 === uploads2, 'repeated syncs do not re-upload an unchanged file', { uploads1, uploads2 });
    t.ok(w.readBack('artifacts/echo.html') === 'mine', 'content is stable across repeated syncs', w.readBack('artifacts/echo.html'));
  }
}
