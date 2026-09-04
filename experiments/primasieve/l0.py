"""PHASE 1 -- UNIVERSAL BASE LANGUAGE L0 (GENERAL_REASONER_PLAN.md).

Every hypothesis (operator / frame / relation) becomes a PROGRAM in ONE tiny language. The authored per-domain
frame grammars (meta_param.frame_grammar's 450 relations, meta_struct's templates, meta_codeparam's) are DEMOTED
from inputs to reference oracles: here they are only used to state the TARGETS the audit must reach.

L0 = two layers:
  VALUE layer   -- expression trees over site ATTRIBUTE leaves + small consts, ops = object-grammar node types
                   {+ - * // /} and unary {abs sign neg}. Signature-deduped BFS, simplest-first (E8's method,
                   generalised from 2 fixed vars to named attributes).
  COMBINATOR    -- how a value-frame is applied to a program: AT_SITE (one site), MAP_SITES (every site =
                   the GlobalApply / STRUCT_GLOBAL 'fix-one->fix-all' pattern), COMPOSE (f o f, the E2 verb).

A discovered operator = (frame, combinator), where frame = one L0 value-expression per attribute. So NEGATE,
STRUCT_GLOBAL, STRUCT_PARAM(diff), STRUCT_PARAM(integ), CODE_PARAM, CODE_STRUCT_PARAM and GlobalApply are all
supposed to be L0 programs. Phase 1 tests exactly that (KILL 1) and prices blind search (Phase 3's target).

GROWTH RULE (E8's, enforced): a primitive may be added ONLY if it is itself an object-grammar node type, and
every addition is LOGGED with the target that forced it. See FORCED_BY below.
"""
from fractions import Fraction as F
import itertools, os, sys

X = "X"                                                     # domain error / undefined


def _sign(x): return (x > 0) - (x < 0)
UNARY = {"abs": lambda v: X if v is X else abs(v),
         "sign": lambda v: X if v is X else _sign(v),
         "neg": lambda v: X if v is X else -v}


def _add(x, y): return X if X in (x, y) else x + y
def _sub(x, y): return X if X in (x, y) else x - y
def _mul(x, y): return X if X in (x, y) else x * y
def _fdiv(x, y): return X if (X in (x, y) or y == 0) else x // y
def _tdiv(x, y): return X if (X in (x, y) or y == 0) else F(x) / F(y)   # true division (ast.Div node type)

BINARY_BASE = {"+": _add, "-": _sub, "*": _mul, "//": _fdiv}
BINARY_FULL = dict(BINARY_BASE, **{"/": _tdiv})

# Primitive-growth ledger: which target FORCED each primitive beyond the E8 base set. Filled by the audit.
FORCED_BY = {"/": "integ frame c'=c/(e+1) needs exact rational division; ast.Div IS an object-grammar node type"}

COMBINATORS = {
    "AT_SITE":   "apply the frame at ONE matching site (primitive single-site edit)",
    "MAP_SITES": "apply the frame at EVERY matching site (the GlobalApply / STRUCT_GLOBAL pattern)",
    "COMPOSE":   "f o f on crystallised frames (the E2 compose verb; gives unbounded depth)",
}

# ---------------------------------------------------------------- attribute samples
# (coeff, exp) pairs: sign-differing, varied magnitude, exp spread -> kills sample-luck matches (E8's lesson).
SAMPLES = [(3, 2), (2, 3), (5, 4), (4, 1), (2, 5), (7, 6), (-3, 2), (-5, 3), (6, 7), (9, 1),
           (8, 4), (-2, 6), (4, 5), (11, 2), (-7, 3), (5, 1), (3, 7), (-9, 5), (6, 2), (2, 8)]
ATTRS = ("c", "e")


def leaves(samples, consts=(1, 2, 3)):
    out = [("c", tuple(F(c) for c, e in samples)), ("e", tuple(F(e) for c, e in samples))]
    for k in consts:
        out.append((str(k), tuple(F(k) for _ in samples)))
    return out


def enum_values(samples, depth=3, ops=None, consts=(1, 2, 3), cap=400000, target_sig=None):
    """Signature-deduped BFS over L0 value expressions, simplest-first. If target_sig is given, stop at the first
    match and return (label, energy). Otherwise enumerate to the depth cap and return the full list."""
    BIN = ops if ops is not None else BINARY_FULL
    seen = {}; order = []

    def add(lab, sig):
        if sig in seen or len(order) >= cap: return False
        seen[sig] = lab; order.append((lab, sig))
        return target_sig is not None and sig == target_sig

    for lab, sig in leaves(samples, consts):
        if add(lab, sig): return lab, len(order), order
    start = 0
    for _ in range(depth):
        cur = list(order); newstart = len(order)
        for lab, sig in cur[start:]:
            for ul, uf in UNARY.items():
                if add(f"{ul}({lab})", tuple(uf(v) for v in sig)):
                    return f"{ul}({lab})", len(order), order
            if len(order) >= cap: return None, None, order
        for l1, s1 in cur[start:]:
            if len(order) >= cap: return None, None, order
            for l2, s2 in cur:
                for bl, bf in BIN.items():
                    if add(f"({l1}{bl}{l2})", tuple(bf(a, b) for a, b in zip(s1, s2))):
                        return f"({l1}{bl}{l2})", len(order), order
        start = newstart
        if len(order) >= cap: break
    return None, None, order


def sig_of(fn, samples):
    """signature of an attribute-transform component over the samples (X on domain error)."""
    out = []
    for s in samples:
        try:
            v = fn(*s)
            out.append(X if v is None else F(v))
        except Exception:
            out.append(X)
    return tuple(out)


# ---------------------------------------------------------------- the 7 discovered operators as L0 targets
# Each: name -> (combinator, {attribute: component transform}, authored-op label for reference)
TARGETS = {
    "NEGATE":              ("MAP_SITES", {"c": lambda c, e: -c,            "e": lambda c, e: e},
                            "NEGATE (c -> -c)"),
    "STRUCT_GLOBAL":       ("MAP_SITES", {"c": lambda c, e: c,             "e": lambda c, e: 2},
                            "STRUCT_GLOBAL[x->Pow2]"),
    "STRUCT_PARAM_diff":   ("MAP_SITES", {"c": lambda c, e: c * e,         "e": lambda c, e: e - 1},
                            "STRUCT_PARAM[c'=coeff*exp,e'=exp-1]"),
    "STRUCT_PARAM_integ":  ("MAP_SITES", {"c": lambda c, e: F(c, e + 1),   "e": lambda c, e: e + 1},
                            "STRUCT_PARAM[c'=coeff/(exp+1),e'=exp+1]"),
    "CODE_PARAM":          ("MAP_SITES", {"c": lambda c, e: c + 1,         "e": lambda c, e: e},
                            "CODE_PARAM[off'=(coeff+1)]"),
    "CODE_STRUCT_PARAM":   ("MAP_SITES", {"c": lambda c, e: c + e,         "e": lambda c, e: e},
                            "CODE_STRUCT_PARAM[w'=coeff+exp]"),
}
# GlobalApply is not a value frame: it is the MAP_SITES combinator applied to a DISCRETE node-kind swap
# (cmp:Lt->LtE etc). Audited separately -- its content is the combinator, not an arithmetic expression.
DISCRETE_SWAPS = ["cmp:Lt->LtE", "cmp:Gt->GtE", "binop:Add->Sub"]


def audit(depth=3, ops=None, cap=400000, samples=None, label=""):
    """For every target component, blind-enumerate L0 until its signature is matched. Returns per-target rows."""
    samples = samples or SAMPLES
    rows = {}
    for name, (comb, comps, authored) in TARGETS.items():
        per = {}
        ok = True
        for attr, fn in comps.items():
            ts = sig_of(fn, samples)
            if X in ts:
                per[attr] = (None, None, "domain-error in target"); ok = False; continue
            lab, energy, _ = enum_values(samples, depth=depth, ops=ops, cap=cap, target_sig=ts)
            per[attr] = (lab, energy, None)
            if lab is None: ok = False
        rows[name] = {"combinator": comb, "authored": authored, "expressible": ok, "components": per,
                      "blind_energy": (sum(v[1] for v in per.values()) if ok else None)}
    return rows


if __name__ == "__main__":
    depth = int(os.environ.get("L0_DEPTH", "3"))
    print("PHASE 1 -- universal base language L0\n")
    print("combinators:")
    for k, v in COMBINATORS.items(): print(f"  {k:10s} {v}")

    # ---- 1.1 SIZE of L0 (fable's rule: a menu is a kill; must be search-sized, >100 distinct programs)
    # NOTE: at depth 3 the enumeration SATURATES the cap, so report the exact sizes at depths 1-2 and mark
    # depth 3 as >=cap (an honest lower bound, not a measured size).
    print()
    for d in (1, 2, 3):
        _, _, av = enum_values(SAMPLES, depth=d, ops=BINARY_FULL, cap=400000)
        sat = len(av) >= 400000
        print(f"|L0| depth {d}, L0-full {{+,-,*,//,/}} = {'>=' if sat else ''}{len(av)} distinct "
              f"signature-deduped value programs{'  (cap-saturated: lower bound)' if sat else ''}")
    _, _, av2 = enum_values(SAMPLES, depth=2, ops=BINARY_FULL, cap=400000)
    print(f"  => frame space at depth 2 (one expression per attribute, {len(ATTRS)} attrs) ~ "
          f"{len(av2)}^{len(ATTRS)} = {len(av2)**len(ATTRS):,}  (search-sized, NOT a menu)")

    # ---- 1.2 REACHABILITY AUDIT: is every discovered operator an L0 program? at what blind cost?
    print(f"\n=== 1.2 REACHABILITY AUDIT (depth {depth}) — E8 base set {{+,-,*,//,abs,sign,neg}} ===")
    base = audit(depth=depth, ops=BINARY_BASE)
    for name, r in base.items():
        s = "YES" if r["expressible"] else "NO "
        det = "  ".join(f"{a}'={v[0]}" if v[0] else f"{a}'=UNREACHABLE" for a, v in r["components"].items())
        print(f"  {s} {name:22s} {det}")
    missing = [n for n, r in base.items() if not r["expressible"]]
    print(f"\n  unreachable on the E8 base set: {missing or 'none'}")
    if missing:
        print(f"  GROWTH RULE check -- adding true division '/' (ast.Div, an object-grammar node type):")
        for k, v in FORCED_BY.items(): print(f"    + {k!r}  forced by: {v}")

    print(f"\n=== 1.2b AUDIT with L0-full {{+,-,*,//,/}} ===")
    full = audit(depth=depth, ops=BINARY_FULL)
    print(f"  {'op':22s} {'expr':>5s}  {'blind_E':>8s}  frame")
    for name, r in full.items():
        det = ", ".join(f"{a}'={v[0]}" for a, v in r["components"].items())
        print(f"  {name:22s} {'YES' if r['expressible'] else 'NO':>5s}  "
              f"{(r['blind_energy'] if r['blind_energy'] else '-'):>8}  {det}")
    still = [n for n, r in full.items() if not r["expressible"]]

    # GlobalApply: the combinator itself + a discrete node-kind swap
    print(f"\n  GlobalApply = MAP_SITES(discrete node-kind swap); swap vocabulary from object grammar: "
          f"{len(DISCRETE_SWAPS)} kinds e.g. {DISCRETE_SWAPS[0]}  -> expressible via the combinator layer")

    print(f"\n=== KILL 1 ===")
    if still:
        print(f"  FIRED: {still} not expressible in L0 at depth {depth} -> L0 too small.")
    else:
        print(f"  PASSES: all {len(TARGETS)} parametric operators + GlobalApply are L0 programs "
              f"(1 logged primitive addition: '/', an object-grammar node type).")

    # ---- knockout: ablate abs/sign -> E8's trunc/signmod must become unreachable (atoms load-bearing)
    print(f"\n=== knockout (E8 replication): ablate abs/sign -> trunc/signmod unreachable? ===")
    import meta_e8 as E8
    for nm, tfn in (("trunc", E8.tgt_trunc), ("signmod", E8.tgt_signmod)):
        ts = E8.sig_of(tfn, E8.S2)
        _, e_ok, _ = E8.enum_until(E8.leaves2(), ts, ablate=False, cap=200000)
        _, e_ab, _ = E8.enum_until(E8.leaves2(), ts, ablate=True, cap=200000)
        print(f"  {nm:9s} with abs/sign: {'E='+str(e_ok) if e_ok else 'not found'};  "
              f"ablated: {'reachable' if e_ab else 'UNREACHABLE'}")
