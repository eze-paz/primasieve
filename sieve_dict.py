"""SD (sieve_lang_prereg.md): dictionary access. WordNet 3.1 (_nldata/dict) turned into word-level inputs for Sieve:
attributes wpos (part-of-speech set), wlex (lexicographer file of the most frequent sense), wlem (base form), the
dictionary tree view "d" (depth-k hypernym ancestor of the first sense), and kind "gloss" (rare recent words vote for
their synonyms / definition words / hypernym + hyponym lemmas). Run: SZ_EXACT=1 py -3.12 -W ignore sieve_dict.py
build | offer [state] | eval"""
import os, sys, json, time, re
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); NL = os.path.join(HERE, "_nldata", "dict"); POS = "nvar"
def parse():
    """synset table: offset key -> (lexfile, lemmas, pointers, gloss words); index: (lemma, pos) -> offsets by sense frequency"""
    syn, index = {}, {}
    for p, nm in zip(POS, ("noun", "verb", "adj", "adv")):
        for l in open(os.path.join(NL, f"data.{nm}"), encoding="utf-8"):
            if l.startswith(" "): continue
            head, _, gloss = l.partition("|"); f = head.split(); off, lexf, nw = f[0], int(f[1]), int(f[3], 16)
            lem = [f[4 + 2 * i].lower() for i in range(nw)]; j = 4 + 2 * nw; npt = int(f[j]); ptr = [(f[j + 1 + 4 * i], f[j + 2 + 4 * i], f[j + 3 + 4 * i]) for i in range(npt)]
            syn[(p if p != "s" else "a", off)] = (lexf, [re.sub(r"\(.*\)$", "", x) for x in lem], ptr, re.findall(r"[a-z]+", gloss.split(";")[0].lower()))
        for l in open(os.path.join(NL, f"index.{nm}"), encoding="utf-8"):
            if l.startswith(" "): continue
            f = l.split(); w = f[0].lower(); n = int(f[2]); pc = int(f[3]); offs = f[4 + pc + 2:]; index[(w, p)] = offs
    exc = {}
    for p, nm in zip(POS, ("noun", "verb", "adj", "adv")):
        for l in open(os.path.join(NL, f"{nm}.exc"), encoding="utf-8"):
            f = l.split()
            if len(f) >= 2: exc.setdefault((f[0], p), f[1])
    return syn, index, exc
RULES = {"n": [("s", ""), ("ses", "s"), ("xes", "x"), ("zes", "z"), ("ches", "ch"), ("shes", "sh"), ("men", "man"), ("ies", "y")],
         "v": [("s", ""), ("ies", "y"), ("es", "e"), ("es", ""), ("ed", "e"), ("ed", ""), ("ing", "e"), ("ing", "")], "a": [("er", ""), ("est", ""), ("er", "e"), ("est", "e")], "r": []}
def base_forms(w, index, exc):
    """(pos, base) pairs WordNet knows for this spelling: exact, exception list, then suffix rules"""
    out = []
    for p in POS:
        if (w, p) in index: out.append((p, w))
        elif (w, p) in exc and (exc[(w, p)], p) in index: out.append((p, exc[(w, p)]))
        else:
            for a, b in RULES[p]:
                if w.endswith(a) and (w[:len(w) - len(a)] + b, p) in index: out.append((p, w[:len(w) - len(a)] + b)); break
    return out
def build():
    words = json.load(open(os.path.join(HERE, "learned", "lx", "lx_vocab.json"), encoding="utf-8"))["words"]; V = len(words) + 2; wid = {w: i + 1 for i, w in enumerate(words)}
    syn, index, exc = parse(); cnt = np.load(os.path.join(HERE, "learned", "lx", "lx_tokens.npz"))["tr"]; freq = np.bincount(cnt, minlength=V)
    top = np.zeros(V, bool); top[np.argsort(-freq)[:300]] = True                                    # function words carry no meaning link
    wpos = np.zeros(V, np.int64); wlex = np.full(V, 45, np.int64); wlem = np.arange(V); paths = {}; rel = {r: [None] * V for r in ("syn", "gloss", "hyper")}
    lemid = {}
    def chain(key):
        out, seen = [], set()
        while key and key not in seen:
            seen.add(key); out.append(key); hy = [(p2, o) for sym, o, p2 in syn[key][2] if sym in ("@", "@i")]; key = (hy[0][1] and (hy[0][0].replace("s", "a"), hy[0][1])) if hy else None
        return out[::-1]
    for w, i in wid.items():
        bf = base_forms(w, index, exc)
        if not bf: continue
        for p, b in bf: wpos[i] |= 1 << POS.index(p)
        p0, b0 = bf[0]; wlem[i] = wid.get(b0, i); senses = [(p, o) for p, b in bf for o in index[(b, p)][:2]]
        best = max(((p, index[(b, p)][0]) for p, b in bf), key=lambda k: 0)                      # first listed POS's most frequent sense
        k0 = (best[0], best[1]); wlex[i] = syn[k0][0]
        paths[i] = [f"{best[0]}:{x[1]}" for x in chain(k0)] if best[0] in "nv" else [f"{best[0]}:{syn[k0][0]}"]
        S, G, H = set(), set(), set()
        for key in senses:
            if key not in syn: continue
            lf, lem, ptr, gl = syn[key]; S.update(lem); G.update(gl)
            for sym, o, p2 in ptr:
                if sym in ("@", "@i", "~", "~i"): kk = (p2.replace("s", "a"), o); H.update(syn[kk][1] if kk in syn else [])
        for r, X in (("syn", S), ("gloss", G), ("hyper", H)):
            ids = [wid[x] for x in X if x in wid and wid[x] != i and not top[wid[x]]]; ids = sorted(ids, key=lambda j: -freq[j])[:30]; rel[r][i] = np.array(ids, np.int64)
    out = dict(wpos=wpos, wlex=wlex, wlem=wlem)
    for k in range(1, 14):
        ids = {}; arr = np.full(V, -1, np.int64)
        for w in range(V): arr[w] = ids.setdefault(paths[w][min(k, len(paths[w])) - 1] if w in paths else "#none", len(ids))   # shorter chains stay at their leaf
        out[f"d{k}"] = arr
    for r in rel:
        lens = np.array([0 if x is None else len(x) for x in rel[r]]); out[f"{r}_ptr"] = np.r_[0, np.cumsum(lens)]; out[f"{r}_ids"] = np.concatenate([x for x in rel[r] if x is not None])
    np.savez(os.path.join(HERE, "learned", "lx", "sieve_dict.npz"), **out)
    cov = (wpos[1:V - 1] > 0); tokcov = (wpos[cnt] > 0).mean()
    print(f"SD dictionary: {cov.sum():,} of {V - 2:,} vocabulary words in WordNet; {tokcov:.3f} of training tokens; tree depth max {max(len(p) for p in paths.values())}; "
          f"related ids syn {len(out['syn_ids']):,}, gloss {len(out['gloss_ids']):,}, hyper {len(out['hyper_ids']):,}", flush=True)
DZ = None
def load(F):
    global DZ
    if DZ is None: DZ = dict(np.load(os.path.join(HERE, "learned", "lx", "sieve_dict.npz")))
    for k in ("wpos", "wlex", "wlem"): F.AT[k] = DZ[k]
    for k in range(1, 14): F.AT[f"hd{k}"] = DZ[f"d{k}"]
    return DZ
def related(r, w):
    if r == "all": return np.concatenate([related(x, w) for x in ("syn", "gloss", "hyper")])
    p = DZ[f"{r}_ptr"]; return DZ[f"{r}_ids"][p[w]:p[w + 1]]
def gloss_vote(cx, sp, F, P):
    s, T, _ = F.ctx(cx); SL, ans = P.shortlist(cx); n, K = SL.shape; C = P.ccount(); y = s[T]
    D = np.zeros((n, K + 1), np.float32); N = np.zeros(n); TD = np.zeros(n); EX = np.zeros(n); cache = {}
    for i, t in enumerate(T):
        ws = np.unique(s[max(0, t - sp["B"]):t]); ws = ws[(ws != 0) & (C[ws] <= 1000)]
        if not len(ws): continue
        tk = np.concatenate([cache.setdefault(int(w), related(sp["rel"], int(w))) for w in ws])
        if not len(tk): continue
        c = np.searchsorted(SL[i], tk); cc = np.minimum(c, K - 1); hit = SL[i][cc] == tk
        D[i, :K] = np.bincount(c[hit], minlength=K)[:K]; D[i, K] = (~hit).sum(); N[i] = len(tk); TD[i] = len(np.unique(tk)); EX[i] = (tk == y[i]).sum()
    ne = N > 0; D[ne] /= N[ne, None]
    if P.EXACT: D = P.exactify(D, EX / np.maximum(N, 1e-12), ans, K)
    return D, ne, N, TD
def install():
    import sieve_fs2 as F, sieve_prim as P, sieve_prim3 as P3, sieve_onto as O
    load(F); P3.TOKATTR = tuple(dict.fromkeys(P3.TOKATTR + ("wpos", "wlex", "wlem")))
    old = P.vote
    def vote(cx, sp):
        if sp.get("kind") != "gloss": return old(cx, sp)
        r = O.cached(cx, sp)
        if r is not None: return r
        return O.save(cx, sp, *gloss_vote(cx, sp, F, P))
    P.vote = P3.vote = vote
    _d = P.describe; P.describe = P3.describe = lambda sp: f"Gloss[rare words in the last {sp['B']} -> their dictionary {sp['rel']} words]" if sp.get("kind") == "gloss" else _d(sp)
    _b = P.bits_of; P.bits_of = P3.bits_of = lambda sp: 6.0 if sp.get("kind") == "gloss" else _b(sp)
    _v = P.valid; P.valid = P3.valid = lambda sp: True if sp.get("kind") == "gloss" else _v(sp)
    return F, P, P3, O
CANDS = [dict(src="static", terms=[[0, "wlem", 1, None]], span=1, w="1"), dict(src="static", terms=[[0, "wlex", 1, None]], span=1, w="1"),
         dict(src="static", terms=[[0, "id", 1, None], [1, "wlem", 1, None]], span=1, w="1"), dict(src="static", terms=[[0, "wpos", 1, None], [1, "wpos", 1, None]], span=1, w="1"),
         dict(src="book", terms=[[0, "wlem", 1, None]], span=1, w="1"), dict(src="w1000", terms=[[0, "wlex", 1, None]], span=1, w="1")] + \
        [dict(kind="nodecache", view="d", k=k, W=W) for k in (2, 4, 6) for W in (200, "book")] + [dict(kind="descend", view="d", k=k, terms=[[0, "id", 1, None]]) for k in (4, 8)] + \
        [dict(kind="ctrig", view="d", k=4, B=50, thr=1000, span=20)] + [dict(kind="gloss", rel=r, B=B) for r in ("syn", "gloss", "hyper", "all") for B in (20, 100)]
def main(argv):
    if argv[1] == "build": build(); return
    sys.argv = [sys.argv[0], "none"]
    import sieve_l1 as L1, sieve_l2 as L2; F, P, P3, O = install(); L1.install(); L2.install(); O.setup_attrs()
    import sieve_paq as SPQ; SPQ.load_trees()
    src = argv[2] if len(argv) > 2 else "sieve_sn_offer.json"; out = os.path.join(F.HERE, "sieve_sd_offer.json")
    if argv[1] == "offer":
        miss = [sp for sp in CANDS if O.cached("fit9", sp) is None]; t0 = time.time()
        for sp in miss:
            if time.time() - t0 > 150: break
            t = time.time(); P.vote("fit9", sp); print(f"   built {P.describe(sp)}: {time.time() - t:.0f} s", flush=True)
        if any(O.cached("fit9", sp) is None for sp in CANDS): F.log(f"SD: {sum(O.cached('fit9', sp) is None for sp in CANDS)} still to build; rerun"); return
        st = json.load(open(out)) if os.path.exists(out) else json.load(open(os.path.join(F.HERE, src)))
        st, acc, fit = O.move_loop(st, CANDS, budget=200, save=lambda s: json.dump(s, open(out, "w"))); json.dump(st, open(out, "w")); F.log(f"SD: {len(acc)} accepted this run; fit {fit:.4f} bits/word (SN 7.3471)")
    else:
        st = json.load(open(out)); M = P3.Model("eval", st); M.gact = st["gact"]; F.log(f"SD scored on the {M.n:,} positions: {M.bits() / M.n:.4f} bits/word static (SN 7.7073)")
if __name__ == "__main__": main(sys.argv[:])
