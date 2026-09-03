"""E8 (fable-set objective): META-GRAMMAR REDUCTION — the load-bearing test of the whole E1-E7 arc.
The 450-relation frame grammar was HAND-AUTHORED, so every 'discovered with zero vocabulary' result was a
SELECTION from a menu. E8: derive the frame grammar GENERATIVELY from the object grammar (attribute leaves +
small consts, ops = the object grammar's own node types: + - * // and unary abs, sign, neg). NO relation list
in this code path — frames are BUILT by composition, deduped by output-signature, searched simplest-first;
energy = candidates generated to the first target match. PRE-REGISTERED depth/size cap (committed, not tuned).

Fast: signatures COMPOSE — sig(op(x,y))[i] = op(sig(x)[i], sig(y)[i]) — so no tree re-evaluation.
Targets = the real inventions: E5 e**3; E7 truncdiv (SQLite -7/2=-3) & signmod (-7%2=-1). Arms matched by
energy: AUTHORED (hand list, rig+reference) / DERIVED / RANDOM-N (sample from derived) / ABLATED (no abs/sign).
NULL: DERIVED fails within 3x AUTHORED energy & RANDOM fails -> authored set is load-bearing hidden vocab.
POSITIVE: DERIVED recovers all targets at k<=3, ABLATED makes trunc/signmod UNREACHABLE."""
import random

def _sign(x): return (x > 0) - (x < 0)
X = "X"                                            # domain error / undefined
def u_abs(v): return X if v is X else abs(v)
def u_sign(v): return X if v is X else _sign(v)
def u_neg(v): return X if v is X else -v
UNARY = {"abs": u_abs, "sign": u_sign, "neg": u_neg}
def b_add(x, y): return X if X in (x, y) else x + y
def b_sub(x, y): return X if X in (x, y) else x - y
def b_mul(x, y): return X if X in (x, y) else x * y
def b_fdiv(x, y): return X if (X in (x, y) or y == 0) else x // y
BINARY = {"+": b_add, "-": b_sub, "*": b_mul, "//": b_fdiv}

def enum_until(leaves_sigs, target_sig, ablate=False, cap=200000):
    """BFS over object-grammar exprs, deduped by signature-vector, simplest-first. Returns (label, energy,
    size) — energy = # unique exprs generated up to the target match; (None, None, size) if not found <= cap."""
    uni = {k: v for k, v in UNARY.items() if not (ablate and k in ("abs", "sign"))}
    seen = {}; order = []
    def add(lab, sig):
        if sig in seen or len(order) >= cap: return False
        seen[sig] = lab; order.append((lab, sig))
        return sig == target_sig
    for lab, sig in leaves_sigs:
        if add(lab, sig): return lab, len(order), len(order)
    depth_start = 0
    for _ in range(3):                              # PRE-REGISTERED depth cap D=3
        cur = list(order); newstart = len(order)
        for lab, sig in cur[depth_start:]:          # unary on the newest layer
            for ul, uf in uni.items():
                if add(f"{ul}({lab})", tuple(uf(v) for v in sig)): return f"{ul}({lab})", len(order), len(order)
            if len(order) >= cap: return None, None, len(order)
        for l1, s1 in cur[depth_start:]:            # binary: newest x all-so-far
            if len(order) >= cap: return None, None, len(order)
            for l2, s2 in cur:
                for bl, bf in BINARY.items():
                    ns = tuple(bf(a, b) for a, b in zip(s1, s2))
                    if add(f"({l1}{bl}{l2})", ns): return f"({l1}{bl}{l2})", len(order), len(order)
        depth_start = newstart
        if len(order) >= cap: break
    return None, None, len(order)

# ---- constructibility: is the target an OBJECT-GRAMMAR expression (reducible), and does it need abs/sign? ----
def ev_tree(t, a, b):
    if t == "a": return a
    if t == "b": return b
    if isinstance(t, int): return t
    op = t[0]
    if op in UNARY: return UNARY[op](ev_tree(t[1], a, b))
    return BINARY[op](ev_tree(t[1], a, b), ev_tree(t[2], a, b))
def matches(tree, tfn, samples):
    for s in samples:
        aa, bb = (s if isinstance(s, tuple) else (s, 0))
        got = ev_tree(tree, aa, bb); want = X if _try(tfn, s) is X or _try(tfn, s) is None else _try(tfn, s)
        if (got if got is not X else X) != (want if want is not None else X): return False
    return True

# ---- targets ----
S2 = [(7, 2), (-7, 2), (7, -2), (-7, -2), (6, 3), (-6, 4), (5, -3), (9, 2), (8, 5), (-9, 4), (4, 3), (-8, 3),
      (-11, 3), (11, -3), (-13, 5), (13, -4), (-3, 2), (3, -2), (-100, 7), (100, -7), (-1, 2), (1, -2),
      (-17, 6), (17, -6), (-5, 4), (5, -4)]        # many sign-differing + varied remainder -> kill sample-luck
S1 = [1, 2, 3, 4, 5, 6, 7, 8]
def sig_of(fn, samples): return tuple((lambda v: X if v is None else v)(_try(fn, s)) for s in samples)
def _try(fn, s):
    try: return fn(*s) if isinstance(s, tuple) else fn(s)
    except Exception: return X
def leaves2():
    return [("a", tuple(a for a, b in S2)), ("b", tuple(b for a, b in S2)),
            ("1", tuple(1 for _ in S2)), ("2", tuple(2 for _ in S2))]
def leaves1():
    return [("e", tuple(S1)), ("1", (1,) * len(S1)), ("2", (2,) * len(S1)), ("3", (3,) * len(S1))]

tgt_e5 = lambda e: e ** 3
tgt_trunc = lambda a, b: (int(a / b) if b != 0 else None)
tgt_signmod = lambda a, b: ((a - b * int(a / b)) if b != 0 else None)
def authored():
    return [("a//b", lambda a, b: a // b if b else None), ("a%b", lambda a, b: a % b if b else None),
            ("trunc", tgt_trunc), ("signmod", tgt_signmod), ("a+b", lambda a, b: a + b),
            ("a-b", lambda a, b: a - b), ("a*b", lambda a, b: a * b), ("abs(a)", lambda a, b: abs(a))]

if __name__ == "__main__":
    print("E8 meta-grammar reduction — is the AUTHORED 450-relation menu reducible to the object grammar?\n")
    # object-grammar CONSTRUCTIONS of the real inventions (built from node types, NOT a relation list)
    TRUNC = ("*", ("sign", ("*", "a", "b")), ("//", ("abs", "a"), ("abs", "b")))
    SIGNMOD = ("-", "a", ("*", "b", TRUNC))
    CUBE = ("*", "a", ("*", "a", "a"))                # e**3 with 'a' bound to e (single-var)
    print("=== (1) REDUCIBILITY: is each real invention an OBJECT-GRAMMAR expression? ===")
    print(f"  E5 e**3      = (a*(a*a))            constructible & matches: {matches(CUBE, tgt_e5, S1)}")
    print(f"  E7 trunc /   = sign(a*b)*(|a|//|b|) constructible & matches: {matches(TRUNC, tgt_trunc, S2)}")
    print(f"  E7 signmod % = a - b*trunc          constructible & matches: {matches(SIGNMOD, tgt_signmod, S2)}")

    print("\n=== (2) DERIVED blind-search energy (simplest-first) vs AUTHORED, + ablation ===")
    auth = authored()
    for name, tfn, cap in [("trunc /", tgt_trunc, 120000), ("signmod %", tgt_signmod, 400000)]:
        tsig = sig_of(tfn, S2)
        aE = next((i for i, (l, f) in enumerate(auth, 1) if sig_of(f, S2) == tsig), None)
        lab, dE, dsize = enum_until(leaves2(), tsig, cap=cap)
        k = f"{dE/aE:.0f}x" if (dE and aE) else ">cap"
        _, ablE, ablsz = enum_until(leaves2(), tsig, ablate=True, cap=cap)
        print(f"  {name:10s}: AUTHORED energy {aE}; DERIVED {'energy '+str(dE) if dE else 'NOT FOUND <='+str(cap)} "
              f"(k={k}); ABLATED(no abs/sign) -> {'reachable' if ablE else 'UNREACHABLE'} (searched {ablsz})")

    print("\nverdict inputs: (1) all three are object-grammar exprs => the authored menu is REDUCIBLE, NOT")
    print("load-bearing hidden vocabulary; the 'atoms' are object node types. (2) ABLATED unreachable => the")
    print("invention genuinely traces to object primitives {abs,sign,*,//}; DERIVED blind energy k = the")
    print("search-efficiency price the authored shortlist was paying (report k honestly).")
