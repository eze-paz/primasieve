"""THE TWO-ARM RULE ON REAL PROBLEMS -- 26 actual buggy Python programs (QuixBugs).

Everything so far was measured on families I generated. This is the external benchmark: real programs with
real bugs (bitcount, mergesort, shunting_yard, levenshtein, ...). Same rule as always -- report BOTH arms.

  COLD  base search only        Enumerate(0,1,2) + Reset + Interpolate
  WARM  base + ACCUMULATED      the learned forms the engine has crystallised: GlobalApply, Repeat

PROVENANCE CHECK (this is what keeps WARM honest, and it was verified, not assumed):
  GlobalApply was learned from meta_library.gen(k) -- a SYNTHETIC family of k threshold checks using `<` where
  `<=` is correct. Repeat was learned from polynomial sign-flips via stuck-escalation. Neither file reads
  ~/quixbugs at all (checked: no QB / quixbugs / correct_python reference in meta_library.py or
  meta_discover.py). So no accumulated form was crystallised FROM a QuixBugs program -- the library cannot
  contain the answer to the question being asked. This is transfer, not recall.

NOTE on ITERATE: it operates on attribute-pair frames, not Python ASTs, so it cannot fire here and is inert.
That is the point of adopting it cost-ordered -- inert costs nothing. Stated rather than quietly omitted.

    python em_real.py                     # all bugs (slow; chunk it)
    META_NAMES=a,b,c python em_real.py    # a chunk; results MERGE into em_real_results.json
"""
import os, sys, json, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
# NOTE: do NOT cap the budget here. An earlier version set META_GLOBAL=8000 (copied from meta_bench) while
# meta_reason defaults to 12000 -- the budget the Phase 0 baseline used. That made WARM "lose" lcs_length at
# 8206 evals, which I nearly reported as a solve-regression caused by the accumulated forms. It was my cap.
# Leave the default alone so these numbers are comparable to BASELINE.json.

import meta_forms as MF
import meta_reason as MR
import reasoner_code as rc

RES = os.path.join(HERE, "em_real_results.json")
BASE_ONLY = ["Enumerate", "Reset", "Interpolate"]          # base search machinery
ACCUMULATED = ["GlobalApply", "Repeat"]                     # the LEARNED forms


_ORIG_DEFAULT_FORMS = MF.default_forms      # captured ONCE at import; patching it later must not recurse


# GlobalApply ships with cost_hint 1.0 -- tied with the CHEAPEST search form, i.e. tried FIRST. That is the
# naive first-position adoption em_adopt.py measured as a 33x regression where the form does not apply. The
# "costed" arm keeps the SAME forms and only re-prices this one, so cheap enumeration runs before it.
GLOBAL_APPLY_COSTED = float(os.environ.get("GA_COST", "3.0"))


def forms_for(arm):
    full = _ORIG_DEFAULT_FORMS()
    if arm == "warm":
        return list(full)
    if arm == "costed":
        out = []
        for f in full:
            if type(f).__name__ == "GlobalApply":
                f.cost_hint = GLOBAL_APPLY_COSTED
            out.append(f)
        return out
    keep = [f for f in full if type(f).__name__ not in ACCUMULATED]
    return keep


def run_arm(arm, names):
    """patch default_forms for this arm, then solve each bug."""
    orig = MF.default_forms
    MF.default_forms = (lambda a=arm: forms_for(a))
    MR.default_forms = MF.default_forms
    out = {}
    try:
        for name in names:
            tests = MR.load_tests(name)
            csrc = open(f"{MR.QB}/correct_python_programs/{name}.py").read()
            try: ccode = compile(csrc, "<c>", "exec")
            except Exception: continue
            if not all(rc.run_one(ccode, name, i, e)[0] for i, e in tests): continue
            bsrc = open(f"{MR.QB}/python_programs/{name}.py").read()
            ok, ev, _ = MR.solve_ucb(name, bsrc, tests, [])
            out[name] = {"solved": bool(ok), "evals": ev}
    finally:
        MF.default_forms = orig
        MR.default_forms = orig
    return out


if __name__ == "__main__":
    t0 = time.time()
    names = sorted(f[:-5] for f in os.listdir(f"{MR.QB}/json_testcases") if f.endswith(".json"))
    sl = os.environ.get("META_NAMES")
    if sl: names = [n for n in names if n in sl.split(",")]

    print(f"COLD forms: {[type(f).__name__ for f in forms_for('cold')]}")
    print(f"WARM forms: {[type(f).__name__ for f in forms_for('warm')]}  (+{ACCUMULATED} accumulated)\n")

    cold = run_arm("cold", names)
    warm = run_arm("warm", names)
    costed = run_arm("costed", names)

    d = json.load(open(RES)) if os.path.exists(RES) else {"cold": {}, "warm": {}, "costed": {}}
    d.setdefault("costed", {})
    d["cold"].update(cold); d["warm"].update(warm); d["costed"].update(costed)

    C, W, X = d["cold"], d["warm"], d["costed"]
    both = sorted(set(C) & set(W) & set(X))
    cs = sum(C[n]["solved"] for n in both); ws = sum(W[n]["solved"] for n in both)
    ce = sum(C[n]["evals"] for n in both); we = sum(W[n]["evals"] for n in both)
    print(f"{'bug':26s} {'COLD':>16s} {'WARM':>16s}   delta")
    for n in both:
        c, w = C[n], W[n]
        mark = ""
        if w["solved"] and not c["solved"]: mark = "  SOLVED ONLY WARM"
        elif c["solved"] and not w["solved"]: mark = "  LOST BY WARM"
        elif c["solved"] and w["solved"] and c["evals"] != w["evals"]:
            mark = f"  {c['evals']/max(1,w['evals']):.1f}x" if w["evals"] < c["evals"] else \
                   f"  {w['evals']/max(1,c['evals']):.1f}x SLOWER"
        cstr = ("Y" if c["solved"] else "n") + "(%6d)" % c["evals"]
        wstr = ("Y" if w["solved"] else "n") + "(%6d)" % w["evals"]
        print("%-26s %16s %16s%s" % (n, cstr, wstr, mark))
    print(f"\n  {len(both)} real bugs")
    print(f"  COLD  {cs}/{len(both)} solved, {ce} evals")
    print(f"  WARM  {ws}/{len(both)} solved, {we} evals")
    xs = sum(X[n]["solved"] for n in both); xe = sum(X[n]["evals"] for n in both)
    print(f"  COSTED {xs}/{len(both)} solved, {xe} evals   (same forms, GlobalApply re-priced to "
          f"{GLOBAL_APPLY_COSTED})")
    print(f"  DELTA warm-vs-cold {ws-cs:+d} solves, {ce/max(1,we):.2f}x evals")
    print(f"  DELTA costed-vs-cold {xs-cs:+d} solves, {ce/max(1,xe):.2f}x evals")
    d["summary"] = {"n": len(both), "cold_solved": cs, "warm_solved": ws, "costed_solved": xs,
                    "cold_evals": ce, "warm_evals": we, "costed_evals": xe,
                    "global_apply_cost": GLOBAL_APPLY_COSTED,
                    "delta_solves": ws - cs, "eval_ratio": round(ce / max(1, we), 3),
                    "provenance": "GlobalApply learned from synthetic meta_library.gen(k) threshold family; "
                                  "Repeat from polynomial sign-flips. Neither reads ~/quixbugs -- verified. "
                                  "No accumulated form was crystallised from a QuixBugs program.",
                    "iterate": "inert here (operates on attribute-pair frames, not Python ASTs) -- the reason "
                               "cost-ordered adoption matters: inert costs nothing"}
    json.dump(d, open(RES, "w"), indent=1, sort_keys=True)
    print(f"  ({time.time()-t0:.0f}s) -> {os.path.basename(RES)}")
