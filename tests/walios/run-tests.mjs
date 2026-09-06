// Unit tests for the walios office→PDF bridge in modules/sandpie-worker.js:
// the fd-1 frame scanner the shell tool uses to hear `soffice`'s host calls, the
// guest-path → OPFS-path mapping, and _officeConvertGuest's end-to-end flow against
// a mocked OPFS + page. Function sources are extracted from the worker file and
// evaluated here, so these exercise the shipped code, not a reimplementation.
//
// Run: node tests/walios/run-tests.mjs
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const workerSrc = readFileSync(join(here, '..', '..', 'modules', 'sandpie-worker.js'), 'utf8');

function extract(marker) {
  const i = workerSrc.indexOf(marker);
  if (i < 0) throw new Error('extract: not found: ' + marker);
  const end = workerSrc.indexOf('\n}\n', i);
  return workerSrc.slice(i, end + 3);
}
function extractConst(name) {
  const m = workerSrc.match(new RegExp('^const ' + name + ' = [\\s\\S]*?;[^\\n]*\\n', 'm'));
  if (!m) throw new Error('extract const: ' + name);
  return m[0];
}

let passed = 0, failed = 0;
function check(name, cond, detail) {
  if (cond) { passed++; console.log('  ok  ' + name); }
  else { failed++; console.log('  FAIL ' + name + (detail ? ' — ' + detail : '')); }
}

const b64enc = s => Buffer.from(s, 'utf8').toString('base64');
const frame = obj => '\x02' + b64enc(JSON.stringify(obj)) + '\x03\n';

// ── harness: worker globals the extracted code touches ─────────────────────
const POSTED = [];
const OPFS = new Map();           // rel path → Uint8Array
const harness = `
const self = { postMessage(m) { POSTED.push(m); } };
function _b64dec(s) { return Buffer.from(s, 'base64').toString('utf8'); }
function _b64enc(s) { return Buffer.from(s, 'utf8').toString('base64'); }
async function opfsReadBytes(rel) { if (!OPFS.has(rel)) { const e = new Error('not found'); e.name = 'NotFoundError'; throw e; } return OPFS.get(rel); }
async function opfsWriteBytes(rel, bytes) { if (rel.startsWith('sandpie/')) throw new Error('sandpie/ is system-only'); OPFS.set(rel, new Uint8Array(bytes)); }
${extractConst('OFFICE_TIMEOUT')}
${extractConst('OFFICE_FILTER')}
const _officeReqs = new Map();
let _officeSeq = 0;
${extract('function _guestToOpfs(')}
${extract('async function _officeConvertGuest(')}
${extract('async function _waliosGuestCall(')}
${extract('function _waliosFrameScanner(')}
return { _guestToOpfs, _officeConvertGuest, _waliosGuestCall, _waliosFrameScanner, _officeReqs };
`;
const W = new Function('POSTED', 'OPFS', harness)(POSTED, OPFS);

// ── frame scanner ──────────────────────────────────────────────────────────
{
  const out = [], calls = [];
  const sc = W._waliosFrameScanner(s => out.push(s), f => calls.push(f));
  sc.feed('hello\n');
  sc.feed(frame({ t: 'call', id: 1, op: 'office', args: { src: '/root/a.docx' } }));
  sc.feed('after\n');
  sc.flush();
  check('scanner: plain text passes through', out.join('') === 'hello\nafter\n', JSON.stringify(out.join('')));
  check('scanner: call frame decoded and hidden', calls.length === 1 && calls[0].op === 'office' && calls[0].id === 1);
}
{
  const out = [], calls = [];
  const sc = W._waliosFrameScanner(s => out.push(s), f => calls.push(f));
  const f = frame({ t: 'call', id: 7, op: 'office', args: {} });
  const cut = 12;
  sc.feed('x' + f.slice(0, cut));
  check('scanner: partial frame is held back', out.join('') === 'x' && calls.length === 0, JSON.stringify(out));
  sc.feed(f.slice(cut) + 'y');
  sc.flush();
  check('scanner: split frame reassembled', calls.length === 1 && calls[0].id === 7 && out.join('') === 'xy', JSON.stringify(out));
}
{
  const out = [], calls = [];
  const sc = W._waliosFrameScanner(s => out.push(s), f => calls.push(f));
  sc.feed('lone \x02 in output\n');
  check('scanner: lone STX withheld until flush', out.join('') === 'lone ');
  sc.flush();
  check('scanner: lone STX released at exit', out.join('') === 'lone \x02 in output\n', JSON.stringify(out.join('')));
  check('scanner: no bogus call', calls.length === 0);
}
{
  const out = [], calls = [];
  const sc = W._waliosFrameScanner(s => out.push(s), f => calls.push(f));
  sc.feed('a\x02not-base64-json\x03b');
  sc.flush();
  check('scanner: foreign STX..ETX span passes through', out.join('') === 'a\x02not-base64-json\x03b' && calls.length === 0, JSON.stringify(out.join('')));
}
{
  const out = [], calls = [];
  const sc = W._waliosFrameScanner(s => out.push(s), f => calls.push(f));
  sc.feed(frame({ t: 'done', id: 1 }) + frame({ t: 'call', id: 2, op: 'office' }));
  sc.flush();
  check('scanner: only t:call frames are calls', calls.length === 1 && calls[0].id === 2 && out.join('') === '', JSON.stringify(out));
}

// ── path mapping ───────────────────────────────────────────────────────────
check('path: /root/a/b.docx → a/b.docx', W._guestToOpfs('/root/a/b.docx') === 'a/b.docx');
check('path: doubled slashes collapse', W._guestToOpfs('/root//a///b.docx') === 'a/b.docx');
check('path: /tmp rejected', W._guestToOpfs('/tmp/x.docx') === null);
check('path: /root itself rejected', W._guestToOpfs('/root') === null && W._guestToOpfs('/root/') === null);
check('path: /rootfs prefix trick rejected', W._guestToOpfs('/rootfs/x.docx') === null);
check('path: .. rejected', W._guestToOpfs('/root/../etc/passwd') === null);

// ── conversion flow against a mocked page ──────────────────────────────────
// The page half: answer each office-convert-request the worker posts.
function pageAnswers(fn) {
  const t = setInterval(() => {
    for (let i = POSTED.length - 1; i >= 0; i--) {
      const m = POSTED[i];
      if (m.type === 'forward-to-page' && m.payload.type === 'office-convert-request' && !m._done) {
        m._done = true;
        const d = W._officeReqs.get(m.payload.id);
        if (d) { W._officeReqs.delete(m.payload.id); d.resolve(fn(m.payload)); }
      }
    }
  }, 5);
  return () => clearInterval(t);
}

{
  OPFS.clear(); POSTED.length = 0;
  OPFS.set('docs/report.docx', new TextEncoder().encode('PK-fake-docx'));
  let seenExt = null, seenLen = 0;
  const stop = pageAnswers(p => { seenExt = p.args.ext; seenLen = p.args.bytes.byteLength; return { ok: true, pdf: new TextEncoder().encode('%PDF-1.7 fake').buffer }; });
  const r = await W._officeConvertGuest({ src: '/root/docs/report.docx' });
  stop();
  check('convert: ok_call with default output next to the source', r.ok_call === true && r.out === '/root/docs/report.pdf', JSON.stringify(r));
  check('convert: page got the ext and the exact bytes', seenExt === 'docx' && seenLen === 'PK-fake-docx'.length, seenExt + ' ' + seenLen);
  check('convert: writer filter reported', r.filter === 'writer_pdf_Export');
  check('convert: PDF landed in OPFS', OPFS.has('docs/report.pdf') && new TextDecoder().decode(OPFS.get('docs/report.pdf')).startsWith('%PDF'));
  check('convert: page told about the new file', POSTED.some(m => m.type === 'forward-to-page' && m.payload.type === 'sw-opfs-changed' && m.payload.paths[0] === 'docs/report.pdf'));
}
{
  OPFS.clear(); POSTED.length = 0;
  OPFS.set('deck.pptx', new Uint8Array([1, 2, 3]));
  const stop = pageAnswers(() => ({ ok: true, pdf: new Uint8Array([37, 80]).buffer }));
  const r = await W._officeConvertGuest({ src: '/root/deck.pptx', out: '/root/out/deck.pdf' });
  stop();
  check('convert: explicit out path honoured + impress filter', r.ok_call && r.out === '/root/out/deck.pdf' && r.filter === 'impress_pdf_Export' && OPFS.has('out/deck.pdf'), JSON.stringify(r));
}
{
  OPFS.clear(); POSTED.length = 0;
  const r = await W._officeConvertGuest({ src: '/tmp/x.docx' });
  check('convert: source outside /root refused before any page call', r.ok_call === false && /under \/root/.test(r.error) && POSTED.length === 0, JSON.stringify(r));
}
{
  OPFS.clear(); POSTED.length = 0;
  OPFS.set('notes.md', new Uint8Array([1]));
  const r = await W._officeConvertGuest({ src: '/root/notes.md' });
  check('convert: unsupported extension refused', r.ok_call === false && /\.md is not/.test(r.error), JSON.stringify(r));
}
{
  OPFS.clear(); POSTED.length = 0;
  const r = await W._officeConvertGuest({ src: '/root/missing.docx' });
  check('convert: missing source reported', r.ok_call === false && /could not read \/root\/missing.docx/.test(r.error), JSON.stringify(r));
}
{
  OPFS.clear(); POSTED.length = 0;
  OPFS.set('a.xlsx', new Uint8Array([1]));
  const stop = pageAnswers(() => ({ ok: false, error: 'engine boot timed out' }));
  const r = await W._officeConvertGuest({ src: '/root/a.xlsx' });
  stop();
  check('convert: page error surfaces verbatim', r.ok_call === false && r.error === 'engine boot timed out', JSON.stringify(r));
  check('convert: nothing written on failure', !OPFS.has('a.pdf'));
}
{
  OPFS.clear(); POSTED.length = 0;
  OPFS.set('a.docx', new Uint8Array([1]));
  const stop = pageAnswers(() => ({ ok: true, pdf: new Uint8Array([1]).buffer }));
  const r = await W._officeConvertGuest({ src: '/root/a.docx', out: '/root/sandpie/config/x.pdf' });
  stop();
  check('convert: OPFS write guard error is surfaced', r.ok_call === false && /could not write/.test(r.error) && /system-only/.test(r.error), JSON.stringify(r));
}
{
  const r = await W._waliosGuestCall({ op: 'nope', args: {} });
  check('guest call: unknown op refused', r.ok_call === false && /unknown host op/.test(r.error));
}

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
