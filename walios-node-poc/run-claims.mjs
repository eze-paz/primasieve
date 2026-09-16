// Drive the REAL walios terminal (same backend as the run_walios tool) and run
// claims.sh in it. The poc page is not good enough here: it boots a bare kernel
// without the bin set the backend manifest mounts, so every `prog-*` claim would
// read as missing for the wrong reason.
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
const require = createRequire(import.meta.url);
const { execSync } = require('node:child_process');
const { chromium } = require(execSync('npm root -g').toString().trim() + '/playwright');

const ORIGIN = process.env.ORIGIN || 'https://sandpie.gasn2cloud.com';
const tok = readFileSync('.prod-token', 'utf8').trim();
const browser = await chromium.launch({ headless: !process.argv.includes('--headed') });
const ctx = await browser.newContext();
await ctx.addCookies([{ name: 'sp_session', value: tok, domain: new URL(ORIGIN).hostname, path: '/', httpOnly: true, secure: true, sameSite: 'Lax' }]);
const page = await ctx.newPage();
page.on('pageerror', (e) => console.log('[pageerror] ' + e));
await page.goto(ORIGIN + '/walios/terminal.html', { waitUntil: 'domcontentloaded' });
console.log('crossOriginIsolated:', await page.evaluate(() => self.crossOriginIsolated));

const settle = (ms) => new Promise((r) => setTimeout(r, ms));
await settle(12000);                                  // busybox + ash come up (a cold page is slower)
await page.mouse.click(400, 300);                     // focus the terminal
// Fetch over the guest's own TCP stack rather than typing the whole script in:
// xterm keystroke injection is slow and mangles quoting.
await page.keyboard.type('wget -qO /tmp/c.sh ' + ORIGIN + '/walios-node-poc/' + (process.env.SCRIPT || 'claims.sh') + ' && sh /tmp/c.sh');
await page.keyboard.press('Enter');

const read = () => page.evaluate(() => (document.body.innerText || ''));
const t0 = Date.now();
let text = '';
while (Date.now() - t0 < 420000) {
  await settle(1500);
  text = await read();
  if (text.includes(process.env.DONE || 'CLAIMS-DONE')) break;
}
const i = text.indexOf(process.env.MARK || '=== FAILURES ===');
console.log(i < 0 ? '--- raw tail ---' + String.fromCharCode(10) + text.slice(-3000) : text.slice(i));
await browser.close();
process.exit(0);
