"""STAGE 3 foundation -- COGS logical forms as a HEAD-PASSING representation, plus the faithful serializer.

fable's verdict on Stage 2's engine: it structurally cannot do COGS. SCAN recursion concatenates opaque STRINGS;
COGS recursion emits `prev_head . nmod . prep ( x_prev , x_new )` -- a predicate referencing the HEAD VARIABLE of a
sibling constituent. String combinators (PREPEND/APPEND/REPEAT/CONCAT) cannot reference another constituent's head,
so they are dead at depth 1, not merely at depth 12. Stage 3a therefore needs a different output side: constituents
that export a HEAD, with generic combinators PRIM / EMIT(pred, head_i, head_j) / UNION / HEAD-select.

This module is step 0 of that: parse an LF into (definites, conjuncts) where every argument is either a VARIABLE
(a 0-based token position) or a CONSTANT (a proper noun), and serialize back. Verified round-trip on train:
24012 ok / 0 mismatch / 21 parse-fail / 122 LAMBDA primitive rows.

MEASURED CORRECTION to the received description of the format: conjunct order is NOT simply "sorted by first
argument index" -- only 17889/24012 (74.5%) of training LFs are in that order. The order is DERIVATION-determined,
so a correct engine must get it from the parse, not from a sort. Recorded because an unverified convention would
have silently capped the achievable exact-match score."""
import os, re, sys

DEF = re.compile(r"^\* (.+?) \( x _ (\d+) \)$")
CJ = re.compile(r"^(.+?) \( (.*) \)$")
VARG = re.compile(r"^x _ (\d+)$")

def norm_lf(lf): return " ".join(lf.split())

def parse_lf(lf):
    """-> ('LAMBDA', raw) | None | (definites, conjuncts)
    definites: [(noun, var_index)]   conjuncts: [(predicate, ((kind, value), ...))] kind in {'v','c'}"""
    lf = norm_lf(lf)
    if lf.startswith("LAMBDA"): return ("LAMBDA", lf)
    parts = lf.split(" ; ")
    defs = []; body = parts[-1]
    for part in parts[:-1]:
        m = DEF.match(part.strip())
        if not m: return None
        defs.append((m.group(1), int(m.group(2))))
    conj = []
    if body.strip():
        for c in body.split(" AND "):
            m = CJ.match(c.strip())
            if not m: return None
            args = []
            for a in m.group(2).split(","):
                a = a.strip(); mv = VARG.match(a)
                args.append(("v", int(mv.group(1))) if mv else ("c", a))
            conj.append((m.group(1), tuple(args)))
    return defs, conj

def serialize(defs, conj):
    head = [f"* {n} ( x _ {i} )" for n, i in defs]
    def arg(a): return f"x _ {a[1]}" if a[0] == "v" else a[1]
    body = " AND ".join(f"{p} ( " + " , ".join(arg(a) for a in ar) + " )" for p, ar in conj)
    return (" ; ".join(head) + " ; " + body) if head else body

def alpha_canon_bag(defs, conj):
    """Alpha/order-invariant view: variables renamed by first appearance, conjuncts as a SET (ReCOGS-style)."""
    order = {}
    def rn(a):
        if a[0] == "c": return ("c", a[1])
        if a[1] not in order: order[a[1]] = len(order)
        return ("v", order[a[1]])
    d2 = tuple(sorted((n, rn(("v", i))[1]) for n, i in defs))
    c2 = frozenset((p, tuple(rn(a) for a in ar)) for p, ar in conj)
    return d2, c2

if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(__file__))
    from cogs_data import load
    tr, dev, test, gen = load()
    ok = bad = fail = lam = 0
    for s, lf, c in tr:
        p = parse_lf(lf)
        if p is None: fail += 1; continue
        if p[0] == "LAMBDA": lam += 1; continue
        ok += (serialize(*p) == norm_lf(lf)); bad += (serialize(*p) != norm_lf(lf))
    print(f"round-trip TRAIN: ok {ok} mismatch {bad} parse-fail {fail} LAMBDA {lam} / {len(tr)}")
    def key(c): return tuple(a[1] if a[0] == "v" else -1 for a in c[1])
    same = tot = 0
    for s, lf, c in tr:
        p = parse_lf(lf)
        if p is None or p[0] == "LAMBDA": continue
        tot += 1; same += (p[1] == sorted(p[1], key=key))
    print(f"conjuncts in sorted-by-arg order: {same}/{tot} = {same/tot:.3f}  (so order is DERIVATION-determined)")