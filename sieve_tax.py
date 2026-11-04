"""TX1 (sieve_lang_prereg.md): an explicit word taxonomy, every vocabulary word in exactly one leaf. Level 1: WordNet's
45 lexicographer files + a grammar branch (300 most frequent words) + not-in-WordNet, the categories with the most tokens
split by 2-means on topic profiles until there are 100; level 2: round(sqrt(words)) groups per category (<= 100); level 3:
groups of > 30 words split into groups of <= 30. Views t1 / t2 / t3 (F.AT ht1..ht3). Names = 3 most frequent words.
Run: SZ_EXACT=1 py -3.12 -W ignore sieve_tax.py build | show | offer | eval"""
import os, sys, json, math, time
import numpy as np
LEX = ["adj.all", "adj.pert", "adv.all", "noun.Tops", "noun.act", "noun.animal", "noun.artifact", "noun.attribute", "noun.body", "noun.cognition", "noun.communication", "noun.event", "noun.feeling", "noun.food",
       "noun.group", "noun.location", "noun.motive", "noun.object", "noun.person", "noun.phenomenon", "noun.plant", "noun.possession", "noun.process", "noun.quantity", "noun.relation", "noun.shape", "noun.state",
       "noun.substance", "noun.time", "verb.body", "verb.change", "verb.cognition", "verb.communication", "verb.competition", "verb.consumption", "verb.contact", "verb.creation", "verb.emotion", "verb.motion",
       "verb.perception", "verb.possession", "verb.social", "verb.stative", "verb.weather", "adj.ppl", "not in WordNet", "grammar"]
def kmeans(X, k, seed=0, it=12):
    """deterministic k-means (k-means++ seeding, seed 0) on rows of X; returns labels"""
    import torch
    g = np.random.default_rng(seed); n = len(X)
    if k <= 1 or n <= k: return np.arange(n) % max(k, 1) if n <= k else np.zeros(n, int)
    Xt = torch.from_numpy(X.astype(np.float32)); c = [int(g.integers(n))]; d = ((Xt - Xt[c[0]]) ** 2).sum(1)
    for _ in range(1, k):
        p = d.numpy().astype(np.float64); s_ = p.sum(); j = int(g.choice(n, p=p / s_)) if s_ > 0 and np.isfinite(s_) else int(g.integers(n))   # identical points: any
        c.append(j); d = torch.minimum(d, ((Xt - Xt[j]) ** 2).sum(1))
    Cn = Xt[c].clone()
    for _ in range(it):
        lab = torch.cdist(Xt, Cn).argmin(1)
        for j in range(k):
            m = lab == j
            if m.any(): Cn[j] = Xt[m].mean(0)
    return torch.cdist(Xt, Cn).argmin(1).numpy()
def path(F): import sieve_fast as FS; return os.path.join(FS.IDX, "vec", "taxonomy.npz")
def build(F, P):
    import sieve_vec as SV, sieve_dict as SD
    t0 = time.time(); SD.load(F); X = SV.vectors(F, P, True); has = np.abs(X).sum(1) > 0; C = P.ccount().astype(float); Vt = F.Vt
    words = json.load(open(os.path.join(F.SC.LX, "lx_vocab.json"), encoding="utf-8"))["words"]; ids = np.arange(1, Vt - 1)
    cat = F.AT["wlex"].copy(); cat[np.argsort(-C)[:301]] = 46; cat[0] = -1; cat[Vt - 1] = -1; ncat = 47; names = {c: LEX[c] for c in range(47)}
    while len(np.unique(cat[ids])) < 100:                                                               # split the category with the most tokens
        mass = np.bincount(cat[ids], weights=C[ids], minlength=ncat); order = np.argsort(-mass)
        for c in order:
            m = ids[(cat[ids] == c) & has[ids]]
            if len(m) >= 40: break
        lab = kmeans(X[m], 2); cat[m[lab == 1]] = ncat; names[ncat] = names[c] + "'"; ncat += 1
    u = np.unique(cat[ids]); remap = {c: i for i, c in enumerate(u)}; t1 = np.full(Vt, -1); t1[ids] = [remap[c] for c in cat[ids]]
    t2 = np.full(Vt, -1); t3 = np.full(Vt, -1); n2 = n3 = 0
    for c in range(len(u)):
        m = ids[t1[ids] == c]; mp = m[has[m]]; mu = m[~has[m]]; k = int(min(100, max(1, round(math.sqrt(len(m))))))
        lab = kmeans(X[mp], k) if len(mp) else np.zeros(0, int)
        for j in range(max(k, 1)):
            g = mp[lab == j] if len(mp) else mp
            if not len(g): continue
            t2[g] = n2; kk = int(math.ceil(len(g) / 30)); lab3 = kmeans(X[g], kk) if kk > 1 else np.zeros(len(g), int)
            for q in range(kk):
                h = g[lab3 == q]
                if len(h): t3[h] = n3; n3 += 1
            n2 += 1
        if len(mu): t2[mu] = n2; t3[mu] = n3; n2 += 1; n3 += 1                                              # the category's unprofiled leaf
    for t in (t1, t2, t3): t[0] = t.max() + 1; t[Vt - 1] = t.max() + 1                                    # boundary / unknown: own nodes
    top = lambda m: " / ".join(words[w - 1] for w in m[np.argsort(-C[m])][:3] if 0 < w <= len(words))
    nm1 = [f"{names[u[c]]}: {top(ids[t1[ids] == c])}" for c in range(len(u))]
    np.savez(path(F), t1=t1, t2=t2, t3=t3); json.dump(nm1, open(path(F).replace(".npz", "_names.json"), "w"), indent=0)
    F.log(f"TX1 taxonomy: {len(u)} level-1 categories, {n2} level-2 groups, {n3} leaves; every vocabulary word mapped ({time.time() - t0:.0f} s)")
def load(F):
    f = path(F)
    if os.path.exists(f):
        z = np.load(f)
        for k in (1, 2, 3): F.AT[f"ht{k}"] = z[f"t{k}"]
CANDS = [dict(kind="descend", view="t", k=k, terms=[[0, "id", 1, None]]) for k in (1, 2, 3)] + [dict(kind="nodecache", view="t", k=k, W=W) for k in (1, 2, 3) for W in (200, "book")]
def setup():
    import sieve_knn as KN; F, P, P3, O = KN.setup(); load(F); return F, P, P3, O
def main(argv):
    F, P, P3, O = setup(); out = os.path.join(F.HERE, "sieve_tx_offer.json")
    if argv[1] == "build": build(F, P); return
    if argv[1] == "show":
        nm = json.load(open(path(F).replace(".npz", "_names.json"))); words = json.load(open(os.path.join(F.SC.LX, "lx_vocab.json"), encoding="utf-8"))["words"]; wid = {w: i + 1 for i, w in enumerate(words)}; C = P.ccount()
        for i, n_ in enumerate(nm): print(f"   {i:3d} {n_}", flush=True)
        for w in ("ship", "boat", "sea", "sword", "horse", "drink", "london", "happy"):
            i = wid[w]; same = [words[x - 1] for x in np.nonzero(F.AT["ht3"] == F.AT["ht3"][i])[0] if 0 < x <= len(words)]; same = sorted(same, key=lambda x: -C[wid[x]])[:10]
            print(f"   {w}: level 1 = {nm[F.AT['ht1'][i]]}; leaf = {', '.join(same)}", flush=True)
        return
    if argv[1] == "offer":
        t0 = time.time()
        for sp in CANDS:
            if O.cached("fit9", sp) is None and time.time() - t0 < 200: t = time.time(); P.vote("fit9", sp); print(f"   built {P.describe(sp)}: {time.time() - t:.0f} s", flush=True)
        if any(O.cached("fit9", sp) is None for sp in CANDS): F.log("TX1: still building; rerun"); return
        st = json.load(open(out)) if os.path.exists(out) else json.load(open(os.path.join(F.HERE, "sieve_sc_offer.json")))
        st, acc, fit = O.move_loop(st, CANDS, budget=100, save=lambda s_: json.dump(s_, open(out, "w"))); json.dump(st, open(out, "w")); F.log(f"TX1: {len(acc)} accepted; fit {fit:.4f} bits/word (SC1 7.2511)"); return
    st = json.load(open(out)); M = P3.Model("eval", st); M.gact = st["gact"]; F.log(f"TX program scored on the {M.n:,} positions: {M.bits() / M.n:.4f} bits/word static (SC1 7.6212)")
if __name__ == "__main__": main(sys.argv[:])
