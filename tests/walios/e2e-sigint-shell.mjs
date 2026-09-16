// Repro: after ^C kills a foreground job, does the interactive shell come back?
//
// Reported symptom: `ping google.com` then ^C -- ping DOES die and prints its
// statistics, but no new prompt is ever drawn and nothing typed afterwards runs
// (the tty keeps echoing, so the characters appear, but nobody reads the line).
//
// Two candidates, and the test separates them:
//   A. the shell is signalled too and dies       -> broken for EVERY job
//   B. only handler-carrying jobs leave it stuck -> ping's SIGINT handler is implicated
// `sleep` takes the DEFAULT action for SIGINT; `ping` installs a handler and exits
// on its own. Running both says which.
//
// Run: node tests/walios/e2e-sigint-shell.mjs [--headed]
import { spawn, execSync } from 'node:child_process';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const GLOBAL_ROOT = execSync('npm root -g').toString().trim();
const { chromium } = require(GLOBAL_ROOT + '/playwright');

const PORT = Number(process.env.PORT || 8793);
const WISP_PORT = 6973;
const HEADED = process.argv.includes('--headed');
const win = (u) => new URL(u, import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1');

const server = spawn(process.execPath, [win('../../walios-node-poc/serve.mjs')],
  { env: { ...process.env, PORT: String(PORT) }, stdio: ['ignore', 'pipe', 'pipe'] });
const wisp = spawn(process.execPath, [win('../../../sandpie-server/scripts/wisp-standalone.mjs'), String(WISP_PORT)],
  { cwd: win('../../walios-node-poc/'),
    env: { ...process.env, WISP_ENABLED: '1', WISP_ALLOW_HOSTS: '*', WISP_ALLOW_PORTS: '53,80,443',
           WISP_ALLOW_ORIGINS: 'http://localhost:' + PORT }, stdio: ['ignore', 'pipe', 'pipe'] });
let log = '';
for (const p of [server, wisp]) { p.stdout.on('data', d => { log += d; }); p.stderr.on('data', d => { log += d; }); }
const stop = () => { try { server.kill(); } catch {} try { wisp.kill(); } catch {} };
process.on('exit', stop);

let passed = 0, failed = 0;
const check = (name, cond, detail) => {
  if (cond) { passed++; console.log('  ok   ' + name); }
  else { failed++; console.log('  FAIL ' + name + (detail ? '\n         ' + String(detail).replace(/\n/g, '\n         ') : '')); }
};

const sleep = ms => new Promise(r => setTimeout(r, ms));
let browser;
try {
  await sleep(1500);
  browser = await chromium.launch({ headless: !HEADED });
  const page = await browser.newPage();
  page.on('console', m => { log += '[page] ' + m.text() + '\n'; });
  await page.goto(`http://localhost:${PORT}/walios-node-poc/?mode=repl`);
  await page.waitForFunction(() => window.__text && /walios:/.test(window.__text()), null, { timeout: 60000 });

  const send = s => page.evaluate(x => window.__send(x), s);
  const text = () => page.evaluate(() => window.__text());
  const since = async (mark) => { const t = await text(); const i = t.lastIndexOf(mark); return i < 0 ? t : t.slice(i); };

  // ---- case 1: a job with NO signal handler (default action) ----
  console.log('\n--- case 1: sleep 30 (no SIGINT handler) + ^C ---');
  await send('sleep 30\n'); await sleep(2500);
  await send('\x03');       await sleep(2500);
  await send('echo MARK""ER-A\n'); await sleep(4000);
  const a = await since('sleep 30');
  console.log('    ' + a.replace(/\n/g, '\n    '));
  check('case 1: shell still runs commands after ^C', /^MARKER-A$/m.test(a), a);
  check('case 1: a fresh prompt is drawn after ^C', (a.match(/walios:/g) || []).length >= 1, a);

  // ---- case 2: a job that HANDLES SIGINT itself (ping) ----
  console.log('\n--- case 2: ping (installs a SIGINT handler) + ^C ---');
  await send('ping google.com\n'); await sleep(6000);
  await send('\x03');              await sleep(3000);
  await send('echo MARK""ER-B\n');   await sleep(5000);
  const b = await since('ping google.com');
  console.log('    ' + b.replace(/\n/g, '\n    '));
  check('case 2: ping was actually interrupted (stats printed)', /packet loss/.test(b), b);
  check('case 2: shell still runs commands after ^C', /^MARKER-B$/m.test(b), b);
  check('case 2: a fresh prompt is drawn after the job dies', (b.match(/walios:/g) || []).length >= 1, b);

  console.log('--- page stderr (kernel warnings) ---');
  console.log(await page.evaluate(() => document.getElementById('err').textContent));
} catch (e) {
  console.log('HARNESS ERROR: ' + ((e && e.stack) || e));
  failed++;
} finally {
  if (browser) await browser.close();
  stop();
}
if (failed) console.log('\n--- server/wisp log tail ---\n' + log.slice(-1500));
console.log('\n' + passed + ' passed, ' + failed + ' failed');
process.exit(failed ? 1 : 0);
