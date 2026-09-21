"""REASON -- the one loop under every world (f4_prereg.md Part 1; worlds as a LIST, one pipe step, and context
readings in general_prereg.md W2/W4/W5).

    SEGMENT -> READINGS -> STRUCTURES (affordances) -> SURVIVORS (world-supported) -> PIPE (once) -> RANK -> VERDICT

The loop holds no word of any language, no entity, no operator. A World object supplies:
    readings(syms)                -> [(i, j, kind, payload, label)]      spans and what the world reads them as
    structures(readings)          -> [structure]                         affordances of the reading counts
    evaluate(structure)           -> (value, support, certs) | None      None = the world does not support it
    spans_of(structure)           -> [(i, j)]                            the reading spans the structure uses
    content_kinds                 -> set of reading kinds whose non-use makes the verdict PARTIAL
    weak(structure)               -> (value, support) | None            optional: a weak connection to report
    label(value)                  -> str                                 optional: a printable label
    consulted()                   -> list                                what was looked up (for PROPOSE)
    name                          -> str                                 optional: the provenance label (given from outside)
Several worlds: every world reads the same symbols; each structure is evaluated by the world that afforded it. No
world knows another exists. PIPE: a survivor covering a strict sub-span is substituted (its label's symbols replace
the span) and the loop runs once more over all worlds; a survivor of that pass that uses the substituted region is a
COMPOSITE whose spans map back to the original positions, whose certificates are the union, and whose support lists
both halves. CONTEXT: prior values (a session's previous answers) are offered as VIRTUAL readings at positions past
the end of the text -- each world reads the value's label and the reading is re-positioned there -- so a structure
may take one as an argument at ZERO coverage; an explicit reading always outranks it.
Ranking: coverage (question symbols covered, virtual positions count nothing), then simplicity (fewer spans), then
specificity (lower summed definition-frequency of the first symbol of each span, when a df function is given).
Verdicts: ATTRIBUTED/COMMIT (unique value, or several values from ONE structure = a set), READINGS (several
structures, different values), PARTIAL (a content reading unused by every top survivor), WEAK, NOT_FOUND -- always
with `consulted` = the union of what every world looked up."""
import collections
import unicodedata

from .resolve import segment
from .verdict import ATTRIBUTED, COMMIT

READINGS, PARTIAL, WEAK, NOT_FOUND = "READINGS", "PARTIAL", "WEAK", "NOT FOUND"


def symbols(text, cats="L"):
    return [s.lower() for s in segment(text) if unicodedata.category(s[0])[0] in cats]


class Composite:
    """a structure of one world fed by a survivor of another (or the same) world: (inner, outer) with the map back."""

    def __init__(self, inner, outer, a, b, L):
        self.inner, self.outer, self.a, self.b, self.L = inner, outer, a, b, L      # inner covered [a,b); label length L

    def back(self, i, j):
        """map an outer-pass span to original positions (the label region maps to [a,b))."""
        a, b, L = self.a, self.b, self.L
        def m(p):
            if p < a: return p
            if p < a + L: return None
            return p - L + (b - a)
        lo, hi = m(i), m(j - 1)
        if lo is None and hi is None: return (a, b)
        if lo is None: lo = a
        if hi is None: hi = b - 1
        return (lo, hi + 1)


def _sym_pos(sp, n):
    return len({p for i, j in sp for p in range(i, j) if p < n})        # distinct question positions covered


def _readings(world, syms, context):
    """context items: a label, or (label, world, kind, payload): the world that produced a reading gets it back
    verbatim (no re-search of an ambiguous label); every other world reads the label."""
    rd = list(world.readings(syms)); n = len(syms)
    for k, item in enumerate(context):
        lab, w, kind, payload = (item if isinstance(item, tuple) else (item, None, None, None))
        if w is world and kind is not None:
            rd.append((n + k, n + k + 1, kind, payload, lab, "ctx")); continue
        lsyms = symbols(str(lab), "LN")
        if not lsyms: continue
        for i, j, kind2, payload2, label2 in world.readings(lsyms):
            if i == 0 and j == len(lsyms): rd.append((n + k, n + k + 1, kind2, payload2, label2, "ctx"))    # 6th element = virtual
    return rd


def _pass(syms, worlds, context):
    """one pass over all worlds -> (survivors [(world, st, res)], weaks [(world, st, (v, sup))], readings [(world, r)])"""
    survivors, weaks, readings = [], [], []
    for w in worlds:
        rd = _readings(w, syms, context)
        readings += [(w, r) for r in rd]
        for st in w.structures(rd):
            res = w.evaluate(st)
            if res is not None:
                survivors.append((w, st, res)); continue
            wk = w.weak(st) if hasattr(w, "weak") else None
            if wk: weaks.append((w, st, wk))
    return survivors, weaks, readings


def _spans(w, st):
    if isinstance(st, Composite):
        wi, sti, _ = st.inner; wo, sto, _ = st.outer
        return _spans(wi, sti) + [st.back(i, j) for i, j in _spans(wo, sto)]
    return list(w.spans_of(st))


def _key(w, st):
    if isinstance(st, Composite):
        return ("PIPE", _key(st.inner[0], st.inner[1]), _key(st.outer[0], st.outer[1]))
    return w.key(st) if hasattr(w, "key") else id(st)


def _label(w, v):
    return w.label(v) if hasattr(w, "label") else str(v)


def _attributed(w, st):
    if isinstance(st, Composite):
        return _attributed(st.inner[0], st.inner[1]) or _attributed(st.outer[0], st.outer[1])
    return getattr(w, "attributed", True)


def _rank_key(w, st):
    if isinstance(st, Composite): return _rank_key(st.inner[0], st.inner[1]) + _rank_key(st.outer[0], st.outer[1])
    return w.rank_key(st) if hasattr(w, "rank_key") else 0


def _quotes(w, st):
    if isinstance(st, Composite): return _quotes(st.outer[0], st.outer[1])
    return getattr(w, "quotes", False)


def _names(w, st):
    if isinstance(st, Composite):
        return _names(st.inner[0], st.inner[1]) + _names(st.outer[0], st.outer[1])
    return [getattr(w, "name", type(w).__name__)]


def reason(text, world, df=None, cats="L", context=(), pipe=None):
    """-> Frame dict: kind, answers [(value, label, supports, certs, structure)], missing, weak, readings, consulted,
    sources (the world names of the top survivors), syms."""
    worlds = list(world) if isinstance(world, (list, tuple)) else [world]
    if pipe is None: pipe = len(worlds) > 1          # composition is a several-worlds affair; one world keeps its own chains
    if len(worlds) > 1 and cats == "L": cats = "LN"
    syms = symbols(text, cats); n = len(syms)
    survivors, weaks, readings = _pass(syms, worlds, context)
    if pipe and n > 1:
        for wi, sti, resi in list(survivors):
            if getattr(wi, "quotes", False): continue            # quoted text is not a value to compute with
            if hasattr(wi, "labelled") and not wi.labelled(resi[0]): continue     # a value the world cannot name is not substitutable
            sp = _spans(wi, sti); real = [(i, j) for i, j in sp if i < n]
            if not real: continue
            a, b = min(i for i, _ in real), max(j for _, j in real)
            if b - a >= n: continue
            lab = symbols(_label(wi, resi[0]), "LN")
            if not lab: continue
            syms2 = syms[:a] + lab + syms[b:]
            surv2, _, _ = _pass(syms2, worlds, context)
            for wo, sto, reso in surv2:
                if wo is wi: continue                            # composition is across worlds; a world's own chains are its own
                if getattr(wo, "quotes", False): continue        # a gloss of a computed value is not a composition
                osp = [(i, j) for i, j in wo.spans_of(sto) if i < len(syms2)]
                if not any(i < a or j > a + len(lab) for i, j in osp): continue     # the outer must read something beyond the substituted value
                if not any(i < a + len(lab) and j > a for i, j in wo.spans_of(sto) if i < len(syms2)): continue
                c = Composite((wi, sti, resi), (wo, sto, reso), a, b, len(lab))
                v, supo, certo = reso
                survivors.append((wo, c, (v, [resi[1], supo], set(resi[2]) | set(certo))))
    consulted = []
    for w in worlds:
        if hasattr(w, "consulted"): consulted += list(w.consulted())
    frame = dict(readings=[r for _, r in readings], consulted=consulted, answers=[], missing=[], weak=None, syms=syms, sources=[], answer_worlds=[])
    if not survivors:
        if weaks:
            w, st, (v, sup) = weaks[0]
            frame.update(kind=WEAK, weak=(v, _label(w, v), sup), sources=_names(w, st))
        else:
            frame.update(kind=NOT_FOUND)
        return frame

    def spec(w, st):
        return sum((df(syms[i]) if (df and i < n) else 0) for i, j in _spans(w, st))

    def rank(w, st):
        """coverage; a computed value over a quoted text; fewer explicit spans; specificity; recency of context."""
        sp = _spans(w, st); real = [(i, j) for i, j in sp if i < n]
        own = _rank_key(w, st)                                    # a world's own structural preference
        return (_sym_pos(sp, n), 0 if _quotes(w, st) else 1, -len(real), -spec(w, st), own, -sum(i for i, j in sp if i >= n))

    top = max(rank(w, st) for w, st, _ in survivors)
    best = [(w, st, res) for w, st, res in survivors if rank(w, st) == top]
    used = [span for w, st, _ in best for span in _spans(w, st)]
    unused = [r for w, r in readings if r[0] < n and r[2] in getattr(w, "content_kinds", set())
              and not any(a < r[1] and r[0] < b for a, b in used)]
    values = collections.OrderedDict()
    for w, st, (v, sup, certs) in best:
        values.setdefault(v, []).append((w, st, sup, certs))
    frame["answers"] = [(v, _label(lst[0][0], v), [x[2] for x in lst], set().union(*[set(x[3]) for x in lst]), lst[0][1])
                        for v, lst in values.items()]
    frame["answer_worlds"] = [lst[0][0] for lst in values.values()]          # the world of each answer, aligned
    frame["sources"] = sorted({nm for lst in values.values() for w, st, _, _ in lst for nm in _names(w, st)})
    attributed = any(_attributed(w, st) for lst in values.values() for w, st, _, _ in lst)
    if unused:
        frame.update(kind=PARTIAL, missing=sorted({r[4] for r in unused}))
        return frame
    if len(values) == 1:
        frame.update(kind=ATTRIBUTED if attributed else COMMIT); return frame
    kinds = {_key(w, st) for lst in values.values() for w, st, _, _ in lst}
    if len(kinds) == 1:
        frame.update(kind=ATTRIBUTED if attributed else COMMIT, multi=True); return frame
    frame.update(kind=READINGS)
    return frame
