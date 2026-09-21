"""REASON -- the one loop under every world (f4_prereg.md Part 1).

    SEGMENT -> READINGS -> STRUCTURES (affordances) -> SURVIVORS (world-supported) -> RANK -> VERDICT

The loop holds no word of any language, no entity, no operator. A World object supplies:
    readings(syms)                -> [(i, j, kind, payload, label)]      spans and what the world reads them as
    structures(readings)          -> [structure]                         affordances of the reading counts
    evaluate(structure)           -> (value, support, certs) | None      None = the world does not support it
    spans_of(structure)           -> [(i, j)]                            the reading spans the structure uses
    content_kinds                 -> set of reading kinds whose non-use makes the verdict PARTIAL
    weak(structure)               -> (value, support) | None            optional: a weak connection to report
    label(value)                  -> str                                 optional: a printable label
    consulted()                   -> list                                what was looked up (for PROPOSE)
Ranking: coverage (question symbols covered by the structure's spans), then simplicity (fewer spans), then
specificity (lower summed definition-frequency of the first symbol of each span, when a df function is given).
Verdicts: ATTRIBUTED/COMMIT (unique value, or several values from ONE structure = a set), READINGS (several
structures, different values), PARTIAL (a content reading unused by every top survivor), WEAK, NOT_FOUND."""
import collections
import unicodedata

from .resolve import segment
from .verdict import ATTRIBUTED, COMMIT

READINGS, PARTIAL, WEAK, NOT_FOUND = "READINGS", "PARTIAL", "WEAK", "NOT FOUND"


def symbols(text, cats="L"):
    return [s.lower() for s in segment(text) if unicodedata.category(s[0])[0] in cats]


def reason(text, world, df=None, cats="L"):
    """-> Frame dict: kind, answers [(value, label, support, certs, structure)], missing, weak, readings, consulted."""
    syms = symbols(text, cats)
    rd = world.readings(syms)
    survivors, weaks = [], []
    for st in world.structures(rd):
        res = world.evaluate(st)
        if res is not None:
            survivors.append((st, res)); continue
        w = world.weak(st) if hasattr(world, "weak") else None
        if w: weaks.append((st, w))
    consulted = world.consulted() if hasattr(world, "consulted") else []
    frame = dict(readings=rd, consulted=consulted, answers=[], missing=[], weak=None, syms=syms)
    if not survivors:
        if weaks:
            st, (v, sup) = weaks[0]
            frame.update(kind=WEAK, weak=(v, world.label(v) if hasattr(world, "label") else str(v), sup))
        else:
            frame.update(kind=NOT_FOUND)
        return frame

    def spec(st):
        return sum((df(syms[i]) if df else 0) for i, j in world.spans_of(st))

    def rank(st):
        sp = world.spans_of(st)
        return (sum(j - i for i, j in sp), -len(sp), -spec(st))

    top = max(rank(st) for st, _ in survivors)
    best = [(st, res) for st, res in survivors if rank(st) == top]
    used = [span for st, _ in best for span in world.spans_of(st)]
    content = getattr(world, "content_kinds", set())
    unused = [r for r in rd if r[2] in content and not any(a < r[1] and r[0] < b for a, b in used)]
    lab = world.label if hasattr(world, "label") else str
    values = collections.OrderedDict()
    for st, (v, sup, certs) in best:
        values.setdefault(v, []).append((st, sup, certs))
    frame["answers"] = [(v, lab(v), [x[1] for x in lst], set().union(*[set(x[2]) for x in lst]), lst[0][0]) for v, lst in values.items()]
    if unused:
        frame.update(kind=PARTIAL, missing=sorted({r[4] for r in unused}))
        return frame
    if len(values) == 1:
        frame.update(kind=ATTRIBUTED if getattr(world, "attributed", True) else COMMIT); return frame
    kinds = {world.key(st) for lst in values.values() for st, _, _ in lst} if hasattr(world, "key") else {id(st) for lst in values.values() for st, _, _ in lst}
    if len(kinds) == 1:
        frame.update(kind=ATTRIBUTED if getattr(world, "attributed", True) else COMMIT, multi=True); return frame
    frame.update(kind=READINGS)
    return frame
