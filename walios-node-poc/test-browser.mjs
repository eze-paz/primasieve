const BAR = String.fromCharCode(10) + '================ ';
// Automated browser run: starts the COOP/COEP server, drives headless Chromium via
// Playwright, and prints everything the page and kernel produced.
//
// This is what makes the browser step iterable without a human. The in-app browser
// pane cannot create nested workers from a URL-based worker, which walios needs for
// every process; real Chromium can.
//
//   node walios-node-poc/test-browser.mjs            headless
//   node walios-node-poc/test-browser.mjs --headed   watch it
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { execSync } from 'node:child_process';

const require = createRequire(import.meta.url);
const GLOBAL_ROOT = execSync('npm root -g').toString().trim();
const { chromium } = require(GLOBAL_ROOT + '/playwright');

const PORT = Number(process.env.PORT || 8791);
const HEADED = process.argv.includes('--headed');
const URL_ = `http://localhost:${PORT}/walios-node-poc/`;
const WAIT_MS = Number(process.env.WAIT_MS || 60000);

// ---- server -----------------------------------------------------------------
const server = spawn(process.execPath, [new URL('./serve.mjs', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1')], {
  env: { ...process.env, PORT: String(PORT) },
  stdio: ['ignore', 'pipe', 'pipe'],
});
let serverLog = '';
server.stdout.on('data', (d) => { serverLog += d; });
server.stderr.on('data', (d) => { serverLog += d; });
const stop = () => { try { server.kill(); } catch (_) {} };
process.on('exit', stop);

await new Promise((r) => setTimeout(r, 600));

// ---- browser ----------------------------------------------------------------
const browser = await chromium.launch({ headless: !HEADED });
const ctx = await browser.newContext();
const page = await ctx.newPage();

const console_ = [];
const pageErrors = [];
page.on('console', (m) => console_.push('[' + m.type() + '] ' + m.text()));
page.on('pageerror', (e) => pageErrors.push(String(e && e.stack || e)));
page.on('requestfailed', (r) => console_.push('[netfail] ' + r.url() + ' ' + (r.failure() || {}).errorText));

await page.goto(URL_, { waitUntil: 'domcontentloaded' });

const isolated = await page.evaluate(() => self.crossOriginIsolated);
console.log('crossOriginIsolated:', isolated);
if (!isolated) { console.log('NOT ISOLATED -- SharedArrayBuffer unavailable; check COOP/COEP headers'); }

// Wait for the demo to finish (the page writes "[process exited" when the root exits)
const t0 = Date.now();
let text = '';
while (Date.now() - t0 < WAIT_MS) {
  text = await page.evaluate(() => document.getElementById('out').textContent + '@@SPLIT@@' + document.getElementById('err').textContent);
  if (text.includes('[process exited')) break;
  await new Promise((r) => setTimeout(r, 400));
}
// A unique marker, not a space: splitting on ' ' silently truncated stdout at its
// first space and made every content check read the wrong stream.
const [outText, errText] = text.split('@@SPLIT@@');

console.log('\n================ page stdout ================');
console.log(outText.trimEnd() || '(empty)');
console.log('\n================ page stderr ================');
console.log((errText || '').trimEnd() || '(empty)');

if (pageErrors.length) {
  console.log('\n================ page errors ================');
  for (const e of pageErrors) console.log(e);
}
const interesting = console_.filter((l) => !/^\[log\]\s*$/.test(l));
if (interesting.length) {
  console.log('\n================ console ================');
  for (const l of interesting.slice(0, 60)) console.log(l);
}

// ---- interactive session: `walios:/root$ node` -> REPL ----------------------
// A real pty shell, typed into keystroke by keystroke, exactly as a user would.
const NLc = String.fromCharCode(10);
const page2 = await ctx.newPage();
let replText = '';
await page2.goto(URL_ + '?mode=repl', { waitUntil: 'domcontentloaded' });
const settle = async (ms) => { await new Promise((r) => setTimeout(r, ms)); };
const type = async (s) => { await page2.evaluate((x) => window.__send(x), s + NLc); await settle(1200); };
await settle(2500);                              // let ash come up
await type('node');                              // <- the moment of truth
await settle(2500);                              // node boots (341 modules)
await type('2+2');
await type('const who = "walios-repl"');
await type('who');
await type('require("path").join("/a","b")');
await type('require("fs").readFileSync("/etc/hosts","utf8").trim()');
await type('.exit');
await type('echo BACK-IN-ASH');
await type('exit');
await settle(1200);
replText = await page2.evaluate(() => window.__text());
console.log(BAR + 'interactive pty session' + BAR);

console.log(replText.trimEnd() || '(empty)');
await page2.close();

await browser.close();
stop();

// ---- verdict ----------------------------------------------------------------
const all = outText + errText;
const checks = [
  ['REPL started from ash', /Welcome to walios-node/.test(replText)],
  ['REPL evaluated 2+2', /(^|\s)4(\s|$)/m.test(replText)],
  ['REPL kept a const across lines', /walios-repl/.test(replText)],
  ['REPL require() works', /\/a\/b/.test(replText)],
  ['REPL did real fs I/O', /127\.0\.0\.1/.test(replText)],
  ['.exit returned to ash', /BACK-IN-ASH/.test(replText)],
  ['stub module loaded', /node-stub\.wasm/.test(all)],
  ['node -v printed a version', /v\d+\.\d+\.\d+/.test(outText)],
  ['node -e printed hello', /hello from node/.test(outText)],
  ['busybox read node’s file', /written by node/.test(outText)],
  ['node read ash’s file', /hello-from-ash/.test(outText)],
  ['node script.js ran', /script says: one,two/.test(outText)],
  ['pipe into grep worked', /findme-123/.test(outText)],
  ['&& chaining worked', /&& worked/.test(outText)],
  ['exit code propagated', /exit code was 3/.test(outText)],
  ['echo | node ran stdin as a script', /from-stdin-777/.test(outText)],
  ['node < file ran the redirect', /from-redirect-888/.test(outText)],
  ['npm-lite installed from the real registry', /installed left-pad@1\.3\.0/.test(outText)],
  ['tarball sha512 was verified', /integrity sha512 ok/.test(outText)],
  ['the installed package runs', /\[00000042\]/.test(outText)],
];
console.log('\n================ verdict ================');
let pass = 0;
for (const [name, okc] of checks) { console.log((okc ? '  PASS  ' : '  FAIL  ') + name); if (okc) pass++; }
console.log(`\n${pass}/${checks.length}`);
process.exit(pass === checks.length ? 0 : 1);
