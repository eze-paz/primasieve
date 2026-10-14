"""AG (AG_prereg.md): a gradient-trained translator from sentences to symbolic events, trained only on the generator
stories' gold events, then used as the reader of the symbolic world state (World3) on hand-written stories.
Run: py -3.12 ag1_translator.py            (AG1 + AG2)
     py -3.12 ag1_translator.py --heldout  (AG1b: verbs never seen)"""
import os, sys, re, json, time, random, collections
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE))
import numpy as np, torch, torch.nn as nn
import r24_dict as D
torch.manual_seed(0); random.seed(0); np.random.seed(0)
SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'])")
TOK = re.compile(r"[\w'-]+|[^\w\s]")
PRON_A = ("he", "she", "they"); PRON_P = ("it", "them", "him", "her")
ROLES = ["agent", "patient", "place", "recip"]
ATAGS = ["O"] + [f"{b}-{r}" for r in ROLES for b in ("B", "I")]
HELDOUT = {"steal", "borrow", "chase", "drop", "return", "ride"}
IRREG = {"was": "be", "were": "be", "is": "be", "are": "be", "had": "have", "has": "have"}


def lemma(w):
    w = w.lower()
    return IRREG.get(w) or D.verb_base(w) or w


def toks(s): return TOK.findall(s)


def find_span(tokens, phrase):
    """first token span equal to the phrase (case-insensitive), else None"""
    p = [t.lower() for t in toks(phrase)]; low = [t.lower() for t in tokens]
    for i in range(len(low) - len(p) + 1):
        if low[i:i + len(p)] == p: return i, i + len(p)
    return None


def gold_examples(story):
    """(tokens, verb_positions, [(verb_pos, {role: (i, j)})]) per sentence"""
    ss = [x.strip() for x in SENT.split(story["text"]) if x.strip()]; out = []
    per = collections.defaultdict(list)
    for e in story["events"]: per[e[0]].append(e)
    for k, s in enumerate(ss):
        tk = toks(s); low = [t.lower() for t in tk]; used = set(); evs = []
        for e in per.get(k, []):
            lem = e[2]; vp = next((i for i, t in enumerate(tk) if i not in used and lemma(t) == lem), None)
            if vp is None: continue
            used.add(vp); spans = {}
            for role, f in zip(ROLES, (e[1], e[3], e[4], e[5])):
                if not f: continue
                sp = find_span(tk, f)
                if sp is None:
                    prons = PRON_A if role == "agent" else PRON_P if role == "patient" else ()
                    cand = [i for i, t in enumerate(low) if t in prons and (role == "agent" or i > vp)]
                    if cand: sp = (cand[0], cand[0] + 1)
                if sp: spans[role] = sp
            if "agent" in spans: evs.append((vp, spans))
        out.append((tk, evs))
    return out


class Feats:
    def __init__(self, train_sents):
        z = np.load(os.path.join(HERE, "r25_vectors.npz"), allow_pickle=True)
        self.vec = {w: v for w, v in zip(z["vocab"].tolist(), z["vecs"])}; self.dim = z["vecs"].shape[1]
        cnt = collections.Counter(t.lower() for tk in train_sents for t in tk)
        self.wid = {w: i + 2 for i, (w, c) in enumerate(cnt.most_common()) if c >= 2}
        suf = collections.Counter(t.lower()[-3:] for tk in train_sents for t in tk)
        self.sid = {s: i + 2 for i, (s, c) in enumerate(suf.most_common()) if c >= 3}

    def encode(self, tk):
        v = np.stack([self.vec.get(t.lower(), np.zeros(self.dim, dtype=np.float32)) for t in tk]).astype(np.float32)
        w = [self.wid.get(t.lower(), 1) for t in tk]; s = [self.sid.get(t.lower()[-3:], 1) for t in tk]
        cap = [[float(t[0].isupper()), float(i == 0), float(t.lower().endswith("ed")), float(t.lower().endswith("s"))] for i, t in enumerate(tk)]
        return torch.tensor(v), torch.tensor(w), torch.tensor(s), torch.tensor(cap)


class Tagger(nn.Module):
    def __init__(self, F, ntags, marker):
        super().__init__()
        self.wemb = nn.Embedding(len(F.wid) + 2, 32); self.semb = nn.Embedding(len(F.sid) + 2, 16)
        self.marker = marker; self.memb = nn.Embedding(2, 16) if marker else None
        din = F.dim + 32 + 16 + 4 + (16 if marker else 0)
        self.rnn = nn.LSTM(din, 128, num_layers=2, bidirectional=True, batch_first=True, dropout=0.2)
        self.drop = nn.Dropout(0.3); self.out = nn.Linear(256, ntags)

    def forward(self, v, w, s, cap, mark=None):
        x = [v, self.wemb(w), self.semb(s), cap]
        if self.marker: x.append(self.memb(mark))
        h, _ = self.rnn(self.drop(torch.cat(x, -1)).unsqueeze(0)); return self.out(self.drop(h.squeeze(0)))


def train(model, examples, epochs, lr=2e-3):
    opt = torch.optim.Adam(model.parameters(), lr=lr); lossf = nn.CrossEntropyLoss()
    for ep in range(epochs):
        model.train(); random.shuffle(examples); tot = 0
        for ex in examples:
            opt.zero_grad(); logits = model(*ex[:-1]); loss = lossf(logits, ex[-1]); loss.backward(); opt.step(); tot += loss.item()
        print(f"    epoch {ep + 1} loss {tot / len(examples):.4f}", flush=True)
    model.eval()


def build(F, stories):
    """verb examples: (v,w,s,cap, tags01); arg examples: (v,w,s,cap,mark, tags)"""
    vx, ax = [], []
    for st in stories:
        for tk, evs in gold_examples(st):
            if not tk: continue
            enc = F.encode(tk); vt = torch.zeros(len(tk), dtype=torch.long)
            for vp, _ in evs: vt[vp] = 1
            vx.append((*enc, vt))
            for vp, spans in evs:
                mark = torch.zeros(len(tk), dtype=torch.long); mark[vp] = 1; at = torch.zeros(len(tk), dtype=torch.long)
                for role, (i, j) in spans.items():
                    at[i] = ATAGS.index(f"B-{role}")
                    for q in range(i + 1, j): at[q] = ATAGS.index(f"I-{role}")
                ax.append((*enc, mark, at))
    return vx, ax


class Translator:
    """read(sentence) -> [dict(agent, verb, patient, place, recip)]; the reader interface of worldstate.World"""
    def __init__(self, F, vm, am): self.F, self.vm, self.am = F, vm, am; self.last_agent = None; self.last_patient = None

    def spans(self, tk, vp):
        enc = self.F.encode(tk); mark = torch.zeros(len(tk), dtype=torch.long); mark[vp] = 1
        with torch.no_grad(): tags = self.am(*enc, mark).argmax(-1).tolist()
        out = {}; i = 0
        while i < len(tk):
            t = ATAGS[tags[i]]
            if t.startswith("B-"):
                role = t[2:]; j = i + 1
                while j < len(tk) and ATAGS[tags[j]] == f"I-{role}": j += 1
                out.setdefault(role, " ".join(tk[i:j])); i = j
            else: i += 1
        return out

    def events(self, tk):
        if not tk: return []
        with torch.no_grad(): vt = self.vm(*self.F.encode(tk)).argmax(-1).tolist()
        evs = []
        for vp, flag in enumerate(vt):
            if not flag: continue
            sp = self.spans(tk, vp); evs.append((vp, lemma(tk[vp]), sp))
        return evs

    def read(self, s):
        out = []
        for vp, lem, sp in self.events(toks(s)):
            if "agent" in sp: out.append(dict(agent=sp["agent"], verb=lem, patient=sp.get("patient"), place=sp.get("place"), recip=sp.get("recip")))
        return out


def ag1_score(T, stories, only_verbs=None):
    """event-level P/R/F1 (verb lemma, agent, patient, place all equal, surface form); plus verb recall and arg F1 given verb"""
    tp = fp = fn = 0; vtp = vfn = 0; atp = afp = afn = 0
    for st in stories:
        for tk, evs in gold_examples(st):
            gold = {(vp, tk[vp] and lemma(tk[vp]), tuple(" ".join(tk[i:j]) for r in ("agent", "patient", "place") for (i, j) in [sp.get(r, (0, 0))])) for vp, sp in evs}
            if only_verbs is not None: gold = {g for g in gold if g[1] in only_verbs}
            pred = T.events(tk) if gold or only_verbs is None else []
            pred = {(vp, lem, tuple(sp.get(r, "") for r in ("agent", "patient", "place"))) for vp, lem, sp in pred if only_verbs is None or lem in only_verbs}
            tp += len(gold & pred); fp += len(pred - gold); fn += len(gold - pred)
            gv = {g[0] for g in gold}; pv = {p[0] for p in pred}; vtp += len(gv & pv); vfn += len(gv - pv)
            for vp, sp in evs:                                                       # argument F1 given the gold verb position
                if only_verbs is not None and lemma(tk[vp]) not in only_verbs: continue
                g = {(r, " ".join(tk[i:j])) for r, (i, j) in sp.items()}; p = set(T.spans(tk, vp).items())
                atp += len(g & p); afp += len(p - g); afn += len(g - p)
    P = tp / max(1, tp + fp); R = tp / max(1, tp + fn); F = 2 * P * R / max(1e-9, P + R)
    aP = atp / max(1, atp + afp); aR = atp / max(1, atp + afn); aF = 2 * aP * aR / max(1e-9, aP + aR)
    return dict(event_P=round(P, 4), event_R=round(R, 4), event_F1=round(F, 4), verb_recall=round(vtp / max(1, vtp + vfn), 4), arg_F1=round(aF, 4), n_gold=tp + fn)


def ag2(T):
    import r25_world3 as W3
    from b6_rwkv import hit
    stories = json.load(open(os.path.join(HERE, "val_all13.json"), encoding="utf-8"))["stories"]; out = []; t0 = time.time()
    for k, s in enumerate(stories):
        W = W3.World3(T)
        try: W.read(s["text"])
        except Exception as e: print("read error", s.get("id"), e, flush=True)
        for q, g in s["qs"]:
            try: out.append(W.ask(q))
            except Exception: out.append(None)
        if k % 100 == 0: print(f"  {k} stories ({time.time() - t0:.0f} s)", flush=True)
    json.dump(out, open(os.path.join(HERE, "ag2_answers.json"), "w", encoding="utf-8"))
    gold = [g for s in stories for _, g in s["qs"]]
    PR = list(range(0, 310)) + list(range(510, 910)); UN = list(range(310, 510)) + list(range(910, 2510))
    def st(idx):
        r = w = 0
        for i in idx:
            if out[i] is not None: r += bool(hit(out[i], gold[i])); w += not hit(out[i], gold[i])
        return r, w, r - 3 * w
    rp, wp, fp_ = st(PR); ru, wu, fu = st(UN)
    print(f"AG2 world alone, translator reader: practice {rp} / {wp} / {fp_}, untouched {ru} / {wu} / {fu}  (right / wrong / fitness); W3 hand 26 / 22, W4 role 40 / 30 untouched", flush=True)
    # policy: trusted reader routes, world fills silent questions (same as r25_world2.report)
    L = [l for l in open(os.path.join(HERE, "r24_diag_asA.txt"), encoding="utf-8", errors="replace") if l.startswith("VAL |")]
    route = [l.split("| route ")[1].split(" |")[0] for l in L]; ans = [l.split("| ans ")[1].split(" |")[0] for l in L]; ans = [None if a == "None" else a for a in ans]
    fr = collections.defaultdict(lambda: [0, 0])
    for i in PR:
        if ans[i]: fr[route[i]][0 if hit(ans[i], gold[i]) else 1] += 1
    trust = {r for r, (a, w) in fr.items() if a - 3 * w > 0}; use = fp_ > 0
    def policy(idx):
        r = w = 0
        for i in idx:
            x = ans[i] if (ans[i] and route[i] in trust) else (out[i] if use else None)
            if x is None: continue
            r += bool(hit(x, gold[i])); w += not hit(x, gold[i])
        return r - 3 * w, r, w
    print(f"AG2 policy (world trusted on practice: {use}): practice {policy(PR)}, untouched {policy(UN)} vs +288 baseline", flush=True)
    return dict(practice=(rp, wp, fp_), untouched=(ru, wu, fu), policy_untouched=policy(UN))


def main():
    t0 = time.time(); heldout = "--heldout" in sys.argv
    data = [s for s in json.load(open(os.path.join(HERE, "stories_train_v2.json"), encoding="utf-8")) if s.get("events")]
    random.Random(0).shuffle(data); train_s, dev_s, test_s = data[:2240], data[2240:2520], data[2520:]
    if heldout:
        train_s = [s for s in train_s if not any(e[2] in HELDOUT for e in s["events"])]
        print(f"AG1b: training stories without {sorted(HELDOUT)}: {len(train_s)}", flush=True)
    F = Feats([tk for st in train_s for tk, _ in gold_examples(st)])
    vx, ax = build(F, train_s); print(f"train sentences {len(vx)}, events {len(ax)} ({time.time() - t0:.0f} s)", flush=True)
    vm = Tagger(F, 2, False); am = Tagger(F, len(ATAGS), True)
    print("verb tagger", flush=True); train(vm, vx, 4 if "--heldout" not in sys.argv else 2)
    print("argument tagger", flush=True); train(am, ax, 4 if "--heldout" not in sys.argv else 2)
    T = Translator(F, vm, am)
    print(f"AG1 dev  {ag1_score(T, dev_s)}", flush=True)
    res = ag1_score(T, test_s); print(f"AG1 test {res}  ({time.time() - t0:.0f} s)", flush=True)
    if heldout:
        print(f"AG1b held-out verbs on test {ag1_score(T, test_s, HELDOUT)}", flush=True); return
    torch.save(dict(vm=vm.state_dict(), am=am.state_dict()), os.path.join(HERE, "ag1_translator.pt"))
    r2 = ag2(T); print(f"done ({time.time() - t0:.0f} s)", flush=True)
    json.dump(dict(ag1_test=res, ag2=r2), open(os.path.join(HERE, "ag_results.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
