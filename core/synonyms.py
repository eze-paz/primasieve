"""SYNONYMS -- substitutes in the same slot, and definitions that name each other (synonyms_prereg.md, FLUENCY H5). Zero
LLM; holds no word of any language.

Two arms. DISTRIBUTIONAL: two symbols are substitutes as far as they fill the same two-sided slot (the same left AND right
neighbour) in the text model's counts. DICTIONARY: the statements of sameness a dictionary world holds (given as data:
symbol -> symbols). Combined, the dictionary's statements come first, then two-sided substitutes, then the text model's
single-neighbour similarity. Same interface as the text model for core/rephrase.py: `.uni` and `.similar(w, k)`."""
import collections


class Synonyms:
    def __init__(self, model, same=None, arms=("dictionary", "two-sided", "neighbours")):
        self.model = model; self.uni = model.uni; self.same = same or {}; self.arms = tuple(arms)
        self._slots = None

    def _index(self):
        if self._slots is None:
            self._slots = collections.defaultdict(set); self._fillers = {}
            for key, lst in self.model.both.items():
                self._fillers[key] = [w for w, n in lst]
                for w, n in lst: self._slots[w].add(key)
        return self._slots

    def two_sided(self, w, k=10):
        slots = self._index().get(w, ())
        shared = collections.Counter()
        for key in slots:
            for v in self._fillers[key]:
                if v != w: shared[v] += 1
        return sorted(shared.items(), key=lambda x: (-x[1], x[0]))[:k]

    def similar(self, w, k=10):
        """-> [(symbol, count)] in arm order; the count is the arm's own (0 for a dictionary statement, shared slots, shared
        contexts)"""
        lists = []
        for arm in self.arms:
            # 0: a statement, not a count; commonest first -- a person means a common word more often than a rare one
            if arm == "dictionary": lists.append([(v, 0) for v in sorted(self.same.get(w, ()), key=lambda v: (-self.uni.get(v, 0), v))])
            elif arm == "two-sided": lists.append(self.two_sided(w, k))
            else: lists.append(self.model.similar(w, k))
        # the arms take turns (one candidate each, in arm order): a long list from one arm cannot use up every try
        out, seen = [], {w}
        for rank in range(max((len(l) for l in lists), default=0)):
            for l in lists:
                if rank < len(l) and l[rank][0] not in seen:
                    seen.add(l[rank][0]); out.append(l[rank])
                    if len(out) >= k: return out
        return out
