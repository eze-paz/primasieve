"""DIAGNOSTIC (read-only, no gates, no claim): is the nolf strings ceiling a REPRESENTATIONAL COLLISION?

core/grow.py fixes the priority: REPRESENTATION BEFORE LIBRARY -- "a collision means the representation cannot
hold the target distinction, so every reachability judgment about that distinction is unreliable". nolf_closure.py
ran the degree-3 (closure stall) arm without ever testing degree 4. This measures degree 4 before anything is built.

A COLLISION, exactly: two rows of one skeleton group that agree on the SITUATION and on every SLOT FILL but
disagree on TRUTH. Then no function of (situation, fill) -> truth exists for that skeleton at any term size, and
the search was hunting in a space provably containing no solution.

No collision means a consistent function exists and the ceiling is purely search -- which ELIMINATES the degree-4
arm for this world, which is the point of running it first.

    python nolf_collide_probe.py --world strings
"""
import os, sys, collections
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import nolf_worlds as NW
import nolf_learn as NL


def probe(world):
    W = NW.Records() if world == "records" else NW.Strings()
    train = NW.splits(W, 1)["train"]
    L = NL.Learner(time_budget=1)
    L._classes(train)
    L.demoted = set()               # fit() normally sets this; we are calling _key() outside fit()

    # group by the RAW class-sequence key (no reduction: reduction needs a learned grammar, and at the start
    # there is none -- this is the skeleton set the learner first faces)
    groups = collections.defaultdict(list)
    for sit, toks, tv in train:
        key, fill = L._key([("c", L.cls[w], w) for w in toks])
        groups[key].append((sit, tuple(fill), tv))

    print(f"=== {W.name}: {len(train)} rows, {len(L.cls)} words, {len(L.members)} classes, {len(groups)} raw skeletons")
    tot_coll = 0
    rows = []
    for key, rs in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        seen = {}
        coll = 0
        for sit, fill, tv in rs:
            k = (repr(sit), fill)
            if k in seen and seen[k] != tv: coll += 1
            seen[k] = tv
        tot_coll += coll
        # how much the truth column actually varies -- a constant column is memorisable and says nothing
        pos = sum(1 for _, _, tv in rs if tv)
        rows.append((len(rs), coll, pos / len(rs), [x if x == "B" else x[1] for x in key]))
    print(f"{'rows':>6} {'collisions':>11} {'true frac':>10}  skeleton")
    for n, coll, pf, k in rows:
        if n < NL.MIN_ROWS: continue
        flag = "  <-- COLLISION" if coll else ""
        print(f"{n:6d} {coll:11d} {pf:10.3f}  {k}{flag}")
    print(f"\nTOTAL COLLISIONS across every skeleton: {tot_coll}")
    print("-> DEGREE 4 APPLIES: some skeleton admits no function at all; search was hunting an empty space."
          if tot_coll else
          "-> DEGREE 4 ELIMINATED for this world: every skeleton admits a consistent function of (situation, fill).\n"
          "   The ceiling is SEARCH -- the fitting function exists and is not in the enumerated term space.")


if __name__ == "__main__":
    probe(sys.argv[sys.argv.index("--world") + 1] if "--world" in sys.argv else "strings")
