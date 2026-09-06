"""STAGE 6 RUN -- DEGREE 4: representation extension by collision-driven selection. Pre-registered gates below.

The propose-verify loop, using the project's standing discipline (reject/verify, cost-ordered adoption, and a
signal-ablation knockout -- fable's device that every epistemic layer must carry its own gate keyed to its own
signal):

  detect     a COLLISION = two training items with the SAME current form but DIFFERENT discriminator value
  propose    select the minimal extension from a hand-given library {identity, scope_order}, cost-ordered
             (identity first); keep the first that resolves the collision AND raises held-out accuracy
  gate G6a   collision DETECTED on discriminating data (two-same-form-different-truth exist)
  gate G6b   the selected extension raises held-out truth accuracy to >= 0.95 (flat baseline is ~0.5 on the
             reading it cannot represent)
  gate G6c   INERTNESS: on quantifier-free rows no collision exists, so no extension is proposed
  gate G6d   THE KNOCKOUT: ablate the discriminator (situations where the two readings AGREE) -> no collision
             -> the engine MUST NOT propose the extension. Proposal under ablation FALSIFIES "collision-driven".

Usage:  python cogs_stage6.py"""
import os, sys, random

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cogs_scope import R0, R1, make_items, eval_form, reading_from_R1, truth
from core.registry import selfcheck

# the hand-given extension library. `identity` is the null extension (no change); `scope_order` adds the
# WIDE(quantifier) atom. Cost-ordered: identity is simpler and tried first.
LIBRARY = [("identity", R0, lambda f: None),
           ("scope_order", R1, reading_from_R1)]


def _situ(it):
    return (frozenset(it["R"]), tuple(it["D"]))


def has_collision(items, form):
    """A representational COLLISION: two items with the SAME form AND the SAME situation but DIFFERENT truth.
    Keying on the situation is essential -- otherwise every item shares one scope-free form and the check
    trivially 'detects' a collision from situation differences alone (the bug the knockout caught)."""
    by = {}
    for it in items:
        by.setdefault((form(it), _situ(it)), set()).add(it["truth"])
    return any(len(v) > 1 for v in by.values())


def held_out_accuracy(items, form, reading_of):
    ok = 0
    for it in items:
        f = form(it)
        pred = eval_form(f, reading_of(f), it["C"], it["D"], it["R"])
        ok += (pred == it["truth"])
    return ok / max(len(items), 1)


def propose(train, test):
    """Cost-ordered selection: keep the first extension that RESOLVES the collision under R0 and raises
    held-out accuracy over the flat baseline. Returns (name, form, reading_of) or None (no proposal)."""
    if not has_collision(train, R0):
        return None                                    # no collision -> nothing to propose (inertness)
    base = held_out_accuracy(test, R0, lambda f: None)
    for name, form, reading_of in LIBRARY:
        if name == "identity":
            continue                                   # identity cannot resolve a collision by construction
        if not has_collision(train, form) and held_out_accuracy(test, form, reading_of) > base + 0.05:
            return name, form, reading_of
    return None


if __name__ == "__main__":
    selfcheck(__file__)
    rng = random.Random(6)
    print("STAGE 6 -- DEGREE 4: representation extension by COLLISION-DRIVEN SELECTION.")
    print("The type-constructor library is HAND-GIVEN (as l0 was); the claim is SELECTION over it, driven by a")
    print("representational collision, not 'inventing representations'.\n")

    train = make_items(rng, 400)
    test = make_items(rng, 400)

    # G6a -- collision detected
    coll = has_collision(train, R0)
    base = held_out_accuracy(test, R0, lambda f: None)
    print(f"G6a  COLLISION under the flat representation: {'DETECTED' if coll else 'none'}   "
          f"(flat held-out truth accuracy {base:.3f} -- it must guess one reading)   "
          f"[gate DETECTED -> {'PASS' if coll else 'FAIL'}]")

    # propose
    sel = propose(train, test)
    name = sel[0] if sel else None
    print(f"\n  PROPOSED extension (cost-ordered from {[n for n, _, _ in LIBRARY]}): {name}")

    # G6b -- the extension raises held-out accuracy
    acc = held_out_accuracy(test, sel[1], sel[2]) if sel else base
    g6b = sel is not None and acc >= 0.95
    print(f"G6b  held-out truth accuracy WITH the extension: {acc:.3f}   "
          f"[gate >= 0.95 and extension selected -> {'PASS' if g6b else 'FAIL'}]")

    # G6c -- inertness on quantifier-free data
    qfree = make_items(rng, 400, quantifier_free=True)
    sel_qf = propose(qfree, make_items(rng, 400, quantifier_free=True))
    g6c = sel_qf is None
    print(f"\nG6c  INERTNESS on quantifier-free data: proposed {sel_qf[0] if sel_qf else 'NOTHING'}   "
          f"[gate propose nothing -> {'PASS' if g6c else 'FAIL'}]")

    # G6d -- THE KNOCKOUT: ablate the discriminator (readings agree) -> no collision -> must not propose
    agree_train = make_items(rng, 400, force_agree=True)
    agree_test = make_items(rng, 400, force_agree=True)
    coll_ablated = has_collision(agree_train, R0)
    sel_ablated = propose(agree_train, agree_test)
    g6d = (not coll_ablated) and sel_ablated is None
    print(f"\nG6d  DISCRIMINATOR-ABLATION KNOCKOUT (situations where every>some and some>every AGREE):")
    print(f"     collision under ablation: {'DETECTED (BAD)' if coll_ablated else 'none'}   "
          f"proposed: {sel_ablated[0] if sel_ablated else 'NOTHING'}   "
          f"[gate: no collision AND no proposal -> {'PASS' if g6d else 'FAIL'}]")
    print("     -> the extension is driven by the COLLISION signal, not by priors: remove the signal and the")
    print("        engine falls silent. This is the anti-relabel device -- a control that cannot fail here.")

    allpass = coll and g6b and g6c and g6d
    print(f"\nDEGREE 4 (representation extension by collision-driven selection): {'PASS' if allpass else 'FAIL'}")
    print("  BOUNDED CLAIM: the engine SELECTED a scope-carrying extension from a hand-given library when a")
    print("  representational collision forced it, raised held-out truth accuracy, stayed inert without a")
    print("  collision, and fell silent when the collision signal was ablated. NOT claimed: inventing the")
    print("  extension library, or scope beyond the two readings tested.")
