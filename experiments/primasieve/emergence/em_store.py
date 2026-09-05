"""PERSISTENT FORM STORE -- knowledge the engine KEEPS across sessions, with a leakage guard.

Owner's point, and it is correct: wiping the emergent library between runs is scientific hygiene, but an
engineer wants the accumulated forms to survive, because a system that gets cheaper every run is the whole
value. Standing rule adopted here: EVERY run reports BOTH arms.

    COLD  empty library -- the scientific number. Did the mechanism work with no inherited knowledge?
    WARM  library loaded from disk -- the engineering number. What does the deployed system actually do?
    DELTA the two together measure what the accumulated knowledge is WORTH. Neither alone is the answer.

WHAT WAS BROKEN BEFORE THIS FILE: em_loop.py wrote library.json with str(frame) and NOTHING ever read it
back, so "persistent library" was a claim the code did not support -- every run really did start cold. Frames
are now round-tripped properly (JSON lists -> tuples) and load() is real.

LEAKAGE GUARD -- this is what keeps WARM honest rather than rigged. Every entry records the PROVENANCE of the
task that produced it. An evaluation may exclude entries whose provenance is an eval task, so the warm library
can never contain the answer to the very question being asked. That is the real anti-rig control; wiping the
library was only a blunt substitute for it. Provenance makes it CHECKABLE instead of asserted.
"""
import os, json, time

HERE = os.path.dirname(os.path.abspath(__file__))
STORE = os.path.join(HERE, "form_store.json")


def _jsonable(t):
    if isinstance(t, tuple): return ["#t"] + [_jsonable(x) for x in t]
    return t


def _detuple(o):
    if isinstance(o, list) and o and o[0] == "#t":
        return tuple(_detuple(x) for x in o[1:])
    if isinstance(o, list): return [_detuple(x) for x in o]
    return o


def load(path=STORE, exclude_provenance=(), verbose=False):
    """Return (library, provenance). exclude_provenance = task signatures that must NOT contribute entries."""
    if not os.path.exists(path): return {}, {}
    d = json.load(open(path))
    lib, prov, dropped = {}, {}, 0
    excl = set(exclude_provenance)
    for name, rec in d.get("entries", {}).items():
        if rec.get("task_sig") in excl:
            dropped += 1
            continue                                  # LEAKAGE GUARD
        lib[name] = _detuple(rec["frame"])
        prov[name] = rec
    if verbose:
        print(f"  store: loaded {len(lib)} entries from {os.path.basename(path)}"
              + (f"; DROPPED {dropped} by leakage guard" if dropped else ""))
    return lib, prov


def save(lib, provenance, path=STORE, run_id=None):
    """Merge new entries into the store, keeping the first provenance for an existing signature."""
    d = {"entries": {}, "runs": []}
    if os.path.exists(path):
        d = json.load(open(path))
        d.setdefault("entries", {}); d.setdefault("runs", [])
    for name, fr in lib.items():
        if name in d["entries"]: continue
        rec = dict(provenance.get(name, {}))
        rec["frame"] = _jsonable(fr)
        rec.setdefault("ts", time.strftime("%Y-%m-%dT%H:%M:%S"))
        rec.setdefault("run_id", run_id or "unknown")
        d["entries"][name] = rec
    d["runs"].append({"run_id": run_id or "unknown", "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                      "entries_after": len(d["entries"])})
    json.dump(d, open(path, "w"), indent=1, sort_keys=True)
    return len(d["entries"])


def summary(path=STORE):
    if not os.path.exists(path): return {"entries": 0, "runs": 0}
    d = json.load(open(path))
    return {"entries": len(d.get("entries", {})), "runs": len(d.get("runs", [])),
            "names": sorted(d.get("entries", {}))}


if __name__ == "__main__":
    s = summary()
    print(f"form store: {s['entries']} entries accumulated over {s['runs']} runs")
    if s.get("names"): print(f"  {s['names']}")
