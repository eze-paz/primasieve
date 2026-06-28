const { spawn } = require('child_process');
const http = require('http');

const PORT = 8765;
const MAX_WAIT = 30000;

function startServer() {
  return new Promise((resolve, reject) => {
    const proc = spawn('node', ['server.js'], { cwd: __dirname, stdio: 'pipe' });
    const timer = setTimeout(() => { proc.kill(); reject(new Error('server start timeout')); }, MAX_WAIT);

    proc.stdout.on('data', d => process.stdout.write(d));
    proc.stderr.on('data', d => process.stderr.write(d));

    // Poll until server responds
    function poll() {
      const req = http.get('http://localhost:' + PORT, (res) => {
        if (res.statusCode === 200) {
          clearTimeout(timer);
          resolve(proc);
        } else {
          setTimeout(poll, 300);
        }
      });
      req.on('error', () => setTimeout(poll, 300));
      req.setTimeout(500, () => req.destroy());
    }
    setTimeout(poll, 500);
  });
}

function runTests() {
  return new Promise((resolve, reject) => {
    const proc = spawn('npx', ['playwright', 'test', 'smoke.spec.js', '--config', 'playwright.config.js', '--reporter=line'], {
      cwd: __dirname,
      stdio: 'inherit',
      shell: true,
    });
    proc.on('close', code => resolve(code));
    proc.on('error', err => reject(err));
  });
}

(async () => {
  let server;
  try {
    console.log('[runner] starting server...');
    server = await startServer();
    console.log('[runner] server up, running smoke...');
    const code = await runTests();
    console.log('[runner] smoke exited with code ' + code);
    server.kill();
    process.exit(code);
  } catch (e) {
    console.error('[runner] failed:', e.message);
    if (server) server.kill();
    process.exit(1);
  }
})();
