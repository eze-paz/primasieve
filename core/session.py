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
from .reason import reason, symbols, shape_of, READINGS, PARTIAL, WEAK, NOT_FOUND
from .verdict import ATTRIBUTED, COMMIT, CONJECTURED
from fractions import Fraction


def _same(a, b):
    try: return Fraction(str(a)) == Fraction(str(b))
    except Exception: return str(a).lower() == str(b).lower()


_shape = shape_of


class Session:
    def __init__(self, worlds, df=None, depth=3, ledger=None, deny_words=()):
        self.worlds = list(worlds); self.df = df; self.depth = depth; self.ledger = ledger
        self.history = []            # [(text, frame)]
        self.memory = []             # the chat layer's record of each turn (fields of the realized frame), aligned with history
        self.prefs = {}              # shape -> chosen structure key
        self.teaching = []           # [(question, gold)]
        self.deny_words = set(deny_words)       # chat-layer data: a word that, beside a choice, denies the previous answer
        for w in self.worlds:                   # the transcript world (chat_acts_prereg.md) reads this session's own records
            if getattr(w, "transcript", False): w.session = self

    def remember(self, fields):
        """the chat layer records what it said for the last turn (fields of the realized frame)."""
        while len(self.memory) < len(self.history) - 1: self.memory.append({})
        self.memory.append(dict(fields))

    def _reads(self, syms):
        """does any non-quoting content world read any of these symbols? (the remainder of a choice must be function words)"""
        if not syms: return False
        for w in self.worlds:
            if getattr(w, "quotes", False) or getattr(w, "transcript", False): continue
            if any(r[0] < len(syms) for r in w.readings(syms)): return True
        return False

    # ---- context: the previous turns' values and the readings their answers used ----------------------------
    def context(self):
        """-> items tagged by ROLE: a previous ANSWER ("value") is offered to every world; a reading a previous
        question USED ("used") only to the world that used it (core.reason R0)."""
        out, seen = [], set()
        for text, fr in reversed(self.history[-self.depth:]):
            if fr.get("retracted"): continue                     # a denied turn leaves the context (the cascade, chat_acts_prereg.md)
            for (v, lab, sups, certs, st), w in zip(fr.get("answers", []), fr.get("answer_worlds", [])):
                if getattr(w, "transcript", False) or getattr(w, "quotes", False): continue      # a recall or a quoted gloss is not a value to bind to
                vr = w.value_reading(v) if hasattr(w, "value_reading") else None
                item = (lab, w, vr[0], vr[1], "value") if vr else lab
                if lab not in seen: seen.add(lab); out.append(item)
            for lab, w, kind, payload in fr.get("used", []):
                if lab not in seen: seen.add(lab); out.append((lab, w, kind, payload, "used"))
        return out

    def shapes(self):
        """the shapes of the recent turns' answers: what a turn that supplies only arguments may repeat (core.reason R2)."""
        out = []
        for text, fr in reversed(self.history[-self.depth:]):
            if fr.get("retracted"): continue
            for (v, lab, sups, certs, st), w in zip(fr.get("answers", []), fr.get("answer_worlds", [])):
                if getattr(w, "transcript", False) or getattr(w, "quotes", False): continue
                s = shape_of(w, st)
                if s not in out: out.append(s)
        return out

    def turn(self, text):
        """-> frame dict (core.reason's, plus 'chosen' when a READINGS option was picked)."""
        syms = symbols(text, "LN")
        prev = self.history[-1][1] if self.history else None
        if prev is not None and prev["kind"] == READINGS:
            # a CHOICE: the turn CONTAINS exactly one option's label and every other symbol is read by no content world
            # (W4 required equality; "no, I meant X" and "X please" are the same act -- chat_acts_prereg.md)
            hits = []
            for a in prev["answers"]:
                ls = symbols(str(a[1]), "LN")
                if not ls or not _contains(syms, ls): continue
                rest = [s for s in syms if s not in ls and s not in self.deny_words]
                if not self._reads(rest): hits.append(a)
            if len(hits) == 1:
                v, lab, sups, certs, st = hits[0]
                w = prev["answer_worlds"][prev["answers"].index(hits[0])]
                self.prefs[_shape(w, st)] = True
                fr = dict(prev, kind=prev.get("attributed_kind", COMMIT), answers=[hits[0]], chosen=True)
                fr["used"] = _used(fr, w, st)
                self.history.append((text, fr)); return fr
        recent = frozenset(s for t, _ in self.history[-self.depth:] for s in symbols(t, "LN"))
        fr = reason(text, self.worlds, self.df, cats="LN", context=self.context(), ledger=self.ledger, shapes=self.shapes(), recent=recent)
        if fr["kind"] == READINGS and self.prefs:
            keep = [(a, w) for a, w in zip(fr["answers"], fr["answer_worlds"]) if _shape(w, a[4]) in self.prefs]
            if len(keep) == 1:
                a, w = keep[0]; idx = fr["answers"].index(a)
                srcs = fr.get("answer_sources", [[]])[idx] if idx < len(fr.get("answer_sources", [])) else fr["sources"]
                fr = dict(fr, kind=ATTRIBUTED if getattr(w, "attributed", True) else COMMIT, answers=[a], answer_worlds=[w],
                          answer_sources=[srcs], sources=list(srcs), preferred=True)       # the chosen option's sources, not every option's
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

    def deny(self, question):
        """the denial channel (chat_prereg.md A7): the oracle says the answer to `question` was wrong WITHOUT supplying
        the right one. Every source that spoke on it is recorded as contradicted, with the claim; nothing is
        re-induced (no gold to induce from) and nothing cascades yet (the transcript world, CHAT_PLAN.md phase B)."""
        out = {}
        for t, fr in reversed(self.history):
            if t != question or not fr.get("answers"): continue
            fr["retracted"] = True                   # the cascade: its values and used readings leave the context
            if self.ledger is not None:
                for a, src in zip(fr["answers"], fr.get("answer_sources", [])):
                    self.ledger.record(src, False, claim=(a[1], question))
                out["ledger"] = self.ledger.snapshot()
            break
        return out


def _contains(syms, sub):
    L = len(sub)
    return any(syms[i:i + L] == sub for i in range(len(syms) - L + 1))


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
