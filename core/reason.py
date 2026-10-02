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
from .verdict import ATTRIBUTED, COMMIT, CONJECTURED

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


def shape_of(w, st):
    """the structure with its explicit readings abstracted (a world's own shape(), else its key): what a READINGS
    choice generalizes over (core.session)."""
    if isinstance(st, Composite):
        return ("PIPE", shape_of(st.inner[0], st.inner[1]), shape_of(st.outer[0], st.outer[1]))
    return w.shape(st) if hasattr(w, "shape") else (w.key(st) if hasattr(w, "key") else id(st))


def _readings(world, syms, context):
    """context items: a label, or (label, world, kind, payload[, role]): the world that produced a reading gets it
    back verbatim (no re-search of an ambiguous label); every other world reads the label -- except that a reading
    a previous question USED (role "used") is offered to its owning world only (R0, chat_prereg.md: the previous
    question's column word, re-read by the graph as a property, was borrowed onto an unrelated entity). An answer
    (role "value", or a bare label) is read by every world, as a chain across worlds needs."""
    rd = list(world.readings(syms)); n = len(syms)
    for k, item in enumerate(context):
        lab, w, kind, payload = (item[:4] if isinstance(item, tuple) else (item, None, None, None))
        role = item[4] if isinstance(item, tuple) and len(item) > 4 else "value"
        if w is world and kind is not None:
            rd.append((n + k, n + k + 1, kind, payload, lab, "ctx")); continue
        if role == "used": continue
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
    """the identity of a CLAIM: the structure AND the world that made it. Two sources asserting the same
    structure with different values are two claims in contest, never one multi-valued claim."""
    if isinstance(st, Composite):
        return ("PIPE", _key(st.inner[0], st.inner[1]), _key(st.outer[0], st.outer[1]))
    return (getattr(w, "name", type(w).__name__), w.key(st) if hasattr(w, "key") else id(st))


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


def reason(text, world, df=None, cats="L", context=(), pipe=None, ledger=None, shapes=(), recent=frozenset()):
    """-> Frame dict: kind, answers [(value, label, supports, certs, structure)], missing, weak, readings, consulted,
    sources (the world names of the top survivors), syms."""
    worlds = list(world) if isinstance(world, (list, tuple)) else [world]
    if pipe is None: pipe = len(worlds) > 1          # composition is a several-worlds affair; one world keeps its own chains
    if len(worlds) > 1 and cats == "L": cats = "LN"
    syms = symbols(text, cats); n = len(syms)
    survivors, weaks, readings = _pass(syms, worlds, context)
    # a structure that reads nothing of the TEXT answers nothing of it: context readings alone (two previous values
    # under a previous operator word) built thousands of such survivors per turn, and every one was pipe-expanded
    # (turns prereg: "minus 4" after three turns took 638 s and 5.0 million evaluations; the same pass was re-run
    # for every tree that produced the same label, 721 passes for 2 distinct substitutions)
    recs = [(w, st, res, _spans(w, st)) for w, st, res in survivors]
    recs = [r for r in recs if any(i < n for i, _ in r[3])]
    # context fills what the text leaves OPEN, nothing more: a survivor that reaches into context for a reading of
    # kind K is dropped when the same world has a context-free survivor using an EXPLICIT reading of kind K that the
    # first one does not use (turns prereg T-a: after "capital of france", "what is the capital of japan" answered
    # Japan -- the three-symbol name reading "capital of Japan" plus the previous turn's property word outranked the
    # text's own LOOKUP by coverage; the explicit property word was there and unused)
    kinds_at = collections.defaultdict(set)
    for w, r in readings: kinds_at[(w, r[0], r[1])].add(r[2])
    free = collections.defaultdict(set)                       # world -> {(span, kind)} used by its context-free survivors
    for w, st, res, sp in recs:
        if all(i < n for i, _ in sp):
            for i, j in sp:
                for k in kinds_at[(w, i, j)]: free[w].add((i, j, k))
    def virtual_kinds(w, sp):
        return set().union(*[kinds_at[(w, i, j)] for i, j in sp if i >= n]) if any(i >= n for i, _ in sp) else set()
    def dominated(w, sp):
        vk = virtual_kinds(w, sp)
        if not vk: return False
        mine = set(sp)
        return any((i, j) not in mine and k in vk for i, j, k in free[w])
    recs = [r for r in recs if not dominated(r[0], r[3])]
    # context is ELLIPSIS, never a second question (chat_prereg.md run 1: a 200-turn session of unrelated questions
    # produced 11 confabulations, every one a structure built from context on a text the world could not read).
    #   R1  the text already affords a complete structure of this world covering everything this one reads of the
    #       text -> the context added nothing the text needed (the lowest salary, asked after a question about one
    #       employee: MIN over all salaries stands, MIN over that employee's does not)
    #   R2  context is ELLIPSIS, two halves. (i) A turn that supplies only ARGUMENTS (every explicit reading it uses is
    #       of a kind in which its world reads previous answers: an entity, a filter value, a number) repeats a recent
    #       question with a slot changed, so its structure must have a shape a recent turn had (an employee name after
    #       a salary question; a country after a continent question); a turn that supplies a PREDICATE (an operator, a
    #       column, a property) may take its arguments from context freely (the difference, after two salaries). (ii)
    #       A fragment brings no topic of its own: declared criterion, the loop's specificity bias (E-10) -- no symbol
    #       left unread may be RARER (lower definition frequency; absent everywhere = rarest) than the rarest label
    #       borrowed from context (a museum no world knows, left unread beside a borrowed property) -- and a symbol
    #       that a RECENT turn's own text already contained is not a new topic, whatever its frequency (the question
    #       words recur from turn to turn; the museum does not). (ii) is inactive without df. Withdrawn on the way,
    #       recorded: rarity against the symbols READ (the table ranks a question word rarer than a property word),
    #       and a detector by any world's readings (the offline graph reads common words as entities).
    #   R3  a structure that borrows a context item and returns that very label says nothing (a capital question
    #       asked after a continent question: MEMBER(country, continent) returning the continent)
    role = {n + k: (item[4] if isinstance(item, tuple) and len(item) > 4 else "value") for k, item in enumerate(context)}
    lab_at = {n + k: str(item[0] if isinstance(item, tuple) else item).lower() for k, item in enumerate(context)}
    thing = collections.defaultdict(set)                      # world -> kinds in which it reads previous answers
    for w, r in readings:
        if len(r) > 5 and role.get(r[0]) == "value": thing[w].add(r[2])
    def explicit(sp): return {(i, j) for i, j in sp if i < n}
    def rarity(s): return min((df(t) if df(t) > 0 else -1) for t in (symbols(s, "LN") or [s]))
    free_spans = collections.defaultdict(list)
    for w, st, res, sp in recs:
        if all(i < n for i, _ in sp): free_spans[w].append(explicit(sp))
    def keep(w, st, res, sp):
        virt = [i for i, _ in sp if i >= n]
        if not virt: return True
        ex = explicit(sp)
        if any(fs >= ex for fs in free_spans[w]): return False                                                  # R1
        ow = st.outer[0] if isinstance(st, Composite) else w
        predicate = any(k not in thing[ow] for i, j in ex for k in kinds_at[(ow, i, j)])
        if not predicate and shape_of(w, st) not in shapes: return False                                        # R2 (i)
        if df is not None:                                                                                      # R2 (ii)
            read = {p for i, j in ex for p in range(i, j)}
            unread = [rarity(syms[p]) for p in range(n) if p not in read and syms[p] not in recent]
            if unread and min(unread) < min(rarity(lab_at[i]) for i in virt): return False
        if any(lab_at.get(i) == str(_label(w, res[0])).lower() for i in virt): return False                     # R3
        return True
    recs = [r for r in recs if keep(*r)]
    survivors = [(w, st, res) for w, st, res, _ in recs]
    explicit_kinds = collections.defaultdict(set)              # world -> {(span, kind)} of every explicit reading
    for w, r in readings:
        if r[0] < n: explicit_kinds[w].add((r[0], r[1], r[2]))
    passes = {}
    if pipe and n > 1:
        for wi, sti, resi, sp in list(recs):
            if getattr(wi, "quotes", False): continue            # quoted text is not a value to compute with
            if hasattr(wi, "labelled") and not wi.labelled(resi[0]): continue     # a value the world cannot name is not substitutable
            real = [(i, j) for i, j in sp if i < n]
            if not real: continue
            # an inner that borrowed a kind-K reading from context while an explicit kind-K reading of the text
            # sits unused is not composed further: the text's own reading comes first ("minus 4" with three turns
            # of numbers in context built 216 distinct inner values from context operators over the explicit 4)
            vk = virtual_kinds(wi, sp)
            if vk and any((i, j) not in set(sp) and k in vk for i, j, k in explicit_kinds[wi]): continue
            a, b = min(i for i, _ in real), max(j for _, j in real)
            if b - a >= n: continue
            lab = symbols(_label(wi, resi[0]), "LN")
            if not lab: continue
            syms2 = syms[:a] + lab + syms[b:]
            k2 = tuple(syms2)
            if k2 not in passes: passes[k2] = _pass(syms2, worlds, context)[0]       # one pass per distinct substitution
            surv2 = passes[k2]
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
    frame["answer_sources"] = [sorted({nm for w, st, _, _ in lst for nm in _names(w, st)}) for lst in values.values()]
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
    # a CONTEST between values. An attached world (attributed=False: the user's own data, an executable) is an
    # oracle over quoted claims: its value stands, the quoted claims that differ are contradicted on the ledger.
    quoted = [all(_attributed(w, st) for w, st, _, _ in lst) for lst in values.values()]
    if ledger is not None and quoted.count(False) == 1:
        k = quoted.index(False); keep = list(values)[k]
        for i, (v, lst) in enumerate(values.items()):
            if i != k: ledger.record(frame["answer_sources"][i], False, claim=(_label(lst[0][0], v), text))
        frame["answers"] = [frame["answers"][k]]; frame["answer_worlds"] = [frame["answer_worlds"][k]]
        frame["answer_sources"] = [frame["answer_sources"][k]]; frame["sources"] = frame["answer_sources"][0]
        frame.update(kind=COMMIT, settled_by=frame["answer_sources"][0]); return frame
    if ledger is not None and all(quoted):
        recs = [ledger.of(src) for src in frame["answer_sources"]]
        frame["contest"] = [(a[1], src, rec[1], rec[0]) for a, src, rec in zip(frame["answers"], frame["answer_sources"], recs)]
        b = ledger.better(frame["answer_sources"])
        if b is not None:                       # exactly one option's sources have a strictly better record: a guess with a correction channel
            order = [b] + [i for i in range(len(recs)) if i != b]
            for key in ("answers", "answer_worlds", "answer_sources", "contest"): frame[key] = [frame[key][i] for i in order]
            frame.update(kind=CONJECTURED); return frame
    frame.update(kind=READINGS)
    return frame
