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
    if "--dict" in ARGV:                                                                 # R24-ap: the dictionary as a reading-time source
        import r24_dict as D; D.ON = True; vf = D.verb_forms() - E.NOUNISH; T.SPAN_STOP.update(vf)
        if "--modal-stop" in ARGV: T.SPAN_STOP.update(E.MODALS)                          # R25-t: 'the beaver must' -- a modal ends a name / thing span
        print(f"R24-ap dictionary on: {len(vf)} verb forms end name / thing spans; irregular forms {len(D.EXC)}", flush=True)
    DIAG = "--diag" in ARGV; ROUTES2 = "--routes2" in ARGV; SHAPE = "--shape-keys" in ARGV
    kind = lambda q: q.lower().split()[0]
    import r24_qreader as QR0; QR0.ARGV = list(ARGV)
    if "--store" in ARGV: QR0.STORE.update(json.load(open("r25_store.json", encoding="utf-8"))); print("R25 store loaded:", {k: len(v) for k, v in QR0.STORE.items() if isinstance(v, dict)}, flush=True)                                   # R24-ag2: the flags, captured before a downstream import resets sys.argv
    PRONS = ("it", "them", "him", "her", "he", "she", "they")
    def qslots(q): qs, qf = QR0.qshape(q, names); return [f if isinstance(f, str) else " ".join(f) for x, f in zip(qs, qf) if x in ("PERSON", "ENT") and f and (f if isinstance(f, str) else " ".join(f)).lower() not in PRONS]   # R24-ah2: a pronoun slot names nothing ('he' is inside 'the')
    n_self = sum(1 for s in data[:7000] for q, g in s["qs"] if any(same(g[0], f) for f in qslots(q))); n_all = sum(len(s["qs"]) for s in data[:7000])
    SELF_RATE = n_self / max(1, n_all); print(f"R24-aa: answers that repeat a question slot in the generator: {n_self}/{n_all} = {SELF_RATE:.3f}", flush=True)
    def qshape_nw(q): qs, qf = QR0.qshape(q, names); return tuple(x for x in QR0.abstract_q(qs) if x != "w")
    SELF_BY = collections.defaultdict(lambda: [0, 0])                                   # R24-ab: the same rate per question shape
    for s in data[:7000]:
        for q, g in s["qs"]: k = qshape_nw(q); SELF_BY[k][0] += any(same(g[0], f) for f in qslots(q)); SELF_BY[k][1] += 1
    SELF_SHAPES = {k for k, (r, t) in SELF_BY.items() if t >= 20 and r / t < 0.02}
    lnames = {n.lower() for n in names}
    CLS = json.load(open("r25_classes.json", encoding="utf-8")) if "--classes" in ARGV else E.CLASS     # R25-d: the learner's own refined word groups
    def atype(ans):                                                                      # R24-am: an answer's type: a name, or the induced word class of its head word
        w = [x for x in T.TOK.findall(ans.lower()) if x.isalpha()]
        if not w: return "EMPTY"
        if w[-1] in lnames or ans.split()[-1][:1].isupper(): return "NAME"
        return f"C{CLS[w[-1]]}" if w[-1] in CLS else "UNK"
    TYPES = collections.defaultdict(collections.Counter)                                 # (question shape) -> answer types seen in the generator's gold answers
    for s_ in data[:7000]:
        for q, g in s_["qs"]:
            t_ = atype(g[0]); TYPES[qshape_nw(q)][t_] += 1; TYPES[("kind", kind(q))][t_] += 1
    ALLT = collections.Counter()
    for k_, c_ in TYPES.items():
        if k_[0] == "kind": ALLT.update(c_)
    def type_ok(q, ans):
        for key in (qshape_nw(q), ("kind", kind(q))):
            c = TYPES.get(key)
            if c and sum(c.values()) >= 50:
                t_ = atype(ans); return c[t_] > 0 or ALLT[t_] < 50                       # refused only if this question never takes a type that is common elsewhere
        return True
    OBJ = collections.defaultdict(collections.Counter); SUBJ = collections.defaultdict(collections.Counter)
    if "--selpref" in ARGV:                                                              # R25-e: which of the learner's own groups fill the object / subject slot of each verb group, counted in the books
        RC = json.load(open("r25_classes.json", encoding="utf-8")); DETS = {"the", "a", "an", "his", "her", "their", "my", "our", "your", "its", "some", "this", "that"}
        g = lambda w: RC.get(w.lower())
        for p_ in B.paragraphs(train_b, 150000):
            for sent in T.SENT.split(p_["text"]):
                w = [x for x in T.TOK.findall(sent) if x.isalpha()]
                for i, x in enumerate(w):
                    lx = x.lower()
                    if lx in DETS or lx in T.STOP or not R.is_verb(lx): continue
                    vg = g(E.lemma(lx))
                    if vg is None: continue
                    j = next((j for j in range(i + 1, min(i + 3, len(w))) if w[j].lower() in DETS), None)
                    if j is not None and j + 1 < len(w):
                        h = w[j + 2] if (j + 2 < len(w) and w[j + 2].lower() not in T.STOP and not R.is_verb(w[j + 2].lower()) and g(w[j + 2]) is not None) else w[j + 1]
                        if g(h) is not None: OBJ[vg][g(h)] += 1
                    if i >= 1 and w[i - 1].lower() not in T.STOP and w[i - 1].lower() not in DETS:
                        h = w[i - 1]; key = "NAME" if (h[:1].isupper() and i - 1 > 0) else g(h)
                        if key is not None: SUBJ[vg][key] += 1
        colO = collections.Counter(); colS = collections.Counter()
        for c_ in OBJ.values(): colO.update(c_)
        for c_ in SUBJ.values(): colS.update(c_)
        totO = sum(colO.values()); totS = sum(colS.values())
        print(f"R25-e roles counted from the books: {totO} verb-object and {totS} subject-verb pairs over {len(OBJ)} verb groups", flush=True)
    LIFT = [None]
    def role_ok(q, ans):
        LIFT[0] = None
        qs, qf = QR0.qshape(q, names); k = kind(q); v = next((x[2:] for x in qs if x.startswith("V:")), None)
        if v is None or k not in ("what", "who"): return True
        role = "obj" if (k == "what" and "did" in qs) or (k == "who" and "did" in qs) else ("subj" if k == "who" else None)
        if role is None: return True
        vg = RC.get(v); hw = [x for x in T.TOK.findall(ans) if x.isalpha()]
        if vg is None or not hw: return True
        h = hw[-1]; ng = "NAME" if (h[:1].isupper() and role == "subj") else RC.get(h.lower())
        if ng is None or ng == "NAME": return True
        tab, col, tot = (OBJ, colO, totO) if role == "obj" else (SUBJ, colS, totS)
        row = sum(tab[vg].values()); expected = row * col[ng] / max(1, tot)
        LIFT[0] = (tab[vg][ng] + 0.5) / (expected + 0.5)                                 # R25-s: how much more (or less) often the books pair these groups than chance
        if "--lift-only" in ARGV: return True
        return tab[vg][ng] > 0 or expected < 5                                           # refused only where the books confidently never put this group in this role
    print(f"R24-am answer types learned for {sum(1 for k, c in TYPES.items() if sum(c.values()) >= 50)} question shapes / kinds", flush=True)
    print(f"R24-ab: question shapes whose answer never repeats a question slot: {len(SELF_SHAPES)} of {sum(1 for v in SELF_BY.values() if v[1] >= 20)} with >= 20 evidence", flush=True)
    SOFT = "--soft" in ARGV; ROLE = "--role" in ARGV; RTV, RTA = 0.8, 0.5
    if "--role-json" in ARGV: _rk = json.load(open("r25_soft_k.json", encoding="utf-8")); RTV, RTA = _rk["tv"], _rk["ta"]; print(f"R25-w role reader thresholds from the learner's choice: verb >= {RTV}, args >= {RTA}", flush=True)
    if SOFT or ROLE:
        import r25_soft as S; S.ARGV_SOFT = list(ARGV); PROTOS = S.protos_from(data[:7000]); print(f"R25-i similarity reader on: prototypes for {sorted(PROTOS)}", flush=True)
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
        dissent = None
        if LEARNED_Q and b is not None and QR.LASTQ.get("level") not in ("exact", "noword", "exact-r", "noword-r", "alias"): dissent = b; b = None   # R24-ao: a coarse reading is too weak to answer but still counts against a lone cue answer
        if "--selpref" in ARGV:
            if a is not None and not role_ok(q, a): a = None
            if b is not None and not role_ok(q, b): b = None
        if "--type-check" in ARGV:
            if a is not None and not type_ok(q, a): a = None
            if b is not None and not type_ok(q, b): b = None
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
            if "--state-alone" in ARGV and c is not None:                              # R24-aj: the learned world layer speaks on its own; admission decides whether it is trusted
                return c, ("state-alone" if (a is None and b is None) else "state-vs-reader")
        if ROUTES2:                                                                     # R24-x: no hand routing flags; every single-reader case is a route, admission decides per kind
            st, sm = (S.top(text, q, names, PROTOS) if (SOFT and ql.split()[0] in ("who", "what", "where", "when", "whom")) else (None, 0.0))   # R25-i: the similarity reader as a third vote
            rr = None
            if ROLE:                                                                     # R25-l: the loose role reader (R25-k thresholds chosen by the learner: verb >= 0.8, args >= 0.5)
                ra, rv, ram = S.soft_role(text, q, names); rr = ra if (ra is not None and rv >= RTV and ram >= RTA) else None
            plus = lambda x: ("+soft" if (st is not None and x is not None and same(x, st)) else "") + ("+role" if (rr is not None and x is not None and same(x, rr)) else "")
            if a is not None and b is not None and same(a, b): return a, "agree" + plus(a)
            if b is not None and a is None: return b, "learned-alone-" + ("shape" if R.LAST.get("shape") else (QR.LASTQ.get("level") if LEARNED_Q else "x")) + plus(b)
            if a is not None and b is None:
                if (SOFT or ROLE) and not conf and (same(a, st) or same(a, rr)) and (dissent is None or same(a, dissent)): return a, "cue-alone-loose" + plus(a)   # R25-i: a lone unconfident cue answer the similarity reader also picks
                if "--no-loose" in ARGV and (not conf or (dissent is not None and not same(a, dissent))): return None, "silent"   # R24-ao: the hand cue reader alone answers only when its confidence flag is set and no learned reading dissents
                return a, "cue-alone-" + ("strict" if conf else "loose") + plus(a)
            if a is not None and b is not None: return (b, "disagree-shape") if R.LAST.get("shape") else (None, "disagree")
            if ROLE and rr is not None: return rr, "role-alone" + ("+soft" if (st is not None and same(rr, st)) else "")   # R25-l
            if SOFT and st is not None and sm >= 0.3: return st, "soft-alone"            # R25-i: only the similarity reader speaks, clearly ahead
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
    if "--val-more" in ARGV: stories = stories + json.load(open("val_more.json", encoding="utf-8"))["stories"]
    if "--val-fresh2" in ARGV: stories = stories + json.load(open("val_fresh2.json", encoding="utf-8"))["stories"]     # R25-p: the third, untouched set
    if "--val-practice" in ARGV: stories = stories + json.load(open("val_practice_a.json", encoding="utf-8"))["stories"] + json.load(open("val_practice_b.json", encoding="utf-8"))["stories"]   # R25-u: 400 more practice questions     # R24-al: the second hand-written validation set
    n = matched = right = 0; by = {}; valk = collections.defaultdict(lambda: [0, 0]); valkk = collections.defaultdict(lambda: [0, 0])
    for s in stories:
        for q, g in s["qs"]:
            n += 1; a, how = answer(s["text"], q); by.setdefault(how, [0, 0])
            if DIAG and "--selpref" in ARGV and a is not None: role_ok(q, a)
            if DIAG: print(f"VAL | lift {LIFT[0] if (a is not None and '--selpref' in ARGV) else None} | {q} | gold {g} | cue {E.ask_conf(E.Log(names).read(s['text']), q)} | learned {QR.ask_learned(QRD, rd, s['text'], names, q) if LEARNED_Q else R.ask(rd, s['text'], names, q)} lvl {QR.LASTQ.get('level') if LEARNED_Q else '-'} | route {how} | ans {a} | hit {hit(a, g) if a is not None else '-'}", flush=True)
            if a is not None:
                matched += 1; h = hit(a, g); right += h; by[how][0] += h; by[how][1] += 1; valk[(kind(q), how)][0] += h; valk[(kind(q), how)][1] += 1
                for k in akeys(q, how, a): valkk[k][0] += h; valkk[k][1] += 1
    print(f"R24-k validation ({n} questions): matched {matched}, right {right} (precision {right / max(1, matched):.2f}); by route {by}")
    BAR = collections.defaultdict(lambda: 0.95)
    if "--vs-model" in ARGV:                                                             # R24-ai: the bar is the model's own accuracy on that kind of question (validation), not a hand number
        vm = json.load(open("b6_rwkv_val_ckpt_read1b.json", encoding="utf-8"))["items"]; mk = collections.defaultdict(lambda: [0, 0])
        for x in vm: mk[kind(x["q"])][0] += x["hit"]; mk[kind(x["q"])][1] += 1
        tot_r = sum(v[0] for v in mk.values()); tot_n = sum(v[1] for v in mk.values())
        for k, (r, n) in mk.items(): BAR[k] = (r + 2 * tot_r / tot_n) / (n + 2)        # kinds with few questions shrink toward the model's overall accuracy
        BAR.default_factory = lambda: tot_r / tot_n
        print("R24-ai model accuracy on validation by kind (the admission bar):", {k: f"{mk[k][0]}/{mk[k][1]} -> {BAR[k]:.2f}" for k in mk}, f"| overall {tot_r}/{tot_n}", flush=True)
    admitted = {k for k in set(held) | set(valk) if (held[k][1] + valk[k][1]) >= 8 and (held[k][0] + valk[k][0]) / max(1, held[k][1] + valk[k][1]) > BAR[k[0]]} if "--vs-model" in ARGV else                {k for k in set(held) | set(valk) if (held[k][0] + valk[k][0]) / max(1, held[k][1] + valk[k][1]) >= 0.95}      # R24-q3: pooled precision, held-out and validation together
    pooled = {k: (heldk[k][0] + valkk[k][0], heldk[k][1] + valkk[k][1]) for k in set(heldk) | set(valkk)}
    def admit(q, how, a):
        """R24-y: the finest key with enough evidence (>= 8) decides; precision >= 0.95 admits"""
        if "--disagree" in ARGV:
            w, l = WL[(kind(q), how)]
            if w > l: return True                                                        # this route wins its disagreements with the model
            if l > w: return False                                                       # this route loses them
        if not FINE: return (kind(q), how) in admitted
        for k in akeys(q, how, a):
            r, t = pooled.get(k, (0, 0))
            if len(k) == 2: return k in admitted
            if t >= (20 if SHAPE else 8): return r / t > BAR[k[0]] if "--vs-model" in ARGV else r / t >= 0.95
        return False
    WL = collections.defaultdict(lambda: [0, 0])                                         # R24-ak: per (kind, route), on validation, disagreements with the model won / lost by the reader
    if "--disagree" in ARGV:
        vm2 = json.load(open("b6_rwkv_val_ckpt_read1b.json", encoding="utf-8"))["items"]; i2 = 0
        for s2 in stories:
            for q, g in s2["qs"]:
                a2, how2 = answer(s2["text"], q); mh = vm2[i2]["hit"]; i2 += 1
                if a2 is None: continue
                rh = hit(a2, g)
                if rh and not mh: WL[(kind(q), how2)][0] += 1
                if mh and not rh: WL[(kind(q), how2)][1] += 1
        print("R24-ak disagreements with the model on validation (won, lost) by kind and route:", {f"{k[0]}/{k[1]}": tuple(v) for k, v in WL.items() if sum(v)}, flush=True)
    if FINE: print("R24-y admission keys with >= 8 evidence and precision >= 0.95:", sorted(str(k) for k, (r, t) in pooled.items() if t >= 8 and r / t >= 0.95), flush=True)
    print("R24-p admitted (kind, route):", sorted(admitted), "| validation by kind and route:", {f"{k[0]}/{k[1]}": f"{v[0]}/{v[1]}" for k, v in valk.items()}, flush=True)
    adm_right = adm_n = 0; vmi = json.load(open("b6_rwkv_val_ckpt_read1b.json", encoding="utf-8"))["items"] if "--vs-model" in ARGV else None; vi = 0; v_model = v_merged = 0
    for s in stories:
        for q, g in s["qs"]:
            a, how = answer(s["text"], q); ok = a is not None and admit(q, how, a)
            if ok: adm_n += 1; adm_right += hit(a, g)
            if vmi is not None:
                assert vmi[vi]["q"] == q, (vmi[vi]["q"], q)
                v_model += vmi[vi]["hit"]; v_merged += hit(a, g) if ok else vmi[vi]["hit"]; vi += 1
    if vmi is not None: print(f"R24-ai validation merged (readers where admitted, else model): {v_merged}/{vi} vs model alone {v_model}/{vi} -- gate: merged > model", flush=True)
    print(f"R24-x validation after admission: matched {adm_n}, right {adm_right} (precision {adm_right / max(1, adm_n):.2f})", flush=True)
    if adm_n and adm_right / adm_n >= 0.90:
        tests = json.load(open(os.path.join(ROOT, "tests", "battery", "stories.json"), encoding="utf-8"))["stories"]; rep = json.load(open("b6_rwkv_ckpt_read1b.json", encoding="utf-8"))["items"]; i = 0
        model = merged = spoke = spoke_right = 0
        for s in tests:
            for q, g in s["qs"]:
                x = rep[i]; i += 1; model += x["hit"]; a, how = answer(s["text"], q)
                if DIAG and "--b6-lines" in ARGV: print(f"B6 | {q} | gold {g} | model {x['hit']} | route {how} | ans {a} | admitted {admit(q, how, a) if a is not None else '-'} | hit {hit(a, g) if a is not None else '-'}", flush=True)
                if a is not None and not admit(q, how, a): a = None
                if a is not None: spoke += 1; spoke_right += hit(a, g); merged += hit(a, g)
                else: merged += x["hit"]
        print(f"B6 once (R24-k): model {model} | two readers spoke on {spoke}, right {spoke_right} | merged {merged}/100 (model 80, hand world 82, bar 85)")
    json.dump(dict(matched=matched, right=right, by=by), open("r24_agree_results.json", "w"))


if __name__ == "__main__":
    main()
