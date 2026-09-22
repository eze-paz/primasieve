"""SESSION -- turns bind (general_prereg.md W4). Zero LLM; holds no word of any language.

A Session holds the worlds, the frames of previous turns, and the bindings the user has confirmed. Each turn runs
core.reason over ALL worlds with CONTEXT = the values and used readings of the previous turns (most recent first),
offered as virtual readings at zero coverage: an explicit reading always outranks them, so "what is its currency"
binds the property to the previous answer only because nothing in the text supplies an entity.

The only cues a Session uses are its own previous frame's values:
  * a turn whose symbols are exactly the label of ONE option of a previous READINGS frame is a CHOICE: that option
    is committed and its SHAPE (the structure key with its explicit readings abstracted, world.shape) is recorded as
    a preference, so the next question of that shape is answered without asking;
  * `teach(question, gold)` is the confirmation channel: it re-induces every world that can learn from
    (question, gold) pairs and retracts what the new example contradicts.
No pronoun list, no speech-act taxonomy, no question-form classifier."""
from .reason import reason, symbols, READINGS, PARTIAL, WEAK, NOT_FOUND
from .verdict import ATTRIBUTED, COMMIT, CONJECTURED
from fractions import Fraction


def _same(a, b):
    try: return Fraction(str(a)) == Fraction(str(b))
    except Exception: return str(a).lower() == str(b).lower()


def _shape(w, st):
    from .reason import Composite
    if isinstance(st, Composite):
        return ("PIPE", _shape(st.inner[0], st.inner[1]), _shape(st.outer[0], st.outer[1]))
    return w.shape(st) if hasattr(w, "shape") else (w.key(st) if hasattr(w, "key") else id(st))


class Session:
    def __init__(self, worlds, df=None, depth=3, ledger=None):
        self.worlds = list(worlds); self.df = df; self.depth = depth; self.ledger = ledger
        self.history = []            # [(text, frame)]
        self.prefs = {}              # shape -> chosen structure key
        self.teaching = []           # [(question, gold)]

    # ---- context: the previous turns' values and the readings their answers used ----------------------------
    def context(self):
        out, seen = [], set()
        for text, fr in reversed(self.history[-self.depth:]):
            for (v, lab, sups, certs, st), w in zip(fr.get("answers", []), fr.get("answer_worlds", [])):
                vr = w.value_reading(v) if hasattr(w, "value_reading") else None
                item = (lab, w, vr[0], vr[1]) if vr else lab
                if lab not in seen: seen.add(lab); out.append(item)
            for lab, w, kind, payload in fr.get("used", []):
                if lab not in seen: seen.add(lab); out.append((lab, w, kind, payload))
        return out

    def turn(self, text):
        """-> frame dict (core.reason's, plus 'chosen' when a READINGS option was picked)."""
        syms = symbols(text, "LN")
        prev = self.history[-1][1] if self.history else None
        if prev is not None and prev["kind"] == READINGS:
            hits = [a for a in prev["answers"] if symbols(str(a[1]), "LN") == syms]
            if len(hits) == 1:
                v, lab, sups, certs, st = hits[0]
                w = prev["answer_worlds"][prev["answers"].index(hits[0])]
                self.prefs[_shape(w, st)] = True
                fr = dict(prev, kind=prev.get("attributed_kind", COMMIT), answers=[hits[0]], chosen=True)
                fr["used"] = _used(fr, w, st)
                self.history.append((text, fr)); return fr
        fr = reason(text, self.worlds, self.df, cats="LN", context=self.context(), ledger=self.ledger)
        if fr["kind"] == READINGS and self.prefs:
            keep = [(a, w) for a, w in zip(fr["answers"], fr["answer_worlds"]) if _shape(w, a[4]) in self.prefs]
            if len(keep) == 1:
                a, w = keep[0]
                fr = dict(fr, kind=ATTRIBUTED if getattr(w, "attributed", True) else COMMIT, answers=[a], answer_worlds=[w], preferred=True)
        fr["attributed_kind"] = ATTRIBUTED if any(getattr(w, "attributed", True) for w in fr["answer_worlds"]) else COMMIT
        fr["used"] = _used(fr, fr["answer_worlds"][0], fr["answers"][0][4]) if fr["answers"] else []
        self.history.append((text, fr))
        return fr

    def teach(self, question, gold, world=None):
        """the confirmation channel: (question, confirmed answer) -> the world named (or every world that learns)
        re-induces from all its pairs; a binding the new pair contradicts is retracted by the world itself."""
        self.teaching.append((question, gold, world)); out = {}
        if self.ledger is not None:                     # the oracle writes the record of every source that spoke on this question
            for t, fr in reversed(self.history):
                if t != question or not fr.get("answers"): continue
                for a, src in zip(fr["answers"], fr.get("answer_sources", [])):
                    ok = _same(a[1], gold)
                    self.ledger.record(src, ok, claim=None if ok else (a[1], question))
                out["ledger"] = self.ledger.snapshot(); break
        for w in self.worlds:
            if not hasattr(w, "induce_lexicon"): continue
            pairs = [(q, g) for q, g, ww in self.teaching if ww is None or ww is w]
            if world is None or world is w: out[getattr(w, "name", "?")] = w.induce_lexicon(pairs)
        return out


def _used(fr, w, st):
    """the explicit readings the top structure used, as (label, world, kind, payload): context for the next turn."""
    from .reason import _spans, Composite
    n = len(fr["syms"]); out = []
    if isinstance(st, Composite):
        return _used(fr, st.inner[0], st.inner[1]) + [x for x in _used(fr, st.outer[0], st.outer[1]) if x not in out]
    spans = [(i, j) for i, j in _spans(w, st) if i < n]
    for r in fr["readings"]:
        if len(r) > 5: continue
        if (r[0], r[1]) in spans and hasattr(w, "owns") and w.owns(r):
            item = (" ".join(fr["syms"][r[0]:r[1]]), w, r[2], r[3])
            if item not in out: out.append(item)
    return out
