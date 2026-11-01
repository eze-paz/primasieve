"""SQ3 (sieve_lang_prereg.md): graded matching widened -- offsets 1-5 (weights {0,1,2} at 1-3, {0,1} at 4-5), top
1,000, agreement attribute in {identity, mff, form (SP7's 400 MDL forms, sieve_forms.py --save), identity+form (per
offset: same token + same form)}. Cached as gr5_* beside SP3's components (sieve_gr_cache/); every graded component is
charged under the widened grammar. Same 1,000 positions; held-out vs SP3's 6.1598.
Run: py -3.12 -W ignore sieve_graded2.py cache id,mff | cache form,idform | search [--top K] | eval"""
import os, sys, math, json, itertools
import numpy as np
import sieve_count as SC, sieve_trust as ST, sieve_wide as SW, sieve_graded as SG
log = SC.log; Vt = SW.Vt; CD = SG.CD; AT = SG.AT
LAB = np.load(os.path.join(SC.LX, "sieve_forms_labels.npy")); FORM = np.r_[len(LAB) + 1, LAB, len(LAB) + 2]          # <s>, words 1..2000, unknown
W5 = [w for w in itertools.product((0, 1, 2), (0, 1, 2), (0, 1, 2), (0, 1), (0, 1)) if any(w)]
ATTRS = ("id", "mff", "form", "idform")
def eqs(stream, j, t, attr):
    """per-offset agreement (0/1, or 0-2 for identity+form) of the 5 tokens before j with the 5 before t"""
    if attr == "idform": return eqs(stream, j, t, "id") + eqs(stream, j, t, "form")
    A = stream if attr == "id" else (AT["mff"][stream] if attr == "mff" else FORM[stream])
    return np.stack([A[j - a] == A[t - a] for a in range(1, 6)]).astype(np.int16)
def graded5(stream, T, attr, ws, K=1000):
    out = {w: [np.zeros(len(T), bool), np.zeros(len(T)), np.zeros(len(T)), np.zeros(len(T))] for w in ws}; Wm = np.array(ws, np.int16)
    for i, t in enumerate(T):
        j = np.arange(max(5, t - SC.H), t); S = (Wm @ eqs(stream, j, t, attr)).astype(np.int64); F = stream[j]; y = stream[t]
        for r, w in enumerate(ws):
            sc = S[r]; pos = np.nonzero(sc > 0)[0]
            if len(pos) == 0: continue
            sel = pos if len(pos) <= K else pos[np.argpartition(-(sc[pos] * 10**7 + pos), K)[:K]]
            wt = 2.0 ** sc[sel]; f = F[sel]; o = out[w]; o[0][i] = True; o[1][i] = wt[f == y].sum() / wt.sum(); o[2][i] = len(sel); o[3][i] = len(np.unique(f))
    return out
def todo(attr): return [w for w in W5 if attr in ("form", "idform") or w[3] or w[4]]                    # id/mff with offsets 1-3 only: SP3's, already cached
def bits_of(n):
    return 1 + math.log2(len(ATTRS)) + 3 * math.log2(3) + 2 + 1     # kind, attribute, offset weights, top-K
def base_bits(n):
    p = n.split("_")
    if p[0] == "base": return 1 + len(SW.MATCHERS[int(p[1])][0]) * math.log2(len(SW.ATOMS)) + math.log2(len(SW.BOUNDS)) + 1
    if p[0] == "ent": return 1 + 1 + int(p[1]) * math.log2(len(SW.ATOMS)) + 1
    return bits_of(n)
def desc(n):
    p = n.split("_")
    if p[0] == "base": m = SW.MATCHERS[int(p[1])]; return f"[{SW.mname(m)}] {('count', 'recency')[int(p[2])]}"
    if p[0] == "ent": return f"[entity] {('count', 'recency')[int(p[2])]}"
    return f"[graded {p[1]}, offset weights {p[2]}, top {p[3]}]"
def comp_on(stream, book, cap, T, n):
    p = n.split("_")
    if p[0] == "base": ne, P, N, TD = SW.build(stream, book, T, SW.MATCHERS[int(p[1])], AT); return ne, P[int(p[2])], N, TD
    if p[0] == "ent": ne, P, N, TD = SG.ent_build(stream, book, cap, T, SG.ENT[int(p[1])][1]); return ne, P[int(p[2])], N, TD
    w = tuple(int(x) for x in p[2]); w = w + (0,) * (5 - len(w)); return tuple(graded5(stream, T, p[1], [w], int(p[3]))[w])
if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "search"
    if mode == "cache":
        for attr in sys.argv[2].split(","):
            ws = todo(attr)
            for w, (ne, P, N, TD) in graded5(SG.s, SG.T, attr, ws).items(): SG.save(f"gr5_{attr}_{''.join(map(str, w))}_1000.npz", ne, P, N, TD)
            log(f"{len(ws)} widened graded components cached for {attr}")
    elif mode == "search":
        names = sorted(f[:-4] for f in os.listdir(CD)); C = [SG.load(n + ".npz") for n in names]; seen = set(); keep = []
        for i, c in enumerate(C):
            sig = (c[0].tobytes(), np.round(c[1], 12).tobytes())
            if sig not in seen: seen.add(sig); keep.append(i)
        use = [names[i] for i in keep]; NE, PP, NN, TT = (np.array([C[i][j] for i in keep]) for j in range(4))
        if "--top" in sys.argv:                                                                     # search budget: only the best single components (by MDL) enter the beam
            K = int(sys.argv[sys.argv.index("--top") + 1]); sb = [ST.score([(c, None)], NE, PP, NN, TT, Vt, lambda c: base_bits(use[c]))[0] if NE[c].any() else np.inf for c in range(len(use))]
            sel = sorted(np.argsort(sb, kind="stable")[:K]); use = [use[c] for c in sel]; NE, PP, NN, TT = NE[sel], PP[sel], NN[sel], TT[sel]
        log(f"{len(names)} components, {len(use)} distinct by behaviour")
        progs = ST.search(NE, PP, NN, TT, Vt, lambda c: base_bits(use[c]), len(use)); best = min(progs, key=lambda q: (round(progs[q][0], 9), repr(q)))
        sc, b, e = progs[best]
        print(f"   MDL-best: " + desc(use[best[0][0]]) + "".join(ST.cbname(cb) + desc(use[c]) for c, cb in best[1:]) + f" (escape {e}) -- training {b / SG.NSC:.4f}, description {sc - b:.1f} bits", flush=True)
        json.dump(dict(chain=[[use[c], cb] for c, cb in best], escape=e), open(os.path.join(SC.HERE, "sieve_graded2_best.json"), "w")); log("search done")
    else:
        prog = json.load(open(os.path.join(SC.HERE, sys.argv[2] if len(sys.argv) > 2 else "sieve_graded2_best.json")))
        C = [comp_on(SG.full, SG.fbook, SG.fcap, SG.Th, n) for n, _ in prog["chain"]]; NE, PP, NN, TT = (np.array([c[j] for c in C]) for j in range(4))
        chain = [(k, None if cb is None else tuple(cb)) for k, (_, cb) in enumerate(prog["chain"])]; m, p = ST.run(chain, NE, PP, NN, TT); e = prog["escape"]
        log(f"SQ3 held-out: {(-np.log2(np.where(m, (1 - e) * p + e / Vt, 1 / Vt))).mean():.4f} bits/token (SP3 6.1598, SP0 6.1638)")
