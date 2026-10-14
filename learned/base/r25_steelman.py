"""R25-cp: try several answers and argue the best against its strongest rival (R25_prereg.md).
Phase 1 (scores, cached in r25_steelman_scores.json): for each of the 2,510 questions of val_all13.json (the order of
r24_diag_asA.txt), candidates are the story's own word spans; each is put into the question as a statement; its
support = bits(question + statement) - bits(story + question + statement), from the R25-ch network (state carried)
mixed with copy memories of the text read so far keyed by 0, 1 and 2 previous words (fixed weights).
Phase 2: thresholds chosen on the 710 practice questions; reported once on the 1,600 untouched ones.
Run: py -3.12 r25_steelman.py"""
import os, sys, math, json, time, re, collections
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE)); os.chdir(HERE)
V2 = "--v2" in sys.argv; ADAPT = "--adapt" in sys.argv; CACHE = "r26_steelman3_scores.json" if ADAPT else "r25_steelman2_scores.json" if V2 else "r25_steelman_scores.json"
FUNC = set("the a an his her their its my your our this that these those of to in on at by for with from into onto as and or but "
           "was were is are be been had has have did does do not no he she it they we i you him them me us who what where when why "
           "how which whose then so very there here up out off over under near behind after before about".split())
DET = set("the a an his her their its my your our this that these those".split())
PREP = set("on in at to from into onto under near behind by inside outside beside across over through along".split())
AUXDO, AUXBE = {"did", "does", "do"}, {"is", "was", "are", "were"}
words_of = lambda s: [x.lower() for x in re.findall(r"[A-Za-z]+", s)]


def statements(q, cands, verbs):
    qw = words_of(q)
    if len(qw) < 2: return None
    wh, a1 = qw[0], qw[1]
    if wh in ("who", "what"):
        if a1 in AUXDO:                                                                   # object question: subject verb CANDIDATE rest
            rest = qw[2:]; v = next((i for i, w in enumerate(rest) if w in verbs and i > 0), None)
            return [rest[:v + 1] + c + rest[v + 1:] if v is not None else rest + c for c in cands]
        return [c + qw[1:] for c in cands]                                                 # subject question: the wh-word replaced
    if wh in ("where", "when"):
        if a1 in AUXBE: return [qw[2:] + [a1] + c for c in cands]
        if a1 in AUXDO: return [qw[2:] + c for c in cands]
        return [qw[1:] + c for c in cands]
    return None                                                                            # why / how / whose / which: not handled


def candidates(text, q, wh):
    qset = set(words_of(q)); out = []
    for s in re.split(r"(?<=[.!?])\s+", text):
        w = words_of(s)
        for i in range(len(w)):
            for n in range(1, 5):
                c = w[i:i + n]
                if len(c) < n or c[-1] in FUNC: continue
                if c[0] in FUNC and not (c[0] in DET or (wh in ("where", "when") and c[0] in PREP)): continue
                if all(x in qset or x in FUNC for x in c): continue
                if c not in out: out.append(c)
    return out


def phase1():
    sys.argv = ["r25_rnn.py", "--groups", "--oov-groups", "--lookup", "0", "--threads", "4", "--groups-file", "r25_classes_wnx.json"]
    src = open("r25_rnn.py", encoding="utf-8").read(); src = src[:src.index("net = RNet()")]
    R = {"__name__": "r25_rnn_defs", "__file__": os.path.join(HERE, "r25_rnn.py")}; exec(compile(src, "r25_rnn.py", "exec"), R)
    torch, gw, unk2, _uni, _cnt, UNKG, vi = (R[k] for k in "torch gw unk2 _uni _cnt UNKG vi".split())
    import r24_dict as Dct
    verbs = Dct.verb_forms()
    net = R["RNet"](); BASE_SD = torch.load("r25_ch.pt"); net.load_state_dict(BASE_SD); net.eval(); rnn = net.rnn
    LAST = [None]
    def adapt(text):                                                                       # R26 T19: one SGD step on the story itself
        if LAST[0] == text: return
        LAST[0] = text; net.load_state_dict(BASE_SD); ws = words_of(text)
        if len(ws) < 3: return
        ids = torch.tensor([[vi.get(w, 0) for w in ws]]); tg = torch.tensor([gw(w) for w in ws[1:]])
        opt = torch.optim.SGD(net.parameters(), lr=0.3); hs, _ = rnn(net.inp(net.emb(ids)), None)
        loss = torch.nn.functional.cross_entropy(net.out(net.out_ln(hs[0, :-1])), tg); opt.zero_grad(); loss.backward()
        torch.nn.utils.clip_grad_norm_(net.parameters(), 1.0); opt.step()
    share = lambda w, g: (_uni[w] + 0.5) / _cnt[g]
    def wordp(lp_row, w):                                                                  # network probability of word w from a group log-prob row
        g = gw(w); lp = lp_row[g].item()
        return math.exp(lp) * (share(w, g) if g != UNKG else 2 ** -unk2(w))
    WN, WC = 0.7, (0.1, 0.1, 0.1)
    def copyp(mem, hist, w):
        ps = []
        for k in range(3):
            key = tuple(hist[-k:]) if k else ()
            if k and len(hist) < k: ps.append(None); continue
            tot = mem[k].get(("#",) + key, 0)
            ps.append(mem[k].get(key + (w,), 0) / tot if tot else None)
        return ps
    def addmem(mem, hist, w):
        for k in range(3):
            if k and len(hist) < k: continue
            key = tuple(hist[-k:]) if k else ()
            mem[k][key + (w,)] = mem[k].get(key + (w,), 0) + 1; mem[k][("#",) + key] = mem[k].get(("#",) + key, 0) + 1
    def prefix_state(ws):
        ids = torch.tensor([[vi.get(w, 0) for w in ws]])
        with torch.no_grad(): hs, h = rnn(net.inp(net.emb(ids)), None)
        mem = [dict(), dict(), dict()]; hist = []
        for w in ws: addmem(mem, hist, w); hist.append(w)
        return torch.log_softmax(net.out(net.out_ln(hs[0, -1:])), -1)[0], h, mem, hist
    def bits(prefix, stmts):
        lp0, h, mem, hist = prefix_state(prefix); L = max(len(s) for s in stmts)
        ids = torch.zeros((len(stmts), L), dtype=torch.long)
        for i, s in enumerate(stmts): ids[i, :len(s)] = torch.tensor([vi.get(w, 0) for w in s])
        with torch.no_grad():
            hs, _ = rnn(net.inp(net.emb(ids)), h.repeat(1, len(stmts), 1)); lp = torch.log_softmax(net.out(net.out_ln(hs)), -1)
        out = []
        for i, s in enumerate(stmts):
            m2 = [dict(d) for d in mem] if False else mem; added = []; hh = list(hist); b = 0.0
            for k, w in enumerate(s):
                pn = wordp(lp0 if k == 0 else lp[i, k - 1], w); cs = copyp(m2, hh, w)
                wn = WN + sum(WC[j] for j in range(3) if cs[j] is None)
                p = wn * pn + sum(WC[j] * cs[j] for j in range(3) if cs[j] is not None); b -= math.log2(max(p, 1e-30))
                hh.append(w)
            out.append(b)
        return out
    stories = json.load(open("val_all13.json", encoding="utf-8"))["stories"]
    items = [(s["text"], q, g) for s in stories for q, g in s["qs"]]
    L = [l for l in open("r24_diag_asA.txt", encoding="utf-8", errors="replace") if l.startswith("VAL |")]
    assert len(L) == len(items)
    res = []; t0 = time.time()
    for n, ((text, q, gold), l) in enumerate(zip(items, L)):
        assert l.split(" | ")[2].strip() == q.strip(), (n, q)
        route = l.split("| route ")[1].split(" |")[0]; ans = l.split("| ans ")[1].split(" |")[0]; ans = None if ans == "None" else ans
        wh = words_of(q)[0] if words_of(q) else ""
        cs = candidates(text, q, wh)
        if ans and words_of(ans) and words_of(ans) not in cs: cs.append(words_of(ans))
        st = statements(q, cs, verbs) if cs else None
        if not st: res.append(dict(route=route, ans=ans, c=[])); continue
        pre = words_of(text) + words_of(q)
        if ADAPT: adapt(text)
        if V2:                                                                             # R25-cp2: support the candidate gives the question's words
            b_st = bits(pre, st); b_c = bits(pre, cs)
            res.append(dict(route=route, ans=ans, c=[[" ".join(c), round(bc - bs, 4)] for c, bs, bc in zip(cs, b_st, b_c)]))
        else:
            with_story = bits(pre, st); without = bits(words_of(q), st)
            res.append(dict(route=route, ans=ans, c=[[" ".join(c), round(b0 - b1, 4)] for c, b0, b1 in zip(cs, without, with_story)]))
        if n % 250 == 0: print(f"  {n} questions ({time.time() - t0:.0f} s)", flush=True)
    json.dump(res, open(CACHE, "w", encoding="utf-8"))


def phase2():
    from b6_rwkv import hit
    stories = json.load(open("val_all13.json", encoding="utf-8"))["stories"]
    gold = [g for s in stories for _, g in s["qs"]]; res = json.load(open(CACHE, encoding="utf-8"))
    PR = list(range(0, 310)) + list(range(510, 910)); UN = list(range(310, 510)) + list(range(910, 2510))
    def ranked(i):
        c = sorted(res[i]["c"], key=lambda x: -x[1]); return c
    fitr = collections.defaultdict(lambda: [0, 0])
    for i in PR:
        if res[i]["ans"]: fitr[res[i]["route"]][0 if hit(res[i]["ans"], gold[i]) else 1] += 1
    trust = {r for r, (a, w) in fitr.items() if a - 3 * w > 0}
    def decide(i, t1, t2, use_v, use_a):
        r = res[i]; c = ranked(i)
        if r["ans"] and r["route"] in trust:
            if use_v and c:
                mine = next((s for x, s in c if x == " ".join(words_of(r["ans"]))), None)
                rival = max((s for x, s in c if x != " ".join(words_of(r["ans"])) and not hit(x, [" ".join(words_of(r["ans"]))]) and not hit(r["ans"], [x])), default=None)
                if mine is not None and rival is not None and rival - mine > t1: return None
            return r["ans"]
        if use_a and len(c) >= 2 and c[0][1] - c[1][1] > t2: return c[0][0]
        if use_a and len(c) == 1 and t2 == 0: return c[0][0]
        return None
    def fit(idx, *a):
        R_ = W_ = 0
        for i in idx:
            x = decide(i, *a)
            if x is None: continue
            if hit(x, gold[i]): R_ += 1
            else: W_ += 1
        return R_ - 3 * W_, R_, W_
    grid = [0, 1, 2, 3, 4, 6, 8, 12, 16, 1e9]
    base_p, base_u = fit(PR, 0, 0, False, False), fit(UN, 0, 0, False, False)
    t1 = max(grid, key=lambda t: fit(PR, t, 0, True, False)[0]); t2 = max(grid, key=lambda t: fit(PR, 0, t, False, True)[0])
    print(f"R25-cp trust routes chosen on practice: {sorted(trust)}")
    print(f"R25-cp baseline (trust only): practice {base_p}, untouched {base_u}  (fitness, right, wrong)")
    print(f"R25-cp verifier t1 = {t1} (practice): practice {fit(PR, t1, 0, True, False)}, untouched {fit(UN, t1, 0, True, False)}")
    print(f"R25-cp answerer t2 = {t2} (practice): practice {fit(PR, 0, t2, False, True)}, untouched {fit(UN, 0, t2, False, True)}")
    print(f"R25-cp both: practice {fit(PR, t1, t2, True, True)}, untouched {fit(UN, t1, t2, True, True)}")
    top1 = [i for i in UN if res[i]["c"]]; acc = sum(hit(ranked(i)[0][0], gold[i]) for i in top1)
    print(f"R25-cp diagnostic, untouched: questions with a statement {len(top1)} of {len(UN)}; best candidate right {acc} ({acc / max(1, len(top1)):.3f})")


if __name__ == "__main__":
    if not os.path.exists(CACHE) or "--rescore" in sys.argv: phase1()
    phase2()
