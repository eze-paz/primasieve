"""FLUENCY LOOP it.5 -- resumable BUILD of a converged class map (LOOP.md "ITERATION 5"). Not a test.
Loads _nldata/classes_wikt30k_K128.json if present, runs exchange passes with a checkpoint after each, exits at
convergence (0-move pass + rare-word assignment) or after its time slice. Re-invoke until it prints CONVERGED.

Usage:  python loop_it5_build.py [slice_seconds=480]"""
import os, sys, time, json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.seqform import ClassBigram, save_classes, load_classes
from loop_it1_size import load

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(HERE, "_nldata", "classes_wikt30k_K128.json")
META = PATH + ".meta.json"
K, N = 128, 30000

if __name__ == "__main__":
    slice_s = int(sys.argv[1]) if len(sys.argv) > 1 else 480
    t0 = time.time()
    tr, _ = load()
    m = ClassBigram(tr[:N], K)
    meta = json.load(open(META)) if os.path.exists(META) else {"passes": 0, "secs": 0.0, "converged": False, "moves": []}
    resumed = load_classes(m, PATH)
    print(f"build: V={m.V} K={m.K} resumed={resumed} passes so far {meta['passes']} ({meta['secs']:.0f}s) converged={meta['converged']}", flush=True)
    if meta["converged"]:
        print("CONVERGED (nothing to do)"); sys.exit(0)
    words = [w for w in m.vocab if m.wc[w] >= 2]
    rare = [w for w in m.vocab if m.wc[w] < 2]
    while time.time() - t0 < slice_s:
        tp = time.time(); moves = 0
        for w in words:
            a = m.cls[w]; best = (1e-9, a)
            for b in range(m.K):
                if b != a:
                    d = m._delta(w, a, b)
                    if d > best[0]: best = (d, b)
            if best[1] != a: m._move(w, a, best[1]); moves += 1
        meta["passes"] += 1; meta["secs"] += time.time() - tp; meta["moves"].append(moves)
        save_classes(m, PATH); json.dump(meta, open(META, "w"))
        print(f"  pass {meta['passes']}: {moves} moves of {len(words)} frequent words ({time.time()-tp:.0f}s)", flush=True)
        if moves <= 0.01 * len(words):        # settled: < 1% of frequent words still moving (amended, LOOP.md it.5)
            tp = time.time(); assigned = 0
            for w in rare:
                a = m.cls[w]; best = (1e-9, a)
                for b in range(m.K):
                    if b != a:
                        d = m._delta(w, a, b)
                        if d > best[0]: best = (d, b)
                if best[1] != a: m._move(w, a, best[1]); assigned += 1
            meta["secs"] += time.time() - tp; meta["converged"] = True; meta["rare_assigned"] = assigned
            save_classes(m, PATH); json.dump(meta, open(META, "w"))
            print(f"  rare words: {assigned} of {len(rare)} moved ({time.time()-tp:.0f}s)")
            print(f"CONVERGED (settled, last pass {moves} moves) after {meta['passes']} passes, {meta['secs']:.0f}s total build time")
            break
    else:
        print(f"slice over after {meta['passes']} passes ({meta['secs']:.0f}s total); re-invoke to continue")
