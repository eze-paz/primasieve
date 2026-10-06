"""CONSTRUCTIONS -- order-aware form-meaning pairs learned from exposure (construct_prereg.md, COMPREHENSION_PLAN.md C1).
Zero LLM; holds no word of any language, no relation, no entity.

An instance is a sentence's run of symbols strictly between two mentions of things a store relates, in order, with the
relation and its direction (forward: the first mention is the subject). A run is a CONSTRUCTION for (relation, direction)
when it was seen in >= `least` instances and >= `share` of its instances carry that (relation, direction). Reading: two
mentions with an admitted run between them -> the proposition, with the run and its counts as the reason."""
import collections

FORWARD, BACKWARD = "forward", "backward"


class Constructions:
    def __init__(self, least=3, share=0.8, max_len=5):
        self.least, self.share, self.max_len = least, share, max_len
        self.seen = collections.defaultdict(collections.Counter)      # run -> Counter((relation, direction))
        self.total = collections.Counter()                            # run -> sentences it was seen between two related mentions
        self.admitted = {}                                            # run -> [((relation, direction), hits, n)]

    @staticmethod
    def schema(run):
        """run 3: numerals are one symbol class; -> the whole run, then its suffixes and prefixes, longest first, each tagged"""
        run = tuple("#" if str(t)[:1].isdigit() else t for t in run)
        head, run = run[:2], run[2:]                       # run 5: the first two items are the slot types
        out = [("=",) + head + run]
        for k in range(len(run) - 1, 0, -1):
            out.append(("<",) + head + run[len(run) - k:]); out.append((">",) + head + run[:k])
        return out

    def observe(self, run, labels):
        """run: tuple of symbols; labels: set of (relation, direction) holding between the two mentions"""
        if len(run) > self.max_len: return
        for key in self.schema(run):              # run 2: every pair a construction joins counts, related or not
            self.total[key] += 1
            for lab in labels: self.seen[key][lab] += 1

    def settle(self):
        self.admitted = {}
        for run, c in self.seen.items():
            n = self.total[run]
            if n < self.least: continue
            keep = [(lab, h, n) for lab, h in c.items() if h >= self.share * n]
            if keep: self.admitted[run] = sorted(keep, key=lambda x: (-x[1], str(x[0])))
        return len(self.admitted)

    def read(self, run):
        """-> [((relation, direction), hits, n)] for the longest admitted schema of the run (whole, then suffixes and
        prefixes), else []"""
        if len(run) > self.max_len: return []
        for key in self.schema(run):
            if key in self.admitted: return self.admitted[key]
        return []

    def relations(self):
        return {lab[0] for lst in self.admitted.values() for lab, h, n in lst}
