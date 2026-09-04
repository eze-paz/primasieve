"""PHASE 2 (SLEEP) -- crystallise operators from L0 instead of selecting from the authored menu.

Drop-in replacement for meta_param.discover_relation (which searched the HAND-AUTHORED 450-relation
frame_grammar). Same contract -- (label, refs, fn) or None, same honesty guards (>=3 traces, referenced
attributes must VARY) -- but the candidate space is L0: signature-deduped BFS over expression trees whose
leaves are site attributes + small consts and whose ops are object-grammar node types.

WHY A VERIFY SPLIT IS NEEDED (the honest finding this phase exposes): the authored menu was not only a
search shortcut, it was a REGULARISER. |L0| frame space at depth 2 is ~1.3e8 vs a 450-item menu, so 3-5
traces massively UNDERDETERMINE the frame and the first signature match is often spurious. So discovery
here is discover-on-train + REJECT-unless-it-holds-on-HELD-OUT-traces. That is sound rejection (the
project's own discipline), not a tuning knob: a frame that fails held-out traces is thrown away, and if
nothing survives we return None (abstain) rather than crystallise a lie."""
from fractions import Fraction as F

ATTRS = ("c", "e")


def _sign(x): return (x > 0) - (x < 0)


def ev(t, c, e):
    """evaluate an L0 tree; None on domain error (matches discover_relation's contract)."""
    if t == "c": return F(c)
    if t == "e": return F(e)
    if isinstance(t, int): return F(t)
    op = t[0]
    if op == "abs":
        v = ev(t[1], c, e); return None if v is None else abs(v)
    if op == "sign":
        v = ev(t[1], c, e); return None if v is None else F(_sign(v))
    if op == "neg":
        v = ev(t[1], c, e); return None if v is None else -v
    a = ev(t[1], c, e); b = ev(t[2], c, e)
    if a is None or b is None: return None
    if op == "+": return a + b
    if op == "-": return a - b
    if op == "*": return a * b
    if op == "//": return None if b == 0 else F(int(a // b))
    if op == "/":  return None if b == 0 else a / b
    return None


def lab(t):
    if isinstance(t, str): return t
    if isinstance(t, int): return str(t)
    if t[0] in ("abs", "sign", "neg"): return f"{t[0]}({lab(t[1])})"
    return f"({lab(t[1])}{t[0]}{lab(t[2])})"


def refs_of(t):
    if t == "c": return {"c"}
    if t == "e": return {"e"}
    if isinstance(t, (int, str)): return set()
    return set().union(*(refs_of(x) for x in t[1:]))


UN = ("abs", "sign", "neg")
BIN = ("+", "-", "*", "//", "/")


def enum_trees(inputs, depth=3, consts=(1, 2, 3), cap=200000):
    """signature-deduped BFS over L0 trees, simplest-first. inputs = [(c,e), ...]. Yields (tree, sig)."""
    seen = set(); order = []

    def sig(t):
        out = []
        for c, e in inputs:
            v = ev(t, c, e)
            out.append("X" if v is None else v)
        return tuple(out)

    def add(t):
        if len(order) >= cap: return False
        s = sig(t)
        if s in seen: return False
        seen.add(s); order.append((t, s)); return True

    for a in ATTRS: add(a)
    for k in consts: add(k)
    start = 0
    for _ in range(depth):
        cur = list(order); newstart = len(order)
        for t, _s in cur[start:]:
            for u in UN: add((u, t))
            if len(order) >= cap: return order
        for t1, _ in cur[start:]:
            if len(order) >= cap: return order
            for t2, _ in cur:
                for b in BIN: add((b, t1, t2))
        start = newstart
        if len(order) >= cap: break
    return order


def _consistent(t, traces, which):
    for (oc, oe), new in traces:
        v = ev(t, oc, oe)
        tgt = new[which]
        if v is None or abs(v - F(tgt)) > F(1, 1000000): return False
    return True


def discover_relation_l0(traces, which, depth=3, cap=200000, verify=None, energy_box=None):
    """L0 replacement for meta_param.discover_relation.
    traces  : [((oc,oe),(nc,ne)), ...] used for SEARCH
    verify  : held-out traces the winning frame MUST also satisfy (sound rejection). If None, the last
              third of `traces` is held out automatically.
    Returns (label, refs, fn) or None. energy_box (list) receives the candidate count."""
    if len(traces) < 3: return None
    if verify is None:
        cut = max(2, (len(traces) * 2) // 3)
        search, held = traces[:cut], traces[cut:]
    else:
        search, held = traces, verify
    inputs = [o for o, _ in search]
    # the varying-attribute guard (unchanged from discover_relation): a referenced attr must take >=2 values
    varies = {a: len({(oc if a == "c" else oe) for (oc, oe), _ in search}) >= 2 for a in ATTRS}
    cands = enum_trees(inputs, depth=depth, cap=cap)
    if energy_box is not None: energy_box.append(len(cands))
    for i, (t, _s) in enumerate(cands):
        if not _consistent(t, search, which): continue
        rs = refs_of(t)
        if any(not varies[a] for a in rs): continue          # coincidence guard
        if held and not _consistent(t, held, which): continue  # SOUND REJECTION on held-out traces
        if energy_box is not None: energy_box[-1] = i + 1
        return (lab(t), rs, _wrap(t))
    return None


def _wrap(t):
    """Return a plain-number callable. ev() works in Fraction for exactness, but consumers write the result
    straight into an ast.Constant (meta_codeparam.CodeStructParam) where a Fraction is not a valid literal,
    so normalise: exact integers -> int, otherwise -> float. Same contract as the authored discover_relation."""
    def fn(c, e):
        v = ev(t, c, e)
        if v is None: return None
        return int(v) if v.denominator == 1 else float(v)
    return fn
