// Unit tests for tool_write_todos (modules/sandpie-worker.js) — the reconcile
// engine, the delta form, fuzzy matching, auto-advance, and the state-aware
// replies. The real function sources are extracted from the worker file and
// evaluated in isolation, so these tests exercise the shipped code.
//
// The headline scenario replays the measured 2026-08-28 production grind
// (session pu4pu2yv): the model finished its plan, re-sent it REWORDED with
// status pending, the old reconcile resurrected it as pending duplicates, and
// the stop guard + plan-first gate trapped the model in 7 no-op write_todos
// rounds (~130k prompt tokens each). The variant must answer that exact resend
// with "checklist COMPLETE… respond() now" and create no duplicates.
//
// Run: node tests/todos/run-tests.mjs
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const workerSrc = readFileSync(join(here, '..', '..', 'modules', 'sandpie-worker.js'), 'utf8');

function extractFrom(src, marker) {
  const i = src.indexOf(marker);
  if (i < 0) throw new Error('extract: not found: ' + marker);
  const end = src.indexOf('\n}\n', i);
  if (end < 0) throw new Error('extract: no terminator for ' + marker);
  return src.slice(i, end + 3);
}
// Single-line const helpers are extracted by line.
function extractLine(src, marker) {
  const i = src.indexOf(marker);
  if (i < 0) throw new Error('extract line: not found: ' + marker);
  return src.slice(i, src.indexOf('\n', i) + 1);
}
const parts = [
  extractLine(workerSrc, "const _TODO_OPEN = new Set("),
  extractLine(workerSrc, "const _TODO_UNSAT = new Set("),
  extractLine(workerSrc, "const _TODO_ALL = ["),
  extractLine(workerSrc, 'function _todoNextId(tree)'),
  extractLine(workerSrc, 'function _todoBlockers(t, byId)'),
  extractLine(workerSrc, 'function _todoFlat(tree)'),
  extractLine(workerSrc, 'function _todoEst(v)'),
  extractFrom(workerSrc, 'function _todoSummary(tree)'),
  extractFrom(workerSrc, 'async function tool_write_todos({ todos }, ctx) {'),
].join('\n');

const parts2 = parts + '\n' + extractFrom(workerSrc, 'async function tool_write_todos_claude({ todos }, ctx) {');
const factory = new Function(parts2 + '\nreturn { v2: tool_write_todos, claude: tool_write_todos_claude };');
const { v2: tool_write_todos, claude: tool_write_todos_claude } = factory();

let pass = 0, fail = 0;
function check(name, cond, detail) {
  if (cond) { pass++; console.log('  ok  ' + name); }
  else { fail++; console.log('  FAIL ' + name + (detail ? ' — ' + detail : '')); }
}
const call = (ctx, todos) => tool_write_todos({ todos }, ctx);
const live = ctx => ctx._todoTree.filter(t => t.status !== 'deleted');
const statuses = ctx => live(ctx).map(t => t.status).join(',');

// ── 1. Fresh plan: all-pending list auto-starts task 1 ─────────────────────
{
  console.log('fresh build + auto-advance');
  const ctx = {};
  const r = await call(ctx, [
    { content: 'Read the admin sources', est: 6 },
    { content: 'Build the merged admin page' },
    { content: 'Deploy and verify' },
  ]);
  check('three tasks created', live(ctx).length === 3);
  check('task 1 auto-started', ctx._todoTree[0].status === 'in_progress');
  check('result announces auto-start', /Auto-started task 1/.test(r.result));
  check('todos: payload present', /^todos:\[/.test(r.result));
}

// ── 2. Fresh plan with explicit in_progress: no auto-advance needed ────────
{
  console.log('fresh build honors declared in_progress + demotes extras');
  const ctx = {};
  await call(ctx, [
    { content: 'A', status: 'in_progress' },
    { content: 'B', status: 'in_progress' },
  ]);
  check('single-active enforced', statuses(ctx) === 'in_progress,pending');
}

// ── 3. Delta form: one status flip, nothing dropped, auto-advance follows ──
{
  console.log('delta form');
  const ctx = {};
  await call(ctx, [{ content: 'A', status: 'in_progress' }, { content: 'B' }, { content: 'C' }]);
  const r = await call(ctx, [{ id: '1', status: 'completed' }]);
  check('A completed', ctx._todoTree[0].status === 'completed');
  check('B auto-started', ctx._todoTree[1].status === 'in_progress');
  check('C untouched', ctx._todoTree[2].status === 'pending');
  check('nothing dropped', live(ctx).length === 3);
  check('announces auto-start of 2', /Auto-started task 2/.test(r.result));
  const r2 = await call(ctx, [{ id: '99', status: 'completed' }]);
  check('unknown id reported, not fatal', /Unknown id ignored: 99/.test(r2.result));
  const r3 = await call(ctx, [{ id: '1', status: 'pending' }]);
  check('delta cannot un-complete', ctx._todoTree[0].status === 'completed' && /already completed/.test(r3.result));
}

// ── 4. THE RECORDED GRIND: reworded all-pending resend of a finished plan ──
{
  console.log('production grind replay (pu4pu2yv)');
  const ctx = {};
  await call(ctx, [
    { content: 'Read current /admin (admin.html) and /admin/transcripts (admin-transcripts.html) sources from the sandpie-server repo', status: 'in_progress', est: 6 },
    { content: 'Build merged admin.html: transcripts as a 4th in-page view', est: 3 },
    { content: 'Update app.js to remove the /admin/transcripts route', est: 4 },
    { content: 'Deploy to server (git pull + restart) and verify', est: 5 },
  ]);
  // finish everything (delta)
  await call(ctx, [{ id: '1', status: 'completed' }, { id: '2', status: 'completed' }, { id: '3', status: 'completed' }, { id: '4', status: 'completed' }]);
  check('all completed', live(ctx).every(t => t.status === 'completed'));
  // the fatal resend: REWORDED content, all pending (verbatim shape from prod)
  const before = live(ctx).length;
  const r = await call(ctx, [
    { content: 'Read current /admin and /admin/transcripts sources from the sandpie-server repo', status: 'pending' },
    { content: 'Build merged admin.html: transcripts as a 4th in-page tab', status: 'pending' },
    { content: 'Update app.js to remove the /admin/transcripts endpoint', status: 'pending' },
    { content: 'Deploy to the server (git pull + restart) and verify it', status: 'pending' },
  ]);
  check('NO duplicates created', live(ctx).length === before, 'live=' + live(ctx).length);
  check('nothing re-opened', live(ctx).every(t => t.status === 'completed'), statuses(ctx));
  check('reply says COMPLETE + respond()', /COMPLETE/.test(r.result) && /respond\(\)/.test(r.result));
  check('reports already-completed resends', /ALREADY COMPLETED/.test(r.result));
  // second identical resend (the old loop) must keep saying the same thing
  const r2 = await call(ctx, [
    { content: 'Read current /admin and /admin/transcripts sources from the sandpie-server repo', status: 'pending' },
    { content: 'Build merged admin.html: transcripts as a 4th in-page tab', status: 'pending' },
    { content: 'Update app.js to remove the /admin/transcripts endpoint', status: 'pending' },
    { content: 'Deploy to the server (git pull + restart) and verify it', status: 'pending' },
  ]);
  check('repeat still routes to respond()', /respond\(\)/.test(r2.result) && live(ctx).length === before);
}

// ── 5. Reworded task MID-work updates content instead of duplicating ───────
{
  console.log('mid-work reword');
  const ctx = {};
  await call(ctx, [{ content: 'Fix the localization display cache bug', status: 'in_progress' }, { content: 'Write tests for the cache' }]);
  await call(ctx, [
    { content: 'Fix the localization display-cache bug in conversations.js', status: 'in_progress' },
    { content: 'Write tests covering the cache', status: 'pending' },
  ]);
  check('no duplicates on reword', live(ctx).length === 2, 'live=' + live(ctx).length);
  check('content updated in place', /conversations\.js/.test(ctx._todoTree[0].content));
}

// ── 6. Full-list drop semantics + never-uncomplete still hold ──────────────
{
  console.log('safety: drops reported, completed immutable');
  const ctx = {};
  await call(ctx, [{ content: 'Alpha', status: 'in_progress' }, { content: 'Beta' }, { content: 'Totally unrelated gamma work' }]);
  const r = await call(ctx, [{ content: 'Alpha', status: 'completed' }, { content: 'Beta', status: 'in_progress' }]);
  check('omitted open task dropped + reported', /DROPPED 1 open task/.test(r.result));
  check('alpha completed, beta active', ctx._todoTree.find(t => t.content === 'Alpha').status === 'completed');
  const r2 = await call(ctx, [{ content: 'Alpha', status: 'pending' }, { content: 'Beta', status: 'in_progress' }]);
  check('full list cannot un-complete', ctx._todoTree.find(t => t.content === 'Alpha').status === 'completed' && /ALREADY COMPLETED/.test(r2.result));
}

// ── 7. Auto-advance respects blockedBy ──────────────────────────────────────
{
  console.log('auto-advance skips blocked-by tasks');
  const ctx = {};
  await call(ctx, [
    { content: 'First step', status: 'in_progress' },
    { content: 'Needs first', blockedBy: ['1'] },
    { content: 'Independent third' },
  ]);
  await call(ctx, [{ id: '1', status: 'completed' }]);
  // task 2 is unblocked now (1 completed) so IT should start, in list order
  check('unblocked dependent starts', ctx._todoTree[1].status === 'in_progress', statuses(ctx));
  const ctx2 = {};
  await call(ctx2, [
    { content: 'Blocked forever', blockedBy: ['2'], status: 'pending' },
    { content: 'The blocker', status: 'in_progress' },
  ]);
  await call(ctx2, [{ id: '1', status: 'pending' }]); // no-op-ish; 2 still active
  check('active task untouched by delta on other', ctx2._todoTree[1].status === 'in_progress');
}

// ── 8. State-aware no-op with an active task names it ──────────────────────
{
  console.log('state-aware no-op mid-work');
  const ctx = {};
  await call(ctx, [{ content: 'Do the thing', status: 'in_progress' }, { content: 'Then this' }]);
  const r = await call(ctx, [{ content: 'Do the thing', status: 'in_progress' }, { content: 'Then this', status: 'pending' }]);
  check('no-op names the active task', /Task 1 \("Do the thing"\) is in_progress/.test(r.result));
  check('no-op teaches delta form', /"todos":\[\{"id":"1","status":"completed"\}\]/.test(r.result));
}

// ── 9. Token economics: delta vs full-list re-type ──────────────────────────
{
  console.log('token economics (informational)');
  const full = JSON.stringify({ todos: [
    { content: 'Read current /admin (admin.html) and /admin/transcripts (admin-transcripts.html) sources from the sandpie-server repo', status: 'completed', activeForm: 'Reading admin sources', est: 6 },
    { content: 'Build merged admin.html: transcripts as a 4th in-page view', status: 'in_progress', activeForm: 'Building merged admin.html', est: 3 },
    { content: 'Update app.js to remove the /admin/transcripts route', status: 'pending', activeForm: 'Updating app.js', est: 4 },
    { content: 'Deploy to server (git pull + restart) and verify', status: 'pending', activeForm: 'Deploying', est: 5 },
  ]});
  const delta = JSON.stringify({ todos: [{ id: '1', status: 'completed' }] });
  const ratio = (full.length / delta.length).toFixed(1);
  console.log('  info full-list args ' + full.length + ' chars vs delta ' + delta.length + ' chars = ' + ratio + 'x fewer output chars per status flip');
  check('delta is >=8x cheaper on this real list', full.length / delta.length >= 8);
}

// ── 10. Claude-mode clone (DEFAULT): blind full replace, verbatim ack ───────
{
  console.log('claude clone (default mode)');
  const ctx = {};
  const r1 = await tool_write_todos_claude({ todos: [
    { content: 'First', status: 'in_progress', activeForm: 'Doing first' },
    { content: 'Second', status: 'pending', activeForm: 'Doing second' },
  ] }, ctx);
  check('two tasks, positional ids', ctx._todoTree.length === 2 && ctx._todoTree[0].id === '1');
  check('verbatim Claude ack', /Todos have been modified successfully/.test(r1.result));
  check('todos: payload for the page', /^todos:\[/.test(r1.result));
  // blind replace: the model's list IS the state — omissions and rewords included
  await tool_write_todos_claude({ todos: [{ content: 'Second reworded', status: 'completed', activeForm: 'Done' }] }, ctx);
  check('blind replace honored (1 task, completed)', ctx._todoTree.length === 1 && ctx._todoTree[0].status === 'completed');
  const r3 = await tool_write_todos_claude({ todos: 'nope' }, ctx);
  check('non-array rejected', /Error/.test(r3.result));
}

console.log('\n' + pass + ' passed, ' + fail + ' failed');
process.exit(fail ? 1 : 0);
