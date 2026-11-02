"""SZ2 (sieve_lang_prereg.md): better search for SZ's primitive algebra (sieve_prim.py). Proposal strategies: prior
sampling, simplest-first enumeration (Levin order), neighbourhood of accepted Votes, mutation, crossover; a bandit
splits proposals by record ((accepted + 1) / (tried + 2), >= 2 each). Every proposal is screened on 1,000 of the 9,000
fit positions (best 1-D mix / lift gain x 9 minus its bits); positive ones are evaluated on all 9,000 and enter the
move loop (mix / lift / gate). Start from nothing; stop after 6 idle runs.
Run: py -3.12 -W ignore sieve_prim2.py search | eval"""
import os, sys, json, math, time, itertools
import numpy as np
import sieve_fs2 as F
import sieve_prim as P
T0 = time.time(); CX, SUB = "fit9", "fit9s"; F.CTX[SUB] = (F.fit_s, F.CTX[CX][1][::9], F.fit_b)
CK = os.path.join(F.HERE, "sieve_prim2_fit9.json"); STRATS = ("prior", "levin", "neigh", "mutate", "cross")
K1 = [[a, at, B, thr] for a in P.AS for at in P.ATTRS for B in P.BS for thr in P.THRS]; K1s = [t for t in K1 if t[2] == 1 and t[3] is None]
def levin():
    out = []
    for src in P.SRCS:
        for sp in P.SPANS:
            for w in P.WTS:
                for tm in [[]] + [[t] for t in K1] + [list(p) for p in itertools.combinations(K1s, 2)]:
                    d = dict(src=src, terms=tm, span=sp, w=w)
                    if P.valid(d): out.append(d)
    out.sort(key=lambda d: (round(P.bits_of(d), 9), P.key(d))); return out
def neighbours(sp):
    out = []; q0 = json.loads(P.key(sp))
    for f, vals in (("src", P.SRCS), ("span", P.SPANS), ("w", P.WTS)):
        for v in vals:
            q = json.loads(P.key(q0)); q[f] = v; out.append(q)
    for i, t in enumerate(q0["terms"]):
        for j, vals in enumerate((P.AS, P.ATTRS, P.BS, P.THRS)):
            for v in vals:
                q = json.loads(P.key(q0)); q["terms"][i][j] = v; out.append(q)
        q = json.loads(P.key(q0)); q["terms"].pop(i); out.append(q)
    if len(q0["terms"]) < 2:
        for t in K1s: q = json.loads(P.key(q0)); q["terms"].append(t); out.append(q)
    return [q for q in out if P.valid(q) and P.key(q) != P.key(q0)]
def state():
    if not os.path.exists(CK):
        json.dump(dict(mem=[], lift=[], th=[0.0], ga=[0.0], be=[], gact=[0], evaluated=[], rejected=[], screen={}, origin={}, levin_i=0, neigh=[],
                       strat={s: [0, 0] for s in STRATS}, idle=0, run=0, log=[]), open(CK, "w"))
    return json.load(open(CK))
def gains(M, c):
    """best 1-D mix and lift gains (bits) of a Vote under model M"""
    A, logL, W = M.parts(); cur = M.bits(A, logL)
    _, bm = P.golden(lambda lw: M.bits(A + (np.exp(lw) * c[1])[:, None] * c[0], logL), -12, 6, 16)
    lgl = np.where(c[1][:, None], np.log((c[0] + M.Du) / (2 * M.Du + 1e-30)), 0); _, bl = P.golden(lambda be: M.bits(A, logL + be * lgl), -1, 2, 16)
    return cur - bm, cur - bl
mode = (sys.argv[1] if len(sys.argv) > 1 else "search") if __name__ == "__main__" else None     # importable (sieve_prim3.py)
if mode == "search":
    st = state(); st["run"] += 1; rng = np.random.default_rng(1000 + st["run"]); half = 0.5 * math.log2(9000); move = math.log2(4)
    Ms = P.Model(SUB, st); Ms.gact = st["gact"]; scale = 9000 / Ms.n
    F.log(f"SZ2 run {st['run']}: {len(st['mem'])} Votes, {len(st['lift'])} lifts, {int(sum(st['gact']))} gates; bandit {st['strat']}")
    # ---- proposals by strategy (bandit split) ----
    r = {s: (st["strat"][s][1] + 1) / (st["strat"][s][0] + 2) for s in STRATS}; NP = 24; alloc = {s: max(2, round(NP * r[s] / sum(r.values()))) for s in STRATS}
    seen = set(st["screen"]) | set(st["evaluated"]); props = []
    def add(sp, s):
        if sp and P.valid(sp) and P.key(sp) not in seen: seen.add(P.key(sp)); props.append((s, sp))
    members = [json.loads(k) for k in st["mem"] + st["lift"]]
    for _ in range(alloc["prior"]): add(P.sample(rng), "prior")
    L = levin(); c0 = len(props)
    while len(props) - c0 < alloc["levin"] and st["levin_i"] < len(L): add(L[st["levin_i"]], "levin"); st["levin_i"] += 1
    c0 = len(props)
    while len(props) - c0 < alloc["neigh"] and st["neigh"]: add(st["neigh"].pop(0), "neigh")
    if members:
        for _ in range(alloc["mutate"]): add(P.mutate(members[rng.integers(len(members))], rng), "mutate")
        for _ in range(alloc["cross"]):
            if len(members) < 2: break
            a, b = (members[i] for i in rng.choice(len(members), 2, replace=False)); add(dict(src=a["src"], span=a["span"], w=a["w"], terms=b["terms"][:2]), "cross")
    order = {s: i for i, s in enumerate(STRATS)}; props.sort(key=lambda p: order[p[0]])
    rng.shuffle(props)
    # ---- screening on the 1,000-position subsample ----
    for s, sp in props:
        if time.time() - T0 > 115: break
        k = P.key(sp); c = P.vote(SUB, sp); gm, gl = gains(Ms, c); est = max(gm, gl) * scale - (move + P.bits_of(sp) + half)
        st["screen"][k] = est; st["origin"][k] = s; st["strat"][s][0] += 1
    json.dump(st, open(CK, "w"))
    # ---- promotion: full evaluation of the best screened ----
    for k in sorted((k for k, v in st["screen"].items() if v > 0 and k not in st["evaluated"]), key=lambda k: -st["screen"][k]):
        if time.time() - T0 > 170: break
        P.vote(CX, json.loads(k)); st["evaluated"].append(k); F.log(f"   promoted ({st['origin'][k]}, est {st['screen'][k]:.0f} bits): {P.describe(json.loads(k))}")
    json.dump(st, open(CK, "w"))
    # ---- move loop on the 9,000 positions ----
    M = P.Model(CX, st); M.gact = st["gact"]; n = M.n; cur = M.bits(); accepted = 0
    while time.time() - T0 < 235:
        A, logL, W = M.parts(); Lx = np.exp(logL - logL.max(1, keepdims=True)); Z = (A * Lx).sum(1); Pm = A * Lx / Z[:, None]; Aa = A[M.ix, M.ans]; cand = []
        for k in st["evaluated"]:
            if k in st["rejected"]: continue
            c = P.vote(CX, json.loads(k)); sp = json.loads(k)
            if k not in st["mem"]: cand.append(("mix", k, (c[1] * (c[0][M.ix, M.ans] / Aa - (c[0] * Lx).sum(1) / Z)).sum(), move + P.bits_of(sp) + half))
            if k not in st["lift"]:
                lgl = np.where(c[1][:, None], np.log((c[0] + M.Du) / (2 * M.Du + 1e-30)), 0); cand.append(("lift", k, abs((lgl[M.ix, M.ans] - (Pm * lgl).sum(1)).sum()), move + P.bits_of(sp) + half))
        for i, k in enumerate(st["mem"]):
            if not st["gact"][i + 1] and f"gate:{k}" not in st["rejected"]:
                c = M.mem[i]; cand.append(("gate", i + 1, abs((W[i + 1] * (c[0][M.ix, M.ans] / Aa - (c[0] * Lx).sum(1) / Z) * M.lg(c)).sum()), move + math.log2(max(1, len(st["mem"]))) + half))
        best = None
        for kind in ("mix", "lift", "gate"):
            for kd, x, g_, bb in sorted((c for c in cand if c[0] == kind and c[2] > 0), key=lambda c: -c[2])[:3]:
                if kd == "mix": c = P.vote(CX, json.loads(x)); xv, b2 = P.golden(lambda lw: M.bits(A + (np.exp(lw) * c[1])[:, None] * c[0], logL), -12, 6)
                elif kd == "lift":
                    c = P.vote(CX, json.loads(x)); lgl = np.where(c[1][:, None], np.log((c[0] + M.Du) / (2 * M.Du + 1e-30)), 0); xv, b2 = P.golden(lambda be: M.bits(A, logL + be * lgl), -1, 2)
                else: c = M.mem[x - 1]; wk = W[x]; lgc = M.lg(c); xv, b2 = P.golden(lambda ga: M.bits(A + ((wk * np.exp(ga * lgc)) - wk)[:, None] * c[0], logL), -2, 3)
                gain = cur - b2 - bb
                if gain > 0 and (best is None or gain > best[0]): best = (gain, kd, x, xv)
                elif gain <= 0 and kd != "gate": st["rejected"].append(x)
                elif gain <= 0: st["rejected"].append(f"gate:{st['mem'][x - 1]}")
        if best is None: break
        _, kd, x, xv = best
        if kd == "mix": st["mem"].append(x); st["th"].append(float(xv)); st["ga"].append(0.0); st["gact"].append(0); label = P.describe(json.loads(x))
        elif kd == "lift": st["lift"].append(x); st["be"].append(float(xv)); label = "Lift " + P.describe(json.loads(x))
        else: st["ga"][x] = float(xv); st["gact"][x] = 1; label = "Gate " + P.describe(json.loads(st["mem"][x - 1]))
        if kd != "gate":
            s0 = st["origin"].get(x, "prior"); st["strat"][s0][1] += 1; st["neigh"] += [q for q in neighbours(json.loads(x)) if P.key(q) not in st["screen"] and P.key(q) not in st["evaluated"]]
        M = P.Model(CX, st); M.gact = st["gact"]; cur = M.refit(); st.update(th=M.th.tolist(), ga=M.ga.tolist(), be=M.be.tolist(), rejected=[]); accepted += 1
        st["log"].append(f"{kd} ({st['origin'].get(x, '-') if kd != 'gate' else '-'}): {label} -> fit {cur / n:.4f}"); json.dump(st, open(CK, "w"))
        F.log(f"   + {kd} [{st['origin'].get(x, '-') if kd != 'gate' else '-'}]: {label}: fit {cur / n:.4f} bits/word")
    st["idle"] = 0 if accepted else st["idle"] + 1; json.dump(st, open(CK, "w"))
    F.log(f"SZ2 run {st['run']}: accepted {accepted}; idle runs {st['idle']}; fit {cur / n:.4f} bits/word; levin at {st['levin_i']}, neighbourhood queue {len(st['neigh'])}")
elif mode == "eval":
    st = state(); M = P.Model("eval", st); M.gact = st["gact"]; b = M.bits()
    F.log(f"SZ2 scored on the {M.n:,} positions: {b / M.n:.4f} bits/word ({len(st['mem'])} Votes, {len(st['lift'])} lifts, {int(sum(st['gact']))} gates; SZ 9.1298, Counter 8.9368, hand-built 7.7205, LM 6.026); wins per strategy {st['strat']}")
