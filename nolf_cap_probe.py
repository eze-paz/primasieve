"""DIAGNOSTIC (read-only): is BANK_CAP, not MAX_OPS and not enumeration order, the ceiling on the nolf search?

MEASURED (nolf_collide_probe + the bank spy): with the shipped constants the strings BOOL bank retains exactly
6000 terms -- 1+20+178+1815 = 2014 at levels 0-3, then 3986 of the 4-atom level and the bank is FULL. The 4-atom
level is therefore TRUNCATED: ARCHITECTURE.md's "4,663 boolean terms" were never all enumerated. Two banks of
eight are saturated (BOOL and INT).

This sweeps BANK_CAP upward and reports, per cap: retained terms per level, wall time, and which banks saturate.
It answers one question -- how big IS the distinct-signature 4-atom space when nothing truncates it -- which
decides whether the ceiling is a fixable constant or a genuine exponential.

Nothing here is a gate and nothing is claimed. `nolf_learn.py` is NOT edited: BANK_CAP is read from module scope
at table() time, so it is patched in memory for the duration of a measurement.

    python nolf_cap_probe.py --world strings --caps 6000,20000,60000
"""
import os, sys, time, collections
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import nolf_learn as NL
import nolf_worlds as NW
from core.generate import SignatureBank

BANKS = []


class Spy(SignatureBank):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw); BANKS.append(self)


def setup(world):
    W = NW.Records() if world == "records" else NW.Strings()
    train = NW.splits(W, 1)["train"]
    L = NL.Learner(time_budget=1); L._classes(train); L.demoted = set()
    elems = set()
    for sit, _, _ in train:
        for x in sit:
            if NL.P.CHECK[NL.ELEM](x): elems.add(x)
            elif NL.P.CHECK[NL.SEQ](x):
                for y in x:
                    if NL.P.CHECK[NL.ELEM](y): elems.add(y)
    rels = [p for p in NL.P.pids() if NL.P.signature(p) == ((NL.INT, NL.INT), NL.BOOL)]
    sels = [("all",), ("any",)] + [("idx", k) for k in range(-1, 4)]
    by_size = {}
    for sit, _, _ in train: by_size.setdefault(len(sit), []).append(sit)
    probes = [x for k in sorted(by_size) for x in by_size[k][:3]][:8]
    if len(probes) < 8: probes += [sit for sit, _, _ in train[:8 - len(probes)]]
    return W, probes, elems, rels, sels


def run(world, caps):
    W, probes, elems, rels, sels = setup(world)
    NL.SignatureBank = Spy
    print(f"=== {W.name}: MAX_OPS={NL.MAX_OPS}, shipped BANK_CAP={NL.BANK_CAP}", flush=True)
    for cap in caps:
        BANKS.clear()
        NL.BANK_CAP = cap
        t0 = time.time()
        try:
            E = NL.Enumerator(probes, elems, rels, sels)
            T = E.table(False)
        except MemoryError:
            print(f"cap {cap:>7}: MemoryError after {time.time()-t0:.0f}s -- this cap is not affordable", flush=True)
            break
        secs = time.time() - t0
        lv = " ".join(f"{k}:{len(T[k].get(NL.BOOL, []))}" for k in sorted(T))
        tot = sum(len(T[k].get(NL.BOOL, [])) for k in T)
        sat = sum(1 for b in BANKS if b.full())
        print(f"cap {cap:>7}: BOOL total {tot:>7}  levels[{lv}]  {secs:6.0f}s  banks saturated {sat}/{len(BANKS)}"
              + ("   <-- STILL TRUNCATED" if sat else "   <-- COMPLETE at this depth"), flush=True)
        if not sat:
            print(f"\n-> the distinct-signature 4-atom BOOL space is {tot} terms. The shipped cap of 6000 was "
                  f"discarding {tot - 6000} of them.", flush=True)
            break


if __name__ == "__main__":
    world = sys.argv[sys.argv.index("--world") + 1] if "--world" in sys.argv else "strings"
    caps = [int(x) for x in (sys.argv[sys.argv.index("--caps") + 1].split(",")
                             if "--caps" in sys.argv else ["6000", "20000", "60000", "200000"])]
    run(world, caps)
