"""LOCALHOST UI for the English chat -- renders the scene and lets you talk to the engine in a browser.

    python en_server.py            # http://127.0.0.1:8765

Stdlib only. Single-user demo server: the scene and the pending clarification live in module state.
The engine behind it is exactly en_chat.py -- meanings learned by elimination, four responses forced by the
commit rule (COMMIT / ASK / UNKNOWABLE / ABSTAIN). Nothing about the answer logic is special-cased for the UI.
"""
import os, sys, json, random, http.server, socketserver
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE)); sys.path.insert(0, HERE)
import en_world as W
import en_chat as C

PORT = int(os.environ.get("PORT", "8765"))
STATE = {"scene": None, "lex": None, "pending": None, "log": []}


def new_scene(n=5):
    STATE["scene"] = W.rand_scene(random.Random(random.randrange(10 ** 6)), n)
    STATE["pending"] = None
    STATE["log"] = []


def scene_json():
    sc = STATE["scene"]
    return [{"i": i, "x": o[0][0], "y": o[0][1], "w": o[0][2] - o[0][0], "h": o[0][3] - o[0][1],
             "colour": W.COLOURS[o[1]], "css": W.CSS[W.COLOURS[o[1]]], "props": W.true_unary(o)}
            for i, o in enumerate(sc)]


def say(text):
    sc, lex = STATE["scene"], STATE["lex"]
    pend = STATE["pending"]
    if pend and text.strip().lower() in ("yes", "no", "y", "n"):
        p, cands = pend
        want = text.strip().lower().startswith("y")
        cands = [i for i in cands if W.unary_holds(p, sc[i]) == want]
        if len(cands) == 1:
            STATE["pending"] = None
            return {"kind": "COMMIT", "msg": f"object #{cands[0]}", "highlight": cands}
        if not cands:
            STATE["pending"] = None
            return {"kind": "NONE", "msg": "then nothing matches.", "highlight": []}
        q = C.best_question(sc, cands)
        if q is None:
            STATE["pending"] = None
            return {"kind": "UNKNOWABLE", "msg": f"still {cands}; nothing separates them.", "highlight": cands}
        STATE["pending"] = (q, cands)
        return {"kind": "ASK", "msg": f"narrowed to {cands}. Next: is it {q}?", "highlight": cands}
    q = W.parse(text, lex)
    kind, msg, cands = C.answer(sc, q, lex)
    STATE["pending"] = (C.best_question(sc, cands), cands) if kind == "ASK" else None
    return {"kind": kind, "msg": msg, "highlight": cands or [],
            "parsed": {"adjectives": q["left"], "relation": q["rel"], "second": q["right"],
                       "unknown": q["unknown"]}}


PAGE = """<!doctype html><meta charset=utf-8><title>primasieve</title>
<style>
 body{font:14px/1.5 system-ui,sans-serif;margin:0;background:#0f1115;color:#e6e6e6}
 .wrap{max-width:900px;margin:0 auto;padding:20px}
 h1{font-size:16px;font-weight:600;margin:0 0 4px} .sub{color:#8b93a7;margin-bottom:16px}
 .row{display:flex;gap:20px;align-items:flex-start;flex-wrap:wrap}
 #grid{background:#171a21;border:1px solid #262b36;border-radius:8px;position:relative;width:360px;height:360px}
 .obj{position:absolute;border-radius:3px;display:flex;align-items:center;justify-content:center;
      font-size:11px;color:#0008;font-weight:700;transition:outline .15s}
 .hl{outline:3px solid #fff;outline-offset:2px}
 #chat{flex:1;min-width:320px}
 #log{height:300px;overflow:auto;background:#171a21;border:1px solid #262b36;border-radius:8px;padding:10px}
 .m{margin:6px 0} .you{color:#9ecbff} .k{font-weight:700;margin-right:6px}
 .COMMIT{color:#4ade80}.ASK{color:#fbbf24}.ABSTAIN{color:#f87171}.UNKNOWABLE{color:#c084fc}.NONE{color:#8b93a7}
 input{width:100%;padding:9px;margin-top:8px;background:#171a21;color:#e6e6e6;
       border:1px solid #262b36;border-radius:6px;font:inherit}
 button{margin-top:8px;padding:7px 12px;background:#262b36;color:#e6e6e6;border:0;border-radius:6px;cursor:pointer}
 .legend{color:#8b93a7;font-size:12px;margin-top:10px}
 .k{padding:1px 6px;border-radius:4px;background:#ffffff10}
</style>
<div class=wrap>
<h1>primasieve</h1>
<div class=sub>Type real English. It answers only when exactly one thing matches &mdash; otherwise it asks,
reports what is unknowable, or refuses on a word it never learned.</div>
<div class=row>
  <div><div id=grid></div><button onclick="newScene()">new scene</button></div>
  <div id=chat>
    <div id=log></div>
    <input id=inp placeholder="the big red one   /   is the tall blue one above the small green square"
           autofocus onkeydown="if(event.key==='Enter'){event.preventDefault();send()}">
    <button onclick="send()">send</button>
    <div class=legend id=leg></div>
  </div>
</div></div>
<script>
let S=[];
function draw(hl){const g=document.getElementById('grid');g.innerHTML='';
 S.forEach(o=>{const d=document.createElement('div');d.className='obj'+((hl||[]).includes(o.i)?' hl':'');
  d.style.left=(o.x/12*100)+'%';d.style.top=(o.y/12*100)+'%';
  d.style.width=(o.w/12*100)+'%';d.style.height=(o.h/12*100)+'%';d.style.background=o.css;
  d.textContent='#'+o.i;d.title=o.props.join(' ');g.appendChild(d)})}
function add(cls,txt){const l=document.getElementById('log');
 l.innerHTML+=`<div class="m"><span class="k ${cls}">${cls}</span>${txt}</div>`;l.scrollTop=l.scrollHeight}
async function newScene(){const r=await fetch('/api/new',{method:'POST'});const j=await r.json();
 S=j.scene;draw([]);document.getElementById('log').innerHTML='';
 document.getElementById('leg').textContent='words it learned: '+j.words.join(', ')}
async function send(){const i=document.getElementById('inp');const t=i.value.trim();if(!t)return;i.value='';
 document.getElementById('log').innerHTML+=`<div class="m you">you&gt; ${t}</div>`;
 const r=await fetch('/api/say',{method:'POST',body:JSON.stringify({text:t})});const j=await r.json();
 add(j.kind,j.msg);draw(j.highlight)}
newScene();
</script>"""


class H(http.server.BaseHTTPRequestHandler):
    # HTTP/1.1 + a THREADING server. The first version used single-threaded TCPServer, and one aborted
    # keep-alive connection from the browser wedged it: GET still worked from the already-open socket while
    # every later POST queued forever behind it. The logic was never slow (build 0.2s, say 0.00s) -- it was
    # the transport. Worth recording because "the page loads but nothing responds" reads like an app bug.
    protocol_version = "HTTP/1.1"

    def log_message(self, *a): pass

    def _send(self, code, body, ctype="application/json"):
        b = body.encode() if isinstance(body, str) else body
        self.send_response(code); self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        if self.path in ("/", "/index.html"): self._send(200, PAGE, "text/html; charset=utf-8")
        else: self._send(404, "{}")

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n).decode() if n else "{}"
        if self.path == "/api/new":
            new_scene()
            self._send(200, json.dumps({"scene": scene_json(), "words": sorted(STATE["lex"])}))
        elif self.path == "/api/say":
            self._send(200, json.dumps(say(json.loads(raw).get("text", ""))))
        else:
            self._send(404, "{}")


if __name__ == "__main__":
    print("learning the English vocabulary by elimination ...")
    _, lex, _ = C.build()
    STATE["lex"] = lex
    print(f"  learned {len(lex)} words")
    new_scene()
    http.server.ThreadingHTTPServer.allow_reuse_address = True
    with http.server.ThreadingHTTPServer(("127.0.0.1", PORT), H) as srv:
        print(f"  serving http://127.0.0.1:{PORT}")
        srv.serve_forever()
