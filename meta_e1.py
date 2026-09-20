"""E1 (fable-designed): DEGRADATION x COHERENCE. Does INTERNAL belief-consistency compensate for a
degrading EXTERNAL oracle? Tests owner points 2 (reasoning/rejection-first viability) & 3 (belief
inconsistency detection). ZERO LLM.

Two noise arms during DISCOVERY (held-out always graded CLEAN): SUBSET(k)=verify on a random k of the
sample points (SOUND rejection, incomplete acceptance -> false-accepts only); FLIP(p)=symmetric verdict
flip (UNSOUND). Coherence in {OFF, ON, SHUFFLED}. Beliefs = discovered frames; contradiction predicates
(pure Python, NO external oracle): C3 cross-episode consensus (a frame is trusted only if >=2 independent
batches agree); C5 round-trip closure (integ o diff == identity on a grid) = two beliefs checking each
other with no oracle; C2 self-replay (frame reproduces its own support) reported separately (it is cached
provenance, not coherence). SHUFFLED = quarantine a RANDOM same-size set (isolates 'quarantine anything'
from 'quarantine the right thing'). Knockouts: K1 clean/OFF must be 60/60; K2 clean/ON must be 60/60 with
ZERO ground-truth frames quarantined."""
import os, sys, random, statistics
from collections import Counter
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault("META_GLOBAL", "8000")
from meta_forms import MetaState
from meta_reason import solve_ucb
import meta_param as MP
import meta_codeparam as MC

GT = {"diff": ("coeff*exp", "(exp-1)"), "integ": ("coeff/(exp+1)", "(exp+1)"), "codeparam": ("coeff+exp", "exp")}
CLS_IDX = {"diff": 0, "integ": 1, "codeparam": 2}   # stable seed (hash(str) is per-process randomized)
TF = {"diff": MP.differentiate, "integ": MP.integrate}
GRID = [(c, e) for c in (2, 3, 5) for e in (2, 3, 4)]

def _poly(rng):
    k = rng.randint(2, 5); es = rng.sample(range(2, 8), k); return [(rng.randint(2, 9), e) for e in es]

def mk_oracle(arm, level, rng):
    if arm == "clean": return {"mode": "clean"}
    if arm == "subset": return {"mode": "subset", "k_frac": level, "rng": rng}
    return {"mode": "flip", "p": level, "rng": rng}

def _batch_seeds(cls, b, rng):
    if cls == "codeparam": return [(rng.randint(2, 9), rng.randint(1, 6)) for _ in range(3)]
    return [[(rng.randint(2, 9), rng.choice([2, 3, 4, 5]))] for _ in range(3)]

def _boot_math(tf, seeds, oracle):
    tr = []
    for terms in seeds:
        t = MP.make_task(terms, tf); st = MetaState("f", t["src"], t["tests"], oracle=oracle)
        if MP.FitTemplate().run(st, 400)["solved"]:
            nt = MP.parse_terms(st.tree)
            if len(nt) == 1: tr.append((terms[0], nt[0]))
    return tr

def _boot_code(seeds, oracle):
    tr = []
    for (w, i) in seeds:
        src = f"def f(a):\n    return a[{i}]*{w}"; ns = {}
        exec(f"def g(a):\n    return a[{i}]*{w + i}", ns)
        tests = [([v], ns["g"](v)) for v in MC.AVECS + [MC.AVEC_FIT]]
        st = MetaState("f", src, tests, oracle=oracle)
        if MC.CodeFitWeight().run(st, 50)["solved"]:
            s = MC.parse_sites(st.tree)
            if s: tr.append(((w, i), (round(s[0][0]), i)))
    return tr

def discover_one(cls, seeds, oracle):
    """One batch -> a frame (clabel, elabel, fc, fe) or None."""
    tr = _boot_code(seeds, oracle) if cls == "codeparam" else _boot_math(TF[cls], seeds, oracle)
    rc = MP.discover_relation(tr, 0); re = MP.discover_relation(tr, 1)
    if rc and re: return (rc[0], re[0], rc[2], re[2])
    return None

def c5_roundtrip(fdiff, finteg):
    """integ o diff == identity on the grid (the genuinely INTERNAL verifier; no oracle)."""
    for c, e in GRID:
        c1, e1 = fdiff[2](c, e), fdiff[3](c, e)
        c2, e2 = finteg[2](c1, e1), finteg[3](c1, e1)
        if abs(c2 - c) > 1e-6 or int(round(e2)) != e: return False
    return True

def _uniq(frs):
    seen = {}; cnt = Counter()
    for f in frs: seen.setdefault((f[0], f[1]), f); cnt[(f[0], f[1])] += 1
    return list(seen.values()), cnt

def select(frames, coherence, rng):
    """Return (chosen_per_class, n_quarantined, attribution). C5 ADJUDICATES (fix 1): among candidate
    diff & integ frames, pick the (d,i) pair whose round-trip CLOSES = two beliefs validating each other
    with NO oracle -> recovers the correct pair even when no single class has consensus."""
    chosen = {}; quar = 0; attr = Counter()
    if coherence == "OFF":
        for cls, frs in frames.items(): chosen[cls] = frs[0] if frs else None
        return chosen, 0, attr
    dcand, dc = _uniq(frames["diff"]); icand, ic = _uniq(frames["integ"])
    # C5 SURGICAL: a candidate is CONSISTENT iff it participates in >=1 round-trip-closing pair; drop
    # ONLY the inconsistent ones (two beliefs validating each other); keep the highest-support consistent.
    cons_d = [d for d in dcand if any(c5_roundtrip(d, i) for i in icand)]
    cons_i = [i for i in icand if any(c5_roundtrip(d, i) for d in dcand)]
    chosen["diff"] = max(cons_d, key=lambda d: dc[(d[0], d[1])]) if cons_d else None
    chosen["integ"] = max(cons_i, key=lambda i: ic[(i[0], i[1])]) if cons_i else None
    quar += (len(dcand) - len(cons_d)) + (len(icand) - len(cons_i))
    if dcand or icand: attr["C5"] += 1
    ccand, cc = _uniq(frames["codeparam"])                        # no inverse partner -> C3 consensus(m=2)
    if ccand:
        lab, n = cc.most_common(1)[0]
        if n >= 2: chosen["codeparam"] = next(f for f in ccand if (f[0], f[1]) == lab); quar += len(ccand) - 1; attr["C3"] += (len(ccand) > 1)
        else: chosen["codeparam"] = None; quar += len(ccand); attr["C3"] += 1
    else: chosen["codeparam"] = None
    if coherence == "SHUFFLED":                                   # drop `quar` RANDOM distinct frames
        allf = [(cls, f) for cls in frames for f in _uniq(frames[cls])[0]]
        rng.shuffle(allf); drop = {id(f) for _, f in allf[:quar]}
        chosen = {cls: next((f for f in _uniq(frames[cls])[0] if id(f) not in drop), None) for cls in frames}
    return chosen, quar, attr

def grade(cls, frame, rng, n=20):
    if frame is None: return 0, n
    solved = 0
    for _ in range(n):
        if cls == "codeparam":
            t = MC.gen_weight_bug(rng, rng.randint(3, 8))
            op = MC.CodeStructParam(lambda w, i, fc=frame[2]: fc(w, i), frame[0])
            ok, _, _ = solve_ucb("f", t["src"], t["tests"], [], extra_forms=(op, MC.CodeFitWeight()))
        else:
            terms = _poly(rng); t = MP.make_task(terms, TF[cls])
            op = MP.StructParam(frame[2], frame[3], f"{frame[0]},{frame[1]}")
            ok, _, _ = solve_ucb("f", t["src"], t["tests"], [], extra_forms=(op, MP.FitTemplate()))
        solved += ok
    return solved, n

def run_cell(arm, level, seed, coherence, nbatch=3):
    rng = random.Random(seed)
    frames = {}
    for cls in ("diff", "integ", "codeparam"):
        frs = []
        for b in range(nbatch):
            oracle = mk_oracle(arm, level, random.Random(seed * 131 + b * 17 + CLS_IDX[cls]))
            fr = discover_one(cls, _batch_seeds(cls, b, rng), oracle)
            if fr: frs.append(fr)
        frames[cls] = frs
    chosen, quar, attr = select(frames, coherence, rng)
    # quarantine precision/recall vs GT: a frame is GT-correct iff its (clabel,elabel)==GT[cls]
    gt_bad = sum(1 for cls, frs in frames.items() for f in frs if (f[0], f[1]) != GT[cls])
    kept_bad = sum(1 for cls, f in chosen.items() if f and (f[0], f[1]) != GT[cls])
    solved = tot = 0; frame_id = 0; committed = 0
    grng = random.Random(seed + 9999)
    for cls in ("diff", "integ", "codeparam"):
        s, n = grade(cls, chosen[cls], grng); solved += s; tot += n
        if chosen[cls]:
            committed += 1
            if (chosen[cls][0], chosen[cls][1]) == GT[cls]: frame_id += 1
    return {"solved": solved, "tot": tot, "frame_id": frame_id, "committed": committed, "quar": quar,
            "attr": dict(attr), "gt_bad": gt_bad, "kept_bad": kept_bad}

if __name__ == "__main__":
    import time; t0 = time.time()
    print("=== KNOCKOUTS ===")
    k1 = run_cell("clean", 0, 1, "OFF"); print(f"K1 clean/OFF : {k1['solved']}/{k1['tot']} solved, frame_id {k1['frame_id']}/3  (must be 60/60, 3/3)")
    k2 = run_cell("clean", 0, 1, "ON");  print(f"K2 clean/ON  : {k2['solved']}/{k2['tot']} solved, frame_id {k2['frame_id']}/3, GT-quarantined {k2['gt_bad']-(k2['gt_bad']-0)} kept_bad {k2['kept_bad']}  (must be 60/60, 0 GT quarantined)")
    print(f"\n=== SWEEP (3 seeds/cell) — PRECISION = correct among COMMITTED; COVERAGE = committed/3 ===")
    print(f"{'arm':7s} {'level':>6s} {'coh':>9s} {'solved':>7s} {'precision':>10s} {'coverage':>9s}  attr")
    SEEDS = [1, 2, 3]
    for arm, levels in [("subset", [1.0, 0.5, 0.25, 0.13]), ("flip", [0.0, 0.02, 0.08, 0.2])]:
        for level in levels:
            for coh in ("OFF", "ON", "SHUFFLED"):
                rs = [run_cell(arm, level, s, coh) for s in SEEDS]
                sv = statistics.mean(r["solved"] for r in rs)
                com = sum(r["committed"] for r in rs); cor = sum(r["frame_id"] for r in rs)
                prec = cor / com if com else float("nan"); cov = com / (3 * len(SEEDS))
                at = Counter()
                for r in rs: at.update(r["attr"])
                print(f"{arm:7s} {level:>6.2f} {coh:>9s} {sv:>5.0f}/60 {prec:>10.2f} {cov:>9.2f}  {dict(at)}")
    print(f"\ntotal {time.time()-t0:.0f}s")
