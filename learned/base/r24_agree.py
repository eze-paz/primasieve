"""R24-k: two readers, one answer. The cue-built event log (r24_events) and the learned alignment reader (r24_reader)
read every story; a question is answered when both agree (case-blind, head-word match), else by whichever speaks if the
other is silent and that reader's confident flag is set, else not at all. Measured on the 80 validation story
questions; B6 is run once, in front of the 0.4B model, only if validation precision >= 0.90.
Run: python learned/base/r24_agree.py"""
import os, sys, json, random, collections
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
    DIAG = "--diag" in ARGV; ROUTES2 = "--routes2" in ARGV; SHAPE = "--shape-keys" in ARGV
    import r24_qreader as QR0
    def qslots(q): qs, qf = QR0.qshape(q, names); return [f if isinstance(f, str) else " ".join(f) for x, f in zip(qs, qf) if x in ("PERSON", "ENT") and f]
    n_self = sum(1 for s in data[:7000] for q, g in s["qs"] if any(same(g[0], f) for f in qslots(q))); n_all = sum(len(s["qs"]) for s in data[:7000])
    SELF_RATE = n_self / max(1, n_all); print(f"R24-aa: answers that repeat a question slot in the generator: {n_self}/{n_all} = {SELF_RATE:.3f}", flush=True)
    def qshape_nw(q): qs, qf = QR0.qshape(q, names); return tuple(x for x in QR0.abstract_q(qs) if x != "w")
    SELF_BY = collections.defaultdict(lambda: [0, 0])                                   # R24-ab: the same rate per question shape
    for s in data[:7000]:
        for q, g in s["qs"]: k = qshape_nw(q); SELF_BY[k][0] += any(same(g[0], f) for f in qslots(q)); SELF_BY[k][1] += 1
    SELF_SHAPES = {k for k, (r, t) in SELF_BY.items() if t >= 20 and r / t < 0.02}
    print(f"R24-ab: question shapes whose answer never repeats a question slot: {len(SELF_SHAPES)} of {sum(1 for v in SELF_BY.values() if v[1] >= 20)} with >= 20 evidence", flush=True)
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
        if SELF_RATE < 0.02 or ("--self-shapes" in ARGV and qshape_nw(q) in SELF_SHAPES):   # R24-aa/ab: a learned fact about questions: the answer is not something the question already names
            sl = qslots(q)
            if a is not None and any(same(a, f) for f in sl): a = None
            if b is not None and any(same(b, f) for f in sl): b = None
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

    kind = lambda q: q.lower().split()[0]
    FINE = "--fine" in ARGV or SHAPE                                                     # R24-y: admission keys with back-off, scored on pooled evidence
    def akeys(q, how, a):
        """finest to coarsest admission keys for an answer: question shape, whether the answer repeats a question slot, whether it is a name"""
        if not FINE: return [(kind(q), how)]
        import r24_qreader as Q2
        qs, qf = Q2.qshape(q, names); shape = tuple(x for x in Q2.abstract_q(qs) if x != "w")
        in_q = any(f and same(a, f if isinstance(f, str) else " ".join(f)) for x, f in zip(qs, qf) if x in ("PERSON", "ENT")); is_name = a.split()[-1][:1].isupper()
        if SHAPE: return [(kind(q), how, shape), (kind(q), how)]                        # R24-aa: the question shape only, with >= 20 evidence
        return [(kind(q), how, shape, in_q, is_name), (kind(q), how, in_q, is_name), (kind(q), how)]
    held = collections.defaultdict(lambda: [0, 0]); heldk = collections.defaultdict(lambda: [0, 0])
    for s in data[7000:7600]:
        for q, g in s["qs"]:
            a, how = answer(s["text"], q)
            if a is not None:
                held[(kind(q), how)][0] += hit(a, g); held[(kind(q), how)][1] += 1
                for k in akeys(q, how, a): heldk[k][0] += hit(a, g); heldk[k][1] += 1
    print("R24-p held-out precision by kind and route:", {f"{k[0]}/{k[1]}": f"{v[0]}/{v[1]} = {v[0] / max(1, v[1]):.2f}" for k, v in held.items()}, flush=True)
    stories = json.load(open("val_stories.json", encoding="utf-8"))["stories"] + json.load(open("val_fables.json", encoding="utf-8"))["stories"] + json.load(open("val_timespace.json", encoding="utf-8"))["stories"]
    n = matched = right = 0; by = {}; valk = collections.defaultdict(lambda: [0, 0]); valkk = collections.defaultdict(lambda: [0, 0])
    for s in stories:
        for q, g in s["qs"]:
            n += 1; a, how = answer(s["text"], q); by.setdefault(how, [0, 0])
            if DIAG: print(f"VAL | {q} | gold {g} | cue {E.ask_conf(E.Log(names).read(s['text']), q)} | learned {QR.ask_learned(QRD, rd, s['text'], names, q) if LEARNED_Q else R.ask(rd, s['text'], names, q)} lvl {QR.LASTQ.get('level') if LEARNED_Q else '-'} | route {how} | ans {a} | hit {hit(a, g) if a is not None else '-'}", flush=True)
            if a is not None:
                matched += 1; h = hit(a, g); right += h; by[how][0] += h; by[how][1] += 1; valk[(kind(q), how)][0] += h; valk[(kind(q), how)][1] += 1
                for k in akeys(q, how, a): valkk[k][0] += h; valkk[k][1] += 1
    print(f"R24-k validation ({n}): matched {matched}, right {right} (precision {right / max(1, matched):.2f}); by route {by}")
    admitted = {k for k in set(held) | set(valk) if (held[k][0] + valk[k][0]) / max(1, held[k][1] + valk[k][1]) >= 0.95}      # R24-q3: pooled precision, held-out and validation together
    pooled = {k: (heldk[k][0] + valkk[k][0], heldk[k][1] + valkk[k][1]) for k in set(heldk) | set(valkk)}
    def admit(q, how, a):
        """R24-y: the finest key with enough evidence (>= 8) decides; precision >= 0.95 admits"""
        if not FINE: return (kind(q), how) in admitted
        for k in akeys(q, how, a):
            r, t = pooled.get(k, (0, 0))
            if len(k) == 2: return k in admitted
            if t >= (20 if SHAPE else 8): return r / t >= 0.95
        return False
    if FINE: print("R24-y admission keys with >= 8 evidence and precision >= 0.95:", sorted(str(k) for k, (r, t) in pooled.items() if t >= 8 and r / t >= 0.95), flush=True)
    print("R24-p admitted (kind, route):", sorted(admitted), "| validation by kind and route:", {f"{k[0]}/{k[1]}": f"{v[0]}/{v[1]}" for k, v in valk.items()}, flush=True)
    adm_right = adm_n = 0
    for s in stories:
        for q, g in s["qs"]:
            a, how = answer(s["text"], q)
            if a is not None and admit(q, how, a): adm_n += 1; adm_right += hit(a, g)
    print(f"R24-x validation after admission: matched {adm_n}, right {adm_right} (precision {adm_right / max(1, adm_n):.2f})", flush=True)
    if adm_n and adm_right / adm_n >= 0.90:
        tests = json.load(open(os.path.join(ROOT, "tests", "battery", "stories.json"), encoding="utf-8"))["stories"]; rep = json.load(open("b6_rwkv_ckpt_read1b.json", encoding="utf-8"))["items"]; i = 0
        model = merged = spoke = spoke_right = 0
        for s in tests:
            for q, g in s["qs"]:
                x = rep[i]; i += 1; model += x["hit"]; a, how = answer(s["text"], q)
                if DIAG: print(f"B6 | {q} | gold {g} | model {x['hit']} | route {how} | ans {a} | admitted {admit(q, how, a) if a is not None else '-'} | hit {hit(a, g) if a is not None else '-'}", flush=True)
                if a is not None and not admit(q, how, a): a = None
                if a is not None: spoke += 1; spoke_right += hit(a, g); merged += hit(a, g)
                else: merged += x["hit"]
        print(f"B6 once (R24-k): model {model} | two readers spoke on {spoke}, right {spoke_right} | merged {merged}/100 (model 80, hand world 82, bar 85)")
    json.dump(dict(matched=matched, right=right, by=by), open("r24_agree_results.json", "w"))


if __name__ == "__main__":
    main()
