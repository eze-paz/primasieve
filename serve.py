from http.server import HTTPServer, SimpleHTTPRequestHandler
import urllib.request, urllib.error, os, webbrowser

PORT = 8080

class H(SimpleHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Headers', '*')
        self.end_headers()

    def do_GET(self):
        if self.path.startswith('/proxy/'):
            return self._proxy('GET', None)
        super().do_GET()

    def do_POST(self):
        if not self.path.startswith('/proxy/'):
            return self.send_error(404)
        body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
        self._proxy('POST', body)

    def _proxy(self, method, body):
        req = urllib.request.Request('https://' + self.path[7:], data=body, method=method)
        req.add_header('User-Agent', 'Mozilla/5.0 CountAIned/1.0')
        for h in ('Content-Type', 'Authorization'):
            if self.headers.get(h):
                req.add_header(h, self.headers[h])
        try:
            resp = urllib.request.urlopen(req)
        except urllib.error.HTTPError as e:
            resp = e
        self.send_response(resp.status)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Content-Type', resp.headers.get('Content-Type', 'application/octet-stream'))
        self.end_headers()
        while chunk := resp.read1(8192):
            self.wfile.write(chunk)
            self.wfile.flush()

os.chdir(os.path.dirname(os.path.abspath(__file__)))
print(f'Serving at http://localhost:{PORT}')
webbrowser.open(f'http://localhost:{PORT}')
HTTPServer(('127.0.0.1', PORT), H).serve_forever()
