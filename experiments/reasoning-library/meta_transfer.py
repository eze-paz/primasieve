"""P2/P3 — STRATEGY TRANSFER (METAPLAN S2), ZERO LLM. Does a strategy mined from winning episodes
on TRAIN programs speed a HELD-OUT set? A-priori defect signature (from BASELINE, never the fix)
-> k-NN warm-start of the bandit -> measure evals cold vs warm on holdout. Held-back assertions
gate every 'solve' (anti-cheat)."""
import os, json, math, ast, random
import reasoner_code as rc
from meta_forms import MetaState
from meta_reason import solve_ucb, load_tests

QB = os.path.expanduser("~/quixbugs")
HELD_BACK = 0.25          # 25% of testcases hidden from search; true-solve must pass 100%
random.seed(0)

def signature(name, src, tests):
    """A-PRIORI defect signature from the BASELINE only (no knowledge of the fix): baseline error
    class + node-types on the most-suspicious lines + failing-test bucket."""
    st = MetaState(name, src, tests)
    # baseline error class
    try:
        code = compile(ast.fix_missing_locations(st.orig), "<c>", "exec")
        err = "none"
        for inp, exp in tests:
            ok, _ = rc.run_one(code, name, inp, exp)
            if not ok: err = "wrong"; break
    except Exception: err = "syntax"
    # node types on top-suspicion lines
    top = sorted(st.susp.items(), key=lambda kv: -kv[1])[:2]
    toplines = {ln for ln, s in top if s > 0}
    kinds = {}
    for node in ast.walk(st.orig):
        if getattr(node, "lineno", None) in toplines:
            kinds[type(node).__name__] = kinds.get(type(node).__name__, 0) + 1
    keyk = tuple(sorted(k for k in kinds if k in
                 ("Compare", "BinOp", "BoolOp", "Call", "ListComp", "Subscript", "Return", "Name", "Constant")))
    return (err, keyk, min(st.best, 4))

def sig_dist(a, b):
    d = 0
    d += 0 if a[0] == b[0] else 1
    d += len(set(a[1]) ^ set(b[1]))
    d += abs(a[2] - b[2]) * 0.5
    return d

def winning_forms(ep):
    """Forms that produced improvement in a solved episode -> the strategy that worked."""
    return [e["form"] for e in ep if e.get("improved")]

if __name__ == "__main__":
    names = sorted(f[:-5] for f in os.listdir(f"{QB}/json_testcases") if f.endswith(".json"))
    progs = []
    for name in names:
        tests = load_tests(name)
        csrc = open(f"{QB}/correct_python_programs/{name}.py").read()
        try: ccode = compile(csrc, "<c>", "exec")
        except Exception: continue
        if not all(rc.run_one(ccode, name, i, e)[0] for i, e in tests): continue
        bsrc = open(f"{QB}/python_programs/{name}.py").read()
        progs.append((name, bsrc, tests))

    # split: hold out every 3rd program (deterministic, defect-diverse)
    train = [p for i, p in enumerate(progs) if i % 3 != 0]
    holdout = [p for i, p in enumerate(progs) if i % 3 == 0]
    print(f"train {len(train)}  holdout {len(holdout)}  (held-back assertions {int(HELD_BACK*100)}%)\n")

    # TRAIN: run cold UCB, record winning strategy + signature per solved train program
    casebase = []   # (signature, winning_forms)
    for name, src, tests in train:
        ep = []
        ok, en, _ = solve_ucb(name, src, tests, ep, held_back=HELD_BACK)
        if ok:
            casebase.append((signature(name, src, tests), winning_forms(ep)))
    print(f"casebase: {len(casebase)} solved train strategies mined\n")

    def warm_prior(sig, k=3):
        """k-NN over train signatures -> pseudo-reward per form (frequency in nearest winners)."""
        near = sorted(casebase, key=lambda cs: sig_dist(sig, cs[0]))[:k]
        cnt = {}
        for _, forms in near:
            for f in set(forms): cnt[f] = cnt.get(f, 0) + 1
        if not cnt: return None
        m = max(cnt.values())
        return {f: 2.0 * c / m for f, c in cnt.items()}   # up to +2 pseudo-reward for favored forms

    # HOLDOUT: cold vs warm (k-NN warm-start from train casebase)
    print(f"{'program':26s} {'cold':>14s} {'warm':>14s}")
    cold_e = warm_e = cold_s = warm_s = 0
    for name, src, tests in holdout:
        sig = signature(name, src, tests)
        ep = []; cok, cen, _ = solve_ucb(name, src, tests, ep, held_back=HELD_BACK)
        wp = warm_prior(sig)
        ep2 = []; wok, wen, _ = solve_ucb(name, src, tests, ep2, warm=wp, held_back=HELD_BACK)
        cold_s += cok; warm_s += wok; cold_e += cen; warm_e += wen
        tag = "" if cen == wen else ("  <=" if wen < cen else "  >")
        print(f"{name:26s} {('Y' if cok else 'n')}({cen:6d}) {('Y' if wok else 'n')}({wen:6d}){tag}", flush=True)

    print(f"\n=== S2 STRATEGY TRANSFER (holdout {len(holdout)}, held-back {int(HELD_BACK*100)}%) ===")
    print(f"COLD (no transfer) : {cold_s}/{len(holdout)} solved, energy {cold_e}")
    print(f"WARM (k-NN from train): {warm_s}/{len(holdout)} solved, energy {warm_e}")
    print(f"energy warm/cold: {warm_e/max(1,cold_e):.2f}x  (<1.0 = strategy learned on TRAIN transfers to HOLDOUT)")
