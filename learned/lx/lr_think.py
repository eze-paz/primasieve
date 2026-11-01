"""TH1 deliberation (LX_prereg.md). At each held-out position the engine diagnoses why it is uncertain -- u1 previous
word unknown/rare, u2 local context rare, u3 group clear but word open, u4 open choice -- then (u1) asks the
dictionary (WordNet: part of speech of the previous word -> predict as after known words with the same part of speech
and ending) and (u1-u3, or everywhere as a control) looks the sentence's last 2-6 words up in the library
(lr_think_lib.py) and mixes in what followed there, weighted per diagnosis x match length x match count (fitted on
the other fold). Reports absolute word bits overall and per diagnosis, calibration, examples with the stated reason.
Run: py -3.12 -W ignore lr_think.py A|B"""
import sys, re, collections
import numpy as np
from lr_common import *
import lr3, lr8
NL = os.path.join(os.path.dirname(os.path.dirname(HERE)), "_nldata", "dict")
EXTW = json.load(open(os.path.join(HERE, "lx_ext_words.json"), encoding="utf-8"))
def word_of(xid): return wname(int(xid)) if xid < UNK else EXTW[int(xid) - UNK - 1]
# ---------------- dictionary: WordNet part of speech ----------------
IDX = {p: {l.split()[0] for l in open(os.path.join(NL, f"index.{p}"), encoding="utf-8") if not l.startswith(" ")} for p in ("noun", "verb", "adj", "adv")}
EXC = {p: {l.split()[0] for l in open(os.path.join(NL, f"{p}.exc"), encoding="utf-8")} for p in ("noun", "verb", "adj", "adv")}
DET = {"noun": [("s", ""), ("ses", "s"), ("xes", "x"), ("zes", "z"), ("ches", "ch"), ("shes", "sh"), ("men", "man"), ("ies", "y")],
       "verb": [("s", ""), ("ies", "y"), ("es", "e"), ("es", ""), ("ed", "e"), ("ed", ""), ("ing", "e"), ("ing", "")],
       "adj": [("er", ""), ("est", ""), ("er", "e"), ("est", "e")], "adv": []}
def pos_of(w):
    out = set()
    for p in IDX:
        if w in IDX[p] or w in EXC[p] or any(w.endswith(a) and w[:len(w) - len(a)] + b in IDX[p] for a, b in DET[p]): out.add(p)
    return frozenset(out)
cw = np.bincount(tr, minlength=NW)
mtr = np.r_[False, trs[1:] == trs[:-1]]; pk = tr[:-1][mtr[1:]] * NG + gid[tr[1:][mtr[1:]]]
uk, nk = np.unique(pk, return_counts=True); uw, ug = uk // NG, uk % NG
known = np.nonzero(cw >= 20)[0]; known = known[(known > 0) & (known < UNK)]
sig = collections.defaultdict(lambda: np.zeros(NG))
for w in known:
    s = words[w - 1]; p = pos_of(s)
    if not p: continue
    lo, hi = np.searchsorted(uw, w), np.searchsorted(uw, w + 1); row = np.zeros(NG); row[ug[lo:hi]] = nk[lo:hi]
    for key in ((p, s[-3:]), (p, s[-2:]), (p,)): sig[key] += row
def proxy(s):
    p = pos_of(s)
    if not p: return None, p
    for key in ((p, s[-3:]), (p, s[-2:]), (p,)):
        if key in sig and sig[key].sum() >= 50: r = sig[key]; return np.log((r + 50 * P0) / (r.sum() + 50) / np.maximum(P0, 1e-12)) * (P0 > 0), p
    return None, p
# TH2: Wiktionary parts of speech (lr_wikt.py) for words WordNet lacks; proper nouns predict as after training names
WKP = {"Noun": "noun", "Verb": "verb", "Adjective": "adj", "Adverb": "adv"}
WK = {w: {x for v in d.values() for x in v} for w, d in json.load(open(os.path.join(HERE, "lr_wikt.json"), encoding="utf-8")).items()} if os.path.exists(os.path.join(HERE, "lr_wikt.json")) else {}
capshare = np.bincount(tr, weights=trc, minlength=NW) / np.maximum(cw, 1)
names = known[capshare[known] >= 0.8]; nrow = np.zeros(NG)
for w in names: lo, hi = np.searchsorted(uw, w), np.searchsorted(uw, w + 1); nrow[ug[lo:hi]] += nk[lo:hi]
def proxy_wikt(s):
    ps = WK.get(s, set())
    if "Proper noun" in ps: r = nrow
    else:
        p = frozenset(WKP[x] for x in ps if x in WKP); r = next((sig[k] for k in ((p, s[-3:]), (p, s[-2:]), (p,)) if p and k in sig and sig[k].sum() >= 50), None)
        if r is None: return None
    return np.log((r + 50 * P0) / (r.sum() + 50) / np.maximum(P0, 1e-12)) * (P0 > 0)
# ---------------- diagnosis ----------------
_, C2tr = None, None
g1 = gid[np.r_[0, tr[:-1]]]; g2 = np.where(np.r_[False, False, trs[2:] == trs[:-2]], gid[np.r_[0, 0, tr[:-2]]], G0 + 1)
c2k, c2n = np.unique((g2 * NG + g1)[mtr], return_counts=True)
def diagnose(F, topp):
    t = F.pos; prev = F.tok[t - 1]; rare = (prev == UNK) | (cw[np.minimum(prev, NW - 1)] < 5)
    same2 = (t >= 2) & (F.sid[np.maximum(t - 2, 0)] == F.sid[t]); k2 = np.where(same2, gid[F.tok[np.maximum(t - 2, 0)]], G0 + 1) * NG + gid[prev]
    i = np.clip(np.searchsorted(c2k, k2), 0, len(c2k) - 1); n2 = np.where(c2k[i] == k2, c2n[i], 0)
    return np.where(rare, 1, np.where(n2 < 5, 2, np.where(topp >= 0.5, 3, 4)))
def group_parts(F, S, beta, step=10_000):
    lt, tp = [], []
    for a in range(0, F.n, step):
        b = min(a + step, F.n); z = np.log(F.PL[a:b].astype(np.float64))
        for Sk, bk in zip(S, beta): z += bk * Sk[a:b]
        z -= z.max(1, keepdims=True); p = np.exp(z); p /= p.sum(1, keepdims=True); lt.append(p[np.arange(b - a), F.g[a:b]]); tp.append(p.max(1))
    return np.concatenate(lt), np.concatenate(tp)
# ---------------- per fold ----------------
fold = sys.argv[1] if len(sys.argv) > 1 else "A"; _, Ff, Fs = [f for f in FOLDS if f[0] == fold][0]
LB = np.load(os.path.join(HERE, "lr_think_lib.npz"))
S = {}; D = {}
for F in (Ff, Fs):
    Sw, Sg, _, _ = cache(F); c = Sw[:, 0] / np.maximum(Sg[:, 0], 1e-12); act = Sg[:, 0] > 0
    feats = [lr3.feature(lr3.topic_post(F, lr3.PR_), lr3.PR_, 20), lr8.f_dist(F)]
    dic = np.zeros((F.n, NG), np.float32); hasd = np.zeros(F.n, bool); nopos = []; dic2 = np.zeros((F.n, NG), np.float32); hasw = np.zeros(F.n, bool)
    S[F.name] = dict(c=c, act=act, feats=feats, dic=dic, hasd=hasd, nopos=nopos, dic2=dic2, hasw=hasw, k=LB[f"{F.name}_k"].astype(int), n=LB[f"{F.name}_n"], cc=LB[f"{F.name}_c"])
log("registers built")
rr = rules_r(Ff, fit_r(Ff, S[Ff.name]["c"], S[Ff.name]["act"]), S[Ff.name]["c"], S[Ff.name]["act"])[0]
beta = fit_beta(Ff, S[Ff.name]["feats"])
for F in (Ff, Fs):
    Q = S[F.name]; lt, tp = group_parts(F, Q["feats"], beta); Q["diag"] = diagnose(F, tp)
    for i in np.nonzero(Q["diag"] == 1)[0]:
        s = word_of(F.x[F.pos[i] - 1]); r, p = proxy(s)
        if r is not None: Q["dic"][i] = r; Q["dic2"][i] = r; Q["hasd"][i] = True
        elif not p:
            Q["nopos"].append(s); r2 = proxy_wikt(s)
            if r2 is not None: Q["dic2"][i] = r2; Q["hasw"][i] = True
    Q["pw_stack"] = word_logp(F, rr, Q["c"], Q["act"])
log(f"diagnosis on the scored fold: " + ", ".join(f"u{d} {(S[Fs.name]['diag'] == d).mean():.1%}" for d in (1, 2, 3, 4)) + f"; dictionary answered {S[Fs.name]['hasd'].sum():,} of {(S[Fs.name]['diag'] == 1).sum():,} u1 positions")
beta_d = fit_beta(Ff, S[Ff.name]["feats"] + [S[Ff.name]["dic"]])
beta_w = fit_beta(Ff, S[Ff.name]["feats"] + [S[Ff.name]["dic2"]])
for F in (Ff, Fs):
    Q = S[F.name]; Q["lg0"] = group_logp(F, Q["feats"], beta); Q["lgd"] = group_logp(F, Q["feats"] + [Q["dic"]], beta_d); Q["lgw"] = group_logp(F, Q["feats"] + [Q["dic2"]], beta_w)
Q = S[Fs.name]; m = Q["hasw"]
log(f"TH2 online dictionary, {m.sum()} positions after a word only Wiktionary knows: word bits stack + WordNet {-(Q['lgd'] + Q['pw_stack'])[m].mean():.4f}; + Wiktionary {-(Q['lgw'] + Q['pw_stack'])[m].mean():.4f}")
def bucket(Q):
    nb = np.where(Q["n"] < 5, 0, np.where(Q["n"] < 20, 1, 2)); return ((Q["diag"] - 1) * 7 + Q["k"]) * 3 + nb
NB = 4 * 7 * 3
def fit_lam(Q, base_lp, allow):
    p = 2.0 ** base_lp; q = Q["cc"] / np.maximum(Q["n"], 1); on = (Q["k"] > 0) & allow[Q["diag"]]; b = bucket(Q); lam = np.full(NB, 0.2)
    for _ in range(50):
        resp = np.where(on, lam[b] * q / np.maximum((1 - lam[b]) * p + lam[b] * q, 1e-300), 0)
        lam = np.bincount(b, weights=resp, minlength=NB) / np.maximum(np.bincount(b, weights=on, minlength=NB), 1)
    return lam
def mix(Q, base_lp, lam, allow):
    p = 2.0 ** base_lp; q = Q["cc"] / np.maximum(Q["n"], 1); on = (Q["k"] > 0) & allow[Q["diag"]]; l = np.where(on, lam[bucket(Q)], 0)
    return np.log2((1 - l) * p + l * q), l
ALL = np.array([False, True, True, True, True]); DIAG = np.array([False, True, True, True, False]); NONE = np.zeros(5, bool)
res = {}
for nm, gkey, allow in (("stack", "lg0", NONE), ("stack + dictionary", "lgd", NONE), ("+ lookup on u1-u3 (diagnosed)", "lgd", DIAG),
                        ("+ lookup everywhere (control)", "lgd", ALL)):
    Qf = S[Ff.name]; lam = fit_lam(Qf, Qf[gkey] + Qf["pw_stack"], allow) if allow.any() else np.zeros(NB)
    Q = S[Fs.name]; lp, l = mix(Q, Q[gkey] + Q["pw_stack"], lam, allow); res[nm] = (-lp, l, lam)
d = S[Fs.name]["diag"]
np.savez(os.path.join(HERE, f"lr_think_bits_{Fs.name}.npz"), stack=res["stack"][0], lookall=res["+ lookup everywhere (control)"][0], diag=d)   # for lr_c12.py
log(f"fold {fold} (fit {Ff.name}, score {Fs.name}), word bits: " + "; ".join(f"{nm} {v[0].mean():.4f}" for nm, v in res.items()))
for u in (1, 2, 3, 4):
    m = d == u; print(f"   u{u} ({m.sum():,} positions): " + "; ".join(f"{nm} {v[0][m].mean():.4f}" for nm, v in res.items()))
print(f"   lookups per position (diagnosed): {((S[Fs.name]['k'] > 0) & DIAG[d]).mean():.3f}; library found per diagnosis: " + ", ".join(f"u{u} {(S[Fs.name]['k'][d == u] > 0).mean():.2f}" for u in (1, 2, 3, 4)))
print(f"   unknown previous words WordNet lacks (for TH2), {len(set(S[Fs.name]['nopos']))} distinct: {sorted(set(S[Fs.name]['nopos']))[:25]}")
json.dump(sorted(set(S[Ff.name]["nopos"]) | set(S[Fs.name]["nopos"])), open(os.path.join(HERE, f"lr_think_nopos_{fold}.json"), "w"))
if fold == "A":
    F = Fs; Q = S[F.name]; nm = "+ lookup on u1-u3 (diagnosed)"; l = res[nm][1]
    spk = LB["spk"]; Pg = group_logp(F, Q["feats"] + [Q["dic"]], beta_d, full=True); Pl = np.zeros_like(Pg)
    np.add.at(Pl, (spk[:, 0], spk[:, 1]), spk[:, 2]); Pl /= np.maximum(Pl.sum(1, keepdims=True), 1)
    for title, P in (("stack", group_logp(F, Q["feats"], beta, full=True)), ("with deliberation", (1 - l[:, None]) * Pg + l[:, None] * Pl)):
        o = np.argsort(-P, 1)[:, :3]; p = np.take_along_axis(P, o, 1); asrt = p[:, 0] >= 0.9; hit = o == F.g[:, None]
        ps = np.r_[p[asrt, 0], p[~asrt].ravel()]; hs = np.r_[hit[asrt, 0], hit[~asrt].ravel()].astype(float); bins = np.minimum((ps * 10).astype(int), 9)
        ece = sum(abs(ps[bins == b].mean() - hs[bins == b].mean()) * (bins == b).sum() for b in range(10) if (bins == b).any()) / len(ps)
        print(f"   speaking ({title}): asserts {asrt.mean():.2%} (right {hit[asrt, 0].mean():.3f}); top-3: truth among three {hit[~asrt].any(1).mean():.3f}, stated {p[~asrt].sum(1).mean():.3f}; calibration error {ece:.4f}")
    inv = {}
    for i in range(1, NW - 1): inv.setdefault(int(gid[i]), []).append(i)
    gname = lambda g: "/".join(wname(i) for i in inv.get(int(g), [])[:2])
    rng = np.random.default_rng(11); why = {1: "previous word unknown/rare", 2: "local context rare", 3: "group clear, word open", 4: "open choice"}
    for u in (1, 2, 3, 4):
        for i in rng.choice(np.nonzero((d == u) & ((Q["k"] > 0) | (u == 4)))[0], 2, replace=False):
            t = F.pos[i]; ctx = " ".join(word_of(F.x[j]) for j in range(max(t - Q["k"][i], t - 6) if Q["k"][i] else t - 3, t) if F.sid[j] == F.sid[t])
            act = f"library: '{ctx}' found {int(Q['n'][i])}x, followed by the true word {int(Q['cc'][i])}x, weight {l[i]:.2f}" if l[i] > 0 else "no lookup"
            if Q["hasd"][i]: act += f"; dictionary: '{word_of(F.x[t - 1])}' is {'/'.join(sorted(pos_of(word_of(F.x[t - 1]))))}"
            pb = res["stack"][0][i]; pa = res[nm][0][i]
            print(f"   [{why[u]}] ...{ctx} -> '{word_of(F.x[t])}': {act}; bits {pb:.2f} -> {pa:.2f}")
