"""LEDGER -- the record of a source (critical_prereg.md W6). Zero LLM; holds no word of any language.

Per source name: COUNTS of certificate outcomes, `confirmed` and `contradicted`, and the claims retracted. Counts,
never probabilities, never a score. An outcome is written only by an ORACLE (the confirmation channel, an attached
data world, an executable primitive); agreement between quoted sources writes nothing. A record belongs to a source
NAME: rename the sources and the verdicts follow the names (the mechanism prefers none)."""
import collections


class Ledger:
    def __init__(self):
        self.confirmed = collections.Counter(); self.contradicted = collections.Counter(); self.retracted = []

    def record(self, sources, ok, claim=None):
        for s in sources:
            if ok: self.confirmed[s] += 1
            else:
                self.contradicted[s] += 1
                if claim is not None: self.retracted.append((s, claim))

    def of(self, sources):
        """-> (contradicted, confirmed) of the option's BEST source. Not a sum: a sum grows with the number of
        agreeing sources, which is a vote in disguise; an option is as credible as its most reliable source."""
        recs = [(self.contradicted[s], self.confirmed[s]) for s in sources] or [(0, 0)]
        return min(recs, key=self.key)

    @staticmethod
    def key(rec):
        """ordering: fewer contradictions first; on a tie, more confirmations. Equal keys = no preference."""
        return (rec[0], -rec[1])

    def better(self, options):
        """options: [sources per option] -> index of the unique strictly better option, or None."""
        keys = [self.key(self.of(src)) for src in options]
        best = min(keys)
        return keys.index(best) if keys.count(best) == 1 else None

    def snapshot(self):
        names = sorted(set(self.confirmed) | set(self.contradicted))
        return {n: (self.confirmed[n], self.contradicted[n]) for n in names}
