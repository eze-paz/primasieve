// run-tests.mjs — end-to-end tests for pyodide-worker's lazy /files mount.
// Drives tests/pyfs/harness.html (a stand-in for the pool manager) in headless
// Chromium behind COOP/COEP headers (SharedArrayBuffer needs cross-origin
// isolation, matching prod). Usage:  node tests/pyfs/run-tests.mjs [filter]
import { spawn, execSync } from 'node:child_process';
import { createRequire } from 'node:module';
import net from 'node:net';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const PORT = 8931;
const filter = process.argv[2] || '';

// ---- resolve playwright (repo has no node_modules; fall back to the global install)
const require = createRequire(import.meta.url);
let chromium;
try { ({ chromium } = require('playwright')); }
catch (_) {
  const g = execSync('npm root -g').toString().trim();
  ({ chromium } = require(path.join(g, 'playwright')));
}

// ---- static server with COI headers (python coiserver.py) ----
function waitPort(port, ms) {
  return new Promise((resolve, reject) => {
    const t0 = Date.now();
    (function probe() {
      const s = net.connect(port, '127.0.0.1');
      s.once('connect', () => { s.destroy(); resolve(); });
      s.once('error', () => { s.destroy(); Date.now() - t0 > ms ? reject(new Error('server did not come up')) : setTimeout(probe, 200); });
    })();
  });
}

let passed = 0, failed = 0;
const failures = [];
function check(name, cond, detail) {
  if (cond) { passed++; console.log('  ok  ' + name); }
  else { failed++; failures.push(name + (detail ? ' — ' + detail : '')); console.log('  FAIL ' + name + (detail ? ' — ' + detail : '')); }
}
async function pollUntil(fn, ms = 4000, step = 150) {
  const t0 = Date.now();
  for (;;) {
    if (await fn()) return true;
    if (Date.now() - t0 > ms) return false;
    await new Promise(r => setTimeout(r, step));
  }
}

const server = spawn(process.platform === 'win32' ? 'python' : 'python3', ['coiserver.py', String(PORT)], { cwd: repoRoot, stdio: 'ignore' });
try {
  await waitPort(PORT, 10000);
  const browser = await chromium.launch({ headless: !process.env.HEADED });
  const page = await browser.newPage();
  page.on('console', m => { const t = m.text(); if (/error|FAIL|warn/i.test(t)) console.log('  [page]', t.slice(0, 300)); });
  page.on('pageerror', e => console.log('  [pageerror]', String(e).slice(0, 300)));
  await page.goto(`http://127.0.0.1:${PORT}/tests/pyfs/harness.html`);

  const info = await page.evaluate(() => harnessInfo());
  if (!info.coi || !info.sab) throw new Error('harness not crossOriginIsolated — SAB unavailable, aborting (info=' + JSON.stringify(info) + ')');

  const run = (code, opts) => page.evaluate(([c, o]) => runScript(c, o), [code, opts || {}]);
  const ev = (fn, arg) => page.evaluate(fn, arg);
  const tests = [];
  const test = (name, fn) => tests.push({ name, fn });

  // ================= seed =================
  const seed = async () => {
    await ev(() => opfsClear());
    await ev(() => opfsWrite('file1.txt', 'hello one'));
    await ev(() => opfsWrite('file2.txt', 'hello two'));
    await ev(() => opfsWrite('file3.txt', 'hello three'));
    await ev(() => opfsWrite('sub/a.txt', 'alpha'));
    await ev(() => opfsWrite('sub/deep/b.txt', 'beta'));
    await ev(() => opfsMkdir('emptydir'));
    await ev(() => opfsWrite('uni/ñandú café.txt', 'unicode!'));
    await ev(() => opfsWrite('data.csv', 'x,y\n1,2\n3,4'));
    await ev(() => opfsWrite('app.txt', 'AAA'));
    await ev(() => opfsWrite('chg.txt', 'v1'));
    await ev(() => opfsWrite('rc.txt', 'original'));
    await ev(() => opfsWrite('ren_src.txt', 'moved-bytes'));
    await ev(() => opfsWrite('mvdir/x.txt', 'X!'));
    await ev(() => opfsWrite('mvdir/sub2/y.txt', 'Y!'));
    await ev(() => opfsWrite('sandpie/config/test.json', '{"k":1}'));
    return ev(() => opfsWriteBytes('big.bin', 9 * 1024 * 1024, 42));  // > 4MB SAB → chunked
  };

  let bigSum = 0;

  test('T0 probe: what serves /files bytes (diagnostic, no assertions)', async () => {
    await seed();
    await ev(() => spawnWorker({}));
    const r1 = await run(`print(open('/files/file1.txt').read())`, { timeoutMs: 120000 });
    console.log('  [probe] read file1 ->', JSON.stringify(r1.slice(0, 120)));
    const st = await ev(() => debugStats());
    console.log('  [probe] stats:', JSON.stringify(st));
    // A file written by the page AFTER worker init, with NO fs-changed sent:
    // invisible under MEMFS semantics, visible under direct-OPFS semantics.
    await ev(() => opfsWrite('probe_late.txt', 'late'));
    const r2 = await run(`
import os, json
c = None
try: c = open('/files/probe_late.txt').read()
except Exception as e: c = 'ERR:' + type(e).__name__
print(json.dumps({'exists': os.path.exists('/files/probe_late.txt'), 'read': c}))
`);
    console.log('  [probe] late file (no fs-changed):', r2.trim().split('\n').pop());
    const logs = await ev(() => window.workerLogs.filter(l => l.includes('pyodide-worker') || l.includes('opfs-io')));
    for (const l of logs) console.log('  [probe boot]', l.slice(0, 160));
  });

  test('T1 metadata parity without hydration (the file1-file2-file3 regression)', async () => {
    bigSum = await seed();
    await ev(() => spawnWorker({}));
    const r = await run(`
import os, glob, json
out = {}
out['root'] = sorted(os.listdir('/files'))
out['isdir_empty'] = os.path.isdir('/files/emptydir')
out['walk'] = sorted(os.path.join(dp, f) for dp, dn, fn in os.walk('/files/sub') for f in fn)
out['glob'] = sorted(glob.glob('/files/**/*.txt', recursive=True))
out['size1'] = os.path.getsize('/files/file1.txt')
out['size_big'] = os.path.getsize('/files/big.bin')
out['exists_no'] = os.path.exists('/files/nope.txt')
out['exists_uni'] = os.path.exists('/files/uni/ñandú café.txt')
print(json.dumps(out))
`, { timeoutMs: 120000 });
    let o;
    try { o = JSON.parse(r.trim().split('\n').pop()); } catch (e) { check('T1 ran', false, r.slice(0, 500)); return; }
    for (const f of ['file1.txt', 'file2.txt', 'file3.txt', 'sub', 'emptydir', 'uni', 'big.bin', 'data.csv', 'sandpie'])
      check('T1 root listing has ' + f, o.root.includes(f), JSON.stringify(o.root));
    check('T1 empty dir visible', o.isdir_empty === true);
    check('T1 os.walk finds nested', JSON.stringify(o.walk) === JSON.stringify(['/files/sub/a.txt', '/files/sub/deep/b.txt']), JSON.stringify(o.walk));
    check('T1 glob recursive finds nested', o.glob.includes('/files/sub/deep/b.txt'), JSON.stringify(o.glob));
    check('T1 stat size exact', o.size1 === 'hello one'.length);
    check('T1 stat size big', o.size_big === 9 * 1024 * 1024);
    check('T1 missing file is ENOENT', o.exists_no === false);
    check('T1 unicode filename visible', o.exists_uni === true);
    const st = await ev(() => debugStats());
    check('T1 lazy mode active', st.lazy === true, JSON.stringify(st));
    check('T1 ZERO bytes hydrated by metadata ops', st.hydrated.length === 0, JSON.stringify(st.hydrated));
  });

  test('T2 byte reads hydrate lazily and correctly (incl. >4MB chunking, cwd-relative)', async () => {
    const r = await run(`
import os, json
out = {}
with open('/files/file1.txt') as f: out['f1'] = f.read()
os.chdir('/files/sub')
with open('a.txt') as f: out['rel'] = f.read()          # cwd-relative in a subdir
with open('deep/b.txt') as f: out['rel2'] = f.read()
os.chdir('/files')
s = 0
with open('/files/big.bin','rb') as f:
    data = f.read()
for b in data: s = (s + b) % 1000000007
out['bigsum'] = s
out['biglen'] = len(data)
print(json.dumps(out))
`, { timeoutMs: 120000 });
    let o;
    try { o = JSON.parse(r.trim().split('\n').pop()); } catch (e) { check('T2 ran', false, r.slice(0, 500)); return; }
    check('T2 read file1', o.f1 === 'hello one');
    check('T2 cwd-relative read', o.rel === 'alpha');
    check('T2 cwd-relative nested read', o.rel2 === 'beta');
    check('T2 big file length', o.biglen === 9 * 1024 * 1024);
    check('T2 big file checksum (chunked SAB)', o.bigsum === bigSum, o.bigsum + ' != ' + bigSum);
    const st = await ev(() => debugStats());
    for (const f of ['file1.txt', 'sub/a.txt', 'sub/deep/b.txt', 'big.bin'])
      check('T2 hydrated ' + f, st.hydrated.includes(f), JSON.stringify(st.hydrated));
    check('T2 did NOT hydrate untouched files', !st.hydrated.includes('file2.txt') && !st.hydrated.includes('data.csv'), JSON.stringify(st.hydrated));
  });

  test('T3 python writes flush back to OPFS', async () => {
    const r = await run(`
import os
os.makedirs('/files/out', exist_ok=True)
with open('/files/out/new.txt','w') as f: f.write('fresh')
print('done')
`);
    check('T3 script ok', r.trim() === 'done', r.slice(0, 300));
    check('T3 file in OPFS', await pollUntil(() => ev(() => opfsExists('out/new.txt'))));
    check('T3 content', (await ev(() => opfsRead('out/new.txt'))) === 'fresh');
    const r2 = await run(`import os; print(sorted(os.listdir('/files/out')))`);
    check('T3 next run sees it', r2.includes('new.txt'), r2.slice(0, 200));
  });

  test('T4 python deletes an UNFAULTED file — gone everywhere', async () => {
    const r = await run(`
import os, json
os.remove('/files/file3.txt')
print(json.dumps({'ls': 'file3.txt' in os.listdir('/files'), 'ex': os.path.exists('/files/file3.txt')}))
`);
    let o;
    try { o = JSON.parse(r.trim().split('\n').pop()); } catch (e) { check('T4 ran', false, r.slice(0, 400)); return; }
    check('T4 same-run listdir gone', o.ls === false);
    check('T4 same-run exists false', o.ex === false);
    check('T4 OPFS copy deleted', await pollUntil(async () => !(await ev(() => opfsExists('file3.txt')))));
    const r2 = await run(`import os; print(os.path.exists('/files/file3.txt'))`);
    check('T4 next run still gone', r2.trim() === 'False', r2.slice(0, 200));
  });

  test('T5 rename an unfaulted file', async () => {
    const r = await run(`
import os
os.rename('/files/ren_src.txt', '/files/ren_dst.txt')
print(open('/files/ren_dst.txt').read())
`);
    check('T5 content readable post-rename', r.trim() === 'moved-bytes', r.slice(0, 300));
    check('T5 dst in OPFS', await pollUntil(() => ev(() => opfsExists('ren_dst.txt'))));
    check('T5 src gone from OPFS', await pollUntil(async () => !(await ev(() => opfsExists('ren_src.txt')))));
    check('T5 dst content in OPFS', (await ev(() => opfsRead('ren_dst.txt'))) === 'moved-bytes');
  });

  test('T6 rename a dir with UNFAULTED children (data-loss guard)', async () => {
    const r = await run(`
import os
os.rename('/files/mvdir', '/files/mvdir2')
print(sorted(os.listdir('/files/mvdir2')))
`);
    check('T6 script ok', r.includes('x.txt') && r.includes('sub2'), r.slice(0, 300));
    check('T6 child file survived', await pollUntil(() => ev(() => opfsExists('mvdir2/x.txt'))));
    check('T6 nested child survived', await pollUntil(() => ev(() => opfsExists('mvdir2/sub2/y.txt'))));
    check('T6 child content intact', (await ev(() => opfsRead('mvdir2/x.txt'))) === 'X!');
    check('T6 nested content intact', (await ev(() => opfsRead('mvdir2/sub2/y.txt'))) === 'Y!');
    check('T6 old dir gone', await pollUntil(async () => !(await ev(() => opfsExists('mvdir')))));
  });

  test('T7 append to an unfaulted file', async () => {
    const r = await run(`
with open('/files/app.txt','a') as f: f.write('BBB')
print(open('/files/app.txt').read())
`);
    check('T7 merged content in python', r.trim() === 'AAABBB', r.slice(0, 200));
    check('T7 merged content in OPFS', await pollUntil(async () => (await ev(() => opfsRead('app.txt'))) === 'AAABBB'));
  });

  test('T8 external writes invalidate; recreate-after-python-delete resurfaces', async () => {
    const r1 = await run(`print(open('/files/chg.txt').read())`);
    check('T8 initial read', r1.trim() === 'v1', r1.slice(0, 200));
    await ev(() => opfsWrite('chg.txt', 'v2-external'));
    await ev(() => sendMsg({ type: 'fs-changed', rel: 'chg.txt' }));
    const r2 = await run(`print(open('/files/chg.txt').read())`);
    check('T8 sees external new content', r2.trim() === 'v2-external', r2.slice(0, 200));
    // python deletes; page recreates; python must see it again
    await run(`import os; os.remove('/files/rc.txt')`);
    await pollUntil(async () => !(await ev(() => opfsExists('rc.txt'))));
    await ev(() => opfsWrite('rc.txt', 'back'));
    await ev(() => sendMsg({ type: 'fs-changed', rel: 'rc.txt' }));
    const r3 = await run(`
import os, json
print(json.dumps({'ex': os.path.exists('/files/rc.txt'), 'ls': 'rc.txt' in os.listdir('/files'), 'c': open('/files/rc.txt').read()}))
`);
    let o;
    try { o = JSON.parse(r3.trim().split('\n').pop()); } catch (e) { check('T8 recreate ran', false, r3.slice(0, 400)); return; }
    check('T8 recreated file exists', o.ex === true);
    check('T8 recreated file listed', o.ls === true);
    check('T8 recreated content', o.c === 'back');
  });

  test('T9 external removal propagates', async () => {
    await ev(() => opfsDelete('file2.txt'));
    await ev(() => sendMsg({ type: 'fs-removed', paths: ['file2.txt'] }));
    const r = await run(`
import os, json
print(json.dumps({'ex': os.path.exists('/files/file2.txt'), 'ls': 'file2.txt' in os.listdir('/files')}))
`);
    let o;
    try { o = JSON.parse(r.trim().split('\n').pop()); } catch (e) { check('T9 ran', false, r.slice(0, 400)); return; }
    check('T9 exists false', o.ex === false);
    check('T9 not listed', o.ls === false);
  });

  test('T11 rmdir guards unfaulted children; rmtree works', async () => {
    const r = await run(`
import os, json, shutil
out = {}
try:
    os.rmdir('/files/sub'); out['rmdir'] = 'no-error'
except OSError as e: out['rmdir'] = 'OSError:' + str(e.errno)
shutil.rmtree('/files/sub')
out['gone'] = not os.path.exists('/files/sub')
print(json.dumps(out))
`);
    let o;
    try { o = JSON.parse(r.trim().split('\n').pop()); } catch (e) { check('T11 ran', false, r.slice(0, 500)); return; }
    check('T11 rmdir on non-empty raises', String(o.rmdir).startsWith('OSError'), JSON.stringify(o));
    check('T11 rmtree removed tree (python view)', o.gone === true);
    check('T11 rmtree removed tree (OPFS view)', await pollUntil(async () => !(await ev(() => opfsExists('sub')))));
  });

  test('T13 sandpie/ system-folder write guard still enforced', async () => {
    await run(`
import os
os.makedirs('/files/sandpie/evil', exist_ok=True)
open('/files/sandpie/evil/x.txt','w').write('nope')
print('done')
`);
    await new Promise(r => setTimeout(r, 1500));
    check('T13 guarded write never lands in OPFS', !(await ev(() => opfsExists('sandpie/evil/x.txt'))));
    check('T13 allowed sandpie/config readable', (await run(`print(open('/files/sandpie/config/test.json').read())`)).trim() === '{"k":1}');
  });

  test('T14 dehydrated-Dropbox tier still merges on top (metadata only)', async () => {
    await ev(() => sendMsg({ type: 'dbx-token', token: 'fake-token', dehydrated: true }));
    await ev(() => sendMsg({ type: 'dbx-index', index: { 'cloudz': { kind: 'folder' }, 'cloudz/only.txt': { kind: 'file', size: 5 } } }));
    const r = await run(`
import os, json
print(json.dumps({'ls': 'cloudz' in os.listdir('/files'), 'ex': os.path.exists('/files/cloudz/only.txt'),
                  'sz': os.path.getsize('/files/cloudz/only.txt'), 'local': os.path.exists('/files/file1.txt')}))
`);
    let o;
    try { o = JSON.parse(r.trim().split('\n').pop()); } catch (e) { check('T14 ran', false, r.slice(0, 400)); return; }
    check('T14 cloud folder listed', o.ls === true);
    check('T14 cloud file exists', o.ex === true);
    check('T14 cloud size from index', o.sz === 5);
    check('T14 local files still visible alongside', o.local === true);
  });

  test('T10 sqlite3 C-level open through the fault-in (fresh worker)', async () => {
    await run(`
import sqlite3
c = sqlite3.connect('/files/db.sqlite')
c.execute('create table t (a int, b text)')
c.executemany('insert into t values (?,?)', [(1,'one'),(2,'two')])
c.commit(); c.close()
print('created')
`);
    await pollUntil(() => ev(() => opfsExists('db.sqlite')));
    await ev(() => spawnWorker({}));   // FRESH worker: db.sqlite exists only as index metadata
    const r = await run(`
import sqlite3, json
c = sqlite3.connect('/files/db.sqlite')
rows = c.execute('select a, b from t order by a').fetchall()
print(json.dumps(rows))
`, { timeoutMs: 120000 });
    check('T10 rows readable via C open in fresh worker', r.trim().split('\n').pop() === '[[1, "one"], [2, "two"]]', r.slice(0, 400));
    const st = await ev(() => debugStats());
    check('T10 db was byte-hydrated on demand', st.hydrated.includes('db.sqlite'), JSON.stringify(st.hydrated));
  });

  test('T12 eager fallback (?eager=1) still behaves', async () => {
    await ev(() => spawnWorker({ eager: true }));
    const r = await run(`
import os, json
print(json.dumps({'ls': sorted(n for n in os.listdir('/files') if n.endswith('.txt')), 'c': open('/files/file1.txt').read()}))
`, { timeoutMs: 120000 });
    let o;
    try { o = JSON.parse(r.trim().split('\n').pop()); } catch (e) { check('T12 ran', false, r.slice(0, 400)); return; }
    check('T12 eager listdir works', o.ls.includes('file1.txt'), JSON.stringify(o.ls));
    check('T12 eager read works', o.c === 'hello one');
    const st = await ev(() => debugStats());
    check('T12 lazy off', st.lazy === false, JSON.stringify(st));
  });

  test('T15 memory: lazy worker holds ~none of a 48MB OPFS, eager holds all of it', async () => {
    await ev(() => killWorker());
    await ev(() => opfsClear());
    for (let i = 0; i < 6; i++) await ev((i) => opfsWriteBytes('blob' + i + '.bin', 8 * 1024 * 1024, i), i);

    // Primary metric: file bytes RESIDENT in MEMFS (each one is a real JS-heap
    // byte inside the worker) — deterministic, no GC noise.
    await ev(() => spawnWorker({ eager: true }));
    await run(`print('warm')`, { timeoutMs: 120000 });
    const eagerSt = await ev(() => debugStats());
    // Secondary (best-effort): renderer-level memory, if the API exists here.
    const eagerMem = await ev(() => measureMem().catch(() => null));
    await ev(() => killWorker());

    await ev(() => spawnWorker({}));
    await run(`print('warm')`, { timeoutMs: 120000 });
    const lazySt = await ev(() => debugStats());
    const lazyMem = await ev(() => measureMem().catch(() => null));

    const eMB = eagerSt.memfsBytes / 1048576, lMB = lazySt.memfsBytes / 1048576;
    console.log(`  [mem] MEMFS-resident file bytes: eager=${eMB.toFixed(1)}MB lazy=${lMB.toFixed(1)}MB (seed=48MB)`);
    console.log(`  [mem] wasm heap: eager=${(eagerSt.wasmHeapBytes / 1048576).toFixed(1)}MB lazy=${(lazySt.wasmHeapBytes / 1048576).toFixed(1)}MB`);
    if (eagerMem && lazyMem) console.log(`  [mem] renderer total: eager=${(eagerMem.bytes / 1048576).toFixed(1)}MB lazy=${(lazyMem.bytes / 1048576).toFixed(1)}MB`);
    else console.log('  [mem] measureUserAgentSpecificMemory unavailable in this headless build — MEMFS metric is the authoritative one');
    check('T15 eager mirrors the whole 48MB seed', eagerSt.memfsBytes >= 47 * 1048576, eMB.toFixed(1) + 'MB');
    check('T15 lazy holds < 1MB of file bytes', lazySt.memfsBytes >= 0 && lazySt.memfsBytes < 1048576, lMB.toFixed(1) + 'MB');
    check('T15 lazy hydrated nothing', lazySt.hydrated.length === 0, JSON.stringify(lazySt.hydrated));
  });

  // ================= run =================
  for (const t of tests) {
    if (filter && !t.name.includes(filter)) continue;
    console.log('\n== ' + t.name);
    try { await t.fn(); }
    catch (e) { failed++; failures.push(t.name + ' — threw: ' + (e.message || e)); console.log('  FAIL (threw) ' + (e.message || e)); }
  }

  console.log(`\n${passed} passed, ${failed} failed`);
  if (failures.length) { console.log('Failures:'); for (const f of failures) console.log('  - ' + f); }
  await browser.close();
  process.exitCode = failed ? 1 : 0;
} finally {
  server.kill();
}
