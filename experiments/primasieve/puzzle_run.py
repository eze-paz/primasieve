"""FROZEN-engine run over the held-out PuzzLing dev sample (pilot=chickasaw excluded) + controls. Reports per-puzzle
P (correct/commit), C (commit/total), W (wrong), hard/soft abstain, foreign->English items. Pooled + fable controls:
K1 pairing-shuffle (commits must collapse), K7-B1 copy-source baseline. NO tuning on these puzzles (engine frozen)."""
import os, sys, json, io, glob, random, collections
sys.path.insert(0, os.path.dirname(__file__))
import puzzle_engine as E

REF = os.path.join(E.D, "puzzling_ref")
PILOT = "chickasaw"

def run_puzzle(d, shuffle=False, copy_baseline=False):
    train = [(a, b) for a, b in d["train"]]
    if shuffle:
        es = [b for _, b in train]; random.Random(0).shuffle(es)
        train = [(a, es[i]) for i, (a, _) in enumerate(train)]
    items = [it for it in d["test"] if it[2] == ">" and it[0].strip() and it[1].strip()]
    if not items: return None
    M = E.engine(train, [it[0] for it in items])
    rep = E.reproduces(train, M)
    C = P = W = hard = soft = 0
    for it in items:
        gold = E._n(it[1])
        if copy_baseline:
            pred = E._n(it[0]); st = "commit"
        else:
            st, pr = E.solve_fe(it[0], M); pred = E._n(pr) if pr else None
        if st == "commit":
            C += 1; ok = (pred == gold); P += ok; W += (not ok)
        else:
            hard += st == "hard"; soft += st == "soft"
    return dict(lang=d["source_language"], n=len(items), rep=f"{rep}/{len(train)}",
                C=C, P=P, W=W, hard=hard, soft=soft)

if __name__ == "__main__":
    files = sorted(glob.glob(os.path.join(REF, "*")))
    puzzles = []
    for f in files:
        d = json.load(io.open(f, "r", encoding="utf-8"))
        if d["source_language"] != PILOT: puzzles.append(d)

    print("FROZEN ENGINE on held-out dev sample (foreign->English), pilot=chickasaw excluded:\n")
    print(f"  {'lang':12s} {'items':>5} {'repro':>7} {'commit':>6} {'correct':>7} {'wrong':>5} {'hard':>4} {'soft':>4}")
    tot = collections.Counter()
    for d in puzzles:
        r = run_puzzle(d)
        if not r: continue
        for k in ("n", "C", "P", "W", "hard", "soft"): tot[k] += r[k]
        print(f"  {r['lang']:12s} {r['n']:5d} {r['rep']:>7} {r['C']:6d} {r['P']:7d} {r['W']:5d} {r['hard']:4d} {r['soft']:4d}")
    pooledP = tot["P"] / tot["C"] if tot["C"] else 0.0
    print(f"\n  POOLED: items {tot['n']}  commit {tot['C']} (C={tot['C']/tot['n']:.2f})  "
          f"correct {tot['P']} (P={pooledP:.2f})  wrong {tot['W']}  hard {tot['hard']} soft {tot['soft']}")

    # K1 pairing-shuffle control (pooled)
    sh = collections.Counter()
    for d in puzzles:
        r = run_puzzle(d, shuffle=True)
        if r:
            for k in ("n", "C", "P", "W"): sh[k] += r[k]
    print(f"  K1 shuffle-pairing: commit {sh['C']} correct {sh['P']} wrong {sh['W']} "
          f"(commits must collapse vs {tot['C']})")
    # B1 copy-source baseline (pooled)
    cp = collections.Counter()
    for d in puzzles:
        r = run_puzzle(d, copy_baseline=True)
        if r:
            for k in ("n", "C", "P"): cp[k] += r[k]
    print(f"  B1 copy-source baseline: correct {cp['P']}/{cp['n']} EM  (engine correct {tot['P']}/{tot['n']})")
    print("\n  (foreign->English only, per prereg §5; abstain split hard/soft; engine frozen on pilot only.)")