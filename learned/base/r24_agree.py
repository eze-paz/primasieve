"""R24-k: two readers, one answer. The cue-built event log (r24_events) and the learned alignment reader (r24_reader)
read every story; a question is answered when both agree (case-blind, head-word match), else by whichever speaks if the
other is silent and that reader's confident flag is set, else not at all. Measured on the 80 validation story
questions; B6 is run once, in front of the 0.4B model, only if validation precision >= 0.90.
Run: python learned/base/r24_agree.py"""
import os, sys, json, random
ARGV = list(sys.argv)
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE)); os.chdir(HERE); sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(ROOT, "learned"))
import r24_tlm as T, r24_events as E, r24_reader as R
import r24_probe as P
from b6_rwkv import hit


def same(a, b):
    if a is None or b is None: return False
    a, b = a.lower().strip(), b.lower().strip()
    return a == b or a.split()[-1] == b.split()[-1] or a in b or b in a


def main():
    data = json.load(open("stories_train_v2.json", encoding="utf-8")); random.Random(24).shuffle(data); names = T.mid_caps([s["text"] for s in data[:7000]])
    import r24_books as B, data as D
    train_b, _ = D.books(); E.induce_verbish([p["text"] for p in B.paragraphs(train_b, 150000)], k=200)
    E.HOLD_RULES.update(json.load(open("r24_hold_results.json"))["rules"])
    DIAG = "--diag" in ARGV; ROUTES2 = "--routes2" in ARGV
    LEARNED_Q = "--learned-q" in ARGV                                                    # R24-v2: the closed-loop readers, no regex anywhere in the reading path
    if LEARNED_Q:
        import r24_qreader as QR
        train, QRD = R.closed_loop_train(data, names)
    else: train = [(s["text"], [a for a in (R.canonical(q, g) for q, g in s["qs"]) if a] + [R.event_statement(e) for e in (s.get("events") or [])]) for s in data[:7000]]
    seqs = [list(R.construction(x, names)[0]) for s in data[:7000] for x in T.SENT.split(s["text"]) if x.strip()]
    CH = R.Chunks(seqs); n6 = int(len(train) * 6 / 7); rd = R.Reader(CH); rd.learn(train[:n6], names, weigh=False); rd.learn(train[n6:], names, weigh=True)
    tabs = (rd.w, rd.wn, rd.eqw, rd.eqn); rd = R.Reader(CH); rd.w, rd.wn, rd.eqw, rd.eqn = tabs; rd.learn(train, names, weigh=False)
    PM, pnames, HM, hnames = P.fit_all()                                                 # R24-q: the learned world layers (place / time / holder)

    def answer(text, q):
        log = E.Log(names).read(text); a, conf = E.ask_conf(log, q); b = QR.ask_learned(QRD, rd, text, names, q) if LEARNED_Q else R.ask(rd, text, names, q)
        if LEARNED_Q and b is not None and QR.LASTQ.get("level") not in ("exact", "noword"): b = None
        ql = q.lower()
        if ql.startswith(("where was ", "who had ", "who was holding ")):
            try: c = P.answer(PM, pnames, HM, hnames, text, q)
            except Exception: c = None
            if c is not None and a is not None and same(a, c): return a, "state-agree"
            if c is not None and b is not None and same(b, c): return b, "state-agree"
        if ROUTES2:                                                                     # R24-x: no hand routing flags; every single-reader case is a route, admission decides per kind
            if a is not None and b is not None and same(a, b): return a, "agree"
            if b is not None and a is None: return b, "learned-alone-" + ("shape" if R.LAST.get("shape") else (QR.LASTQ.get("level") if LEARNED_Q else "x"))
            if a is not None and b is None: return a, "cue-alone-" + ("strict" if conf else "loose")
            if a is not None and b is not None: return (b, "disagree-shape") if R.LAST.get("shape") else (None, "disagree")
            return None, "silent"
        if q.lower().split()[0] == "when": return (b, "learned-when") if b is not None else (None, "silent")       # R24-p2: 'when' is the learned reader's span
        if a is not None and b is not None and same(a, b): return a, "agree"
        if b is not None and R.LAST.get("shape") and q.lower().split()[0] in ("who", "what", "where"): return b, "learned-confident"   # R24-p5: the exact shape decided
        if a is not None and conf and b is None: return a, "cue-confident"
        if a is not None and q.lower().split()[0] in ("why", "when", "how") and conf: return a, "cue-why-when-how"       # R24-k2: slots the learned reader does not have
        if a is not None and b is not None: return None, "disagree"
        return (a, "cue-only") if (a is not None and conf) else (None, "silent")

    import collections
    kind = lambda q: q.lower().split()[0]
    held = collections.defaultdict(lambda: [0, 0])
    for s in data[7000:7600]:
        for q, g in s["qs"]:
            a, how = answer(s["text"], q)
            if a is not None: held[(kind(q), how)][0] += hit(a, g); held[(kind(q), how)][1] += 1
    print("R24-p held-out precision by kind and route:", {f"{k[0]}/{k[1]}": f"{v[0]}/{v[1]} = {v[0] / max(1, v[1]):.2f}" for k, v in held.items()}, flush=True)
    stories = json.load(open("val_stories.json", encoding="utf-8"))["stories"] + json.load(open("val_fables.json", encoding="utf-8"))["stories"] + json.load(open("val_timespace.json", encoding="utf-8"))["stories"]
    n = matched = right = 0; by = {}; valk = collections.defaultdict(lambda: [0, 0])
    for s in stories:
        for q, g in s["qs"]:
            n += 1; a, how = answer(s["text"], q); by.setdefault(how, [0, 0])
            if DIAG: print(f"VAL | {q} | gold {g} | cue {E.ask_conf(E.Log(names).read(s['text']), q)} | learned {QR.ask_learned(QRD, rd, s['text'], names, q) if LEARNED_Q else R.ask(rd, s['text'], names, q)} lvl {QR.LASTQ.get('level') if LEARNED_Q else '-'} | route {how} | ans {a} | hit {hit(a, g) if a is not None else '-'}", flush=True)
            if a is not None: matched += 1; h = hit(a, g); right += h; by[how][0] += h; by[how][1] += 1; valk[(kind(q), how)][0] += h; valk[(kind(q), how)][1] += 1
    print(f"R24-k validation ({n}): matched {matched}, right {right} (precision {right / max(1, matched):.2f}); by route {by}")
    admitted = {k for k in set(held) | set(valk) if (held[k][0] + valk[k][0]) / max(1, held[k][1] + valk[k][1]) >= 0.95}      # R24-q3: pooled precision, held-out and validation together
    print("R24-p admitted (kind, route):", sorted(admitted), "| validation by kind and route:", {f"{k[0]}/{k[1]}": f"{v[0]}/{v[1]}" for k, v in valk.items()}, flush=True)
    adm_right = sum(v[0] for k, v in valk.items() if k in admitted); adm_n = sum(v[1] for k, v in valk.items() if k in admitted)
    print(f"R24-x validation after admission: matched {adm_n}, right {adm_right} (precision {adm_right / max(1, adm_n):.2f})", flush=True)
    if adm_n and adm_right / adm_n >= 0.90:
        tests = json.load(open(os.path.join(ROOT, "tests", "battery", "stories.json"), encoding="utf-8"))["stories"]; rep = json.load(open("b6_rwkv_ckpt_read1b.json", encoding="utf-8"))["items"]; i = 0
        model = merged = spoke = spoke_right = 0
        for s in tests:
            for q, g in s["qs"]:
                x = rep[i]; i += 1; model += x["hit"]; a, how = answer(s["text"], q)
                if DIAG: print(f"B6 | {q} | gold {g} | model {x['hit']} | route {how} | ans {a} | admitted {(kind(q), how) in admitted} | hit {hit(a, g) if a is not None else '-'}", flush=True)
                if a is not None and (kind(q), how) not in admitted: a = None
                if a is not None: spoke += 1; spoke_right += hit(a, g); merged += hit(a, g)
                else: merged += x["hit"]
        print(f"B6 once (R24-k): model {model} | two readers spoke on {spoke}, right {spoke_right} | merged {merged}/100 (model 80, hand world 82, bar 85)")
    json.dump(dict(matched=matched, right=right, by=by), open("r24_agree_results.json", "w"))


if __name__ == "__main__":
    main()
