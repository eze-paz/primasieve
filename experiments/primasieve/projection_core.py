"""Domain-AGNOSTIC projection engine (the 'reasoning' from reasoner_interp, with ZERO knowledge
of code). The core knows only generic TERMS and one operation: given an analog term, find the
relational FRAME around an ANCHOR (a marked recurring element) — a binary node one of whose
operands is the anchor, the other a HOLE — then ask the domain to PROJECT that frame onto the
target (fill the hole with the target's own material) and VERIFY.

  core (this file, domain-free):  extract_frames(term) -> [(op, side)] ; solve(domain)
  a Domain adapter supplies:      corpus(), to_terms(analog), build_candidates(op), verify(cand),
                                  render(cand)
Nothing here mentions Python, ASTs, tests, arithmetic, or recursion. Two adapters below
(code + arithmetic) prove the SAME core reasons in unrelated domains.
"""

# ---------------- generic term + the ONLY reasoning primitive ----------------
class Term:
    __slots__ = ("label", "children", "anchor")
    def __init__(self, label=None, children=None, anchor=False):
        self.label = label; self.children = children or []; self.anchor = anchor

def extract_frames(term):
    """Domain-free: find binary nodes with an ANCHOR operand -> (op_label, side, hole_side).
    This is the 'clean repetition' the projection will reuse; op comes from the analog, not
    hardcoded, so the core is blind to + vs * vs concat."""
    out = []
    def walk(t):
        if t.label and t.label.startswith("Bin:") and len(t.children) == 2:
            op = t.label[4:]
            if t.children[0].anchor: out.append((op, "left"))
            if t.children[1].anchor: out.append((op, "right"))
        for c in t.children: walk(c)
    walk(term)
    return list(dict.fromkeys(out))

def common_frame(terms):
    """Anti-unify across MANY analogs -> the frames they SHARE (watch repetition, keep the
    invariant). Intersection of each analog's frame set."""
    sets = [set(extract_frames(t)) for group in terms for t in group]
    if not sets: return set()
    inter = sets[0]
    for s in sets[1:]: inter &= s
    return inter

def solve(domain, verbose=True):
    """Generic: rank analogs, extract their frames, project each onto the target, verify.
    The loop is identical for every domain."""
    for aname, analog in domain.corpus():
        frames = []
        for term in domain.to_terms(analog):
            frames += extract_frames(term)
        for (op, side) in dict.fromkeys(frames):
            for desc, cand in domain.build_candidates(op):
                if domain.verify(cand):
                    if verbose:
                        print(f"    SOLVED via analog '{aname}': frame {op}[{side}] -> {desc}")
                    return domain.render(cand), (aname, op, side, desc)
    return None, None
