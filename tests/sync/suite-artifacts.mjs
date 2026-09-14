// Artifact cards on a conversation loaded from history.
//
// conversations.js persists the paths a turn wrote as meta.filesTouched, and
// re-renders them as cards when an old conversation is opened (renderFilesTouched).
// The card is only useful if the file it names can still be opened, so the
// contract is:
//
//   every path in filesTouched must remain RESOLVABLE — present in OPFS, or
//   fetchable from Dropbox — for as long as the conversation exists.
//
// A card that resolves to nothing is the visible symptom of the sync bugs: the
// conversation still advertises work that no longer exists anywhere.
import { connectedWorld, settleDeletes } from './harness.mjs';

const tick = () => new Promise((r) => setTimeout(r, 5));
const CTX = { agentId: 'agent-1' };

// What a card click has to be able to do: read the bytes back.
function resolvable(w, path) { return w.localHas(path) || w.cloudHas(path); }

// The meta a conversation carries across a reload.
function metaFor(paths) { return { filesTouched: paths.map((p) => ({ path: p, ts: 1 })) }; }

export async function run(t) {
  t.group('artifact cards: historical conversation load');

  // ── a turn writes artifacts; the conversation is reopened later ──
  {
    let w = await connectedWorld();
    await w.tools.tool_write_file({ path: 'artifacts/mockup-v1.html', content: '<h1>v1</h1>' }, CTX);
    await w.tools.tool_write_file({ path: 'artifacts/mockup-v2.html', content: '<h1>v2</h1>' }, CTX);
    const meta = metaFor(['artifacts/mockup-v1.html', 'artifacts/mockup-v2.html']);
    await w.sync();

    w = w.reload();
    w.seedTokens();
    await w.sync();

    const dead = meta.filesTouched.filter((f) => !resolvable(w, f.path)).map((f) => f.path);
    t.ok(dead.length === 0, 'every artifact card still resolves after a reload', dead);
    t.ok(w.cloudText('artifacts/mockup-v1.html') === '<h1>v1</h1>', 'card content unchanged after reload', w.cloudText('artifacts/mockup-v1.html'));
  }

  // ── days later: the local copy is purged, the card must still open ──
  // dehydratePurge() drops clean local copies untouched for 24h. The cloud copy
  // is what keeps the card alive, so this is the case that proves uploads matter.
  {
    let w = await connectedWorld();
    await w.tools.tool_write_file({ path: 'artifacts/old.html', content: 'from last week' }, CTX);
    const meta = metaFor(['artifacts/old.html']);
    await w.sync();

    w.advance(3 * 24 * 3600 * 1000);   // three days pass
    w = w.reload();
    w.seedTokens();
    await w.sync();
    await tick();

    t.ok(resolvable(w, 'artifacts/old.html'),
      'a three-day-old artifact card still resolves (cloud copy)', { local: w.localHas('artifacts/old.html'), cloud: w.cloudHas('artifacts/old.html') });
    t.ok(w.cloudText('artifacts/old.html') === 'from last week',
      'the old artifact still has its content in Dropbox', w.cloudText('artifacts/old.html'));
  }

  // ── the observed failure: cards pointing at files that no longer exist ──
  // Same session as before, but the dirty mark was dropped, so the file was
  // never uploaded and the local copy is removed as an orphan. The conversation
  // still lists the card.
  {
    let w = await connectedWorld();
    w.relayBroken = true;
    await w.tools.tool_write_file({ path: 'artifacts/ghost.html', content: 'work that vanished' }, CTX);
    w.relayBroken = false;
    const meta = metaFor(['artifacts/ghost.html']);

    w = w.reload();
    w.seedTokens();
    await w.sync();

    t.known(meta.filesTouched.every((f) => resolvable(w, f.path)),
      'an artifact card never points at a missing file',
      'current behaviour: the file was never uploaded and the local copy is deleted\n          '
      + 'as an orphan, leaving a dead card in the conversation.');
  }

  // ── an artifact edited in a later session keeps one identity ──
  {
    let w = await connectedWorld();
    await w.tools.tool_write_file({ path: 'artifacts/live.html', content: 'draft' }, CTX);
    await w.sync();
    const meta = metaFor(['artifacts/live.html']);

    w = w.reload();
    w.seedTokens();
    await w.sync();
    await w.tools.tool_edit_file({ path: 'artifacts/live.html', old_str: 'draft', new_str: 'final' }, CTX);
    await w.sync();

    t.ok(resolvable(w, 'artifacts/live.html'), 'card resolves after a cross-session edit');
    t.ok(w.cloudText('artifacts/live.html') === 'final', 'the edit from the later session is in Dropbox', w.cloudText('artifacts/live.html'));
    const copies = [...w.CLOUD.keys()].filter((k) => k.includes('live.html'));
    t.ok(copies.length === 1, 'editing across sessions does not fork the file', copies);
  }

  // ── deleting an artifact should invalidate its card, not orphan the cloud ──
  {
    const w = await connectedWorld();
    await w.tools.tool_write_file({ path: 'artifacts/tmp.html', content: 'scratch' }, CTX);
    await w.sync();
    await w.tools.tool_delete_file({ path: 'artifacts/tmp.html' }, CTX);
    await settleDeletes(w);
    t.ok(!resolvable(w, 'artifacts/tmp.html'),
      'a deliberately deleted artifact is gone from both sides',
      { local: w.localHas('artifacts/tmp.html'), cloud: w.cloudHas('artifacts/tmp.html') });
  }
}
