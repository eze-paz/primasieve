"""PHASE 2 (d) -- LIBRARY REUSE: the gap Phase 2 left open.

Phase 2 showed MACHINERY generality (one L0 + one discovery routine crystallises all 6 operators) but NOT
operator REUSE: every class crystallised its own frame from its own traces, so no entry was ever used by a
later class. The ledger keeps these distinct, and knockouts (ii)/(iii) of the plan need reuse to exist.

TEST = the SECOND DERIVATIVE class. Its frame is c''=c*e*(e-1), e''=e-2. Two routes:
  REUSE   : COMPOSE two crystallised library entries (diff o diff) -- the E2 compose verb, now over
            L0-crystallised entries. Search = ordered pairs of library entries (|lib|^2, tiny).
  NO-REUSE: discover the d2 frame from L0 directly. Priced blind at 2687 candidates (2647 + 40).
So reuse should be ~100-600x cheaper. It is reachable either way -- the claim is COST, not impossibility.

ARMS
  A CUMULATIVE   : library has diff (+ decoys) and the COMPOSE form -> should solve via diff o diff
  B EMPTY-LIB    : no library; L0 discovery of the d2 frame from wake traces (plan knockout iii)
  C DELETE-ENTRY : library WITHOUT diff (decoys + integ present) -> COMPOSE must FAIL (plan knockout ii)
  D SHUFFLE      : library present but composed frame checked against shuffled tests -> must not "solve"
Every library entry here is itself crystallised FROM L0 (never hand-written): the decoys too, so the
compose search has real distractors and cannot be handed the answer.
"""
import ast, os, sys, time, random, statistics, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("META_GLOBAL", "8000")

import sleep_l0 as SL
import meta_param as MP
from meta_forms import MetaState

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.environ.get("BASELINE", os.path.join(HERE, "BASELINE.json"))
SEEDS = [[(3, 2)], [(2, 3)], [(5, 4)], [(4, 2)], [(2, 5)], [(7, 3)], [(6, 5)], [(9, 2)], [(8, 3)], [(3, 4)]]


def d2(ts):  return MP.differentiate(MP.differentiate(ts))
def dbl(ts): return [(2 * c, e) for c, e in ts]          # decoy family: c'=2c
def rai(ts): return [(c, e + 1) for c, e in ts]          # decoy family: e'=e+1


def crystallise(transform, tag, depth=3, cap=200000):
    """WAKE (generic FitTemplate single-term solves) -> SLEEP (L0 search) -> (rc, re_, label, energy)."""
    tr = MP.bootstrap_traces(transform, SEEDS)
    if len(tr) < 3: return None
    b1, b2 = [], []
    rc = SL.discover_relation_l0(tr, 0, depth=depth, cap=cap, energy_box=b1)
    re_ = SL.discover_relation_l0(tr, 1, depth=depth, cap=cap, energy_box=b2)
    if not (rc and re_): return None
    return {"rc": rc[2], "re": re_[2], "label": f"c'={rc[0]},e'={re_[0]}",
            "energy": (b1[-1] if b1 else 0) + (b2[-1] if b2 else 0), "tag": tag}


def compose(fa, fb):
    """(fa o fb)(c,e) = fa(fb(c,e)) -- the COMPOSE verb over crystallised frames."""
    def rc(c, e):
        c1, e1 = fb["rc"](c, e), fb["re"](c, e)
        if c1 is None or e1 is None: return None
        return fa["rc"](c1, e1)
    def re_(c, e):
        c1, e1 = fb["rc"](c, e), fb["re"](c, e)
        if c1 is None or e1 is None: return None
        return fa["re"](c1, e1)
    return rc, re_


def apply_frame(st, rc, re_, name):
    """MAP_SITES: rewrite EVERY term by the frame, then score (mirrors meta_param.StructParam.run)."""
    before = st.best
    terms = MP.parse_terms(st.tree)
    if not terms: return False
    try:
        new = [(rc(c, e), int(round(re_(c, e)))) for c, e in terms]
        if any(c is None for c, _ in new): return False
        t2 = ast.parse(MP.poly_src(new))
    except Exception:
        return False
    st.units += 1
    nf, susp2 = st._score(t2)
    if nf == 0:
        st.tree, st.susp, st.best = t2, susp2, nf
        st.log.append((name, before, nf))
        return True
    return False


class ComposeLib:
    """COMPOSE form: search ORDERED PAIRS of crystallised library entries, apply the composition at every
    site, accept only if the task's own tests pass. Energy = pairs tried (NOT handed the winning pair)."""
    cost_hint = 1.0

    def __init__(self, library):
        self.lib = library
        self.name = f"COMPOSE[lib:{len(library)}]"

    def _key(self, st): return ("COMPOSE", st._th())
    def applicable(self, st): return not st.solved() and st._cache.get(self._key(st)) is None

    def run(self, st, budget):
        before = st.best
        st._cache[self._key(st)] = True
        names = list(self.lib)
        tried = 0
        for a in names:                              # depth-1: the entry ALONE (compose includes identity)
            tried += 1
            e = self.lib[a]
            if apply_frame(st, e["rc"], e["re"], f"APPLY[{a}]"):
                return {"form": self.name, "tried": tried, "before": before, "after": 0,
                        "improved": True, "solved": True, "exhausted": False, "fix": a}
        for a in names:                              # depth-2: ordered pairs f o g
            for b in names:
                tried += 1
                rc, re_ = compose(self.lib[a], self.lib[b])
                if apply_frame(st, rc, re_, f"COMPOSE[{a} o {b}]"):
                    return {"form": self.name, "tried": tried, "before": before, "after": 0,
                            "improved": True, "solved": True, "exhausted": False,
                            "fix": f"{a} o {b}"}
        return {"form": self.name, "tried": tried, "before": before, "after": before,
                "improved": False, "solved": False, "exhausted": True, "fix": None}


def gen_d2(rng):
    k = rng.randint(2, 4)
    es = rng.sample(range(3, 9), k)
    return MP.make_task([(rng.randint(2, 9), e) for e in es], d2)


def grade(lib, N, rng_seed=4242, shuffle_tests=False):
    """solve N held-out d2 tasks with the COMPOSE form over `lib`. Returns (solved, energies, fixes)."""
    rng = random.Random(rng_seed)
    solved = 0; ens = []; fixes = {}
    for _ in range(N):
        t = gen_d2(rng)
        tests = list(t["tests"])
        if shuffle_tests:
            outs = [o for _, o in tests]
            random.Random(7).shuffle(outs)
            tests = [(i, outs[j]) for j, (i, _) in enumerate(tests)]
        st = MetaState("f", t["src"], tests)
        f = ComposeLib(lib)
        d = f.run(st, 400) if lib else {"solved": False, "tried": 0, "fix": None}
        solved += bool(d["solved"]); ens.append(d["tried"])
        if d.get("fix"): fixes[d["fix"]] = fixes.get(d["fix"], 0) + 1
    return solved, ens, fixes


if __name__ == "__main__":
    N = int(os.environ.get("REUSE_N", "12"))
    t0 = time.time()
    print("PHASE 2(d) -- LIBRARY REUSE via the COMPOSE verb over L0-crystallised entries\n")

    print("building the library (every entry crystallised FROM L0, decoys included):")
    lib = {}
    for tf, tag in ((MP.differentiate, "diff"), (MP.integrate, "integ"), (dbl, "double"), (rai, "raise")):
        ent = crystallise(tf, tag)
        if ent:
            lib[tag] = ent
            print(f"  {tag:8s} {ent['label']:42s} (L0 energy {ent['energy']})")
        else:
            print(f"  {tag:8s} FAILED to crystallise")
    print(f"  library size {len(lib)} -> COMPOSE search space {len(lib)**2} ordered pairs")

    print(f"\n=== ARM A: CUMULATIVE (library + COMPOSE) on {N} held-out d2 tasks ===")
    sA, eA, fA = grade(lib, N)
    print(f"  solved {sA}/{N}   median pairs tried {int(statistics.median(eA))}   winning composition(s) {fA}")

    print(f"\n=== ARM C: DELETE-ENTRY knockout (library WITHOUT diff) ===")
    lib_nodiff = {k: v for k, v in lib.items() if k != "diff"}
    sC, eC, fC = grade(lib_nodiff, N)
    print(f"  library {list(lib_nodiff)} -> solved {sC}/{N}   {fC or '(no composition works)'}")

    print(f"\n=== ARM B: EMPTY-LIBRARY restart (no reuse; discover the d2 frame from L0 directly) ===")
    tr = MP.bootstrap_traces(d2, SEEDS)
    print(f"  wake traces for d2 (FitTemplate): {len(tr)}")
    b1, b2 = [], []
    rc = SL.discover_relation_l0(tr, 0, energy_box=b1) if len(tr) >= 3 else None
    re_ = SL.discover_relation_l0(tr, 1, energy_box=b2) if len(tr) >= 3 else None
    blind = (b1[-1] if b1 else 0) + (b2[-1] if b2 else 0)
    print(f"  L0 direct discovery: c'={rc[0] if rc else None}  e'={re_[0] if re_ else None}   "
          f"candidates={blind}")
    sB, eB, fB = (0, [0], {})
    if rc and re_:
        ent = {"rc": rc[2], "re": re_[2], "label": "direct"}
        sB, eB, fB = grade({"d2direct": ent}, N)
        print(f"  solved {sB}/{N} once discovered (1 pair)")

    print(f"\n=== ARM D: SHUFFLED-TESTS control (library present) ===")
    sD, eD, fD = grade(lib, N, shuffle_tests=True)
    print(f"  solved {sD}/{N}  (must be 0 -- a composition must not 'solve' scrambled targets)")

    med_pairs = int(statistics.median(eA)) if eA else 0
    speedup = (blind / med_pairs) if (blind and med_pairs) else None
    print(f"\n=== VERDICT (measure d) ===")
    print(f"  A cumulative   {sA}/{N} @ {med_pairs} pair-evals   (reuse: diff o diff)")
    print(f"  B no-reuse     L0 direct discovery cost {blind} candidates")
    print(f"  C delete-diff  {sC}/{N}  -> {'REGRESSES (reuse is specifically on the diff entry)' if sC == 0 else 'no regression = reuse NOT load-bearing'}")
    print(f"  D shuffled     {sD}/{N}  -> {'PASSES' if sD == 0 else 'LEAKS'}")
    if speedup: print(f"  reuse advantage: {speedup:.0f}x cheaper than rediscovering the frame from L0")
    reuse_ok = (sA == N and sC == 0 and sD == 0)
    print(f"  measure (d) {'DEMONSTRATED' if reuse_ok else 'NOT demonstrated'}")
    print(f"  ({time.time()-t0:.0f}s)")

    d = json.load(open(OUT)) if os.path.exists(OUT) else {}
    d["phase2_reuse"] = {
        "library": {k: v["label"] for k, v in lib.items()},
        "arm_A_cumulative": {"solved": sA, "n": N, "median_pair_evals": med_pairs, "compositions": fA},
        "arm_B_no_reuse_l0_direct": {"candidates": blind,
                                     "frame": [rc[0] if rc else None, re_[0] if re_ else None],
                                     "solved_once_discovered": sB},
        "arm_C_delete_diff": {"solved": sC, "n": N, "library": list(lib_nodiff)},
        "arm_D_shuffled_tests": {"solved": sD, "n": N},
        "reuse_speedup_vs_rediscovery": speedup,
        "measure_d": "DEMONSTRATED" if reuse_ok else "NOT demonstrated",
    }
    json.dump(d, open(OUT, "w"), indent=1, sort_keys=True)
    print(f"  -> merged into {os.path.basename(OUT)}")
