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
    def __init__(self, worlds, df=None, depth=3, ledger=None, deny_words=(), transfer=False, researcher=None, guesser=None, rephraser=None):
        self.worlds = list(worlds); self.df = df; self.depth = depth; self.ledger = ledger
        self.guesser = guesser       # guess_prereg.md (G1): a labelled source of mostly-true patterns, heard only when nothing known answers
        self.predicted = set()       # (entity, property) whose guess was already checked against a known answer
        self.rephraser = rephraser   # didyoumean_prereg.md (G3): an unread word -> a reading OFFERED, answered only once confirmed
        self.subs = {}               # unread word -> the word the person confirmed it means
        self.declined_subs = set()   # (unread word, offered word) the person refused
        self.transfer = transfer     # transfer_prereg.md (S4): after every teach, words bound in one world are offered to the others by behaviour
        self.researcher = researcher # research_prereg.md: a turn that leaves symbols unread makes the researcher fetch; what comes back is a world
        self.history = []            # [(text, frame)]
        self.memory = []             # the chat layer's record of each turn (fields of the realized frame), aligned with history
        self.prefs = {}              # shape -> chosen structure key
        self.teaching = []           # [(question, gold)]
        self.deny_words = set(deny_words)       # chat-layer data: a word that, beside a choice, denies the previous answer
        self.frames, self.accepted, self.declined = [], [], []     # E-10 question frames and their observations (chat_request_prereg.md)
        if transfer:                              # worlds taught before the session opened have words to offer each other now
            from .transfer import bridge
            self.borrowed_at_start = bridge(self.worlds)
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
                if getattr(w, "transcript", False) or getattr(w, "quotes", False) or getattr(w, "guess", False): continue      # a recall, a quoted gloss or a guess is not a value to bind to
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
                if getattr(w, "transcript", False) or getattr(w, "quotes", False) or getattr(w, "guess", False): continue
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
                fr = dict(prev, kind=prev.get("attributed_kind", COMMIT), answers=[hits[0]], chosen=True,
                          options=list(prev["answers"]), option_sources=list(prev.get("answer_sources", [])), question=self.history[-1][0])
                fr["used"] = _used(fr, w, st)
                self.history.append((text, fr)); return fr
        recent = frozenset(s for t, _ in self.history[-self.depth:] for s in symbols(t, "LN"))
        read_as = []
        if self.subs:                                   # kept substitutions (G3): the turn is read through them, and says so
            from .rephrase import rewrite
            new, read_as = rewrite(syms, self.subs)
            if read_as: text = " ".join(new)
        fr = reason(text, self.worlds, self.df, cats="LN", context=self.context(), ledger=self.ledger, shapes=self.shapes(), recent=recent)
        fr["researched"] = []
        if self.researcher is not None and self.researcher.unread_spans(fr):           # whatever the verdict: an unread name beside a context answer is the confabulation this prevents
            # RESEARCH BY ITSELF (research_prereg.md): the unread spans go to the fetchers; a fetched world joins the session
            # and the same text is read once more over all worlds. Fetched content is readings, never teaching.
            new = self.researcher.research(self, fr)
            if new:
                fr = reason(text, self.worlds, self.df, cats="LN", context=self.context(), ledger=self.ledger, shapes=self.shapes(), recent=recent)
                fr["researched"] = [getattr(w, "name", "?") for w in new]
                if self.transfer:
                    from .transfer import bridge
                    bridge(self.worlds)
        if fr["kind"] == READINGS and self.prefs:
            keep = [(a, w) for a, w in zip(fr["answers"], fr["answer_worlds"]) if _shape(w, a[4]) in self.prefs]
            if len(keep) == 1:
                a, w = keep[0]; idx = fr["answers"].index(a)
                srcs = fr.get("answer_sources", [[]])[idx] if idx < len(fr.get("answer_sources", [])) else fr["sources"]
                fr = dict(fr, kind=ATTRIBUTED if getattr(w, "attributed", True) else COMMIT, answers=[a], answer_worlds=[w],
                          answer_sources=[srcs], sources=list(srcs), preferred=True)       # the chosen option's sources, not every option's
        if self.guesser is not None: fr = self._guess(fr)
        if read_as: fr["read_as"] = read_as
        # G3 (didyoumean_prereg.md): a turn nothing answered -- or, run 2, an answer from computing worlds that left a
        # content word unread (a guess is not offered over) -- may hold a word that, read as one the worlds know,
        # changes the question; then the reading is OFFERED and the direct answer, to another question, is withheld
        if self.rephraser is not None and not read_as and (fr["kind"] not in (COMMIT, ATTRIBUTED, CONJECTURED)
                                                            or (fr["kind"] in (COMMIT, ATTRIBUTED) and not fr.get("guessed"))):
            off = self.rephraser.offer(self, fr, self.declined_subs)
            if off is not None:                         # an OFFER is a reading, never an answer: no value is carried
                from .rephrase import OFFER
                fr = dict(fr, kind=OFFER, offer=off, answers=[], answer_worlds=[], answer_sources=[], sources=[])
        fr["self_confirmed"] = self._self_confirm(text, fr) if not fr.get("guessed") else []
        fr["attributed_kind"] = ATTRIBUTED if any(getattr(w, "attributed", True) for w in fr["answer_worlds"]) else COMMIT
        fr["used"] = _used(fr, fr["answer_worlds"][0], fr["answers"][0][4]) if fr["answers"] else []
        self.history.append((text, fr))
        return fr

    def _self_confirm(self, text, fr):
        """selfconfirm_prereg.md rule B: a guessed route (world B, word w borrowed from world A) to the one top value, beside
        a PLAIN route of a world C that is neither A nor B and whose certificates carry no link to A -> B receives the
        pair through the confirmation channel, as from a person. -> [(B name, word, A name, C name)]; circular -> []."""
        out = []
        if fr.get("kind") not in (COMMIT,) or len(fr.get("answers", [])) != 1 or not fr.get("routes"): return out
        (v, lab, sups, certs, st), = fr["answers"]
        routes = next(iter(fr["routes"].values()))
        plain = [(name, s) for name, cj, pl, s in routes if pl]
        guessed = [(name, s) for name, cj, pl, s in routes if cj]
        if not plain or not guessed: return out
        by_name = {getattr(w, "name", None): w for w in self.worlds}
        for bname, s in guessed:
            B = by_name.get(bname)
            links = {(c[1], c[2]) for c in certs if c[0] == "TRANSFER"}                 # (word, source) of every borrowed word in play
            for word, src in sorted(links):
                if word not in getattr(B, "borrowed", {}) or B.borrowed[word][1] != src: continue
                A = by_name.get(src)
                for cname, cs in plain:
                    C = by_name.get(cname)
                    if C is None or C is A or C is B: continue
                    ccerts = _route_certs(C, cs)
                    if any(c[0] == "TRANSFER" and c[2] == src for c in ccerts): continue       # C's route borrows from A: same origin
                    if any(src in str(c) for c in ccerts if c[0] not in ("EXEC", "TABLE", "TEACH")): continue
                    if hasattr(B, "induce_lexicon"):
                        self.teaching.append((text, v, B)); B.induce_lexicon([(q, g) for q, g, ww in self.teaching if ww is None or ww is B])
                        out.append((bname, word, src, cname))
                    break
        return out

    # ---- the guesser (guess_prereg.md, GUESS_PLAN.md G1) ------------------------------------------------------------------
    def _guess(self, fr):
        """a KNOWN answer of a looked-up property: the guess the guesser would have made without it is compared, once per
        (entity, property), and written on the guesser's record -- a prediction checked, not a vote (the guesser never
        quotes). NOTHING known: a property the guesser has rules for, named in the turn, of an entity a world holds that
        lacks it -> the guess, CONJECTURED, with its reason. Anything else is left as it was."""
        G = self.guesser
        if fr["kind"] in (COMMIT, ATTRIBUTED) and fr.get("answers"):
            w, st = fr["answer_worlds"][0], fr["answers"][0][4]
            try: kind, es, ps = st
            except (TypeError, ValueError): return fr
            if not (hasattr(w, "source") and len(es) == 1 and len(ps) == 1 and ps[0][4] in G.targets): return fr
            q, t = es[0][3], ps[0][4]
            if (q, t) in self.predicted or self.ledger is None: return fr
            cl = {p: v for p, v in G.claims_of(w.source, q).items() if p != t}
            g = G.guess(es[0][4], cl, t)
            if not g: return fr
            self.predicted.add((q, t)); ok = _same(g[0][0], fr["answers"][0][1])
            self.ledger.record([G.name], ok, claim=None if ok else (G.spell(g[0][0]), fr.get("question", " ".join(fr["syms"]))))
            fr["prediction_checked"] = (G.spell(g[0][0]), ok)
            return fr
        if fr["kind"] in (CONJECTURED, READINGS): return fr
        syms = fr["syms"]; pick = None
        for t in sorted(G.targets, key=lambda t: -len(symbols(t, "LN"))):
            ls = symbols(t, "LN"); L = len(ls)
            at = [i for i in range(len(syms) - L + 1) if ls and syms[i:i + L] == ls]
            if not at: continue
            tspan = (at[0], at[0] + L); ents = []
            for r, w in zip(fr.get("readings", []), fr.get("reading_worlds", [])):
                # a name IN the turn (a context reading is the previous topic: a guess about it would answer another question)
                if r[2] != "E" or r[1] > len(syms) or not hasattr(getattr(w, "source", None), "claims") or not (r[1] <= tspan[0] or r[0] >= tspan[1]): continue
                # the name: the span holding the rarest symbol (the graph world's A1: a frequent symbol is not a name), then
                # the longest; without a df, the longest
                rare = min(self.df(x) for x in syms[r[0]:r[1]]) if self.df is not None else 0
                ents.append((rare, -(r[1] - r[0]), len(ents), r, w))
            texts = self._texts(fr, tspan)
            # one rule for the name, whichever world holds it: the span of rarest symbol, then the longest
            if ents and (not texts or min(ents)[:2] <= texts[2]): pick = (t, min(ents)[3], min(ents)[4]); break
            if texts: pick = (t, None, texts[:2]); break
        if pick is None: return fr
        t, r, w = pick
        if r is None:                                          # no world holds the name; only quoted TEXT about it (guess_text_prereg.md)
            span, text = w
            from .guesser import text_cues
            g = G.guess("", text_cues(text), t)
            r = (span[0], span[1], "T", None, " ".join(syms[span[0]:span[1]]))
        else:
            cl = G.claims_of(w.source, r[3])
            if t in cl: return fr                              # the world holds the property: a guess must not stand beside a fact
            g = G.guess(r[4], cl, t)
        if not g: return fr
        gw = _GuessWorld(G.name)
        answers = [(G.spell(v), G.spell(v), [], set(), ("GUESS", r, t)) for v, why in g]
        rec = self.ledger.of([G.name]) if self.ledger is not None else (0, 0)
        return dict(fr, kind=CONJECTURED, answers=answers, answer_worlds=[gw] * len(g), answer_sources=[[G.name]] * len(g),
                    sources=[G.name], via="guess", guessed=[(G.spell(v), why) for v, why in g], guess_target=(r[4], t),
                    contest=[(G.spell(v), [G.name], rec[1], rec[0]) for v, why in g])

    def _texts(self, fr, tspan, k=3):
        """-> ((i, j), text, key) for the turn's span of rarest symbol that only QUOTING worlds read (their values are texts:
        a dictionary's definitions), the first k texts joined; None when no such span"""
        syms = fr["syms"]; n = len(syms); by = {}
        for w in self.worlds:
            if not getattr(w, "quotes", False) or not hasattr(w, "structures"): continue
            try: sts = w.structures(w.readings(syms))
            except Exception: continue
            for st in sts:
                sp = w.spans_of(st)
                if len(sp) != 1 or sp[0][1] > n or not (sp[0][1] <= tspan[0] or sp[0][0] >= tspan[1]): continue
                got = w.evaluate(st)
                if got: by.setdefault(tuple(sp[0]), []).append(str(got[0]))
        if not by: return None
        rare = lambda sp: (min(self.df(x) for x in syms[sp[0]:sp[1]]) if self.df is not None else 0, -(sp[1] - sp[0]), sp[0])
        sp = min(by, key=rare)
        return sp, " ".join(by[sp][:k]), rare(sp)[:2]

    def accept(self, off):
        """the person confirmed an OFFER: the substitution is kept (G3)"""
        self.subs[off["word"]] = off["sub"]

    def decline(self, off):
        self.declined_subs.add((off["word"], off["sub"]))

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
                if fr.get("chosen"):                         # a confirmed CHOICE: the options not chosen were wrong, on their sources' record
                    for a, src in zip(fr.get("options", []), fr.get("option_sources", [])):
                        if not _same(a[1], gold): self.ledger.record(src, False, claim=(a[1], fr.get("question", question)))
                out["ledger"] = self.ledger.snapshot(); break
        for w in self.worlds:
            if not hasattr(w, "induce_lexicon"): continue
            pairs = [(q, g) for q, g, ww in self.teaching if ww is None or ww is w]
            if world is None or world is w: out[getattr(w, "name", "?")] = w.induce_lexicon(pairs)
        if self.transfer:
            from .transfer import bridge
            out["transfer"] = bridge(self.worlds)
        return out

    # ---- the engine's own questions (core/goals.py, goals_prereg.md) ----------------------------------------------------
    def goals(self):
        from .goals import residue
        return residue(self)

    def propose(self, exclude=()):
        """-> (goal, question) for the residue item one answer would settle most, or (None, None). `exclude`: goal keys
        already proposed (a proposal that drew no answer is not repeated; the next goal is offered)."""
        from .goals import residue, next_goal
        g = next_goal([g for g in residue(self) if g.key not in set(exclude)])
        return (g, g.probe) if g is not None else (None, None)

    # ---- persistence (core/store.py, persist_prereg.md): the session's own evidence ---------------------------------
    def evidence(self):
        L = self.ledger
        return dict(research=self.researcher.evidence() if self.researcher is not None else [],
                    teaching=[[q, str(g), getattr(w, "name", None) if w is not None else None] for q, g, w in self.teaching],
                    frames=[dict(f, skeleton=list(f['skeleton']), support=[list(s) for s in f.get('support', [])]) for f in self.frames],
                    accepted=[[list(sy), tp, kd] for sy, tp, kd in self.accepted], declined=[[list(sy), tp, kd] for sy, tp, kd in self.declined],
                    subs=dict(self.subs), declined_subs=[list(x) for x in sorted(self.declined_subs)],
                    ledger=None if L is None else dict(confirmed=dict(L.confirmed), contradicted=dict(L.contradicted),
                                                       retracted=[[s, list(c) if isinstance(c, (list, tuple)) else c] for s, c in L.retracted]))

    def absorb(self, ev):
        if self.researcher is not None and ev.get("research"): self.researcher.absorb(self, ev["research"])      # fetched worlds re-attached first
        by_name = {getattr(w, "name", None): w for w in self.worlds}
        self.teaching = [(q, _num(g), by_name.get(n) if n else None) for q, g, n in ev.get("teaching", [])]
        self.frames = [dict(f, skeleton=tuple(f['skeleton']), support=[tuple(s) for s in f.get('support', [])]) for f in ev.get("frames", [])]
        self.accepted = [(tuple(sy), tp, kd) for sy, tp, kd in ev.get("accepted", [])]
        self.declined = [(tuple(sy), tp, kd) for sy, tp, kd in ev.get("declined", [])]
        self.subs = dict(ev.get("subs", {})); self.declined_subs = {tuple(x) for x in ev.get("declined_subs", [])}
        led = ev.get("ledger")
        if led and self.ledger is not None:
            self.ledger.confirmed.clear(); self.ledger.confirmed.update(led.get("confirmed", {}))
            self.ledger.contradicted.clear(); self.ledger.contradicted.update(led.get("contradicted", {}))
            self.ledger.retracted = [(s, tuple(c) if isinstance(c, list) else c) for s, c in led.get("retracted", [])]
        return dict(teaching=len(self.teaching), frames=len(self.frames), ledger=None if self.ledger is None else self.ledger.snapshot())

    def deny(self, question, negative=True):
        """the denial channel (chat_prereg.md A7): the oracle says the answer to `question` was wrong WITHOUT supplying
        the right one. Every source that spoke on it is recorded as contradicted, with the claim, and the turn leaves
        the context. negative_prereg.md (S6): the engine's own answer is a NEGATIVE EXAMPLE -- every learning world that
        answered it receives (question, that value) through its `deny` and re-induces, so a binding that produced the
        denied value is dropped and re-bound from all the evidence. `negative=False` is the previous behaviour (the
        knockout arm of negative.py)."""
        out = {}
        for t, fr in reversed(self.history):
            if t != question or not fr.get("answers"): continue
            fr["retracted"] = True                   # the cascade: its values and used readings leave the context
            if self.ledger is not None:
                for a, src in zip(fr["answers"], fr.get("answer_sources", [])):
                    self.ledger.record(src, False, claim=(a[1], question))
                out["ledger"] = self.ledger.snapshot()
            if negative:
                for a, w in zip(fr["answers"], fr.get("answer_worlds", [])):
                    if hasattr(w, "deny") and hasattr(w, "induce_lexicon"):
                        w.deny(question, a[0])
                        pairs = [(q, g) for q, g, ww in self.teaching if ww is None or ww is w]
                        out[getattr(w, "name", "?")] = w.induce_lexicon(pairs)
            break
        return out


def _num(s):
    try: return Fraction(str(s))
    except Exception: return s


def _route_certs(w, st):
    """the certificates of one route, a composite's included (selfconfirm_prereg.md: the independence test reads them)"""
    from .reason import Composite
    if isinstance(st, Composite):
        out = set().union(*[_route_certs(wi, sti) for wi, sti, _ in st.inners]) if st.inners else set()
        return out | _route_certs(st.outer[0], st.outer[1])
    r = w.evaluate(st) if hasattr(w, "evaluate") else None
    return set(r[2]) if r else set()


def _contains(syms, sub):
    L = len(sub)
    return any(syms[i:i + L] == sub for i in range(len(syms) - L + 1))


def _used(fr, w, st):
    """the explicit readings the top structure used, as (label, world, kind, payload): context for the next turn."""
    from .reason import _spans, Composite
    n = len(fr["syms"]); out = []
    if isinstance(st, Composite):
        for wi, sti, _ in st.inners:
            out += [x for x in _used(fr, wi, sti) if x not in out]
        return out + [x for x in _used(fr, st.outer[0], st.outer[1]) if x not in out]
    spans = [(i, j) for i, j in _spans(w, st) if i < n]
    worlds_of = fr.get("reading_worlds") or [None] * len(fr["readings"])
    for r, rw in zip(fr["readings"], worlds_of):
        if len(r) > 5: continue
        # the reading must be THIS world's (transfer_prereg.md, run 3: two worlds reading the same span as an operator
        # word, and the other world's operator id was handed back to this one by kind alone)
        if rw is not None and rw is not w: continue
        if (r[0], r[1]) in spans and hasattr(w, "owns") and w.owns(r):
            item = (" ".join(fr["syms"][r[0]:r[1]]), w, r[2], r[3])
            if item not in out: out.append(item)
    return out


class _GuessWorld:
    """the guesser's stand-in as an answer's world: it reads nothing, binds nothing, learns nothing from a pair, and its
    values never enter the context (a guess is not a value to bind the next turn to)."""
    guess = True; quotes = False; attributed = True

    def __init__(self, name): self.name = name

    def spans_of(self, st): return []

    def owns(self, r): return False
