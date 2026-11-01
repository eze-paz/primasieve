"""SR (sieve_lang_prereg.md): ten improvements, all at full scale. Components on the 3,000 fit positions spread over
the 7 dev books (SQ2) and, for the selected program only, on the 50,114 scored positions. Every component states its
answer probability P and its distribution over forms Q (SP7's 400 forms + 'other' + '<s>'). Kinds: count over the
training + prefix history / the library / training + library + prefix (SR9); any-position recency over the 50,000-token
memory; graded (SR3); long-match lookup in the history / the library (SR8). Search: chains up to 5 (SR5), residual-
steered candidates (SR6), a final reweight stage by recent form shares (SR1, needs Q: SR2), calibration filter on
form-level claims (SR10), residual rounds naming the families offered next (SR7).
Run: py -3.12 -W ignore sieve_fs2.py cache fit <kind> | round <r> | eval"""
import os, sys, json, math, itertools, collections, time
import numpy as np
import sieve_count as SC, sieve_match as SMM, sieve_trust as ST
from core.tolerance import within
log = SC.log; HERE = SC.HERE; CD = os.path.join(SC.LX, "sieve_fs2_cache"); os.makedirs(CD, exist_ok=True)
Z = np.load(os.path.join(SC.LX, "lx_tokens.npz")); DD = np.load(os.path.join(SC.LX, "lx_docs.npz"))
NWD = len(json.load(open(os.path.join(SC.LX, "lx_vocab.json"), encoding="utf-8"))["words"]); Vt = NWD + 2
def mk(tok, sid): tok = tok.astype(np.int64); b = np.nonzero(sid[1:] != sid[:-1])[0] + 1; return np.insert(tok, b, 0)
tr = mk(Z["tr"], Z["trs"]); NT = len(tr)
fit_s = np.r_[tr, mk(DD["dv"], DD["dvs"])]; Tf = np.arange(NT + 1, len(fit_s)); Tf = Tf[(fit_s[Tf] != 0) & (fit_s[Tf - 1] != 0)]; Tf = Tf[np.linspace(0, len(Tf) - 1, 3000).astype(int)]
ev_s = np.r_[tr, mk(Z["te"], Z["tes"])]; Te = np.arange(NT + 1, len(ev_s)); Te = Te[(ev_s[Te] != 0) & (ev_s[Te - 1] != 0)]
CTX = {"fit": (fit_s, Tf), "eval": (ev_s, Te)}
def argmax_by(x, y):
    o = np.lexsort((y, x)); xs, ys = x[o], y[o]; brk = np.r_[True, (xs[1:] != xs[:-1]) | (ys[1:] != ys[:-1])]
    ux, uy = xs[brk], ys[brk]; c = np.diff(np.r_[np.nonzero(brk)[0], len(xs)]); o2 = np.lexsort((-c, ux)); f = np.r_[True, ux[o2][1:] != ux[o2][:-1]]
    r = np.arange(Vt); r[ux[o2][f]] = uy[o2][f]; return r
AT = {"id": np.arange(Vt), "mff": argmax_by(tr[:-1], tr[1:]), "mfp": argmax_by(tr[1:], tr[:-1])}
LAB = np.load(os.path.join(SC.LX, "sieve_forms_labels.npy")); NFORM = int(LAB.max()) + 1; NF = NFORM + 2
FORM = np.full(Vt, NFORM); FORM[1:len(LAB) + 1] = LAB; FORM[0] = NFORM + 1                          # words outside the 2,000 -> 'other'; <s>
U = np.bincount(FORM, minlength=NF) / Vt; PG = np.bincount(FORM[tr], minlength=NF) / NT
LIB = None
def lib():
    global LIB
    if LIB is None: X = np.load(os.path.join(SC.LX, "lx_library.npz")); LIB = mk(X["lib"], X["libs"])
    return LIB
ATOMS = [(a, o) for a in ("id", "mff", "mfp") for o in (1, 2)]; SETS = [(x,) for x in ATOMS] + list(itertools.combinations(ATOMS, 2))
GW = ("221", "22200", "22100", "2210"); KINDS = ("count", "recency", "graded", "long")
def names_of(kind):
    if kind == "count": return [f"count_{i}_{src}" for i in range(len(SETS)) for src in ("all", "library", "all+lib")]
    if kind == "recency": return ["recency"]
    if kind == "graded": return [f"graded_{a}_{w}" for a in ("id", "form", "idform") for w in GW]
    return ["long_hist", "long_library"]
def desc(n):
    p = n.split("_")
    if p[0] == "count": return " & ".join(f"{'token' if a == 'id' else a}(t-{o})" for a, o in SETS[int(p[1])]) + {"all": "", "library": ", in the library", "all+lib": ", in history + library"}[p[2]] + " count"
    if p[0] == "recency": return "any position recency"
    if p[0] == "graded": return f"graded {p[1]}, offset weights {p[2]}"
    return f"longest match (3-8 words) in the {'history' if p[1] == 'hist' else 'library'}"
def dl(n):
    p = n.split("_"); b = math.log2(len(KINDS))
    if p[0] == "count": return b + len(SETS[int(p[1])]) * math.log2(len(ATOMS)) + math.log2(3)
    if p[0] == "graded": return b + math.log2(3) + math.log2(len(GW))
    if p[0] == "long": return b + 1
    return b
# ---------------- component computation: P(answer), matched, n, distinct, Q over forms ----------------
MASK = np.int64((1 << 46) - 1); SH = np.int64(1 << 17); SHF = np.int64(512)
def keys(s, st): k = SMM.keyarr(s, st, AT); return np.where(k == -1, -1, k & MASK)
def static(S, st):
    k = keys(S, st); ok = k != -1; k, y = k[ok], S[ok]
    comb = np.sort(k * SH + y); kk = comb >> np.int64(17); uk, first = np.unique(kk, return_index=True); nN = np.diff(np.r_[first, len(kk)])
    brk = np.r_[True, comb[1:] != comb[:-1]]; pairs = comb[brk]; cnt = np.diff(np.r_[np.nonzero(brk)[0], len(comb)])
    nT = np.bincount(np.searchsorted(uk, pairs >> np.int64(17)), minlength=len(uk))
    cf = np.sort(k * SHF + FORM[y]); bf = np.r_[True, cf[1:] != cf[:-1]]; fpairs = cf[bf]; fcnt = np.diff(np.r_[np.nonzero(bf)[0], len(cf)])
    return uk, nN, nT, pairs, cnt, fpairs, fcnt
def count_comp(s, T, st, src):
    key = keys(s, st); n_ = len(T); ne = np.zeros(n_, bool); P = np.zeros(n_); N = np.zeros(n_); TD = np.zeros(n_); Q = np.zeros((n_, NF), np.float32)
    S = lib() if src == "library" else tr if src == "all" else np.r_[tr, lib()]
    uk, nN, nT, pairs, cnt, fpairs, fcnt = static(S, st); hist = src != "library"
    def base(k, y):
        j = np.searchsorted(uk, k); hit = j < len(uk) and uk[j] == k
        if not hit: return 0, 0, 0, None
        q = k * SH + y; i = np.searchsorted(pairs, q); c = cnt[i] if i < len(pairs) and pairs[i] == q else 0
        lo, hi = np.searchsorted(fpairs, k * SHF), np.searchsorted(fpairs, k * SHF + SHF); v = np.zeros(NF); v[fpairs[lo:hi] - k * SHF] = fcnt[lo:hi]
        return nN[j], nT[j], c, v
    def base_c(k, y):
        q = k * SH + y; i = np.searchsorted(pairs, q); return cnt[i] if i < len(pairs) and pairs[i] == q else 0
    inc_n, inc_c, inc_T, inc_f = collections.Counter(), collections.Counter(), collections.Counter(), collections.defaultdict(collections.Counter)
    want = {int(t): i for i, t in enumerate(T)}
    for t in range(NT, int(T.max()) + 1 if hist else NT):
        k = int(key[t]); y = int(s[t])
        if t in want and k != -1:
            n0, T0, c0, v = base(k, y); i = want[t]; n = n0 + inc_n[k]
            if n > 0:
                v = np.zeros(NF) if v is None else v
                for f, c in inc_f[k].items(): v[f] += c
                ne[i] = True; P[i] = (c0 + inc_c[(k, y)]) / n; N[i] = n; TD[i] = T0 + inc_T[k]; Q[i] = v / n
        if k != -1:
            if inc_c[(k, y)] == 0 and base_c(k, y) == 0: inc_T[k] += 1
            inc_n[k] += 1; inc_c[(k, y)] += 1; inc_f[k][int(FORM[y])] += 1
    if not hist:
        for i, t in enumerate(T):
            k = int(key[t])
            if k == -1: continue
            n, T0, c0, v = base(k, int(s[t]))
            if n > 0: ne[i] = True; P[i] = c0 / n; N[i] = n; TD[i] = T0; Q[i] = v / n
    return ne, P, N, TD, Q
def recency_comp(s, T):
    import sieve_fullsearch as FS
    ne, P, N, TD = FS.comp(s, T, ((), 50000, "recency")); Q = np.zeros((len(T), NF), np.float32)
    for i, t in enumerate(T):
        j = np.arange(max(0, t - 50000), t); Q[i] = np.bincount(FORM[s[j]], weights=1 / (1 + (t - j)), minlength=NF) / (1 / (1 + (t - j))).sum()
    return ne, P, N, TD, Q
def graded_comp(s, T, attr, w, K=1000):
    A = s if attr == "id" else FORM[s]; w = np.array([int(x) for x in w] + [0] * (5 - len(w)))
    n_ = len(T); ne = np.zeros(n_, bool); P = np.zeros(n_); N = np.zeros(n_); TD = np.zeros(n_); Q = np.zeros((n_, NF), np.float32)
    for i, t in enumerate(T):
        j = np.arange(max(5, t - SC.H), t); eq = np.stack([A[j - a] == A[t - a] for a in range(1, 6)]).astype(np.int64)
        if attr == "idform": eq = eq + np.stack([FORM[s[j - a]] == FORM[s[t - a]] for a in range(1, 6)])
        sc = w @ eq; pos = np.nonzero(sc > 0)[0]
        if len(pos) == 0: continue
        sel = pos if len(pos) <= K else pos[np.argpartition(-(sc[pos] * 10**7 + pos), K)[:K]]; f = s[j][sel]; wt = 2.0 ** sc[sel]
        ne[i] = True; P[i] = wt[f == s[t]].sum() / wt.sum(); N[i] = len(sel); TD[i] = len(np.unique(f)); Q[i] = np.bincount(FORM[f], weights=wt, minlength=NF) / wt.sum()
    return ne, P, N, TD, Q
def hkeys(s, k):
    h = np.zeros(len(s), np.int64)
    for a in range(1, k + 1): v = np.zeros(len(s), np.int64); v[a:] = s[:len(s) - a]; h = h * np.int64(1_000_003) + v
    h &= MASK; h[:k] = -1; return h
def long_comp(s, T, src, kmin=3, kmax=8):
    n_ = len(T); ne = np.zeros(n_, bool); P = np.zeros(n_); N = np.zeros(n_); TD = np.zeros(n_); Q = np.zeros((n_, NF), np.float32); FOL = [None] * n_
    S = lib() if src == "library" else s; idx = {}
    for k in range(kmax, kmin - 1, -1):
        hs = hkeys(S, k); o = np.argsort(hs, kind="stable"); idx[k] = (hs[o], o, hkeys(s, k) if S is not s else hs)
    for i, t in enumerate(T):
        for k in range(kmax, kmin - 1, -1):
            sk, o, qk = idx[k]; q = qk[t]; lo, hi = np.searchsorted(sk, q), np.searchsorted(sk, q, "right"); pos = o[lo:hi]
            if src != "library": pos = pos[pos < t]
            if len(pos) == 0: continue
            f = S[pos]; y = s[t]; ne[i] = True; P[i] = (f == y).mean(); N[i] = len(f); u = np.unique(f); TD[i] = len(u); FOL[i] = u
            Q[i] = np.bincount(FORM[f], minlength=NF) / len(f); break
    return ne, P, N, TD, Q, FOL
def compute(ctx, n):
    s, T = CTX[ctx]; p = n.split("_")
    if p[0] == "count": r = count_comp(s, T, SETS[int(p[1])], p[2])
    elif p[0] == "recency": r = recency_comp(s, T)
    elif p[0] == "graded": r = graded_comp(s, T, p[1], p[2])
    else: r = long_comp(s, T, "library" if p[1] == "library" else "hist")
    ne, P, N, TD, Q = r[:5]; y = s[T]
    assert np.all(np.abs(Q[ne].sum(1) - 1) <= 1e-4), f"{n}: Q does not sum to 1"                         # SR2 checks (float32 storage)
    assert np.all(Q[ne, FORM[y[ne]]] >= P[ne] - 1e-4), f"{n}: Q[form of answer] < P(answer)"
    np.savez(os.path.join(CD, f"{ctx}_{n}.npz"), ne=ne, P=P, N=N, TD=TD, Q=Q.astype(np.float16))
    if len(r) > 5: np.save(os.path.join(CD, f"{ctx}_{n}_fol.npy"), np.array(r[5], dtype=object), allow_pickle=True)
MEMO = {}
def load(ctx, n, q=False):
    if (ctx, n, q) in MEMO: return MEMO[(ctx, n, q)]
    f = os.path.join(CD, f"{ctx}_{n}.npz")
    if not os.path.exists(f): compute(ctx, n)
    z = np.load(f); MEMO[(ctx, n, q)] = r = (z["ne"], z["P"], z["N"], z["TD"]) + ((z["Q"].astype(np.float32),) if q else ()); return r
def windows(ctx, W):
    f = os.path.join(CD, f"{ctx}_win{W}.npy")
    if not os.path.exists(f):
        s, T = CTX[ctx]; Pw = np.array([np.bincount(FORM[s[max(0, t - W):t]], minlength=NF) / min(W, t) for t in T], np.float32); np.save(f, Pw)
    return np.load(f)
# ---------------- programs: chain + escape + optional reweight ----------------
RW = [(W, b) for W in (200, 1000, 5000) for b in (0.25, 0.5, 1.0)]
def run_q(chain, C):
    """chain over loaded components C[k] = (ne, P, N, TD, Q): returns m, p, Q"""
    m, p, Q = C[chain[0][0]][0].copy(), C[chain[0][0]][1].copy(), C[chain[0][0]][4].copy(); prev = chain[0][0]
    for c, cb in chain[1:]:
        ne, P, N, TD, Qc = C[c]
        if cb[0] == "orelse": p = np.where(m, p, P); Q = np.where(m[:, None], Q, Qc)
        else:
            lam = cb[1] if cb[0] == "fixed" else np.where(C[prev][0], ST.LT[cb[1]][1](np.maximum(C[prev][2], 1), np.maximum(C[prev][3], 1)), 0.0)
            lam = np.broadcast_to(np.asarray(lam, float), m.shape); both = m & ne
            p = np.where(both, lam * p + (1 - lam) * P, np.where(m, p, P)); Q = np.where(both[:, None], lam[:, None] * Q + (1 - lam[:, None]) * Qc, np.where(m[:, None], Q, Qc))
        m = m | ne; prev = c
    return m, p, Q
def final(m, p, Q, e, rw, ctx, y):
    pe = np.where(m, (1 - e) * p + e / Vt, 1 / Vt); Qe = np.where(m[:, None], (1 - e) * Q + e * U, U)
    if rw is None: return pe, Qe
    W, beta = rw; b = ((windows(ctx, W) + 1e-4) / PG) ** beta; Zn = (Qe * b).sum(1); fy = FORM[y]
    return pe * b[np.arange(len(y)), fy] / Zn, Qe * b / Zn[:, None]
def calib(pf, Qf, y):
    top = np.argsort(-Qf, 1)[:, :3]; sp = np.take_along_axis(Qf, top, 1).ravel(); hit = (top == FORM[y][:, None]).ravel().astype(float)
    bins = np.minimum((sp * 10).astype(int), 9); refuted = 0
    for b in range(10):
        mk_ = bins == b; n = int(mk_.sum())
        if n >= 30 and not within(hit[mk_].mean(), sp[mk_].mean(), math.sqrt(math.log(2 / 0.01) / (2 * n)), distance=lambda a, b: abs(a - b)): refuted += 1
    return refuted
def search(names, budget=200):
    t0 = time.time(); C = [load("fit", n) for n in names]; NE, PP, NN, TT = (np.array([c[j] for c in C]) for j in range(4))
    DLc = lambda c: dl(names[c]); y = fit_s[Tf]
    progs = {((c, None),): ST.score([(c, None)], NE, PP, NN, TT, Vt, DLc) for c in range(len(names)) if NE[c].any()}
    order = lambda q: (round(progs[q][0], 9), repr(q)); beam = sorted(progs, key=order)[:SC.BEAM]; best = progs[beam[0]][0]
    for depth in range(2, 6):                                                                            # SR5: chains up to 5, MDL stops
        new = []
        for ch in beam:
            if len(ch) != depth - 1: continue
            m, p = ST.run(list(ch), NE, PP, NN, TT); e = progs[ch][2]; bits = -np.log2(np.where(m, (1 - e) * p + e / Vt, 1 / Vt)); res = bits >= np.quantile(bits, 0.75)
            gain = [(NE[c][res] * PP[c][res]).sum() if all(c != x for x, _ in ch) else -1 for c in range(len(names))]   # SR6: residual-steered candidates
            for c in np.argsort(gain, kind="stable")[::-1][:20]:
                for cb in ST.COMBS:
                    q = ch + ((int(c), cb),)
                    if q not in progs: progs[q] = ST.score(list(q), NE, PP, NN, TT, Vt, DLc); new.append(q)
        beam = sorted(set(beam) | set(new), key=order)[:SC.BEAM]; nb = progs[beam[0]][0]
        log(f"   depth {depth}: best total {nb:.1f} bits (was {best:.1f})")
        if nb >= best or time.time() - t0 > budget: break
        best = nb
    top = sorted(progs, key=order)[:SC.BEAM]; out = []
    for q in top:                                                                                         # SR1: reweight stage (1 bit none, else 1 + log2 3 + log2 3)
        Cq = {c: load("fit", names[c], True) for c, _ in q}; m, p, Q = run_q(list(q), Cq)
        for rw in [None] + RW:
            for e in SC.ESCS:
                pf, Qf = final(m, p, Q, e, rw, "fit", y); b = -np.log2(pf).sum()
                out.append((b + sum(DLc(c) for c, _ in q) + sum(ST.cbits(cb) for _, cb in q[1:]) + math.log2(len(SC.ESCS)) + (1 if rw is None else 1 + 2 * math.log2(3)), b, q, e, rw))
    out.sort(key=lambda r: (round(r[0], 9), repr(r[2]), repr(r[4])))
    for r in out:                                                                                         # SR10: calibration filter
        Cq = {c: load("fit", names[c], True) for c, _ in r[2]}; m, p, Q = run_q(list(r[2]), Cq); pf, Qf = final(m, p, Q, r[3], r[4], "fit", y)
        ref = calib(pf, Qf, y)
        if ref == 0: return r, out[0], pf
        log(f"   calibration: {pdesc(names, r)} refuted {ref} bin(s), skipped")
    return out[0], out[0], None
def pdesc(names, r):
    q = r[2]; return desc(names[q[0][0]]) + "".join(ST.cbname(cb) + desc(names[c]) for c, cb in q[1:]) + f" (escape {r[3]})" + ("" if r[4] is None else f" REWEIGHT by form shares of the past {r[4][0]} tokens, beta {r[4][1]}")
# ---------------- SR7: residual relations ----------------
def residuals(names, r, pf):
    y = fit_s[Tf]; bits = -np.log2(pf); res = np.nonzero(bits >= np.quantile(bits, 0.75))[0]; perm = np.random.default_rng(5).permutation(res); rows = []
    for W in (200, 1000, 5000):
        Pw = windows("fit", W); own = (Pw[res, FORM[y[res]]] > 0).mean(); ch = (Pw[res, FORM[y[perm]]] > 0).mean(); rows.append((own - ch, "reweight", f"form of the answer in the past {W}", own, ch))
    for src in ("hist", "library"):
        load("fit", f"long_{src}"); fol = np.load(os.path.join(CD, f"fit_long_{src}_fol.npy"), allow_pickle=True)
        has = lambda i, a: fol[i] is not None and a in set(fol[i].tolist())
        own = np.mean([has(i, y[i]) for i in res]); ch = np.mean([has(i, y[j]) for i, j in zip(res, perm)]); rows.append((own - ch, f"long_{src}", f"the answer follows an earlier occurrence of the last 3-8 words in the {src}", own, ch))
    for d, fam, txt, own, ch in rows: print(f"   residual relation '{txt}': {own:.3f} of residual answers vs {ch:.3f} (answers permuted)")
    return max(rows, key=lambda r: (round(r[0], 9), r[1]))
if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "cache":
        ctx, kind = sys.argv[2], sys.argv[3]; t0 = time.time(); done = 0
        for n in names_of(kind) if kind in KINDS else [kind]:
            if os.path.exists(os.path.join(CD, f"{ctx}_{n}.npz")): continue
            if time.time() - t0 > 200: break
            compute(ctx, n); done += 1
        left = sum(not os.path.exists(os.path.join(CD, f"{ctx}_{n}.npz")) for n in (names_of(kind) if kind in KINDS else [kind]))
        log(f"cached {done} {kind} components on {ctx} ({left} left)")
    elif mode == "round":
        r_ = int(sys.argv[2]); stf = os.path.join(HERE, "sieve_fs2_state.json")
        st = json.load(open(stf)) if r_ > 0 else dict(families=["count", "recency", "graded"], rounds=[])
        names = [n for k in ("count", "recency", "graded") if k in st["families"] for n in names_of(k)] + [f for f in st["families"] if f.startswith("long_")]
        rw_on = "reweight" in st["families"]
        if not rw_on: RW.clear()
        log(f"round {r_}: families {st['families']}; {len(names)} components")
        r, r0, pf = search(names)
        print(f"   MDL-best: {pdesc(names, r0)} -- fit {r0[1] / len(Tf):.4f} bits/word, description {r0[0] - r0[1]:.1f} bits")
        print(f"   selected (calibration filter): {pdesc(names, r)} -- fit {r[1] / len(Tf):.4f} bits/word")
        if pf is None: Cq = {c: load("fit", names[c], True) for c, _ in r[2]}; m, p, Q = run_q(list(r[2]), Cq); pf, _ = final(m, p, Q, r[3], r[4], "fit", fit_s[Tf])
        top = residuals(names, r, pf); adopted = [names[c] for c, _ in r[2]] + (["reweight"] if r[4] is not None else [])
        new = [f for f in st["families"] if f not in sum([x["offered"] for x in st["rounds"]], [])]
        st["rounds"].append(dict(round=r_, offered=new, adopted=adopted, program=dict(chain=[[names[c], cb] for c, cb in r[2]], escape=r[3], reweight=r[4]), top_relation=top[2], excess=top[0]))
        offered = st["rounds"][-1]["offered"]; took = r_ == 0 or any(a in offered or (a == "reweight" and "reweight" in offered) for a in adopted)
        fam = top[1]; nxt = took and fam not in st["families"] and r_ < 2                                 # SR7: stop when a round adopts nothing it was newly offered (max 3 rounds)
        if nxt: st["families"].append(fam)
        json.dump(st, open(stf, "w"), indent=1)
        log(f"round {r_}: top residual relation '{top[2]}' (excess {top[0]:.3f}) -> {'offer ' + fam + ' next round' if nxt else 'stop'}")
    else:
        st = json.load(open(os.path.join(HERE, "sieve_fs2_state.json"))); prog = st["rounds"][-1]["program"]
        if len(sys.argv) > 2: prog = dict(st["rounds"][int(sys.argv[2])]["program"])
        if len(sys.argv) > 3: prog["escape"] = float(sys.argv[3]); prog["reweight"] = [int(sys.argv[4]), float(sys.argv[5])] if len(sys.argv) > 5 else None   # the MDL-best variant (before the calibration filter)
        names = [n for n, _ in prog["chain"]]; C = {k: load("eval", n, True) for k, n in enumerate(names)}
        chain = [(k, None if cb is None else tuple(cb)) for k, (_, cb) in enumerate(prog["chain"])]; m, p, Q = run_q(chain, C); y = ev_s[Te]
        for rw in ([None, tuple(prog["reweight"])] if prog["reweight"] else [None]):
            pf, Qf = final(m, p, Q, prog["escape"], rw, "eval", y)
            log(f"SR on the {len(Te):,} positions{' without the reweight stage' if rw is None and prog['reweight'] else ''}: {(-np.log2(pf)).mean():.4f} bits/word; form-claim bins refuted {calib(pf, Qf, y)} (SQ2 8.3411, Stack 8.1507, LM 6.026)")
