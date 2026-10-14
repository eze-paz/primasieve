"""R25-cx-t: verb effect classes emerge from the next-word game (R25_prereg.md). Events 'AGENT VERB DET THING' from the
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


PRT = {"up", "down", "off", "out", "away", "back", "over", "on", "in"}
def events(bid):
    out = []; paras = [p.replace(chr(8217), "'") for p in D0.read(bid).split(chr(10))]
    PT = []
    for para in paras:
        toks = []; starts = set()
        for s_ in SENT.split(para):
            ts = TOK.findall(s_); starts.add(len(toks)); toks += ts
        PT.append((toks, starts, [t.lower() for t in toks]))
    def isname(toks, low, starts, j): return toks[j][0].isupper() and j not in starts and low[j] not in FUNC and len(low[j]) > 1 and not low[j].endswith("'s")
    for pi, (toks, starts, low) in enumerate(PT):
        lastname = PT[pi - 1][3] if pi > 0 and len(PT[pi - 1]) > 3 else None
        for i in range(len(toks) - 3):
            if isname(toks, low, starts, i): lastname = low[i]; agent = low[i]
            elif low[i] in ("he", "she", "they") and lastname: agent = lastname
            else: continue
            v = i + 1
            if low[v].endswith("ly") and v + 1 < len(low): v += 1
            b = base(low[v])
            if not b or b in ("be", "have", "do"): continue
            j = v + 1
            if j < len(low) and low[j] in PRT: j += 1
            if j >= len(low) or low[j] not in DETS: continue
            d = low[j]; j += 1
            if j + 1 < len(low) and low[j + 1].isalpha() and low[j + 1] not in FUNC and not base(low[j + 1]) and not (j + 1) in starts and not toks[j + 1][0].isupper(): j += 1   # one adjective
            if j >= len(low): continue
            th = low[j]
            if th in FUNC or len(th) < 3 or base(th) or toks[j][0].isupper(): continue
            send = next((x for x in sorted(starts) if x > j), len(low))          # search starts after the event's sentence
            found = None
            for q in range(pi, min(pi + 3, len(PT))):
                t2, st2, l2 = PT[q]; k0 = send if q == pi else 0
                k = next((x for x in range(k0, len(l2)) if l2[x] == th), None)
                if k is not None: found = (q, k); break
            if not found: continue
            q, k = found; t2, st2, l2 = PT[q]
            def resolve(x):                                                                  # most recent name before position x (same paragraph, else the previous paragraph's last)
                y = next((y for y in range(x - 1, -1, -1) if isname(t2, l2, st2, y)), None)
                return l2[y] if y is not None else (PT[q - 1][3] if q > 0 and len(PT[q - 1]) > 3 else None)
            near = [l2[x] for x in range(max(0, k - 8), min(len(l2), k + 9)) if x != k and isname(t2, l2, st2, x)]
            near += [resolve(x) for x in range(max(0, k - 6), min(len(l2), k + 7)) if x != k and l2[x] in ("he", "she", "him", "his", "her", "they", "them", "their")]
            near = [x for x in near if x]
            dn = 0 if agent in near else 1 if near else 2
            out.append((b, 0 if q == pi else 1, dn))
        PT[pi] = PT[pi][:3] + (lastname,)
    return out


tr, te = D0.books()
dev = tr[::10]; fit = [b for b in tr if b not in set(dev)]
E = {}
for name, ids in (("fit", fit), ("dev", dev), ("test", te)):
    E[name] = [e for b in ids for e in events(b)]
    print(f"R25-cx-t {name}: {len(ids)} books, {len(E[name])} events ({time.time() - t0:.0f} s)", flush=True)
cnt = collections.Counter(v for v, _, _ in E["fit"]); verbs = sorted(v for v, c in cnt.items() if c >= 30)
vi = {v: i for i, v in enumerate(verbs)}
print(f"R25-cx-t {len(verbs)} verbs with 30+ events", flush=True)
def table(evs, key, smooth=1.0):
    t = collections.defaultdict(lambda: [smooth] * 3)
    for v, de, dn in evs: t[key(v, de)][dn] += 1
    return {k: [x / sum(c) for x in c] for k, c in t.items()}
def bits(evs, prob):
    return sum(-math.log2(prob(v, de)[dn]) for v, de, dn in evs) / len(evs)
prior = table(E["fit"], lambda v, de: de)
def p_prior(v, de): return prior.get(de, [1 / 3] * 3)
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
        new = {v: min(range(K), key=lambda k: -sum(math.log(em.get((k, de), [1 / 3] * 3)[dn]) for _, de, dn in byverb[v])) for v in verbs}
        if new == cls: break
        cls = new
    em = table([e for e in E["fit"] if e[0] in cls], lambda v, de: (cls[v], de))
    return cls, (lambda v, de: em.get((cls[v], de), p_prior(v, de)) if v in cls else p_prior(v, de))
res = {}
for K in (2, 3, 4, 5):
    cls, pk = learn(K); res[K] = (cls, pk); print(f"R25-cx-t K={K}: dev {bits(E['dev'], pk):.4f} bits (prior {bits(E['dev'], p_prior):.4f}, per verb {bits(E['dev'], p_verb):.4f})", flush=True)
K = min(res, key=lambda k: bits(E["dev"], res[k][1])); cls, pk = res[K]
a, b, c = bits(E["test"], p_prior), bits(E["test"], pk), bits(E["test"], p_verb)
print(f"R25-cx-t chosen K={K}. Held-out books ({len(E['test'])} events): no verb {a:.4f}, learned classes {b:.4f}, per verb {c:.4f}; classes recover {(a - b) / max(1e-9, a - c):.1%} of the per-verb gain", flush=True)
cshare = collections.defaultdict(lambda: [0, 0])
for v, de, dn in E["fit"]:
    if v in cls: cshare[cls[v]][0] += dn == 0; cshare[cls[v]][1] += 1
for k in range(K):
    mem = sorted((v for v in verbs if cls[v] == k), key=lambda v: -cnt[v])
    print(f"  class {k}: agent named near the next mention {cshare[k][0] / max(1, cshare[k][1]):.3f}, {len(mem)} verbs: {', '.join(mem[:25])}", flush=True)
ACQ = ["take", "find", "pick", "grab", "steal", "catch", "get", "buy", "receive"]
REL = ["drop", "put", "leave", "give", "set", "hang", "lay", "place", "throw", "sell", "lose", "hide"]
sh = {k: cshare[k][0] / max(1, cshare[k][1]) for k in range(K)}
pairs = [(x, y) for x in ACQ if x in cls for y in REL if y in cls]
good = sum(1 for x, y in pairs if sh[cls[x]] > sh[cls[y]]); ties = sum(1 for x, y in pairs if cls[x] == cls[y])
print(f"R25-cx-t lexicon check: {good} / {len(pairs)} acquire x release pairs ordered as the hand lists say ({ties} in the same class); acquire {[(x, cls[x]) for x in ACQ if x in cls]}, release {[(y, cls[y]) for y in REL if y in cls]}", flush=True)
print(f"R25-cx-t per-verb agent-near share, acquire: {[(x, round(possshare[x], 3)) for x in ACQ if x in cls]}; release: {[(y, round(possshare[y], 3)) for y in REL if y in cls]}", flush=True)
