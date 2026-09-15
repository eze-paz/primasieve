// End-to-end test: the deadline SUSPENDS the run; the next call resumes the same work.
//
// It used to kill it. The deadline called killall, which kept the filesystem but destroyed
// the RUN -- and `./configure` is not resumable, so a build that ran out of budget started
// over from zero every time. The only way round it was to background the job yourself
// (`( ./configure ... ) &`) and poll, which is the wrong tool to hand a model: a
// backgrounded job you are not watching. (Backgrounding itself is ALLOWED and useful --
// a daemon is meant to outlive its call; see check 4 -- the deadline just no longer forces
// you to reach for it.)
//
// Underneath, walios' job control was COSMETIC. SIG_STOPPERS set P.stopped and told the
// parent (so ^Z printed "Stopped" and gave back the prompt) but the child never stopped:
// contWaiters was initialised and drained by SIGCONT, and NOTHING ever pushed to it, so no
// code path ever waited for one. Measured before the fix -- a `kill -STOP` on a busy job:
//     before_stop=9652  after_stop=20944  still_later=32532     FROZEN=NO
// and after, on the same probe:
//     before_stop=4290  after_stop=4298   still_later=4298      FROZEN=yes
// The async delivery path now parks on contWaiters, so the syscall does not return until
// SIGCONT. The SYNC twin cannot await, so a process spinning in pure computation parks at
// its next BLOCKING syscall rather than instantly -- which is why the host still kills
// anything that fails to park, instead of reporting a suspension that did not happen.
//
// THE TWO CHECKS THAT MATTER:
//  - the resumed call finishes the SAME command (a re-run would replay its start), and
//  - the work was really FROZEN in between, not left running. A test that only checked
//    "it finished" would pass just as well on the backgrounding this replaces.
//
// REQUIREMENTS: walios assets in walios/, ../sandpie-server for wisp.js, playwright.
// Run: node tests/walios/e2e-suspend-resume.mjs
import { createRequire } from 'node:module';
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const serverRepo = path.resolve(repoRoot, '..', 'sandpie-server');

const ASSETS = ['wali-worker.js', 'wali-proc-worker.js', 'opfs-worker.js', 'wisp-worker.js',
  'busybox.wasm', 'rootfs.tar.gz'];
const missing = ASSETS.filter(a => !fs.existsSync(path.join(repoRoot, 'walios', a)));
if (missing.length) { console.log('SKIP: walios assets missing - ' + missing.join(', ')); process.exit(0); }
if (!fs.existsSync(path.join(serverRepo, 'wisp.js'))) { console.log('SKIP: ../sandpie-server/wisp.js not found'); process.exit(0); }

const require = createRequire(import.meta.url);
let chromium;
try { ({ chromium } = require('playwright')); }
catch (_) { console.log('SKIP: playwright not installed'); process.exit(0); }

let passed = 0, failed = 0;
const check = (name, cond, detail) => {
  if (cond) { passed++; console.log('  ok  ' + name); }
  else { failed++; console.log('  FAIL ' + name + (detail ? '\n        ' + String(detail).replace(/\n/g, '\n        ') : '')); }
};

const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.json': 'application/json',
  '.css': 'text/css', '.wasm': 'application/wasm', '.gz': 'application/gzip', '.pem': 'text/plain' };
const server = http.createServer((req, res) => {
  const rel = decodeURIComponent(req.url.split('?')[0]).replace(/^\/+/, '') || 'sandpie.html';
  const file = path.join(repoRoot, rel);
  if (!file.startsWith(repoRoot) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) { res.writeHead(404); res.end('nf'); return; }
  res.writeHead(200, { 'content-type': MIME[path.extname(file)] || 'application/octet-stream',
    'cross-origin-opener-policy': 'same-origin', 'cross-origin-embedder-policy': 'require-corp',
    'cross-origin-resource-policy': 'cross-origin', 'cache-control': 'no-store' });
  fs.createReadStream(file).pipe(res);
});
process.env.WISP_ENABLED = '1';
const { attachWisp } = require(path.join(serverRepo, 'wisp.js'));
attachWisp(server, { log: () => {}, warn: () => {}, error: () => {} });

// A loop bounded by COUNT, not by time, stamping wall-clock seconds each tick. Bounded by
// count so that if it were merely left RUNNING it would finish during the gap; and stamped
// so the gap itself is visible in the data the resumed run prints.
const WORK = [
  'rm -rf /tmp/sus; mkdir -p /tmp/sus',
  'echo RUN-STARTED',
  'i=0',
  'while [ $i -lt 15 ]; do i=$((i+1)); date +%s >> /tmp/sus/stamps; sleep 1; done',
  'echo SAME-RUN-FINISHED',
  // The largest gap between consecutive ticks. While parked, no tick is written, so the
  // suspension shows up here as a jump of roughly the wall time between the two calls.
  'awk \'NR>1{d=$1-p; if(d>m)m=d} {p=$1} END{print "MAXGAP="m}\' /tmp/sus/stamps',
  'echo "TICKS=$(wc -l < /tmp/sus/stamps)"',
].join('\n');

let browser;
try {
  await new Promise((r) => server.listen(0, '127.0.0.1', r));
  browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  await page.goto('http://127.0.0.1:' + server.address().port + '/sandpie.html');
  await page.waitForFunction(() => !!window._sandpieWorker, null, { timeout: 30000 });

  const call = (args) => page.evaluate(async (args) => {
    const id = 'e2e' + Math.random().toString(36).slice(2);
    return await new Promise((resolve) => {
      const t = setTimeout(() => resolve('HARNESS TIMEOUT'), 200000);
      const h = (e) => { const d = e.data; if (d && d.type === 'tool_result' && d.id === id) { clearTimeout(t); window._sandpieWorker.removeEventListener('message', h); resolve(d.result); } };
      window._sandpieWorker.addEventListener('message', h);
      window._sandpieWorker.postMessage({ type: 'tool', id, name: 'walios', args });
    });
  }, args);

  // 1. Run it with a deadline it cannot meet (15 ticks x 1s = ~15s, cap 6s).
  // NB busybox sleep takes whole seconds only -- fractional made the loop finish instantly
  // and never reach the deadline at all.
  const a = await call({ timeout: 6, script: WORK });
  console.log('  [call 1]\n    ' + String(a).replace(/\n/g, '\n    '));
  check('the deadline reports a SUSPENSION, not a kill', /SUSPENDED/.test(a), a);
  check('it says how to continue', /resume:true/.test(a), a);
  check('partial output from before the deadline comes back', /RUN-STARTED/.test(a), a);
  check('the run had NOT finished when it was suspended', !/SAME-RUN-FINISHED/.test(a), a);

  // Wall-clock gap while parked. Nothing may advance during this.
  const gapStart = Date.now();
  await new Promise((r) => setTimeout(r, 9000));
  const gapSec = Math.round((Date.now() - gapStart) / 1000);

  // 2. Resume: no script at all.
  const b = await call({ timeout: 60, resume: true });
  console.log('  [call 2, after a ' + gapSec + 's gap]\n    ' + String(b).replace(/\n/g, '\n    '));
  check('resume finishes the SAME run', /SAME-RUN-FINISHED/.test(b), b);
  // A fresh run would replay the start; the resumed one must not.
  check('resume did NOT restart the script', !/RUN-STARTED/.test(b), b);
  check('all 15 ticks are present (no work was lost)', /TICKS=15/.test(b), b);

  // THE control. Without it this suite would pass on the backgrounding it replaces: a job
  // left RUNNING would also finish and also show 30 ticks -- but with no gap in its stamps.
  const m = /MAXGAP=(\d+)/.exec(String(b));
  check('CONTROL: the work was really FROZEN while suspended (stamp gap ~= the pause)',
    !!m && Number(m[1]) >= 5, m ? 'MAXGAP=' + m[1] + 's over a ' + gapSec + 's pause' : b);

  // 3. MULTI-CYCLE. The real case suspends more than once: a ~700s ./configure against a
  //    300s cap needs three calls, i.e. it is suspended, resumed, suspended AGAIN and
  //    resumed again. One cycle working proves nothing about the second -- a resume that
  //    forgot to re-arm the deadline, or left k.suspended false, would pass every check
  //    above and still make the feature useless for the thing it was built for.
  const LONG = [
    'rm -rf /tmp/sus2; mkdir -p /tmp/sus2',
    'echo CYCLE-RUN-STARTED',
    'i=0',
    'while [ $i -lt 24 ]; do i=$((i+1)); echo $i >> /tmp/sus2/n; sleep 1; done',
    'echo CYCLE-RUN-FINISHED',
    'echo "COUNT=$(wc -l < /tmp/sus2/n)"',
  ].join('\n');
  const c1 = await call({ timeout: 6, script: LONG });
  check('cycle 1 suspends', /SUSPENDED/.test(c1) && !/CYCLE-RUN-FINISHED/.test(c1), c1);
  const c2 = await call({ timeout: 6, resume: true });
  check('cycle 2 resumes and suspends AGAIN', /SUSPENDED/.test(c2) && !/CYCLE-RUN-FINISHED/.test(c2), c2);
  const c3 = await call({ timeout: 6, resume: true });
  check('cycle 3 resumes and suspends a THIRD time', /SUSPENDED/.test(c3) && !/CYCLE-RUN-FINISHED/.test(c3), c3);
  const c4 = await call({ timeout: 90, resume: true });
  console.log('  [final resume]\n    ' + String(c4).replace(/\n/g, '\n    '));
  check('a run survives THREE suspensions and finishes', /CYCLE-RUN-FINISHED/.test(c4), c4);
  check('no work was lost across the cycles', /COUNT=24/.test(c4), c4);

  // 4. A BACKGROUNDED JOB DOES OUTLIVE THE CALL -- deliberately. This briefly did the
  //    opposite: the root exiting reaped everything, to stop `&` being used to dodge the
  //    deadline. That killed the legitimate case with it. A daemon is precisely a thing
  //    meant to outlive the command that starts it (a local proxy, a server the next call
  //    talks to), and suspending the deadline already removed the REASON to background a
  //    long build. Nothing is unbounded: the kernel is dropped 10 min after the last call.
  const bg = await call({ timeout: 20, script: [
    'rm -f /tmp/bgtick',
    '( while true; do echo x >> /tmp/bgtick; sleep 1; done ) &',
    'sleep 2',
    'echo "LAUNCHED size=$(wc -c < /tmp/bgtick)"',
  ].join('\n') });
  check('a backgrounded job runs during its own call', /LAUNCHED size=[1-9]/.test(bg), bg);
  await new Promise((r) => setTimeout(r, 5000));
  const bgAfter = await call({ timeout: 20, script: [
    'a=$(wc -c < /tmp/bgtick 2>/dev/null)',
    'sleep 3',
    'b=$(wc -c < /tmp/bgtick 2>/dev/null)',
    'echo "after_call=$a later=$b"',
    'kill %1 2>/dev/null; pkill -f bgtick 2>/dev/null; true',
  ].join('\n') });
  const mb = /after_call=(\d+) later=(\d+)/.exec(String(bgAfter));
  check('it SURVIVES the call that started it (daemons are allowed)',
    !!mb && Number(mb[1]) > 0, mb ? mb[0] : bgAfter);
  check('and it is still making progress in the later call',
    !!mb && Number(mb[2]) > Number(mb[1]), mb ? mb[0] : bgAfter);

  // 5. A suspended run must not be left parked forever: sending a script abandons it.
  const c = await call({ timeout: 20, script: 'echo NEW-SCRIPT-RAN' });
  check('a new script runs normally', /NEW-SCRIPT-RAN/.test(c), c);
  const d = await call({ timeout: 20, resume: true });
  check('CONTROL: resuming with nothing suspended is an error, not a hang',
    /no suspended run/i.test(d), d);

} finally {
  if (browser) await browser.close();
  server.close();
}
console.log('\n' + passed + ' passed, ' + failed + ' failed');
process.exit(failed ? 1 : 0);
