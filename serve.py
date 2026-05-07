from http.server import HTTPServer, SimpleHTTPRequestHandler
import http.client, urllib.parse, os, sys, webbrowser, subprocess, json

PORT = 8080
SHELL_CWD = os.path.dirname(os.path.abspath(__file__))
SHELL_TIMEOUT_MAX = 120
ALLOWED_ORIGINS = {
    'http://localhost:8080',
    'http://127.0.0.1:8080',
    'https://gasn2cloud.com',
}
# Cloud-mode hardening (set in production via env vars):
#   SANDPIE_NO_SHELL=1        → /shell endpoint returns 404 (disables RCE on a public host)
#   SANDPIE_RESTRICT_PROXY=1  → /proxy/* requires Origin header in ALLOWED_ORIGINS when present
SHELL_ENABLED = os.environ.get('SANDPIE_NO_SHELL', '') != '1'
RESTRICT_PROXY = os.environ.get('SANDPIE_RESTRICT_PROXY', '') == '1'

class H(SimpleHTTPRequestHandler):
    # Hop-by-hop + routing headers we must not forward; everything else passes through verbatim.
    # accept-encoding is skipped so upstream returns identity-encoded bodies that the browser
    # can parse directly (we don't forward Content-Encoding back, so otherwise responses would
    # arrive gzipped but tagged as plain JSON, mangling the parse).
    _SKIP = {'host', 'content-length', 'connection', 'keep-alive',
             'proxy-authenticate', 'proxy-authorization', 'te', 'trailers',
             'transfer-encoding', 'upgrade', 'cookie', 'accept-encoding'}

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', '*')
        self.end_headers()

    def do_GET(self):
        if self.path.startswith('/proxy/'):
            return self._proxy('GET', None)
        super().do_GET()

    def do_POST(self):
        if self.path == '/shell':
            if not SHELL_ENABLED:
                return self.send_error(404)
            return self._shell()
        if not self.path.startswith('/proxy/'):
            return self.send_error(404)
        body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
        self._proxy('POST', body)

    def _proxy(self, method, body):
        if RESTRICT_PROXY:
            origin = self.headers.get('Origin')
            # Allow if no Origin (non-browser clients, same-origin GETs that omit it).
            # Reject only when Origin is present and not in our allowlist.
            if origin and origin not in ALLOWED_ORIGINS:
                return self.send_error(403, f'Origin not allowed: {origin}')
        parsed = urllib.parse.urlparse('https://' + self.path[7:])
        path = parsed.path or '/'
        if parsed.query: path += '?' + parsed.query
        # http.client preserves header name casing (urllib does not).
        headers = {k: v for k, v in self.headers.items() if k.lower() not in self._SKIP}
        with open('proxy.log', 'a', encoding='utf-8') as _log:
            _log.write(f'[proxy] {method} {parsed.netloc}{path}\n')
            for k, v in headers.items():
                short = v if len(v) < 80 else v[:77] + '...'
                _log.write(f'        {k}: {short}\n')
            _log.flush()
        conn = http.client.HTTPSConnection(parsed.netloc, timeout=120)
        try:
            conn.request(method, path, body, headers)
            resp = conn.getresponse()
            self.send_response(resp.status)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Content-Type', resp.getheader('Content-Type', 'application/octet-stream'))
            self.end_headers()
            while True:
                chunk = resp.read1(8192)
                if not chunk: break
                self.wfile.write(chunk)
                self.wfile.flush()
        finally:
            conn.close()

    def _shell(self):
        origin = self.headers.get('Origin')
        if origin not in ALLOWED_ORIGINS:
            return self._json(403, {'error': f'Origin not allowed: {origin!r}'})
        try:
            body = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))))
        except Exception as e:
            return self._json(400, {'error': f'bad json: {e}'})
        cmd = (body.get('cmd') or '').strip()
        if not cmd:
            return self._json(400, {'error': 'missing cmd'})
        cwd = body.get('cwd') or SHELL_CWD
        timeout = min(int(body.get('timeout', 30)), SHELL_TIMEOUT_MAX)
        with open('proxy.log', 'a', encoding='utf-8') as _log:
            _log.write(f'[shell] {cmd!r} (cwd={cwd}, timeout={timeout})\n')
            _log.flush()
        # Use Popen so we can forcibly kill the WHOLE process tree on timeout.
        # subprocess.run's built-in timeout only kills cmd.exe / sh on Windows
        # / Linux respectively — children (find, dir, etc.) keep running and
        # the proxy thread blocks waiting for their pipes to close.
        kwargs = dict(shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                      text=True, cwd=cwd)
        if sys.platform == 'win32':
            kwargs['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kwargs['start_new_session'] = True  # equivalent of preexec_fn=os.setsid
        try:
            proc = subprocess.Popen(cmd, **kwargs)
        except Exception as e:
            return self._json(500, {'error': f'spawn failed: {e}'})
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
            self._json(200, {'stdout': stdout, 'stderr': stderr, 'code': proc.returncode, 'cwd': cwd})
        except subprocess.TimeoutExpired:
            # Kill the whole tree, then collect whatever was buffered before.
            try:
                if sys.platform == 'win32':
                    subprocess.run(['taskkill', '/F', '/T', '/PID', str(proc.pid)],
                                   capture_output=True, timeout=5)
                else:
                    import signal
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except Exception:
                pass
            try:
                stdout, stderr = proc.communicate(timeout=2)
            except Exception:
                stdout, stderr = '', ''
            self._json(200, {
                'stdout': stdout or '',
                'stderr': (stderr or '') + f'\n(timeout after {timeout}s — process tree killed)',
                'code': -1, 'cwd': cwd,
            })
        except Exception as e:
            try: proc.kill()
            except Exception: pass
            self._json(500, {'error': str(e)})

    def _json(self, status, obj):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

os.chdir(os.path.dirname(os.path.abspath(__file__)))
print(f'Serving at http://localhost:{PORT}  (shell cwd: {SHELL_CWD})')
# Bootstrap: when running as a downloaded standalone script (no sandpie.html
# alongside us), fetch the latest copy from the public deployment so the page
# can be served same-origin from localhost:8080 — eliminates CORS entirely.
# Set SANDPIE_BOOTSTRAP=0 to skip (cloud deploy does this; Apache serves the
# page from htdocs and doesn't need a local /opt/sandpie/sandpie.html).
SANDPIE_URL = os.environ.get('SANDPIE_URL', 'https://gasn2cloud.com/sdk/sandpie.html')
if not os.path.isfile('sandpie.html') and os.environ.get('SANDPIE_BOOTSTRAP', '1') != '0':
    import urllib.request
    try:
        print(f'Bootstrap: fetching {SANDPIE_URL}')
        with urllib.request.urlopen(SANDPIE_URL, timeout=15) as r:
            with open('sandpie.html', 'wb') as f: f.write(r.read())
        print(f'  → saved sandpie.html')
    except Exception as e:
        print(f'  bootstrap failed: {e} (page will not be served locally)')
if os.path.isfile('sandpie.html'):
    webbrowser.open(f'http://localhost:{PORT}/sandpie.html')
HTTPServer(('127.0.0.1', PORT), H).serve_forever()
