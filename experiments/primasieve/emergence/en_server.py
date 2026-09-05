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
import wn_acquire as ACQ
import en_actions as ACT
import random as _r

PORT = int(os.environ.get("PORT", "8765"))
STATE = {"scene": None, "lex": None, "alex": None, "pending": None, "acquire": None,
         "last_ref": None, "log": []}


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
    acq = STATE["acquire"]
    # ---- confirming (or rejecting) a WordNet PROPOSAL. Unconfirmed proposals are DISCARDED. ----
    if acq and text.strip().lower() in ("yes", "no", "y", "n"):
        word, pred, original = acq
        STATE["acquire"] = None
        if not text.strip().lower().startswith("y"):
            return {"kind": "ABSTAIN", "msg": f"understood - '{word}' stays unknown and I will keep "
                                              f"refusing it.", "highlight": []}
        if isinstance(pred, tuple) and pred[0] == "ACTION":
            STATE["alex"][word] = pred[1]
        else:
            lex[word] = pred
        r = say(original)                      # re-run the sentence now that the word is known
        r["msg"] = f"learned: '{word}' = {pred}. " + r["msg"]
        return r
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
    toks = W.tokenize(text)
    alex = STATE["alex"]
    # ---- COMMAND: an action word turns this into a request to CHANGE the world ----
    act = next((t for t in toks if t in alex), None)
    if act:
        rest = " ".join(t for t in toks if t != act)
        if "it" in W.tokenize(rest) and STATE["last_ref"] is not None:
            tgt = [STATE["last_ref"]]
        else:
            qq = W.parse(rest, lex)
            if qq["unknown"]:
                return _diagnose(qq["unknown"], text)
            tgt = C.referents(sc, qq["left"]) if qq["left"] else []
        if len(tgt) != 1:
            if not tgt:
                return {"kind": "NONE", "msg": "I cannot tell which object you mean.", "highlight": []}
            p = C.best_question(sc, tgt)
            STATE["pending"] = (p, tgt)
            return {"kind": "ASK", "msg": f"which one? {len(tgt)} match {tgt}. Is it {p}?", "highlight": tgt}
        i = tgt[0]
        before = sc
        STATE["scene"] = ACT.OPS[alex[act]](sc, i)
        STATE["last_ref"] = None
        return {"kind": "COMMIT", "msg": f"done - {act} applied to object #{i} "
                                         f"({alex[act]}). {len(before)} -> {len(STATE['scene'])} objects.",
                "highlight": [], "scene": scene_json()}
    q = W.parse(text, lex)
    # ---- ACQUIRE: an unknown word is not a dead end. WordNet PROPOSES; the engine still has to ask. ----
    if q["unknown"]:
        return _diagnose(q["unknown"], text)
    kind, msg, cands = C.answer(sc, q, lex)
    STATE["pending"] = (C.best_question(sc, cands), cands) if kind == "ASK" else None
    if kind == "COMMIT" and cands: STATE["last_ref"] = cands[0]
    return {"kind": kind, "msg": msg, "highlight": cands or [],
            "parsed": {"adjectives": q["left"], "relation": q["rel"], "second": q["right"],
                       "unknown": q["unknown"]}}


def _diagnose(unknown, original):
    """Three DIFFERENT failures were all reported as one generic refusal. Separate them:
       1. a describable word WordNet can bridge to something known  -> ACQUIRE, ask to confirm
       2. an action word WordNet can bridge to a known operation    -> ACQUIRE, ask to confirm
       3. a word with no possible meaning in this world             -> say so plainly, which is different
          from not knowing the word at all.
    """
    lex, alex = STATE["lex"], STATE["alex"]
    for uw in unknown:
        props = ACQ.propose(uw, list(lex))                       # describable?
        if props:
            STATE["acquire"] = (uw, lex[props[0][0]], original)
            return {"kind": "ACQUIRE", "msg": f"I have never learned '{uw}'. WordNet suggests it may mean "
                                              f"'{props[0][0]}'. Is that right?", "highlight": []}
        aprops = ACQ.propose(uw, list(alex), pos_order=("verb",), hops=0)   # an action? STRICT synonymy
        if aprops:
            STATE["acquire"] = (uw, ("ACTION", alex[aprops[0][0]]), original)
            return {"kind": "ACQUIRE", "msg": f"I have never learned '{uw}'. WordNet relates it to "
                                              f"'{aprops[0][0]}', which I know as an action. Is that right?",
                    "highlight": []}
    known_any = [uw for uw in unknown
                 if ACQ.related_words(uw, "noun") or ACQ.related_words(uw, "verb")
                 or ACQ.related_words(uw, "adj")]
    props = ", ".join(sorted(set(lex.values()))[:6])
    acts = ", ".join(sorted(set(alex)))
    if known_any:
        return {"kind": "OUT-OF-WORLD",
                "msg": f"I know {known_any} are real words, but nothing in my world could be their meaning. "
                       f"I can only describe things ({props} ...) and do these actions ({acts}).",
                "highlight": []}
    return {"kind": "ABSTAIN", "msg": f"I have never seen {unknown} anywhere, and WordNet has no entry. "
                                      f"I will not guess.", "highlight": []}


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
 .ACQUIRE{color:#38bdf8}.OUT-OF-WORLD{color:#94a3b8}
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
 if(j.scene){S=j.scene}
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
    alex, _ = ACT.learn_actions(ACT.training(400, _r.Random(4)))
    STATE["alex"] = alex
    print(f"  learned {len(lex)} property words and {len(alex)} action words")
    new_scene()
    http.server.ThreadingHTTPServer.allow_reuse_address = True
    with http.server.ThreadingHTTPServer(("127.0.0.1", PORT), H) as srv:
        print(f"  serving http://127.0.0.1:{PORT}")
        srv.serve_forever()
