"""SZ3 (sieve_lang_prereg.md): seven non-counting primitives added to SZ2's language. (1) sim(K) terms: anchors
ranked by cosine similarity of follower-form signatures, weighted by it; (2) self-made attributes c50 / c200 (k-means
on the same signatures); (3) registers: last rare word / last capitalised mid-sentence word as position attributes,
and eq_ terms (anchor token == t's register); (4) Spell(part, B): shortlist words sharing a 3-letter suffix / 4-letter
prefix with recent tokens; (5) sentence position as a position attribute; (6) cgate: per-c50-class weights for one
member; (7) Lag(m): predict token[t - p] for the m best-agreeing lags. Search as SZ2 (strategies, bandit, screening),
continuing from SZ2's state. Run: py -3.12 -W ignore sieve_prim3.py prep | search | eval | ablate"""
import os, sys, json, math, time, itertools
import numpy as np
import sieve_fs2 as F
import sieve_prim as P
import sieve_prim2 as P2
T0 = time.time(); CX, SUB = P2.CX, P2.SUB; CK = os.path.join(F.HERE, "sieve_prim3_fit9.json"); PD = P.PD
STRATS = P2.STRATS
# ---------------- (1)(2) signatures and self-made attributes ----------------
def signatures():
    f = os.path.join(PD, "sig.npy")
    if not os.path.exists(f):
        S = P.corpus(); uk, nN, nT, pairs, cnt_, _, _ = F.static(S, (("id", 1),)); k = pairs >> np.int64(17); y = pairs & (F.SH - 1)
        G = np.zeros((F.Vt, F.NF), np.float32); np.add.at(G, (k, F.FORM[y]), cnt_.astype(np.float32))
        G = np.sqrt(G / np.maximum(G.sum(1, keepdims=True), 1)); G /= np.maximum(np.linalg.norm(G, axis=1, keepdims=True), 1e-9); np.save(f, G.astype(np.float16))
    return np.load(f).astype(np.float32)
def clusters(k):
    f = os.path.join(PD, f"c{k}.npy")
    if not os.path.exists(f):
        G = signatures(); C = P.ccount(); big = np.nonzero(C >= 20)[0]; X = G[big]; cen = X[np.linspace(0, len(X) - 1, k).astype(int)].copy()
        for _ in range(8):
            lab = np.concatenate([np.argmax(X[a:a + 5000] @ cen.T, 1) for a in range(0, len(X), 5000)])
            for c in range(k):
                m = lab == c
                if m.any(): cen[c] = X[m].mean(0)
            cen /= np.maximum(np.linalg.norm(cen, axis=1, keepdims=True), 1e-9)
        lab_all = np.concatenate([np.argmax(G[a:a + 5000] @ cen.T, 1) for a in range(0, len(G), 5000)]); np.save(f, lab_all.astype(np.int64))
    return np.load(f)
# ---------------- (3)(5) position attributes ----------------
def mkc(tok, sid, c): bk = np.nonzero(sid[1:] != sid[:-1])[0] + 1; return np.insert(c.astype(bool), bk, False)
CAPS = {}
def caps(cx):
    if cx not in CAPS:
        tr_c = mkc(F.Z["tr"], F.Z["trs"], F.DD["trc"]); s, T, _ = F.ctx(cx)
        rest = mkc(F.DD["dv"], F.DD["dvs"], F.DD["dvc"]) if s is F.fit_s else mkc(F.Z["te"], F.Z["tes"], F.DD["tec"])
        CAPS[cx] = np.r_[tr_c, rest][:len(s)]
    return CAPS[cx]
PA = {}
def posattr(cx, name):
    if (cx, name) in PA: return PA[(cx, name)]
    s, T, _ = F.ctx(cx); n = len(s); idx = np.arange(n)
    if name == "spos":
        b = np.maximum.accumulate(np.where(s == 0, idx, 0)); d = idx - b; v = np.digitize(d, [1, 2, 3, 6, 11])
    else:
        if name == "regcap":
            c = caps(cx); prevb = np.r_[True, s[:-1] == 0]; ok = c & ~prevb & (s != 0)
        else: thr = int(name[3:]); ok = (P.ccount()[s] <= thr) & (s != 0)
        last = np.maximum.accumulate(np.where(ok, idx, -1)); v = np.where(last >= 0, s[np.maximum(last, 0)], -1)
    PA[(cx, name)] = v; return v
_valid, _describe, _Model = P.valid, P.describe, P.Model                                             # originals (install() replaces them)
TOKATTR = P.ATTRS + ("c50", "c200"); POSATTR = ("spos", "reg100", "reg1000", "regcap"); EQATTR = ("eq_reg100", "eq_reg1000", "eq_regcap"); SIMATTR = ("sim50", "sim500")
ALLATTR = TOKATTR + POSATTR + EQATTR + SIMATTR
def setup():
    F.AT["c50"] = clusters(50); F.AT["c200"] = clusters(200)
# ---------------- specs ----------------
def kind(sp): return sp.get("kind", "vote")
def valid(sp):
    k = kind(sp)
    if k == "spell": return sp["part"] in ("suf3", "pre4") and sp["B"] in (50, 1000)
    if k == "lag": return sp["m"] in (1, 3)
    tm = sp["terms"]
    if any(t[1] not in ALLATTR for t in tm): return False
    if any(t[3] is not None and t[1] != "id" for t in tm): return False
    special = [t for t in tm if t[1] in POSATTR + EQATTR + SIMATTR]
    if special and sp["src"] == "static": return False
    if any(t[1] in SIMATTR for t in tm) and (sp["src"] != "w1000" or sum(t[1] in SIMATTR for t in tm) > 1): return False
    if any(t[1] in EQATTR + SIMATTR and t[2] != 1 for t in tm): return False
    return _valid({**sp, "terms": [t if t[1] in P.ATTRS else [t[0], "id", t[2], t[3]] for t in tm]})
def bits_of(sp):
    k = kind(sp); b = math.log2(3)
    if k == "spell": return b + 2
    if k == "lag": return b + 1
    return b + math.log2(len(P.SRCS)) + math.log2(3) + len(sp["terms"]) * (math.log2(3) + math.log2(len(ALLATTR)) + math.log2(3) + math.log2(3)) + math.log2(3) + 1
def sample(rng):
    r = rng.random()
    if r < 0.1: return dict(kind="spell", part=str(rng.choice(["suf3", "pre4"])), B=int(rng.choice([50, 1000])))
    if r < 0.15: return dict(kind="lag", m=int(rng.choice([1, 3])))
    while True:
        sp = dict(src=str(rng.choice(P.SRCS)), terms=[[int(rng.choice(P.AS)), str(rng.choice(ALLATTR)), int(rng.choice(P.BS)), (lambda v: None if v is None else int(v))(P.THRS[rng.integers(3)])] for _ in range(int(rng.integers(3)))],
                  span=int(rng.choice(P.SPANS)), w=str(rng.choice(P.WTS)))
        if valid(sp): return sp
def mutate(sp, rng):
    if kind(sp) != "vote": return sample(rng)
    for _ in range(50):
        q = json.loads(P.key(sp)); f = rng.integers(6)
        if f == 0: q["src"] = str(rng.choice(P.SRCS))
        elif f == 1: q["span"] = int(rng.choice(P.SPANS))
        elif f == 2: q["w"] = str(rng.choice(P.WTS))
        elif f == 3 and len(q["terms"]) < 2: q["terms"].append([int(rng.choice(P.AS)), str(rng.choice(ALLATTR)), 1, None])
        elif f == 4 and q["terms"]: q["terms"].pop(int(rng.integers(len(q["terms"]))))
        elif q["terms"]:
            t = q["terms"][int(rng.integers(len(q["terms"])))]; g = rng.integers(4)
            if g == 0: t[0] = int(rng.choice(P.AS))
            elif g == 1: t[1] = str(rng.choice(ALLATTR))
            elif g == 2: t[2] = int(rng.choice(P.BS))
            else: t[3] = (lambda v: None if v is None else int(v))(P.THRS[rng.integers(3)])
        if valid(q) and P.key(q) != P.key(sp): return q
    return None
NEWT = [[a, at, 1, None] for a in P.AS for at in ("c50", "c200") + POSATTR + EQATTR + SIMATTR]
def levin():
    out = [dict(kind="spell", part=p, B=B) for p in ("suf3", "pre4") for B in (50, 1000)] + [dict(kind="lag", m=m) for m in (1, 3)]
    for src in P.SRCS:
        for sp in P.SPANS:
            for w in P.WTS:
                for t in NEWT:
                    d = dict(src=src, terms=[t], span=sp, w=w)
                    if valid(d): out.append(d)
    out.sort(key=lambda d: (round(bits_of(d), 9), P.key(d))); return out
def neighbours(sp):
    if kind(sp) != "vote": return []
    out = P2.neighbours(sp)
    for i in range(len(sp["terms"])):
        for at in ALLATTR:
            q = json.loads(P.key(sp)); q["terms"][i][1] = at; out.append(q)
    if len(sp["terms"]) < 2:
        for t in NEWT: q = json.loads(P.key(sp)); q["terms"].append(t); out.append(q)
    return [q for q in out if valid(q) and P.key(q) != P.key(sp)]
def describe(sp):
    k = kind(sp)
    if k == "spell": return f"Spell[{'3-letter suffix' if sp['part'] == 'suf3' else '4-letter prefix'} shared with the last {sp['B']}]"
    if k == "lag": return f"Lag[best {sp['m']} lag(s) <= 50 over the last 1,000]"
    return _describe(sp)
# ---------------- evaluation of the new kinds ----------------
VOC = None
def parts_of():
    global VOC
    if VOC is None:
        w = [""] + json.load(open(os.path.join(F.SC.LX, "lx_vocab.json"), encoding="utf-8"))["words"] + [""]
        code = lambda keyf: (lambda u: np.array([u.setdefault(keyf(x), len(u)) if x else -1 for x in w]))({})
        VOC = dict(suf3=code(lambda x: x[-3:] if len(x) >= 4 else "#" + x), pre4=code(lambda x: x[:4] if len(x) >= 5 else "#" + x))
    return VOC
_vote = P.vote
def vote(cx, sp):
    if kind(sp) == "vote" and all(t[1] in P.ATTRS for t in sp["terms"]): return _vote(cx, sp)
    if kind(sp) == "vote" and all(t[1] in TOKATTR for t in sp["terms"]) and sp["src"] == "static": return _vote(cx, sp)
    f = os.path.join(PD, f"{cx}_{__import__('hashlib').md5(P.key(sp).encode()).hexdigest()[:16]}.npz")
    if os.path.exists(f): z = np.load(f); return z["D"].astype(np.float32), z["ne"], z["N"], z["TD"]
    s, T, book = F.ctx(cx); SL, ans = P.shortlist(cx); n, K = SL.shape; D = np.zeros((n, K + 1), np.float32); N = np.zeros(n); TD = np.zeros(n)
    def put(i, toks, wts):
        c = np.searchsorted(SL[i], toks); cc = np.minimum(c, K - 1); hit = SL[i][cc] == toks
        D[i, :K] = np.bincount(c[hit], wts[hit], minlength=K)[:K]; D[i, K] = wts[~hit].sum(); N[i] = wts.sum(); TD[i] = len(np.unique(toks))
    k = kind(sp)
    if k == "spell":
        pc = parts_of()[sp["part"]]; B = sp["B"]
        for i, t in enumerate(T):
            rp = pc[s[max(0, t - B):t]]; rp = rp[rp >= 0]
            if not len(rp): continue
            u, c = np.unique(rp, return_counts=True); cp = pc[np.minimum(SL[i], F.Vt - 1)]; j = np.clip(np.searchsorted(u, cp), 0, len(u) - 1)
            v = np.where((SL[i] < F.Vt) & (u[j] == cp), c[j], 0).astype(float)
            if v.sum() > 0: D[i, :K] = v; N[i] = v.sum(); TD[i] = (v > 0).sum()
    elif k == "lag":
        m = sp["m"]; L = np.arange(1, 51)
        for i, t in enumerate(T):
            w0 = np.arange(max(51, t - 1000), t)
            if not len(w0): continue
            agree = (s[w0][None, :] == s[w0[None, :] - L[:, None]]).sum(1); top = np.argsort(-agree, kind="stable")[:m]; top = top[agree[top] > 0]
            if not len(top): continue
            put(i, s[t - L[top]], agree[top].astype(float))
    else:
        Aat = {}
        def arr(at):
            if at not in Aat: Aat[at] = posattr(cx, at) if at in POSATTR else (F.AT[at][s] if at in TOKATTR else None)
            return Aat[at]
        G = signatures() if any(t[1] in SIMATTR for t in sp["terms"]) else None
        C = P.ccount(); Wn = {"w1000": 1000, "w50000": 50000}.get(sp["src"]); bstart = {}; span = sp["span"]
        for i, t in enumerate(T):
            if Wn: j = np.arange(max(3, t - Wn), t - 1)
            else:
                b = book[t]
                if b not in bstart:
                    x = t
                    while x > F.NT and book[x - 1] == b: x -= 1
                    bstart[b] = x
                j = np.arange(max(bstart[b], 3), t - 1)
            wt = None
            for a, at, B, thr in sp["terms"]:
                if not len(j): break
                if at in EQATTR: R = posattr(cx, at[3:]); j = j[s[j - a] == R[t - 1 - a]]
                elif at in SIMATTR:
                    Kk = int(at[3:]); sim = G[s[j - a]] @ G[s[t - 1 - a]]; top = np.argsort(-sim, kind="stable")[:Kk]; j = j[top]; wt = np.maximum(sim[top], 0)
                else:
                    A = arr(at); tg = A[max(0, t - 1 - a - B + 1):t - a]; keep = np.isin(A[j - a], tg); j = j[keep]
                    if wt is not None: wt = wt[keep]
                if thr is not None: keep = C[s[j - a]] <= thr; j = j[keep]; wt = wt[keep] if wt is not None else None
            if not len(j): continue
            e = (j[:, None] + np.arange(1, span + 1)); ok = e < t; base = np.ones(e.shape) if wt is None else np.repeat(wt[:, None], span, 1)
            e, base = e[ok], base[ok]
            if not len(e): continue
            put(i, s[e], base * (1.0 if sp["w"] == "1" else 1.0 / (1 + (t - e))))
    ne = N > 0; D[ne] /= np.maximum(D[ne].sum(1, keepdims=True), 1e-12) if k == "spell" else N[ne, None]
    np.savez(f, D=D.astype(np.float16), ne=ne, N=N, TD=TD); return D, ne, N, TD
# ---------------- (6) cgate model ----------------
class Model(_Model):
    def __init__(s_, cx, st):
        super().__init__(cx, st); sv, T, _ = F.ctx(cx); s_.cprev = clusters(50)[sv[T - 1]]; s_.cg = {int(k): np.array(v) for k, v in st.get("cg", {}).items()}
    def parts(s_):
        w0 = np.exp(s_.th[0]); A = w0 * s_.Du.copy(); W = [np.full(s_.n, w0)]
        for k, c in enumerate(s_.mem):
            w = np.exp(s_.th[k + 1] + s_.ga[k + 1] * s_.lg(c) + (s_.cg[k + 1][s_.cprev] if (k + 1) in s_.cg else 0)) * c[1]; A += w[:, None] * c[0]; W.append(w)
        logL = np.zeros_like(A)
        for k, c in enumerate(s_.lif): logL += s_.be[k] * np.where(c[1][:, None], np.log((c[0] + s_.Du) / (2 * s_.Du + 1e-30)), 0)
        return A, logL, W
def install():
    setup(); P.vote = vote; P.valid = valid; P.bits_of = bits_of; P.describe = describe; P.sample = sample; P.mutate = mutate; P.Model = Model
def state():
    if not os.path.exists(CK):
        s2 = json.load(open(P2.CK)); s2.update(levin_i=0, neigh=[], idle=0, run=0, cg={}, log3=[], strat={s: [0, 0] for s in STRATS}); json.dump(s2, open(CK, "w"))
    return json.load(open(CK))
def search_main():
    """one checkpointed search run (SZ3 rules); state file CK, tag LABEL"""
    install(); st = state(); st["run"] += 1; rng = np.random.default_rng(5000 + st["run"]); half = 0.5 * math.log2(9000); move = math.log2(5)
    Ms = Model(SUB, st); Ms.gact = st["gact"]; scale = 9000 / Ms.n
    F.log(f"{LABEL} run {st['run']}: {len(st['mem'])} Votes, {len(st['lift'])} lifts, {int(sum(st['gact']))} gates, {len(st['cg'])} class-weights; bandit {st['strat']}")
    r = {s: (st["strat"][s][1] + 1) / (st["strat"][s][0] + 2) for s in STRATS}; pr = np.array([r[s] for s in STRATS]); pr /= pr.sum()
    seen = set(st["screen"]) | set(st["evaluated"]); members = [json.loads(k) for k in st["mem"] + st["lift"]]; vm = [m for m in members if kind(m) == "vote"]; L = levin(); nscr = 0
    def gen(s):
        """one proposal from strategy s (None if it has nothing new)"""
        for _ in range(20):
            if s == "prior": sp = sample(rng)
            elif s == "levin":
                if st["levin_i"] >= len(L): return None
                sp = L[st["levin_i"]]; st["levin_i"] += 1
            elif s == "neigh":
                if not st["neigh"]: return None
                sp = st["neigh"].pop(0)
            elif s == "mutate": sp = mutate(members[rng.integers(len(members))], rng) if members else None
            else:
                if len(vm) < 2: return None
                a, b = (vm[i] for i in rng.choice(len(vm), 2, replace=False)); sp = dict(src=a["src"], span=a["span"], w=a["w"], terms=b["terms"][:2])
            if sp and valid(sp) and P.key(sp) not in seen: seen.add(P.key(sp)); return sp
        return None
    while time.time() - T0 < 115:                                                                    # keep proposing until the screening budget is used
        s = STRATS[int(rng.choice(len(STRATS), p=pr))]; sp = gen(s)
        if sp is None: continue
        k = P.key(sp); c = vote(SUB, sp); gm, gl = P2.gains(Ms, c); est = max(gm, gl) * scale - (move + bits_of(sp) + half)
        st["screen"][k] = est; st["origin"][k] = s; st["strat"][s][0] += 1; nscr += 1
    F.log(f"   screened {nscr} proposals")
    json.dump(st, open(CK, "w"))
    for k in sorted((k for k, v in st["screen"].items() if v > 0 and k not in st["evaluated"]), key=lambda k: -st["screen"][k]):
        if time.time() - T0 > 170: break
        vote(CX, json.loads(k)); st["evaluated"].append(k); F.log(f"   promoted ({st['origin'].get(k, '-')}, est {st['screen'][k]:.0f} bits): {describe(json.loads(k))}")
    json.dump(st, open(CK, "w"))
    M = Model(CX, st); M.gact = st["gact"]; n = M.n; cur = M.bits(); accepted = 0
    while time.time() - T0 < 235:
        A, logL, W = M.parts(); Lx = np.exp(logL - logL.max(1, keepdims=True)); Z = (A * Lx).sum(1); Pm = A * Lx / Z[:, None]; Aa = A[M.ix, M.ans]; cand = []
        for k in st["evaluated"]:
            if k in st["rejected"]: continue
            c = vote(CX, json.loads(k)); sp = json.loads(k)
            if k not in st["mem"]: cand.append(("mix", k, (c[1] * (c[0][M.ix, M.ans] / Aa - (c[0] * Lx).sum(1) / Z)).sum(), move + bits_of(sp) + half))
            if k not in st["lift"]:
                lgl = np.where(c[1][:, None], np.log((c[0] + M.Du) / (2 * M.Du + 1e-30)), 0); cand.append(("lift", k, abs((lgl[M.ix, M.ans] - (Pm * lgl).sum(1)).sum()), move + bits_of(sp) + half))
        for i, k in enumerate(st["mem"]):
            c = M.mem[i]; dl = W[i + 1] * (c[0][M.ix, M.ans] / Aa - (c[0] * Lx).sum(1) / Z)
            if not st["gact"][i + 1] and f"gate:{k}" not in st["rejected"]: cand.append(("gate", i + 1, abs((dl * M.lg(c)).sum()), move + math.log2(max(1, len(st["mem"]))) + half))
            if str(i + 1) not in st["cg"] and f"cg:{k}" not in st["rejected"]: cand.append(("cgate", i + 1, np.abs(np.bincount(M.cprev, dl, minlength=50)).sum(), move + math.log2(max(1, len(st["mem"]))) + 50 * half))
        best = None
        for knd in ("mix", "lift", "gate", "cgate"):
            for kd, x, g_, bb in sorted((c for c in cand if c[0] == knd and c[2] > 0), key=lambda c: -c[2])[:3]:
                if kd == "mix": c = vote(CX, json.loads(x)); xv, b2 = P.golden(lambda lw: M.bits(A + (np.exp(lw) * c[1])[:, None] * c[0], logL), -12, 6)
                elif kd == "lift":
                    c = vote(CX, json.loads(x)); lgl = np.where(c[1][:, None], np.log((c[0] + M.Du) / (2 * M.Du + 1e-30)), 0); xv, b2 = P.golden(lambda be: M.bits(A, logL + be * lgl), -1, 2)
                elif kd == "gate": c = M.mem[x - 1]; wk = W[x]; lgc = M.lg(c); xv, b2 = P.golden(lambda ga: M.bits(A + ((wk * np.exp(ga * lgc)) - wk)[:, None] * c[0], logL), -2, 3)
                else:
                    c = M.mem[x - 1]; wk = W[x]; phi = np.zeros(50); b2 = M.bits(A, logL); lr = 0.5
                    for _ in range(15):                                                      # gradient steps on the 50 class weights
                        Ai = A + ((wk * np.exp(phi[M.cprev])) - wk)[:, None] * c[0]; Zi = (Ai * Lx).sum(1); wi = wk * np.exp(phi[M.cprev])
                        g = np.bincount(M.cprev, wi * (c[0][M.ix, M.ans] / Ai[M.ix, M.ans] - (c[0] * Lx).sum(1) / Zi), minlength=50)
                        trial = phi + lr * g / max(1, np.abs(g).max()); bt = M.bits(A + ((wk * np.exp(trial[M.cprev])) - wk)[:, None] * c[0], logL)
                        if bt < b2: phi, b2 = trial, bt; lr *= 1.3
                        else: lr *= 0.5
                    xv = phi.tolist()
                gain = cur - b2 - bb
                if gain > 0 and (best is None or gain > best[0]): best = (gain, kd, x, xv)
                elif gain <= 0: st["rejected"].append(x if kd in ("mix", "lift") else f"{'gate' if kd == 'gate' else 'cg'}:{st['mem'][x - 1]}")
        if best is None: break
        _, kd, x, xv = best
        if kd == "mix": st["mem"].append(x); st["th"].append(float(xv)); st["ga"].append(0.0); st["gact"].append(0); label = describe(json.loads(x))
        elif kd == "lift": st["lift"].append(x); st["be"].append(float(xv)); label = "Lift " + describe(json.loads(x))
        elif kd == "gate": st["ga"][x] = float(xv); st["gact"][x] = 1; label = "Gate " + describe(json.loads(st["mem"][x - 1]))
        else: st["cg"][str(x)] = xv; label = "Class weights " + describe(json.loads(st["mem"][x - 1]))
        if kd in ("mix", "lift"):
            s0 = st["origin"].get(x, "prior"); st["strat"][s0][1] += 1; st["neigh"] += [q for q in neighbours(json.loads(x)) if P.key(q) not in st["screen"] and P.key(q) not in st["evaluated"]]
        M = Model(CX, st); M.gact = st["gact"]; cur = M.refit(); st.update(th=M.th.tolist(), ga=M.ga.tolist(), be=M.be.tolist(), rejected=[]); accepted += 1
        st["log3"].append(f"{kd} ({st['origin'].get(x, '-') if kd in ('mix', 'lift') else '-'}): {label} -> fit {cur / n:.4f}"); json.dump(st, open(CK, "w"))
        F.log(f"   + {kd} [{st['origin'].get(x, '-') if kd in ('mix', 'lift') else '-'}]: {label}: fit {cur / n:.4f} bits/word")
    st["idle"] = 0 if accepted else st["idle"] + 1; json.dump(st, open(CK, "w"))
    F.log(f"{LABEL} run {st['run']}: accepted {accepted}; idle {st['idle']}; fit {cur / n:.4f} bits/word")
LABEL = "SZ3"
mode = (sys.argv[1] if len(sys.argv) > 1 else "search") if __name__ == "__main__" else None
if mode == "prep":
    for k in (50, 200): clusters(k); F.log(f"c{k} attribute ready")
elif mode == "search": search_main()
elif mode in ("eval", "ablate"):
    install(); st = json.load(open(sys.argv[2] if len(sys.argv) > 2 else CK)); M = Model("eval", st); M.gact = st["gact"]; b = M.bits()
    F.log(f"SZ3 scored on the {M.n:,} positions: {b / M.n:.4f} bits/word ({len(st['mem'])} Votes, {len(st['lift'])} lifts, {int(sum(st['gact']))} gates, {len(st.get('cg', {}))} class-weights)")
