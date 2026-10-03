"""STORE -- evidence outlives the process (persist_prereg.md; EMERGENCE_PLAN.md S8). Zero LLM; JSON; holds no word.

What is stored is EVIDENCE, never a conclusion: the confirmed pairs, the denials, the ledger's counts, the frame
observations, and -- as a cache that carries its own forcing record -- each library tree. On load every learning world
RE-INDUCES from the stored evidence, every cached tree is VERIFIED against the examples that forced it (dropped if it
fails), the library is compressed and pruned. A store cannot make the engine believe what its evidence does not support;
a corrupted store costs at most some cached work; a save after a load with no new evidence is byte-identical.

A learning world provides `evidence() -> dict` (JSON-able) and `absorb(evidence) -> report`; optionally `consolidate()`
(sleep + prune). A world without them stores nothing. `save` consolidates first, so a file is always a fixed point."""
import json
import os


def save(session, path):
    """-> report {world: consolidation}. Sorted keys, so the same evidence is the same bytes."""
    report = {}
    for w in session.worlds:
        if hasattr(w, "consolidate"): report[w.name] = w.consolidate()
    data = dict(worlds={w.name: w.evidence() for w in session.worlds if hasattr(w, "evidence")}, session=session.evidence())
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, sort_keys=True, indent=1, ensure_ascii=False)
    return report


def load(session, path):
    """-> report {world: absorb report, "session": session report}. Worlds are matched by name."""
    data = json.load(open(path, encoding="utf-8"))
    report = {}
    for w in session.worlds:
        ev = data.get("worlds", {}).get(getattr(w, "name", None))
        if ev is not None and hasattr(w, "absorb"): report[w.name] = w.absorb(ev)
    report["session"] = session.absorb(data.get("session", {}))
    return report
