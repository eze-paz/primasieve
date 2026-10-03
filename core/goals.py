"""GOALS -- the engine's own questions: what would settle most of the residue it holds (goals_prereg.md; S9). Zero LLM;
holds no word of any language: every question it forms is a question the session already saw with one symbol changed,
or a label the worlds supplied.

A GOAL is a survivor set the engine currently holds without being able to shrink it on its own, together with the
PROBE whose answer would shrink it: a contested word (several operators survive the teaching), a word bound by search
with rivals of its size, a word borrowed from another world and held as a conjecture, a READINGS the user never chose,
a symbol no world reads. The probe is chosen by core.collect.best_split -- the candidate question whose answer takes
the most distinct values across the survivors -- and a goal no candidate splits is IRREDUCIBLE: reported, never asked.
The engine OFFERS the question; the answer enters through the session's existing channels (teach, deny, a choice).
Across goals, the next goal is the one with the largest split (what one answer would remove); ties by recency."""
import collections
import re

from .collect import best_split, n_split


class Goal:
    __slots__ = ("kind", "key", "world", "survivors", "probe", "outcome", "split", "candidates")

    def __init__(self, kind, key, world, survivors, candidates, outcome):
        self.kind, self.key, self.world = kind, key, world
        self.survivors = list(survivors); self.candidates = list(candidates); self.outcome = outcome
        self.probe = best_split(self.survivors, self.candidates, outcome) if len(self.survivors) > 1 else None
        self.split = n_split(self.survivors, self.probe, outcome) if self.probe is not None else 1

    def irreducible(self): return len(self.survivors) > 1 and self.probe is None

    def __repr__(self): return f"Goal({self.kind}, {self.key!r}, survivors {len(self.survivors)}, split {self.split}, probe {self.probe!r})"


def _vary(question, old, new):
    """the question with one symbol replaced (the engine's only way to form a new question: an old one, one slot changed)."""
    return re.sub(rf"\b{re.escape(old)}\b", new, question, count=1)


def residue(session):
    """-> [Goal] from the session's worlds and history. Worlds take part through what they already expose."""
    goals = []
    for w in session.worlds:
        name = getattr(w, "name", "?")
        # contested words: the teaching leaves several operators (a table or exec world's `contested`)
        words = w.contested_words() if hasattr(w, "contested_words") else (getattr(w, "contested", ()) or ())
        for word in sorted(words):
            surv = sorted(w.survivors_of(word)) if hasattr(w, "survivors_of") else []
            if len(surv) < 2: continue
            qs = [q for q, g in getattr(w, "pairs", []) if word in q.split()]
            cands = []
            for q in qs:
                for sym in q.split():
                    for alt in w.alternatives(sym) if hasattr(w, "alternatives") else ():
                        cands.append(_vary(q, sym, alt))
            cands = sorted(set(cands))
            # words that always co-occur share one goal: the same question settles them together
            twin = next((g for g in goals if g.kind == "contested" and g.world is w and g.candidates == cands and g.survivors == surv), None)
            if twin is not None: twin.key = twin.key + (word,); continue
            goals.append(Goal("contested", (name, word), w, surv, cands, lambda op, q, w=w, word=word: w.value_with(word, op, q)))
        # borrowed words held as conjectures: the survivors are {the borrowed operator, nothing}; the probe is the question that used it
        for word, entry in sorted(getattr(w, "borrowed", {}).items()):
            # the probe must be a question THIS world answers through the borrowed word: one of its own taught questions
            # with the taught operator word of the same behaviour swapped for the borrowed one (a seen question, one
            # symbol changed); else a question of the session that used the word; else the word itself
            own = []
            for q, g in getattr(w, "pairs", []):
                for x in q.split():
                    if getattr(w, "lexicon", {}).get(x) == entry[0] and x != word: own.append(_vary(q, x, word))
            used = [t for t, fr in session.history if word in t.split() and fr.get("answers")]
            goals.append(Goal("borrowed", (name, word), w, [entry[0], None], (own[-1:] or used[-1:] or [f"{word}"]),
                              lambda h, q: ("value" if h is not None else "nothing")))
    # READINGS the user never chose
    asked = set()
    for k, (text, fr) in enumerate(session.history):
        if fr.get("kind") == "READINGS" and not fr.get("retracted") and not any(f2.get("chosen") for t2, f2 in session.history[k + 1:k + 2]):
            opts = [str(a[1]) for a in fr["answers"]]
            if len(opts) > 1 and text not in asked:                      # one goal per unanswered question, however often it was asked
                asked.add(text); goals.append(Goal("readings", ("readings", text), None, opts, [text], lambda h, q: h))
    # symbols no world read (the dictionary's UNKNOWN reading): one question each, two outcomes (defined / not a word)
    unknown = collections.OrderedDict()
    for text, fr in session.history:
        for r, w in zip(fr.get("readings", []), fr.get("reading_worlds", [])):
            if r[2] == "U": unknown.setdefault(r[4], text)
    for sym, text in unknown.items():
        goals.append(Goal("unknown", sym, None, ["defined", "not-a-word"], [sym], lambda h, q: h))
    return goals


def next_goal(goals, key=None):
    """the goal whose answer removes most (largest split), ties by the order given (most recent last -> last wins);
    None when every goal is irreducible or there is no residue. `key` replaces the split (the knockout arm)."""
    live = [g for g in goals if g.split > 1]
    if not live: return None
    score = key or (lambda g: g.split)
    best = max(score(g) for g in live)
    tied = [g for g in live if score(g) == best]
    # at equal split, a probe the engine can ACT on -- a question of several symbols the session can answer and the user
    # can confirm -- before a bare unknown symbol (together_prereg.md: the first proposal was a stress typo); then recency
    acts = [g for g in tied if g.probe and len(str(g.probe).split()) > 1]
    return (acts or tied)[-1]
