"""TEXTWORLD -- a world built from the text being read (textworld_prereg.md, COMPREHENSION_PLAN.md C6). Zero LLM; holds
no word of any language.

Entities are found in the text itself (a symbol capitalised in non-initial positions, repeatedly). As sentences are read,
each entity's PROFILE counts the open-class symbols of the sentences that mention it. A hidden mention is guessed as the
candidate whose profile shares the most with the sentence (each symbol scores its count over the profile's total)."""
import collections


def find_entities(sentences, least=5, closed=()):
    """sentences: lists of raw tokens (case kept) -> set of lower-cased entity symbols (run 2: none of `closed`)"""
    cap = collections.Counter(); low = collections.Counter()
    for toks in sentences:
        for k, t in enumerate(toks):
            if not t[:1].isalpha(): continue
            if t[:1].isupper() and k > 0: cap[t.lower()] += 1
            elif t[:1].islower(): low[t.lower()] += 1
    return {w for w, n in cap.items() if n >= least and n > low[w] and w not in closed}


class TextWorld:
    def __init__(self, entities, closed):
        self.entities = set(entities); self.closed = set(closed)
        self.profile = collections.defaultdict(collections.Counter); self.freq = collections.Counter(); self.recent = []

    def content(self, syms):
        return [s for s in syms if s not in self.closed and s not in self.entities and s[:1].isalpha()]

    def read(self, syms):
        """add one sentence (lower-cased symbols) to the world"""
        ents = [s for s in syms if s in self.entities]
        words = self.content(syms)
        for e in set(ents):
            self.freq[e] += 1; self.profile[e].update(words)
        self.recent.append(set(ents)); self.recent = self.recent[-3:]

    def candidates(self, k=10):
        return [e for e, n in self.freq.most_common(k)]

    def score(self, e, words, profile=None):
        p = (profile or self.profile)[e]; tot = sum(p.values()) or 1
        return sum(p[w] for w in words) / tot

    def guess(self, syms, cands, profile=None):
        """-> (entity, score) for a sentence whose entity mention was removed. Run 2: each symbol is evidence split among
        the candidates by their counts of it (its share of the symbol's occurrences in the candidates' profiles)."""
        P = profile or self.profile; words = self.content(syms); score = collections.Counter()
        for w in words:
            tot = sum(P[e][w] for e in cands)
            if tot: 
                for e in cands: score[e] += P[e][w] / tot
        return max(((e, score[e]) for e in cands), key=lambda x: (x[1], self.freq[x[0]]))
