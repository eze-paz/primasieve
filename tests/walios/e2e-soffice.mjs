// End-to-end test for the walios office→PDF bridge, in a REAL browser.
//
// Drives the actual sandpie.html page (real modules/sandpie-worker.js, real
// modules/conversations.js page handler, real convert/office-engine.html) behind
// COOP/COEP headers, and asserts that BOTH guest entry points produce a real PDF in
// OPFS:
//   * the walios shell tool:  soffice --headless --convert-to pdf FILE
//   * run_python on walios:   import soffice; soffice.convert(...)
//
// The unit suite (run-tests.mjs) mocks the page and the engine; this one mocks
// nothing. It is the test that would have caught a bridge that only works on paper.
//
// REQUIREMENTS: the walios runtime assets are NOT in this repo (gitignored, ~22MB).
// Put them in walios/ at the repo root before running:
//   scp sandpie:/opt/sandpie-server/walios/{wali-worker.js,wali-proc-worker.js,\
//   opfs-worker.js,wisp-worker.js,busybox.wasm,rootfs.tar.gz,python_cxx.wasm,\
//   pylib.tar.gz,walios-ext.tar.gz,walios-extras.tar.gz} walios/
// Keep these in sync with the deployed kernel: a STALE wali-worker.js, or a missing
// wali-proc-worker.js (every process runs on one), makes every guest exit 127 rather
// than skip -- which reads like a broken bridge instead of a stale checkout.
// The LibreOffice engine itself is fetched from cdn.zetaoffice.net, so the run needs
// internet access. Skips (exit 0) with a clear message when either is missing.
//
// Run: node tests/walios/e2e-soffice.mjs [--headed]
import { spawn, execSync } from 'node:child_process';
import { createRequire } from 'node:module';
import fs from 'node:fs';
import net from 'node:net';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const PORT = 8143;
const HEADED = process.argv.includes('--headed');
// The whole run must stay under the 5-minute ceiling: a cold LibreOffice boot is the
// slow part (~20-90s), the walios side is seconds.
const CONVERT_TIMEOUT_MS = 210000;

const ASSETS = ['wali-worker.js', 'wali-proc-worker.js', 'opfs-worker.js', 'wisp-worker.js',
  'busybox.wasm', 'rootfs.tar.gz', 'python_cxx.wasm', 'pylib.tar.gz', 'walios-ext.tar.gz',
  'walios-extras.tar.gz'];
const missing = ASSETS.filter(a => !fs.existsSync(path.join(repoRoot, 'walios', a)));
if (missing.length) {
  console.log('SKIP: walios runtime assets missing from walios/ — ' + missing.join(', '));
  console.log('      (see the header of this file for the scp line that fetches them)');
  process.exit(0);
}
// A real document to convert. Any .docx in the repo root works.
const DOCX = ['v-original.docx', 'test-pacifico.docx'].find(f => fs.existsSync(path.join(repoRoot, f)));
if (!DOCX) { console.log('SKIP: no .docx in the repo root to convert'); process.exit(0); }

const require = createRequire(import.meta.url);
let chromium;
try { ({ chromium } = require('playwright')); }
catch (_) {
  try { ({ chromium } = require(path.join(execSync('npm root -g').toString().trim(), 'playwright'))); }
  catch (e) { console.log('SKIP: playwright not installed (npm i -g playwright && npx playwright install chromium)'); process.exit(0); }
}

let passed = 0, failed = 0;
const check = (name, cond, detail) => {
  if (cond) { passed++; console.log('  ok  ' + name); }
  else { failed++; console.log('  FAIL ' + name + (detail ? '\n        ' + String(detail).replace(/\n/g, '\n        ') : '')); }
};
const waitPort = (port, ms) => new Promise((resolve, reject) => {
  const t0 = Date.now();
  (function probe() {
    const s = net.connect(port, '127.0.0.1');
    s.once('connect', () => { s.destroy(); resolve(); });
    s.once('error', () => { s.destroy(); Date.now() - t0 > ms ? reject(new Error('server did not come up')) : setTimeout(probe, 200); });
  })();
});

const server = spawn(process.platform === 'win32' ? 'python' : 'python3', ['coiserver.py', String(PORT)], { cwd: repoRoot, stdio: 'ignore' });
let browser;
try {
  await waitPort(PORT, 10000);
  browser = await chromium.launch({ headless: !HEADED });
  const page = await browser.newPage();
  page.on('pageerror', e => console.log('  [pageerror]', String(e).slice(0, 200)));
  await page.goto(`http://127.0.0.1:${PORT}/sandpie.html`);
  await page.waitForFunction(() => !!window._sandpieWorker && !!window.opfs, null, { timeout: 30000 });

  // walios needs cross-origin isolation (SharedArrayBuffer) and nothing else: every
  // process runs on its own worker and the kernel serves blocking syscalls
  // asynchronously, so there is no engine flag to enable.
  const env = await page.evaluate(() => ({
    coi: crossOriginIsolated,
    engine: typeof (window.opfs && window.opfs._officeEngine) === 'function',
  }));
  check('page is cross-origin isolated', env.coi);
  check('page exposes the office engine', env.engine);
  if (!env.coi) throw new Error('environment cannot run walios: ' + JSON.stringify(env));

  // Seed the workspace: /root in the guest IS the OPFS root.
  await page.evaluate(async (docxUrl) => {
    const root = await navigator.storage.getDirectory();
    try { await root.removeEntry('e2elab', { recursive: true }); } catch (_) {}
    const dir = await root.getDirectoryHandle('e2elab', { create: true });
    const put = async (n, body) => { const fh = await dir.getFileHandle(n, { create: true }); const w = await fh.createWritable(); await w.write(body); await w.close(); };
    await put('report.docx', await (await fetch(docxUrl)).arrayBuffer());
    await put('data.csv', 'product,units\nvalves,12\nsensors,7\n');
  }, '/' + DOCX);

  // Run one tool call through the real worker and wait for its tool_result.
  const runTool = (name, args, timeoutMs) => page.evaluate(async ([name, args, timeoutMs]) => {
    const id = 'e2e' + Math.random().toString(36).slice(2);
    return await new Promise((resolve) => {
      const t = setTimeout(() => { window._sandpieWorker.removeEventListener('message', h); resolve('TIMED OUT (no tool_result)'); }, timeoutMs);
      const h = (e) => { const d = e.data; if (d && d.type === 'tool_result' && d.id === id) { clearTimeout(t); window._sandpieWorker.removeEventListener('message', h); resolve(d.result); } };
      window._sandpieWorker.addEventListener('message', h);
      window._sandpieWorker.postMessage({ type: 'tool', id, name, args });
    });
  }, [name, args, timeoutMs]);

  const readOpfs = (rel) => page.evaluate(async (rel) => {
    try {
      const parts = rel.split('/'); const name = parts.pop();
      let dir = await navigator.storage.getDirectory();
      for (const p of parts) dir = await dir.getDirectoryHandle(p);
      const f = await (await dir.getFileHandle(name)).getFile();
      const head = new TextDecoder().decode(new Uint8Array(await f.slice(0, 5).arrayBuffer()));
      return { size: f.size, head };
    } catch (e) { return { error: String(e.name || e) }; }
  }, rel);

  // ── 1. the shell tool: soffice --convert-to pdf ───────────────────────────
  console.log('\nwalios shell: soffice --headless --convert-to pdf');
  const shell = await runTool('walios', {
    timeout: 280,
    script: [
      'ls -la /usr/bin/soffice',
      'soffice --headless --convert-to pdf /root/e2elab/report.docx; echo "rc-docx=$?"',
      'soffice --convert-to pdf --outdir /root/e2elab/out /root/e2elab/data.csv; echo "rc-csv=$?"',
      'soffice --convert-to docx /root/e2elab/report.docx; echo "rc-refuse=$?"',
    ].join('\n'),
  }, CONVERT_TIMEOUT_MS);
  console.log('    ' + String(shell).replace(/\n/g, '\n    '));
  check('shell: soffice command exists in the guest', /\/usr\/bin\/soffice/.test(shell) && !/not found/.test(shell), shell);
  check('shell: docx conversion reported success', /rc-docx=0/.test(shell), shell);
  check('shell: csv conversion reported success', /rc-csv=0/.test(shell), shell);
  check('shell: non-pdf target refused', /rc-refuse=2/.test(shell), shell);
  // No --outdir means the CURRENT directory, exactly as real soffice behaves; the
  // shell tool's cwd is /root, so the PDF lands at the workspace root.
  const pdf1 = await readOpfs('report.pdf');
  check('shell: report.pdf is a real PDF at the cwd (soffice default)', pdf1.head === '%PDF-' && pdf1.size > 1000, JSON.stringify(pdf1));
  const pdf2 = await readOpfs('e2elab/out/data.pdf');
  check('shell: --outdir landed data.pdf', pdf2.head === '%PDF-' && pdf2.size > 500, JSON.stringify(pdf2));

  // ── 2. run_python on walios: import soffice ───────────────────────────────
  console.log('\nrun_python (walios backend): import soffice');
  // The worker picks the python backend from the config of an 'agent' run, and sets it
  // as the very first thing it does. There is no other selector, so the test starts an
  // agent run purely to flip that flag and aborts it immediately -- after which a direct
  // run_python tool call routes to the warm walios interpreter instead of Pyodide.
  await page.evaluate(async () => {
    localStorage.setItem('sandpie-python-backend', 'walios');
    window._sandpieWorker.postMessage({ type: 'agent', id: 'backend-select', config: { pythonBackend: 'walios', tools: [] } });
    await new Promise(r => setTimeout(r, 300));
    window._sandpieWorker.postMessage({ type: 'abort', id: 'backend-select' });
    await new Promise(r => setTimeout(r, 500));
  });
  const py = await runTool('run_python', {
    timeout: 280,
    code: [
      'import soffice',
      "out = soffice.convert('/root/e2elab/report.docx', outdir='/root/e2elab/py')",
      'print("converted:", out)',
      'try:',
      "    soffice.convert('/root/e2elab/report.docx', to='html')",
      'except ValueError as e:',
      '    print("refused:", str(e)[:40])',
    ].join('\n'),
  }, CONVERT_TIMEOUT_MS);
  console.log('    ' + String(py).replace(/\n/g, '\n    '));
  check('python: soffice.convert returned the pdf path', /converted: \/root\/e2elab\/py\/report\.pdf/.test(py), py);
  check('python: non-pdf target refused', /refused:/.test(py), py);
  const pdf3 = await readOpfs('e2elab/py/report.pdf');
  check('python: report.pdf is a real PDF in the workspace', pdf3.head === '%PDF-' && pdf3.size > 1000, JSON.stringify(pdf3));

  await page.evaluate(async () => { const r = await navigator.storage.getDirectory(); for (const n of ['e2elab', 'report.pdf']) { try { await r.removeEntry(n, { recursive: true }); } catch (_) {} } });
} catch (e) {
  failed++;
  console.log('  FAIL harness — ' + (e && e.stack || e));
} finally {
  try { await browser?.close(); } catch (_) {}
  try { server.kill(); } catch (_) {}
}

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
