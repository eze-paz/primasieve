"""GUESSER -- a labelled source that learns mostly-true patterns (guess_prereg.md, GUESS_PLAN.md G1). Zero LLM; holds no
word of any language, no property, no entity.

The engine's knowledge stays certificate-bound. The guesser is the other half: from many entities it learns RULES of the
form "of the n entities that carry cue c and property t, hits have t = v", admits a rule iff n >= support and
hits >= share * n, and guesses (entity, t) from the admitted rules of the entity's cues. Cues are the entity's own
(property, value) claims and three cues of its name, character-level and language-blind (last token, first token, last
three characters). Counts are kept and reported as the guess's REASON; nothing is turned into a probability.

A guess is never a fact: the session gives it as CONJECTURED, only when nothing known answers, and the guesser earns a
record on the ledger (core/ledger.py) from the oracle -- the user's word, or a known fact met later that a prediction
made before it was read is compared with."""
import collections
import json

from .reason import symbols

NAME = "#name"                 # tag of a name cue's property slot: never a property label (labels carry no leading '#')
TEXT = "#text"                 # tag of a text cue (guess_text_prereg.md): a symbol, or two adjacent symbols, of a text


def text_cues(text):
    """a text as pseudo-claims: {TEXT:w: [symbols], TEXT:b: [adjacent pairs]}. No word list: a symbol that names no
    value in 0.9 of its occurrences never makes a rule, so the admission bar is the filter."""
    syms = symbols(str(text or ""), "LN")
    return {TEXT + ":w": sorted(set(syms)), TEXT + ":b": sorted({a + " " + b for a, b in zip(syms, syms[1:])})}


def name_cues(label):
    syms = symbols(str(label or ""), "LN")
    out = set()
    if syms: out.add((NAME + ":last", syms[-1])); out.add((NAME + ":first", syms[0]))
    low = str(label or "").lower()
    if len(low) >= 4: out.add((NAME + ":end", low[-3:]))
    return out


def cues(label, claims, skip=(), max_values=8):
    """-> set of (property, value) cues; properties in `skip` (the target) are left out."""
    out = {(p, str(v).lower()) for p, vs in claims.items() if p not in skip
           for v in (vs if str(p).startswith(TEXT) else list(vs)[:max_values])}
    return out | name_cues(label)


class Guesser:
    name = "guesser"
    quotes = False

    def __init__(self, targets, support=5, share=0.9):
        self.targets = list(targets); self.support = support; self.share = share
        self.rules = {t: {} for t in self.targets}          # t -> {cue: [(value, hits, n), ...]} admitted only
        self.display = {}                                    # value (case-blind) -> its spelling as first seen
        self.labels = {}                                     # id -> label, injected by the caller (a store's label table)

    # ---- learning: two passes, so that a cue seen fewer than `support` times never takes memory ----------------------
    def learn(self, entities):
        """entities: a re-iterable of (label, {property: [values]}). Values compared case-blind."""
        freq = collections.Counter()
        for label, claims in entities:
            freq.update(cues(label, claims))
        keep = {c for c, k in freq.items() if k >= self.support}
        for t in self.targets:
            n = collections.Counter(); hit = collections.Counter()
            for label, claims in entities:
                vals = {str(v).lower() for v in claims.get(t, [])}
                if not vals: continue
                for v in claims.get(t, []): self.display.setdefault(str(v).lower(), str(v))
                cs = cues(label, claims, skip=(t,)) & keep
                n.update(cs)
                for c in cs:
                    for v in vals: hit[(c, v)] += 1
            rules = collections.defaultdict(list)
            for (c, v), h in hit.items():
                if n[c] >= self.support and h >= self.share * n[c]:
                    rules[c].append((v, h, n[c]))
            self.rules[t] = dict(rules)
        return {t: len(r) for t, r in self.rules.items()}

    # ---- guessing ---------------------------------------------------------------------------------------------------
    def guess(self, label, claims, target):
        """-> [(value, reason)] most-supported first; reason = (cue, hits, n). [] when no admitted rule applies.
        One element = one value all admitted rules agree on; several = admitted rules disagree (every value offered)."""
        rules = self.rules.get(target, {})
        best = {}
        for c in cues(label, claims, skip=(target,)):
            for v, h, n in rules.get(c, []):
                if v not in best or h > best[v][1]: best[v] = (c, h, n)
        return sorted(((v, r) for v, r in best.items()), key=lambda x: (-x[1][1], x[0]))

    # ---- persistence: only the admitted rules -----------------------------------------------------------------------
    def save(self, path):
        data = dict(targets=self.targets, support=self.support, share=self.share, display=self.display,
                    rules={t: [[list(c), [list(x) for x in lst]] for c, lst in r.items()] for t, r in self.rules.items()})
        with open(path, "w", encoding="utf-8") as fh: json.dump(data, fh, ensure_ascii=False)

    @classmethod
    def load(cls, path):
        d = json.load(open(path, encoding="utf-8"))
        g = cls(d["targets"], d["support"], d["share"])
        g.rules = {t: {tuple(c): [tuple(x) for x in lst] for c, lst in r} for t, r in d["rules"].items()}
        g.display = d.get("display", {})
        return g

    def spell(self, v): return self.display.get(v, v)

    # ---- an entity held by a world, in label form ---------------------------------------------------------------------
    def label_of(self, source, x):
        """an id's label: the injected table first; the source's own label only when the source never goes online
        (a guess must not cost a network call per value)"""
        if x in self.labels: return self.labels[x]
        if getattr(source, "offline", True) and hasattr(source, "label"):
            try: return source.label(x)
            except Exception: return x
        return x

    def claims_of(self, source, q, max_values=8):
        try: cl = source.claims(q)
        except Exception: return {}
        return {str(self.label_of(source, p)): [str(self.label_of(source, v)) for v in list(vs)[:max_values]] for p, vs in cl.items()}
