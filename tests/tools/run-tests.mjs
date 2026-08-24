// Unit tests for the file-tool layer of modules/sandpie-worker.js:
// write_file create/refuse/overwrite semantics, read_file content dedupe,
// and the raw-block parser's |overwrite| flag. The real function sources are
// extracted from the worker file and evaluated against an in-memory OPFS mock,
// so these tests exercise the shipped code, not a reimplementation.
//
// Run: node tests/tools/run-tests.mjs
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const workerSrc = readFileSync(join(here, '..', '..', 'modules', 'sandpie-worker.js'), 'utf8');

// ── extract function sources (from declaration to the first column-0 "}") ──
function extract(marker) {
  const i = workerSrc.indexOf(marker);
  if (i < 0) throw new Error('extract: not found: ' + marker);
  const end = workerSrc.indexOf('\n}\n', i);
  if (end < 0) throw new Error('extract: no terminator for ' + marker);
  return workerSrc.slice(i, end + 3);
}
const srcFnv    = extract('function _fnv1a(');
const srcRead   = extract('async function tool_read_file(');
const srcWrite  = extract('async function tool_write_file(');
const srcParse  = extract('function parseBlobToolCalls(');

// ── in-memory OPFS mock + worker-global stubs ──────────────────────────────
const mockSrc = `
const FILE_TEXT_MAX = 2 * 1024 * 1024;
const FILE_TOOL_CAP = 30000;
let _toolCallSeq = 0;
const self = { postMessage() {} };
const _pyBroadcast = () => {};
const _ensureDbxCtx = async () => {};
const _indexEntry = () => null;
const hydrateAsync = async () => { throw new Error('no dropbox in tests'); };
const normFilesPath = p => p ? String(p).replace(/^\\/+/, '').replace(/^files\\//, '') : '';
const _nf = () => { const e = new Error('not found'); e.name = 'NotFoundError'; return e; };
const opfsRoot = async () => {
  const dirHandle = prefix => ({
    async getDirectoryHandle(name) {
      const p = prefix + name;
      if (![...FS.keys()].some(k => k.startsWith(p + '/')) && !DIRS.has(p)) throw _nf();
      return dirHandle(p + '/');
    },
    async getFileHandle(name) {
      if (!FS.has(prefix + name)) throw _nf();
      return {};
    },
  });
  return dirHandle('');
};
const opfsReadBytes  = async rel => new TextEncoder().encode(FS.get(rel));
const opfsWriteBytes = async (rel, bytes) => { FS.set(rel, new TextDecoder().decode(bytes)); };
const _opfsGetFile = async rel => {
  if (!FS.has(rel)) throw _nf();
  const s = FS.get(rel);
  return { size: new TextEncoder().encode(s).length, text: async () => s };
};
const _emittedFileHashes = new Map();
`;

const factory = new Function('FS', 'DIRS',
  mockSrc + srcFnv + srcRead + srcWrite + srcParse +
  '\nreturn { tool_read_file, tool_write_file, parseBlobToolCalls, _fnv1a, _emittedFileHashes };');

// fresh world per test group
function world(files = {}, dirs = ['proj']) {
  const FS = new Map(Object.entries(files));
  return { FS, api: factory(FS, new Set(dirs)) };
}

let passed = 0, failed = 0;
function ok(cond, label, extra) {
  if (cond) { passed++; console.log('  ok  ' + label); }
  else { failed++; console.log('  FAIL ' + label + (extra != null ? ' — got: ' + JSON.stringify(extra).slice(0, 200) : '')); }
}

// ── _fnv1a ──────────────────────────────────────────────────────────────────
{
  const { api } = world();
  ok(api._fnv1a('abc') === api._fnv1a('abc'), 'fnv1a deterministic');
  ok(api._fnv1a('abc') !== api._fnv1a('abd'), 'fnv1a differs on different input');
  ok(api._fnv1a('') === 0x811c9dc5, 'fnv1a empty = offset basis');
}

// ── parseBlobToolCalls: |overwrite| flag ────────────────────────────────────
{
  const { api } = world();
  const plain = api.parseBlobToolCalls('<|write_file:proj/a.txt|>\nhello\n<|end_write_file|>');
  const a1 = JSON.parse(plain.toolCalls[0].function.arguments);
  ok(plain.toolCalls.length === 1 && a1.path === 'proj/a.txt' && a1.content === 'hello' && !('overwrite' in a1), 'raw block: plain write has no overwrite', a1);

  const ow = api.parseBlobToolCalls('<|write_file:proj/a.txt|overwrite|>\nnew body\n<|end_write_file|>');
  const a2 = JSON.parse(ow.toolCalls[0].function.arguments);
  ok(ow.toolCalls.length === 1 && a2.overwrite === true && a2.content === 'new body', 'raw block: |overwrite| flag parsed', a2);

  const ed = api.parseBlobToolCalls('<|edit_file:proj/a.txt|>\n<<<<<<< SEARCH\nold\n=======\nnew\n>>>>>>> REPLACE\n<|end_edit_file|>');
  const a3 = JSON.parse(ed.toolCalls[0].function.arguments);
  ok(ed.toolCalls.length === 1 && a3.old_str === 'old' && a3.new_str === 'new', 'raw block: edit_file unaffected', a3);

  const mix = api.parseBlobToolCalls('before <|write_file:x.txt|overwrite|>\nc\n<|end_write_file|> after');
  ok(mix.stripped === 'before  after'.replace('  ', ' ').trim() || mix.stripped === 'before  after' || mix.stripped === 'before after', 'raw block: stripped text preserved', mix.stripped);
}

// ── write_file semantics ────────────────────────────────────────────────────
{
  const { FS, api } = world();
  const r1 = await api.tool_write_file({ path: 'proj/a.txt', content: 'v1', _conv: 'c1' });
  ok(/^Created: proj\/a\.txt/.test(r1.result) && FS.get('proj/a.txt') === 'v1', 'create new file', r1.result);

  const r2 = await api.tool_write_file({ path: 'proj/a.txt', content: 'v2', _conv: 'c1' });
  ok(/already exists \(2 bytes\) — NOT overwritten/.test(r2.result) && /overwrite:true/.test(r2.result) && /v1/.test(r2.result) && FS.get('proj/a.txt') === 'v1',
     'collision: refused, hint names overwrite:true, echoes head once', r2.result);

  const r3 = await api.tool_write_file({ path: 'proj/a.txt', content: 'v3', _conv: 'c1' });
  ok(/unchanged since it last appeared in your context/.test(r3.result) && !/\bv1\b/.test(r3.result),
     'second collision: no re-echo of unchanged content', r3.result);

  const r4 = await api.tool_write_file({ path: 'proj/a.txt', content: 'v1', _conv: 'c1' });
  ok(/already contains exactly this content/.test(r4.result), 'identical content: no-op message', r4.result);

  const r5 = await api.tool_write_file({ path: 'proj/a.txt', content: 'v2', overwrite: true, _conv: 'c1' });
  ok(/^Overwrote: proj\/a\.txt/.test(r5.result) && FS.get('proj/a.txt') === 'v2', 'overwrite:true replaces content', r5.result);

  const r6 = await api.tool_write_file({ path: 'proj/b.txt', content: 'fresh', overwrite: true, _conv: 'c1' });
  ok(/^Created: proj\/b\.txt/.test(r6.result) && FS.get('proj/b.txt') === 'fresh', 'overwrite:true on missing file still creates', r6.result);

  // long existing content: echo capped at ~2k
  FS.set('proj/big.txt', 'x'.repeat(10000));
  const r7 = await api.tool_write_file({ path: 'proj/big.txt', content: 'y', _conv: 'c1' });
  ok(r7.result.length < 2600 && /truncated; 10000 bytes total/.test(r7.result), 'collision echo capped at 2k', r7.result.length);
}

// ── read_file dedupe ────────────────────────────────────────────────────────
{
  const { FS, api } = world({ 'proj/a.txt': 'line1\nline2\nline3' });
  const r1 = await api.tool_read_file({ path: 'proj/a.txt', _conv: 'c1' });
  ok(/1\tline1/.test(r1.result) && /3\tline3/.test(r1.result), 'first read: full content', r1.result);

  const r2 = await api.tool_read_file({ path: 'proj/a.txt', _conv: 'c1' });
  ok(/UNCHANGED since the copy already in your context/.test(r2.result) && !/line2/.test(r2.result), 're-read unchanged: stub, no content', r2.result);

  const r3 = await api.tool_read_file({ path: 'proj/a.txt', force: true, _conv: 'c1' });
  ok(/2\tline2/.test(r3.result), 'force:true re-emits', r3.result);

  FS.set('proj/a.txt', 'line1\nCHANGED\nline3');
  const r4 = await api.tool_read_file({ path: 'proj/a.txt', _conv: 'c1' });
  ok(/CHANGED/.test(r4.result), 'changed file re-emits in full', r4.result);

  const r5 = await api.tool_read_file({ path: 'proj/a.txt', offset: 2, limit: 1, _conv: 'c1' });
  ok(/2\tCHANGED/.test(r5.result), 'different range: full emit (own key)', r5.result);

  const r6 = await api.tool_read_file({ path: 'proj/a.txt', _conv: 'OTHER-conv' });
  ok(/CHANGED/.test(r6.result), 'different conversation: full emit', r6.result);

  // compaction clears the map → next read re-emits
  const r7pre = await api.tool_read_file({ path: 'proj/a.txt', _conv: 'c1' });
  ok(/UNCHANGED/.test(r7pre.result), 'stub again before compaction-clear', r7pre.result);
  api._emittedFileHashes.clear();
  const r7 = await api.tool_read_file({ path: 'proj/a.txt', _conv: 'c1' });
  ok(/CHANGED/.test(r7.result), 'after compaction clear: full emit again', r7.result);

  const r8 = await api.tool_read_file({ path: 'proj/missing.txt', _conv: 'c1' });
  ok(/file not found/.test(r8.result), 'missing file still errors normally', r8.result);
}

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
