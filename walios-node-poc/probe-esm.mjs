// Runs probe-esm.html in real Chromium and prints what it found.
//   node walios-node-poc/probe-esm.mjs
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { execSync } from 'node:child_process';

const require = createRequire(import.meta.url);
const { chromium } = require(execSync('npm root -g').toString().trim() + '/playwright');

const PORT = Number(process.env.PORT || 8793);
const server = spawn(process.execPath, [new URL('./serve.mjs', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1')], {
  env: { ...process.env, PORT: String(PORT) },
  stdio: ['ignore', 'pipe', 'pipe'],
});
process.on('exit', () => { try { server.kill(); } catch (_) {} });
await new Promise((r) => setTimeout(r, 900));

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();
page.on('pageerror', (e) => console.log('[pageerror] ' + e));
await page.goto(`http://localhost:${PORT}/walios-node-poc/probe-esm.html`, { waitUntil: 'domcontentloaded' });

let text = '';
const t0 = Date.now();
while (Date.now() - t0 < 20000) {
  await new Promise((r) => setTimeout(r, 300));
  text = await page.evaluate(() => document.getElementById('out').textContent);
  if (text.startsWith('RESULT') || text.startsWith('WORKER ERROR')) break;
}
console.log(text);
await browser.close();
try { server.kill(); } catch (_) {}
process.exit(0);
