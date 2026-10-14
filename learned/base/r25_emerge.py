"""R25-cu-t: verb effect classes emerge from the next-word game (R25_prereg.md). Events 'AGENT VERB DET THING' from the
training books; the judge is the determiner class of THING's next mention later in the paragraph. Verbs are grouped into
K classes by alternating assignment; K chosen on a held-out 10% of training books; scored once on the held-out books.
Run: py -3.12 r25_emerge.py"""
import os, sys, re, math, time, collections
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE)); os.chdir(HERE)
import data as D0, r24_dict as Dct
t0 = time.time()
POSS = {"his", "her", "their", "my", "its", "our", "your"}
DETS = POSS | {"the", "a", "an"}
FUNC = set("the a an his her their my its our your this that these those of to in on at by for with from and or but not no he she it they we i you him them me us was were is are be been had has have did does do".split())
def dclass(tok): return 0 if (tok in POSS or tok.endswith("'s")) else 1 if tok == "the" else 2 if tok in ("a", "an") else 3
SENT = re.compile(r"(?<=[.!?])\s+")
TOK = re.compile(r"[A-Za-z]+(?:'s)?")
vb = {}
def base(w):
    if w not in vb: vb[w] = Dct.verb_base(w) if Dct.mainly_verb(w) else None
    return vb[w]


def events(bid):
    out = []
    for para in D0.read(bid).split("\n"):
        sents = SENT.split(para.replace(chr(8217), "'"))
        toks = []; starts = set()
        for s in sents:
            ts = TOK.findall(s); starts.add(len(toks)); toks += ts
        low = [t.lower() for t in toks]
        for i in range(len(toks) - 3):
            a, v, d, th = toks[i], low[i + 1], low[i + 2], low[i + 3]
            if not (low[i] in ("he", "she", "they") or (toks[i][0].isupper() and i not in starts and low[i] not in FUNC)): continue
            if d not in DETS or th in FUNC or not th.isalpha() or len(th) < 3 or base(th): continue
            b = base(v)
            if not b or b in ("be", "have", "do"): continue
            nxt = next((j for j in range(i + 4, len(low)) if low[j] == th), None)
            if nxt is None or nxt == 0: continue
            out.append((b, dclass(d), dclass(low[nxt - 1])))
    return out


tr, te = D0.books()
dev = tr[::10]; fit = [b for b in tr if b not in set(dev)]
E = {}
for name, ids in (("fit", fit), ("dev", dev), ("test", te)):
    E[name] = [e for b in ids for e in events(b)]
    print(f"R25-cu-t {name}: {len(ids)} books, {len(E[name])} events ({time.time() - t0:.0f} s)", flush=True)
cnt = collections.Counter(v for v, _, _ in E["fit"]); verbs = sorted(v for v, c in cnt.items() if c >= 30)
vi = {v: i for i, v in enumerate(verbs)}
print(f"R25-cu-t {len(verbs)} verbs with 30+ events", flush=True)
def table(evs, key, smooth=1.0):
    t = collections.defaultdict(lambda: [smooth] * 4)
    for v, de, dn in evs: t[key(v, de)][dn] += 1
    return {k: [x / sum(c) for x in c] for k, c in t.items()}
def bits(evs, prob):
    return sum(-math.log2(prob(v, de)[dn]) for v, de, dn in evs) / len(evs)
prior = table(E["fit"], lambda v, de: de)
def p_prior(v, de): return prior.get(de, [0.25] * 4)
# per-verb reference (backs off to the prior for verbs outside the list)
pv_t = table([e for e in E["fit"] if e[0] in vi], lambda v, de: (v, de))
def p_verb(v, de): return pv_t.get((v, de), p_prior(v, de)) if v in vi else p_prior(v, de)
# learned classes
byverb = collections.defaultdict(list)
for e in E["fit"]:
    if e[0] in vi: byverb[e[0]].append(e)
possshare = {v: sum(1 for _, _, dn in byverb[v] if dn == 0) / len(byverb[v]) for v in verbs}
def learn(K):
    order = sorted(verbs, key=lambda v: possshare[v]); cls = {v: min(K - 1, i * K // len(order)) for i, v in enumerate(order)}
    for it in range(30):
        em = table([e for e in E["fit"] if e[0] in cls], lambda v, de: (cls[v], de))
        new = {v: min(range(K), key=lambda k: -sum(math.log(em.get((k, de), [0.25] * 4)[dn]) for _, de, dn in byverb[v])) for v in verbs}
        if new == cls: break
        cls = new
    em = table([e for e in E["fit"] if e[0] in cls], lambda v, de: (cls[v], de))
    return cls, (lambda v, de: em.get((cls[v], de), p_prior(v, de)) if v in cls else p_prior(v, de))
res = {}
for K in (2, 3, 4, 5):
    cls, pk = learn(K); res[K] = (cls, pk); print(f"R25-cu-t K={K}: dev {bits(E['dev'], pk):.4f} bits (prior {bits(E['dev'], p_prior):.4f}, per verb {bits(E['dev'], p_verb):.4f})", flush=True)
K = min(res, key=lambda k: bits(E["dev"], res[k][1])); cls, pk = res[K]
a, b, c = bits(E["test"], p_prior), bits(E["test"], pk), bits(E["test"], p_verb)
print(f"R25-cu-t chosen K={K}. Held-out books ({len(E['test'])} events): no verb {a:.4f}, learned classes {b:.4f}, per verb {c:.4f}; classes recover {(a - b) / max(1e-9, a - c):.1%} of the per-verb gain", flush=True)
cshare = collections.defaultdict(lambda: [0, 0])
for v, de, dn in E["fit"]:
    if v in cls: cshare[cls[v]][0] += dn == 0; cshare[cls[v]][1] += 1
for k in range(K):
    mem = sorted((v for v in verbs if cls[v] == k), key=lambda v: -cnt[v])
    print(f"  class {k}: possessive next mention {cshare[k][0] / max(1, cshare[k][1]):.3f}, {len(mem)} verbs: {', '.join(mem[:25])}", flush=True)
ACQ = ["take", "find", "pick", "grab", "steal", "catch", "get", "buy", "receive"]
REL = ["drop", "put", "leave", "give", "set", "hang", "lay", "place", "throw", "sell", "lose", "hide"]
sh = {k: cshare[k][0] / max(1, cshare[k][1]) for k in range(K)}
pairs = [(x, y) for x in ACQ if x in cls for y in REL if y in cls]
good = sum(1 for x, y in pairs if sh[cls[x]] > sh[cls[y]]); ties = sum(1 for x, y in pairs if cls[x] == cls[y])
print(f"R25-cu-t lexicon check: {good} / {len(pairs)} acquire x release pairs ordered as the hand lists say ({ties} in the same class); acquire {[(x, cls[x]) for x in ACQ if x in cls]}, release {[(y, cls[y]) for y in REL if y in cls]}", flush=True)
print(f"R25-cu-t per-verb possessive share, acquire: {[(x, round(possshare[x], 3)) for x in ACQ if x in cls]}; release: {[(y, round(possshare[y], 3)) for y in REL if y in cls]}", flush=True)
