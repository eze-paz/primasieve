"""FHRR (sieve_lang_prereg.md), Test A: does a phasor (FHRR) state hold the scene?
Atoms = fitted LSA phases (tau 32, D 64, MT 27M training text; cached to mtest/fhrr_th32.npy); pronouns map to one atom per
group (he/him/his -> he). Roles from the EWT tag dictionary + sentence position (noun/pronoun before the sentence's first
verb = SUBJ, after = OBJ); verbs bind their subject. Token phasor = exp(i (atom + role)) (verbs: atom + subject atom +
role VERB); function words weight 0; state = sum_j lam^j phasor(t - j), lam = 1 - 1/32 (no step rotation, so unbinding
works). At each sentence end of held-out human passages: unbind SUBJ (multiply by conj(role)), clean up against the
entities mentioned so far, compare with the next sentence's subject. Baselines: most recent subject; Centering salience
(3/2/1, halved per sentence). Run: py -3.12 sieve_fhrr.py"""
import json, os, time, numpy as np
exec(open("sieve_parse.py", encoding="utf-8").read().split("# ---- sanity")[0])
z = np.load("mtest/books_data.npz"); S = z["S"].astype(np.int64); ntr = int(z["ntr"]); vw = [str(w) for w in z["vw"]]; VV = int(S.max()) + 1
wid = {w: i for i, w in enumerate(vw)}; D = 64; TAU = 32
if os.path.exists("mtest/fhrr_th32.npy"): TH = np.load("mtest/fhrr_th32.npy")
else:                                                                                                       # same LSA phase fit as sieve_g1b_kernel.py (tau 32)
    import scipy.sparse as sp
    from scipy.sparse.linalg import svds
    Str_ = S[:ntr]; n_ = len(Str_) // TAU; idx_ = np.arange(n_ * TAU)
    X = sp.csr_matrix((np.ones(n_ * TAU, np.float32), (np.repeat(np.arange(n_, dtype=np.int32), TAU), Str_[idx_].astype(np.int32))), shape=(n_, VV)); X.sum_duplicates(); X.data = np.sqrt(X.data)
    c_ = np.asarray(X.sum(0)).ravel(); X = (X @ sp.diags((1 / np.sqrt(np.maximum(c_, 1e-12))).astype(np.float32))).astype(np.float32); U, s_, Vt = svds(X, k=2 * D); V_ = (Vt.T * s_[None]).astype(np.float64)
    V_ = V_ / np.maximum(np.linalg.norm(V_, axis=1, keepdims=True), 1e-12); TH = np.arctan2(V_[:, 1::2], V_[:, 0::2]); dead = np.linalg.norm(V_, axis=1) < 1e-9
    TH[dead] = np.random.default_rng(7).random((dead.sum(), D)) * 2 * np.pi; np.save("mtest/fhrr_th32.npy", TH)
print(f"atoms: {TH.shape} ({time.time() - T0:.0f} s)", flush=True)
# ---- roles (vectorised rule, same for corpus and text)
TAGW = np.full(VV, ti["NOUN"])                                                                              # unseen words: treated as nouns
for w, i in wid.items():
    if w in cw: TAGW[i] = max(range(len(TAGS)), key=lambda k: cw[w][k])
NOM = np.isin(TAGW, [ti["NOUN"], ti["PROPN"], ti["PRON"]]); VRB = TAGW == ti["VERB"]
PG = {w: g for g, ws in dict(he="he him his himself", she="she her hers herself", they="they them their theirs themselves", it="it its itself", i="i me my mine myself", you="you your yours yourself", we="we us our ours ourselves").items() for w in ws.split()}
ATOMID = np.arange(VV)
for w, g in PG.items():
    if w in wid and g in wid: ATOMID[wid[w]] = wid[g]
rg = np.random.default_rng(3); ROLE = {r: rg.random(D) * 2 * np.pi for r in ("SUBJ", "OBJ", "VERB")}
def roles(ids):
    """per token: role (0 none, 1 SUBJ, 2 OBJ, 3 VERB) and the atom of the verb's subject (-1 none)"""
    ids = np.asarray(ids); n = len(ids); sid = np.cumsum(ids == 0); idx = np.arange(n)
    isv = VRB[ids] & (ids != 0); fv = np.full(n, n)
    first = {}
    for k in np.nonzero(isv)[0]: first.setdefault(sid[k], k)
    fv = np.array([first.get(s_, n) for s_ in sid])
    nom = NOM[ids] & (ids != 0); role = np.where(nom & (idx < fv), 1, np.where(nom & (idx > fv), 2, np.where(isv, 3, 0)))
    last = np.maximum.accumulate(np.where(role == 1, idx, -1)); ok = (last >= 0) & (sid[np.maximum(last, 0)] == sid)
    vsub = np.where((role == 3) & ok, ATOMID[ids[np.maximum(last, 0)]], -1); return role, vsub
def phasors(ids):
    role, vsub = roles(ids); ph = TH[ATOMID[ids]].copy(); w = (role > 0).astype(float)
    for r, name in ((1, "SUBJ"), (2, "OBJ"), (3, "VERB")): ph[role == r] += ROLE[name]
    m = vsub >= 0; ph[m] += TH[vsub[m]]
    return np.exp(1j * ph) * w[:, None], role
def state(ids):
    P, _ = phasors(ids); lam = 1 - 1 / TAU; j = np.arange(len(ids))[::-1]; return ((lam ** j)[:, None] * P).sum(0)
# ---- Test A on held-out human passages
ev = S[ntr:]; st = np.nonzero((ev[1:-300] != 0) & (ev[:-301] == 0))[0] + 1; st = st[np.linspace(0, len(st) // 2, 400).astype(int)]
hit = dict(fhrr=0, recent=0, salience=0); n = 0
for s0 in st:
    ids = ev[s0:s0 + 150].astype(np.int64); cut = np.nonzero(ids == 0)[0]
    if len(cut) < 3: continue
    role, _ = roles(ids); atoms = ATOMID[ids]
    for a, b in zip(cut[:-1], cut[1:]):                                                                     # state at the end of a sentence (position a), truth = first SUBJ of the next sentence
        nxt = np.nonzero(role[a + 1:b] == 1)[0]
        if len(nxt) == 0: continue
        truth = atoms[a + 1 + nxt[0]]; seen = sorted(set(atoms[:a][np.isin(role[:a], (1, 2))]))
        if truth not in seen or len(seen) < 2: continue
        u = state(ids[:a + 1]) * np.exp(-1j * ROLE["SUBJ"]); sc = [float(np.real((u * np.exp(-1j * TH[e])).sum())) for e in seen]
        pred_f = seen[int(np.argmax(sc))]
        subs = atoms[:a][role[:a] == 1]; pred_r = subs[-1] if len(subs) else seen[0]
        sal = {}; sid_ = np.cumsum(ids[:a] == 0)
        for k in range(a):                                                                                  # Centering salience, halved per sentence
            if role[k] in (1, 2): sal[atoms[k]] = sal.get(atoms[k], 0) + (3.0 if role[k] == 1 else 2.0) * 0.5 ** (sid_[-1] - sid_[k])
        pred_s = max(sal, key=sal.get)
        n += 1; hit["fhrr"] += pred_f == truth; hit["recent"] += pred_r == truth; hit["salience"] += pred_s == truth
R = {k: round(v / max(n, 1), 4) for k, v in hit.items()}; R["cases"] = n
print("FHRR Test A: next-sentence subject (among entities already mentioned):", R, flush=True); json.dump(R, open("sieve_fhrr_testA.json", "w"), indent=1)
