// Reading a file that is in Dropbox but NOT in OPFS.
//
// This is the gate for refactor step 2. Reads used to consult the cloud index:
// a snapshot that is empty on a cold boot, stale after another device wrote,
// and blind to anything added outside the app. A miss in it read as "the file
// does not exist" even when Dropbox was holding the file. Reads now ask
// Dropbox, so the only question that matters is whether the bytes come back.
//
// The contract survives the rest of the refactor unchanged: after step 4 there
// is no local mirror at all, and every one of these reads is a cold read.
import { connectedWorld } from './harness.mjs';

const CTX = { agentId: 'agent-1' };

export async function run(t) {
  t.group('cold reads: the file is only in Dropbox');

  // ── hydrateAsync is the miss hook every reader funnels through ──
  {
    const w = await connectedWorld({ cloud: { 'docs/cold.md': '# only in the cloud' } });
    t.ok(!w.localHas('docs/cold.md'), 'precondition: not in OPFS');

    const got = await w.tools.hydrateAsync('docs/cold.md');
    t.ok(got === true, 'hydrateAsync reports success for a cloud-only file', got);
    t.ok(w.localText('docs/cold.md') === '# only in the cloud',
      'and the bytes land in OPFS', w.localText('docs/cold.md'));
  }

  // ── a file in neither place is simply absent ──
  {
    const w = await connectedWorld();
    const got = await w.tools.hydrateAsync('docs/nowhere.md');
    t.ok(got === false, 'hydrateAsync reports absence without throwing', got);
  }

  // ── a transport failure must NOT be read as absence ──
  // This is the distinction the index could never make: "not in my snapshot"
  // and "Dropbox is unreachable" looked identical, and both meant "gone".
  // Absence is a 409; anything else has to surface as an error.
  {
    const w = await connectedWorld({ cloud: { 'docs/flaky.md': 'present' } });
    w.failOnce('get_temporary_link', 500);
    let threw = false;
    try { await w.tools.hydrateAsync('docs/flaky.md'); } catch (_) { threw = true; }
    t.ok(threw, 'a 5xx surfaces as an error rather than a silent "not found"');

    // and the next attempt succeeds, so the failure is not sticky
    const got = await w.tools.hydrateAsync('docs/flaky.md');
    t.ok(got === true, 'a retry after the transient failure succeeds', got);
  }

  // ── read_file on a cloud-only file ──
  {
    const w = await connectedWorld({ cloud: { 'notes/remote.md': 'written on the laptop' } });
    const r = await w.tools.tool_read_file({ path: 'notes/remote.md' }, CTX);
    t.ok(/written on the laptop/.test(r.result),
      'read_file returns the content of a file it only has in Dropbox', r.result);
  }

  // ── read_file on a file that truly does not exist ──
  {
    const w = await connectedWorld();
    const r = await w.tools.tool_read_file({ path: 'notes/ghost.md' }, CTX);
    t.ok(/not found/i.test(r.result), 'read_file says not found when it really is not there', r.result);
  }

  // ── edit_file on a cloud-only file ──
  // The model edits something a previous session wrote from another device.
  {
    const w = await connectedWorld({ cloud: { 'notes/edit-me.md': 'version one' } });
    const r = await w.tools.tool_edit_file({ path: 'notes/edit-me.md', old_str: 'one', new_str: 'two' }, CTX);
    t.ok(!/not found|Error/i.test(r.result), 'edit_file can edit a cloud-only file', r.result);
    t.ok(w.readBack('notes/edit-me.md') === 'version two', 'the edit applies to the fetched content', w.readBack('notes/edit-me.md'));
  }

  // ── sandpie/* is not fetched on demand ──
  // App metadata is eagerly synced by the page, so a miss there is a real miss.
  // Faulting it in on demand would race the engine that owns that subtree.
  {
    const w = await connectedWorld({ cloud: { 'sandpie/memory/x.md': 'engine-owned' } });
    w.FS.delete('sandpie/memory/x.md');
    const got = await w.tools.hydrateAsync('sandpie/memory/x.md');
    t.ok(got === false, 'hydrateAsync declines engine-owned paths', got);
  }

  t.group('cold listings');

  // ── a cloud-only file shows up in a listing ──
  {
    const w = await connectedWorld({ cloud: { 'proj/a.txt': '1', 'proj/b.txt': '2' } });
    const rows = await w.tools._cloudEntriesUnder('proj', false);
    const names = rows.map((r) => r.path).sort();
    t.ok(names.includes('proj/a.txt') && names.includes('proj/b.txt'),
      'a listing reports files that exist only in Dropbox', names);
  }

  // ── engine-owned paths stay out of the listing ──
  {
    const w = await connectedWorld({ cloud: { 'sandpie/memory/m.md': 'x', 'proj/keep.txt': 'y' } });
    const rows = await w.tools._cloudEntriesUnder('', true);
    const paths = rows.map((r) => r.path);
    t.ok(!paths.some((p) => p.startsWith('sandpie/')), 'engine-owned paths are excluded', paths);
  }

  // ── the listing is not a stale snapshot ──
  // The whole point of step 2. Under the old index a folder the app had never
  // seen simply did not exist; now the first listing of it goes to Dropbox.
  // (The 15s cache window itself is not asserted: it reads the real Date.now(),
  // which the world clock cannot travel. Its invalidation-on-write is covered
  // by the next case, which is the part that could actually hide a file.)
  {
    const w = await connectedWorld({ cloud: { 'proj/first.txt': '1' } });
    await w.tools._cloudEntriesUnder('proj', false);          // this folder is now cached
    w.cloudPut('/sandpie/other/added-elsewhere.txt', '2');    // another device writes
    const rows = await w.tools._cloudEntriesUnder('other', false);
    t.ok(rows.some((r) => r.path === 'other/added-elsewhere.txt'),
      'a folder the app has never seen is listed straight from Dropbox', rows.map((r) => r.path));
  }

  // ── an upload invalidates the listing cache immediately ──
  {
    const w = await connectedWorld({ cloud: { 'proj/one.txt': '1' } });
    await w.tools._cloudEntriesUnder('proj', false);          // warm the cache
    await w.tools.tool_write_file({ path: 'proj/two.txt', content: '2' }, CTX);
    await new Promise((r) => setTimeout(r, 20));
    const rows = await w.tools._cloudEntriesUnder('proj', false);
    t.ok(rows.some((r) => r.path === 'proj/two.txt'),
      'a file we just wrote is in the next listing, not hidden by the cache', rows.map((r) => r.path));
  }
}
