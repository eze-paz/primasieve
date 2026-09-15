// End-to-end test: a 127.0.0.1 listener works, so local servers and proxies are possible.
//
// Nothing could bind. listen() handed the port to the WISP relay (OP.LISTEN), but WISP is
// an OUTBOUND transport -- a browser cannot accept inbound TCP -- so the relay refused, and
// because it refused with -98 the guest saw "Address in use" on EVERY port. Measured on
// unused ports in a fresh kernel, three independent stacks agreeing:
//     nc -l -p 9001        -> nc: listen: Address in use
//     python bind(9002)    -> [Errno 98] Address in use
//     tlswrap -L 9443 ...  -> listen: Address in use
// The last one matters because the run_walios description TELLS the model to do exactly
// that ("for TLS on a raw socket run `tlswrap -L LOCALPORT HOST 443`"): a documented
// workflow that could not work.
//
// A loopback listener never needed the relay -- both ends are inside the kernel. It is now
// served there: connections are ordinary socketpairs, so read/write/poll/close all reuse
// the existing spair paths, and accept blocks the way the relay one does, by returning
// EAGAIN for sysAsync's retry loop.
//
// 0.0.0.0 counts as local too. A guest binding "any" in a browser has no "any" available --
// there is no route by which an outside connection could arrive -- so local is the only
// meaning it can have, and it is what makes a plain `nc -l -p N` work.
//
// Fixed alongside it, because loopback was the first thing to reach that path by the
// recvfrom shape: the spair branch of recvmsg/recvfrom read a[1] as a msghdr for BOTH, but
// recvfrom's a[1] is a plain buffer. A recvfrom therefore dereferenced a wild pointer, and
// the resulting exception came back as -1 -- so python's conn.recv() after a local accept
// reported "PermissionError: [Errno 1] Operation not permitted". Its sendto/sendmsg twin
// had always separated the two cases; this side never did.
//
// REQUIREMENTS: walios assets in walios/, ../sandpie-server for wisp.js, playwright.
// Run: node tests/walios/e2e-loopback.mjs
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
process.env.WISP_ALLOW_HOSTS = '*';
process.env.WISP_ALLOW_PORTS = '80,443';
const { attachWisp } = require(path.join(serverRepo, 'wisp.js'));
attachWisp(server, { log: () => {}, warn: () => {}, error: () => {} });

// Heredoc'd python, so no C/shell string survives a trip through JSON and a shell.
const SCRIPT = [
  // NB no backticks in these echoes: the shell runs them as command substitution, and an
  // earlier version of this line quietly executed "nc -l -p N" (bad port) mid-test.
  'echo "=== nc: a plain listener (nc -l -p N binds 0.0.0.0)"',
  'rm -f /tmp/lb.out /tmp/lb.err',
  'nc -l -p 9101 > /tmp/lb.out 2>/tmp/lb.err &',
  'sleep 2',
  'echo "nc_listen_err=[$(cat /tmp/lb.err)]"',
  '( printf "hello-loopback\\n"; sleep 1 ) | nc 127.0.0.1 9101 &',
  'sleep 3; kill %1 %2 2>/dev/null',
  'echo "nc_received=[$(cat /tmp/lb.out 2>/dev/null)]"',
  '',
  'echo "=== python: bind, listen, accept, and BOTH directions of data"',
  'python3 - <<\'PY\'',
  'import socket, threading, time',
  'srv = socket.socket(); srv.bind(("127.0.0.1", 9301)); srv.listen(1)',
  'print("py_bind=ok")',
  'def server():',
  '    conn, addr = srv.accept()',
  '    print("py_accept_ip=" + addr[0])',
  '    print("py_server_got=" + conn.recv(64).decode())',
  '    conn.sendall(b"RESPONSE-BACK")',
  '    conn.close()',
  't = threading.Thread(target=server, daemon=True); t.start()',
  'time.sleep(0.5)',
  'c = socket.socket(); c.settimeout(10); c.connect(("127.0.0.1", 9301))',
  'c.sendall(b"REQUEST-OUT")',
  'try:',
  '    print("py_client_got=" + c.recv(64).decode())',
  'except Exception as e:',
  '    print("py_client_got=FAILED:" + type(e).__name__)',
  'c.close(); t.join(timeout=5)',
  'PY',
  '',
  'echo "=== CONTROL: a port with NO listener must be REFUSED, not accepted and not hung"',
  'echo x | nc 127.0.0.1 9599 > /tmp/ref 2>&1; echo "refused_exit=$?"',
  '',
  'echo "=== CONTROL: a SECOND listener on the same port must really collide"',
  'python3 -c "',
  'import socket',
  'a=socket.socket(); a.bind((\'127.0.0.1\',9302)); a.listen(1)',
  'b=socket.socket()',
  'try:',
  '    b.bind((\'127.0.0.1\',9302)); b.listen(1); print(\'dup_bind=ALLOWED\')',
  'except OSError as e: print(\'dup_bind=refused:\' + str(e.errno))',
  '" 2>&1 | tail -1',
  '',
  'echo "=== CONTROL: outbound still works (the direction that always did)"',
  // wget, not curl: `curl -w` writes nothing to a redirected stdout in this guest (empty
  // output AND empty stderr, rc aside), which is a curl quirk and not what this control is
  // about. The point is only that touching connect() for loopback did not break the
  // OUTBOUND path through the relay, and wget answers that unambiguously.
  'wget -q -O /tmp/ow https://example.com 2>/dev/null; echo "outbound_rc=$? outbound_bytes=$(wc -c < /tmp/ow 2>/dev/null)"',
].join('\n');

// A listener started in ONE call must still be there in the NEXT: that is the whole point
// of a daemon, and it is what makes `tlswrap -L` usable across a sequence of calls.
const SERVE = [
  'rm -f /tmp/srv.log',
  'python3 - > /tmp/srv.log 2>&1 <<\'PY\' &',
  'import socket',
  's = socket.socket(); s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)',
  's.bind(("127.0.0.1", 9401)); s.listen(4)',
  'while True:',
  '    c, _ = s.accept()',
  '    c.recv(64)',
  '    c.sendall(b"HTTP/1.0 200 OK\\r\\n\\r\\nserved-across-calls")',
  '    c.close()',
  'PY',
  'sleep 3',
  'echo "server_started=$(cat /tmp/srv.log)"',
].join('\n');
const FETCH = [
  'printf "GET / HTTP/1.0\\r\\n\\r\\n" | nc 127.0.0.1 9401 > /tmp/got 2>&1',
  'echo "cross_call_body=[$(tail -1 /tmp/got)]"',
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

  const out = await call({ timeout: 180, script: SCRIPT });
  console.log('    ' + String(out).replace(/\n/g, '\n    '));

  check('nc binds a listening port at all (was: Address in use)', /nc_listen_err=\[\]/.test(out), out);
  check('data reaches the nc listener', /nc_received=\[hello-loopback\]/.test(out), out);
  check('python bind+listen succeeds', /py_bind=ok/.test(out), out);
  check('accept reports the peer as loopback', /py_accept_ip=127\.0\.0\.1/.test(out), out);
  check('client -> server data arrives', /py_server_got=REQUEST-OUT/.test(out), out);
  // The reply direction is the half that recvfrom broke: it used to raise EPERM here.
  check('server -> client data arrives (the recvfrom path)', /py_client_got=RESPONSE-BACK/.test(out), out);
  // Without these two, "listen works" would also pass on a kernel that accepted everything
  // and on one that still reported every port as taken.
  check('CONTROL: an unlistened port is refused, not accepted', /refused_exit=[1-9]/.test(out), out);
  check('CONTROL: a duplicate bind gives a REAL EADDRINUSE', /dup_bind=refused:98/.test(out), out);
  check('CONTROL: outbound TLS still works (connect() not regressed)', /outbound_rc=0/.test(out) && /outbound_bytes=[1-9]/.test(out), out);

  const s1 = await call({ timeout: 60, script: SERVE });
  console.log('    ' + String(s1).replace(/\n/g, '\n    '));
  const s2 = await call({ timeout: 60, script: FETCH });
  console.log('    ' + String(s2).replace(/\n/g, '\n    '));
  check('a server started in one call is reachable from the NEXT call',
    /cross_call_body=\[served-across-calls\]/.test(s2), s2);

} finally {
  if (browser) await browser.close();
  server.close();
}
console.log('\n' + passed + ' passed, ' + failed + ' failed');
process.exit(failed ? 1 : 0);
