// Tool calls inside ONE session: what the model writes must end up in Dropbox,
// byte-for-byte, with no errors.
//
// These are CONTRACT tests: they describe what the user observes, not how the
// sync engine achieves it. They must still pass after the full-Dropbox refactor,
// where settle() becomes a no-op because a write IS the upload.
//
// Assertions read through readBack()/readable() rather than OPFS directly: after
// the refactor a project file has no local copy, and that is correct, not a bug.
import { connectedWorld, settleDeletes } from './harness.mjs';

const tick = () => new Promise((r) => setTimeout(r, 5));
const CTX = { agentId: 'agent-1' };

// "Everything the session wrote is now durable." Today that means running a
// sync pass; after the refactor it will mean awaiting in-flight uploads.
async function settle(w) { await w.sync(); await tick(); }

export async function run(t) {
  t.group('session: tool calls -> Dropbox');

  // ── the canonical case: create, then edit, in one session ──
  {
    const w = await connectedWorld();
    const a = await w.tools.tool_write_file({ path: 'artifacts/report.html', content: '<h1>v1</h1>' }, CTX);
    const b = await w.tools.tool_edit_file({ path: 'artifacts/report.html', old_str: 'v1', new_str: 'v2' }, CTX);
    await settle(w);

    t.ok(/^Created:/.test(a.result), 'create reports Created', a.result);
    t.ok(!/Error|failed|Refused/i.test(b.result), 'edit after create raises no error', b.result);
    t.ok(w.readBack('artifacts/report.html') === '<h1>v2</h1>', 'reading it back gives the edited version', w.readBack('artifacts/report.html'));
    t.ok(w.cloudHas('artifacts/report.html'), 'file exists in Dropbox');
    t.ok(w.cloudText('artifacts/report.html') === '<h1>v2</h1>', 'Dropbox content matches local after create+edit', w.cloudText('artifacts/report.html'));
  }

  // ── several edits in one session converge on one cloud copy ──
  {
    const w = await connectedWorld();
    await w.tools.tool_write_file({ path: 'artifacts/m.html', content: 'a' }, CTX);
    await w.tools.tool_edit_file({ path: 'artifacts/m.html', old_str: 'a', new_str: 'b' }, CTX);
    await w.tools.tool_edit_file({ path: 'artifacts/m.html', old_str: 'b', new_str: 'c' }, CTX);
    await settle(w);
    t.ok(w.cloudText('artifacts/m.html') === 'c', 'three writes -> final content in Dropbox', w.cloudText('artifacts/m.html'));
    const copies = [...w.CLOUD.keys()].filter((k) => k.includes('m.html'));
    t.ok(copies.length === 1, 'no duplicate/renamed copies created', copies);
  }

  // ── multiple files in one session ──
  {
    const w = await connectedWorld();
    await w.tools.tool_write_file({ path: 'artifacts/one.html', content: '1' }, CTX);
    await w.tools.tool_write_file({ path: 'artifacts/two.html', content: '2' }, CTX);
    await w.tools.tool_write_file({ path: 'notes/three.md', content: '3' }, CTX);
    await settle(w);
    t.ok(w.cloudText('artifacts/one.html') === '1' && w.cloudText('artifacts/two.html') === '2' && w.cloudText('notes/three.md') === '3',
      'every file written in the session reaches Dropbox',
      [...w.CLOUD.keys()]);
  }

  // ── overwrite semantics ──
  {
    const w = await connectedWorld();
    await w.tools.tool_write_file({ path: 'artifacts/o.html', content: 'first' }, CTX);
    await settle(w);
    const refused = await w.tools.tool_write_file({ path: 'artifacts/o.html', content: 'second' }, CTX);
    t.ok(/NOT overwritten/.test(refused.result), 'second write without overwrite is refused', refused.result);
    t.ok(w.cloudText('artifacts/o.html') === 'first', 'refused write leaves Dropbox untouched', w.cloudText('artifacts/o.html'));

    const forced = await w.tools.tool_write_file({ path: 'artifacts/o.html', content: 'second', overwrite: true }, CTX);
    await settle(w);
    t.ok(/^Overwrote:/.test(forced.result), 'overwrite:true reports Overwrote', forced.result);
    t.ok(w.cloudText('artifacts/o.html') === 'second', 'overwrite reaches Dropbox', w.cloudText('artifacts/o.html'));
  }

  // ── a failed edit must not corrupt anything ──
  {
    const w = await connectedWorld();
    await w.tools.tool_write_file({ path: 'artifacts/e.html', content: 'hello' }, CTX);
    await settle(w);
    const bad = await w.tools.tool_edit_file({ path: 'artifacts/e.html', old_str: 'NOT-PRESENT', new_str: 'x' }, CTX);
    await settle(w);
    t.ok(/not found|no match|Error/i.test(bad.result), 'edit with non-matching old_str errors', bad.result);
    t.ok(w.readBack('artifacts/e.html') === 'hello' && w.cloudText('artifacts/e.html') === 'hello',
      'a failed edit leaves the content intact everywhere', [w.readBack('artifacts/e.html'), w.cloudText('artifacts/e.html')]);
  }

  // ── delete removes it from both sides ──
  {
    const w = await connectedWorld();
    await w.tools.tool_write_file({ path: 'artifacts/d.html', content: 'bye' }, CTX);
    await settle(w);
    t.ok(w.cloudHas('artifacts/d.html'), 'precondition: uploaded');
    const del = await w.tools.tool_delete_file({ path: 'artifacts/d.html' }, CTX);
    await settleDeletes(w);
    t.ok(/^Deleted:/.test(del.result), 'delete_file reports Deleted', del.result);
    t.ok(!w.readable('artifacts/d.html'), 'the file is no longer readable', w.where('artifacts/d.html'));
    t.ok(!w.cloudHas('artifacts/d.html'), 'file gone from Dropbox');
  }

  // ── a write is durable the moment the tool returns ──
  // The headline of the full-Dropbox refactor: no sync pass in between. Before
  // step 1 this file sat in OPFS until a sync ran, which could be minutes (sync
  // is suppressed mid-turn and while the tab is hidden) or never.
  {
    const w = await connectedWorld();
    await w.tools.tool_write_file({ path: 'artifacts/immediate.html', content: 'now' }, CTX);
    await tick();
    t.ok(w.cloudText('artifacts/immediate.html') === 'now',
      'a tool write reaches Dropbox without waiting for a sync', w.where('artifacts/immediate.html'));
  }

  // ── an edit is durable immediately too ──
  {
    const w = await connectedWorld();
    await w.tools.tool_write_file({ path: 'artifacts/imm-edit.html', content: 'v1' }, CTX);
    await w.tools.tool_edit_file({ path: 'artifacts/imm-edit.html', old_str: 'v1', new_str: 'v2' }, CTX);
    await tick();
    t.ok(w.cloudText('artifacts/imm-edit.html') === 'v2',
      'an edit reaches Dropbox without waiting for a sync', w.cloudText('artifacts/imm-edit.html'));
  }

  // ── work written during a turn is durable by the end of it ──
  // Sync is suppressed while a turn generates, because it must not PULL while
  // files are being written. Whether the bytes land during the turn (step 1) or
  // at the end of it (the old engine), the contract is the same.
  {
    const w = await connectedWorld();
    w.generating = true;
    await w.tools.tool_write_file({ path: 'artifacts/g.html', content: 'mid-turn' }, CTX);
    w.generating = false;
    await settle(w);
    t.ok(w.cloudText('artifacts/g.html') === 'mid-turn',
      'work written during a turn is in Dropbox by the time it ends', w.cloudText('artifacts/g.html'));
  }

  // ── a long turn writing many files still lands everything ──
  {
    const w = await connectedWorld();
    w.generating = true;
    for (let i = 0; i < 12; i++) await w.tools.tool_write_file({ path: `artifacts/batch-${i}.txt`, content: 'x' + i }, CTX);
    w.generating = false;
    await settle(w);
    const missing = [];
    for (let i = 0; i < 12; i++) if (w.cloudText(`artifacts/batch-${i}.txt`) !== 'x' + i) missing.push(i);
    t.ok(missing.length === 0, 'all 12 files from a long turn reach Dropbox', missing);
  }
}
