"""PHASE 0 -- FREEZE THE YARDSTICK (GENERAL_REASONER_PLAN.md). One scoreboard over every task family the
general-reasoner claim must eventually satisfy, emitted as ONE JSON (BASELINE.json) so nothing downstream can fish.

Components (run separately to respect the 5-minute test cap; results MERGE into BASELINE.json):
    python bench_all.py matrix     # meta_bench 6 classes x N held-out instances: primitives vs discovered-op
    python bench_all.py quixbugs   # 26 QuixBugs: hand-coded escalation vs UCB-over-forms (energy ratio)
    python bench_all.py seg        # br-phono unsupervised segmentation: token F vs Zhikov 0.7542
    python bench_all.py env        # interpreter capability report (which python has numpy/torch)
    python bench_all.py show       # print the merged baseline
Env: BENCH_N (instances/class, default 20), META_NAMES (quixbugs subset), BASELINE (output path).

NOTE the two interpreters (plan 0.3): stdlib-only tasks (matrix/quixbugs/seg) run on ANY python; the learned
parts of Phase 3 need numpy+torch, which live ONLY in the system Python312, not the default `python`."""
import os, sys, json, time, random, statistics, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
OUT = os.environ.get("BASELINE", os.path.join(HERE, "BASELINE.json"))


def load():
    if os.path.exists(OUT):
        try: return json.load(open(OUT))
        except Exception: pass
    return {}


def save(d):
    d["_updated"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    json.dump(d, open(OUT, "w"), indent=1, sort_keys=True)
    print(f"\n-> merged into {os.path.basename(OUT)}")


# ------------------------------------------------------------------ matrix (6 classes x N)
def run_matrix(N):
    import meta_bench as MB
    t0 = time.time()
    info = MB.discover_all()
    ops = {k: (info[k][0].name if info[k][0] else None) for k, _ in MB.CLASSES}
    vocab_added = sum(info[k][2] for k, _ in MB.CLASSES)
    cells = {}
    tot_p = tot_d = 0
    print(f"{'class':10s} {'prim':>9s} {'disc':>9s} {'prim_medE':>10s} {'disc_medE':>10s}")
    for name, gen in MB.CLASSES:
        op, prim, _ = info[name]
        rng = random.Random(1000 + hash(name) % 999)   # same seeding as meta_bench (held-out)
        pr = ds = 0; ep = []; ed = []
        for _ in range(N):
            task = gen(rng)
            okP, enP, okD, enD = MB.grade(op, prim, task)
            pr += okP; ds += okD; ep.append(enP); ed.append(enD)
        tot_p += pr; tot_d += ds
        cells[name] = {"n": N, "prim_solved": pr, "disc_solved": ds,
                       "prim_med_evals": int(statistics.median(ep)),
                       "disc_med_evals": int(statistics.median(ed)),
                       "prim_evals": ep, "disc_evals": ed, "op": ops[name]}
        print(f"{name:10s} {pr:>5d}/{N:<3d} {ds:>5d}/{N:<3d} "
              f"{cells[name]['prim_med_evals']:>10d} {cells[name]['disc_med_evals']:>10d}")
    total = len(MB.CLASSES) * N
    print(f"\nTOTAL primitives {tot_p}/{total}   +discovered {tot_d}/{total}   vocab_added={vocab_added}")
    return {"n_per_class": N, "total": total, "prim_solved": tot_p, "disc_solved": tot_d,
            "vocab_added": vocab_added, "ops": ops, "cells": cells, "secs": round(time.time() - t0, 1)}


# ------------------------------------------------------------------ quixbugs (26)
def run_quixbugs(prev=None):
    """Chunkable (5-min cap): META_NAMES selects a slice; results MERGE with any prior per_bug in BASELINE.json,
    and the totals are recomputed over the union. Run all chunks to get the full-26 number."""
    import meta_reason as MR, reasoner_code as rc
    t0 = time.time()
    names = sorted(f[:-5] for f in os.listdir(f"{MR.QB}/json_testcases") if f.endswith(".json"))
    sl = os.environ.get("META_NAMES")
    if sl: names = [n for n in names if n in sl.split(",")]
    per = dict((prev or {}).get("per_bug", {}))       # carry forward earlier chunks
    A = {"solved": 0, "energy": 0}; B = {"solved": 0, "energy": 0}
    for name in names:
        tests = MR.load_tests(name)
        csrc = open(f"{MR.QB}/correct_python_programs/{name}.py").read()
        try: ccode = compile(csrc, "<c>", "exec")
        except Exception: continue
        if not all(rc.run_one(ccode, name, i, e)[0] for i, e in tests): continue   # fair-scoring guard
        bsrc = open(f"{MR.QB}/python_programs/{name}.py").read()
        aok, aen, _ = MR.solve_handcoded(name, bsrc, tests)
        bok, ben, _ = MR.solve_ucb(name, bsrc, tests, [])
        per[name] = {"hand_solved": bool(aok), "hand_evals": aen,
                     "ucb_solved": bool(bok), "ucb_evals": ben}
        print(f"{name:26s} hand {'Y' if aok else 'n'}({aen:5d})  ucb {'Y' if bok else 'n'}({ben:5d})", flush=True)
    for v in per.values():                            # recompute totals over the UNION of all chunks
        A["solved"] += v["hand_solved"]; A["energy"] += v["hand_evals"]
        B["solved"] += v["ucb_solved"]; B["energy"] += v["ucb_evals"]
    n = len(per)
    ratio = B["energy"] / max(1, A["energy"])
    print(f"\n[union of {n} bugs] hand {A['solved']}/{n} @E{A['energy']}   "
          f"ucb {B['solved']}/{n} @E{B['energy']}   ratio {ratio:.2f}x")
    return {"n": n, "hand_solved": A["solved"], "hand_energy": A["energy"],
            "ucb_solved": B["solved"], "ucb_energy": B["energy"], "energy_ratio": round(ratio, 3),
            "per_bug": per, "secs": round(time.time() - t0, 1)}


# ------------------------------------------------------------------ segmentation (br-phono)
def run_seg():
    import seg_zhikov as SZ
    t0 = time.time()
    utts = SZ.load_brp(); gold = SZ.gold_spans(utts); streams = [s for s, _ in gold]
    scores = SZ.entropy_abs(streams, k=4)
    low = SZ.percentile([scores[u][g] for u in range(len(streams)) for g in range(1, len(streams[u]))], 35)
    pred, mdl = SZ.zhikov_segment(streams, k=4, kappa=1.5, rounds=8, sweeps=6, scores=scores, low_thresh=low)
    tf, P, R = SZ.token_f(gold, pred); bf, _, _ = SZ.boundary_f(gold, pred)
    print(f"token F={tf:.3f} P={P:.3f} R={R:.3f}  boundary F={bf:.3f}  types={mdl.M}  (Zhikov F=0.7542)")
    return {"corpus": "br-phono", "utts": len(utts), "tokens": sum(len(w) for w in utts),
            "token_f": round(tf, 4), "token_p": round(P, 4), "token_r": round(R, 4),
            "boundary_f": round(bf, 4), "lexicon_types": mdl.M,
            "zhikov_token_f": 0.7542, "gap": round(0.7542 - tf, 4), "secs": round(time.time() - t0, 1)}


# ------------------------------------------------------------------ interpreter capability (plan 0.3)
def run_env():
    cands = {"default_python": sys.executable,
             "system_py312": "C:/Users/aezequiel/AppData/Local/Programs/Python/Python312/python.exe"}
    rep = {}
    for tag, exe in cands.items():
        if not exe: continue
        code = ("import sys,json;d={'version':sys.version.split()[0]}\n"
                "\nfor m in ('numpy','torch'):\n"
                "    try:\n        mod=__import__(m); d[m]=getattr(mod,'__version__','?')\n"
                "    except Exception:\n        d[m]=None\n"
                "print(json.dumps(d))")
        try:
            o = subprocess.run([exe, "-c", code], capture_output=True, text=True, timeout=90)
            rep[tag] = json.loads(o.stdout.strip().splitlines()[-1]) | {"exe": exe}
        except Exception as e:
            rep[tag] = {"exe": exe, "error": str(e)[:80]}
        print(f"  {tag:16s} {rep[tag]}")
    learned = [t for t, v in rep.items() if v.get("torch")]
    print(f"\n  interpreter for LEARNED parts (Phase 3): {learned or 'NONE -- Phase 3 blocked'}")
    return {"interpreters": rep, "torch_capable": learned}


# ------------------------------------------------------------------ recorded prior baselines (ledger)
LEDGER = {
    "note": "numbers recorded in the project ledger BEFORE this plan; re-measured by the components above",
    "matrix_prim_solved": 25, "matrix_disc_solved": 120, "matrix_total": 120,
    "quixbugs_ucb_solved": 26, "quixbugs_energy_ratio": 0.83,
    "seg_token_f": 0.741, "zhikov_token_f": 0.7542,
    "e8_authored_vs_blind": {"trunc": 36401, "signmod": "unreachable at depth<=3",
                             "comment": "authored shortlist buys ~1e4-1e5x search efficiency = "
                                        "the factor Phase 3's proposer must recover from L0"},
}

if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "show"
    N = int(os.environ.get("BENCH_N", "20"))
    d = load()
    d.setdefault("ledger_recorded", LEDGER)
    if what in ("matrix", "all"):
        print("=== MATRIX (held-out emergence benchmark) ===")
        d["matrix"] = run_matrix(N)
    if what in ("quixbugs", "all"):
        print("\n=== QUIXBUGS (hand-coded vs UCB) ===")
        d["quixbugs"] = run_quixbugs(d.get("quixbugs"))
    if what in ("seg", "all"):
        print("\n=== SEGMENTATION (br-phono) ===")
        d["segmentation"] = run_seg()
    if what in ("env", "all"):
        print("\n=== INTERPRETERS ===")
        d["env"] = run_env()
    if what == "show":
        print(json.dumps(d, indent=1, sort_keys=True)[:4000]); sys.exit(0)
    save(d)
