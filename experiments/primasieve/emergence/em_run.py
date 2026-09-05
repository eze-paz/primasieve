"""THE TWO-ARM RULE -- every run reports COLD and WARM. Standing policy for this thread.

    COLD  empty library      -- the scientific number (mechanism works with no inherited knowledge)
    WARM  library from disk  -- the engineering number (what the deployed system actually does)
    DELTA what the accumulated knowledge is WORTH

Run it repeatedly; the store accumulates and WARM should get cheaper each time while COLD stays flat. COLD
staying flat is not a failure -- it is the control that proves WARM's gain is accumulated knowledge and not a
change in the task.

    python em_run.py            # both arms on the standard d^k curriculum, then persist
    python em_run.py --reset    # wipe the store first (fresh cold start)
    python em_run.py --guard    # demonstrate the leakage guard: exclude entries whose provenance IS the eval

LEAKAGE: the WARM arm is only honest because entries carry provenance and the eval can exclude any entry
crystallised FROM the eval task. Wiping the library was a blunt substitute for that control; provenance makes
it checkable. --guard shows the guard actually biting.
"""
import os, sys, json, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import em_depth as D
import em_recursion as R
import em_store as S

OUT = os.path.join(HERE, "EMERGENCE.json")
KS = [1, 2, 3, 4, 5, 6, 8, 10, 12, 16]


def arm(lib, ks, crystallise=True):
    """solve each k; library first, blind fallback. Returns (reached, cost, lib, provenance)."""
    lib = dict(lib); prov = {}
    reached = []; cost = 0
    for k in ks:
        tgt = D.sig_k(k)
        fr = None; how = None
        if lib:
            fr, tag, ev = D.solve_by_library(k, lib); cost += ev
            if fr is not None: how = f"library:{tag}"
        if fr is None:
            fr, ev = D.solve_blind(k); cost += ev
            if fr is not None: how = "blind"
        if fr is not None:
            reached.append(k)
            if crystallise:
                sg = D.frame_sig(fr)
                if sg and not any(D.frame_sig(v) == sg for v in lib.values()):
                    name = f"d{k}"
                    lib[name] = fr
                    prov[name] = {"task_sig": str(tgt)[:80], "task": f"d^{k}", "how": how}
    return reached, cost, lib, prov


if __name__ == "__main__":
    t0 = time.time()
    if "--reset" in sys.argv and os.path.exists(S.STORE):
        os.remove(S.STORE); print("store wiped -- fresh cold start\n")
    run_id = time.strftime("%H%M%S")
    before = S.summary()
    print(f"TWO-ARM RUN  (store had {before['entries']} entries from {before['runs']} prior runs)\n")

    # ---- COLD: the scientific arm, no inherited knowledge ----
    cold_reached, cold_cost, cold_lib, cold_prov = arm({}, KS)
    print(f"  COLD  reached k={cold_reached}  max {max(cold_reached) if cold_reached else 0:>2}  cost {cold_cost}")

    # ---- WARM: the engineering arm, knowledge loaded from disk ----
    excl = [str(D.sig_k(k))[:80] for k in KS] if "--guard" in sys.argv else []
    wlib, wprov = S.load(exclude_provenance=excl, verbose=True)
    warm_reached, warm_cost, warm_lib, warm_prov = arm(wlib, KS)
    print(f"  WARM  reached k={warm_reached}  max {max(warm_reached) if warm_reached else 0:>2}  cost {warm_cost}"
          + ("   [leakage guard ON: entries from the eval tasks EXCLUDED]" if excl else ""))

    delta = (cold_cost / warm_cost) if warm_cost else float("inf")
    print(f"\n  DELTA  warm is {delta:.1f}x cheaper than cold "
          f"({cold_cost} -> {warm_cost} evals); same tasks, same verifier")
    if not excl:
        n = S.save(warm_lib or cold_lib, {**cold_prov, **warm_prov}, run_id=run_id)
        print(f"  store: {before['entries']} -> {n} entries persisted (run {run_id})")

    d = json.load(open(OUT)) if os.path.exists(OUT) else {}
    hist = d.get("two_arm_runs", [])
    hist.append({"run_id": run_id, "guard": bool(excl),
                 "cold": {"reached": cold_reached, "cost": cold_cost},
                 "warm": {"reached": warm_reached, "cost": warm_cost, "lib_in": len(wlib)},
                 "delta_x": round(delta, 2), "store_entries_before": before["entries"]})
    d["two_arm_runs"] = hist
    d["two_arm_rule"] = ("STANDING POLICY: every run reports COLD (empty library -- the scientific number) and "
                         "WARM (library from disk -- the engineering number), plus the delta, which measures "
                         "what the accumulated knowledge is worth. WARM stays honest via PROVENANCE on every "
                         "entry: an eval can exclude entries crystallised from the eval task itself, so the "
                         "library can never hold the answer to the question being asked. Wiping the library was "
                         "a blunt substitute for that control.")
    json.dump(d, open(OUT, "w"), indent=1, sort_keys=True)
    print(f"  ({time.time()-t0:.0f}s)")
