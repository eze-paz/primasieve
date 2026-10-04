"""TEXTMODEL -- a counting model of text (textmodel_prereg.md, GUESS_PLAN.md G4). Zero LLM; holds no word of any
language; stdlib only.

It counts, over a corpus of sentences: how often each symbol occurs, which symbol follows which, and which symbol stands
between which two. Nothing is smoothed and nothing becomes a probability. Two uses:
  FILL     a blank between a left and a right symbol: the most specific context ever seen decides (both sides, then the
           left, then the right, then the commonest symbol); within it, more counts first. The reason is the context and
           its count.
  SIMILAR  two symbols are as alike as the number of their characteristic contexts (left/right neighbours) they share.
           A context seen with very many distinct symbols is uninformative and dropped -- by its spread, a count.
Symbols seen fewer than `min_count` times are one token, RARE."""
import collections
import json

from .reason import symbols

RARE = "\x00"            # the one token for every rare symbol (never a symbol: symbols are letters and digits)
EDGE = "\x01"            # the sentence edge, as a neighbour


class TextModel:
    def __init__(self, min_count=3, keep=5, contexts=50, spread_cut=0.01):
        self.min_count, self.keep, self.n_ctx, self.spread_cut = min_count, keep, contexts, spread_cut
        self.uni = collections.Counter()
        self.both = {}; self.left = {}; self.right = {}          # context -> [(symbol, count)] best `keep`
        self.ctx = {}                                            # symbol -> [(context, count)] characteristic contexts
        self.index = collections.defaultdict(set)                # context -> symbols that keep it

    # ---- learning --------------------------------------------------------------------------------------------------
    def learn(self, sentences):
        """sentences: a re-iterable of texts (two passes: the vocabulary first)."""
        for s in sentences: self.uni.update(symbols(s, "LN"))
        vocab = {w for w, c in self.uni.items() if c >= self.min_count}
        self.uni = collections.Counter({w: c for w, c in self.uni.items() if w in vocab})
        ids = {w: i for i, w in enumerate(sorted(vocab) + [RARE, EDGE])}; words = sorted(vocab) + [RARE, EDGE]
        V = len(words); tri = collections.Counter(); bi = collections.Counter()
        for s in sentences:
            seq = [ids[EDGE]] + [ids.get(w, ids[RARE]) for w in symbols(s, "LN")] + [ids[EDGE]]
            for a, b in zip(seq, seq[1:]): bi[a * V + b] += 1
            for a, b, c in zip(seq, seq[1:], seq[2:]): tri[(a * V + b) * V + c] += 1
        rare, edge = ids[RARE], ids[EDGE]
        both = collections.defaultdict(list)
        for k, n in tri.items():
            if n < 2: continue
            lr, c = divmod(k, V); a, b = divmod(lr, V)
            if b in (rare, edge): continue
            both[(words[a], words[c])].append((words[b], n))
        self.both = {k: sorted(v, key=lambda x: (-x[1], x[0]))[:self.keep] for k, v in both.items()}
        del tri
        left = collections.defaultdict(list); right = collections.defaultdict(list)
        ctx = collections.defaultdict(list); spread = collections.Counter()
        for k, n in bi.items():
            a, b = divmod(k, V); wa, wb = words[a], words[b]
            if b not in (rare, edge): left[wa].append((wb, n)); ctx[wb].append((("L", wa), n)); spread[("L", wa)] += 1
            if a not in (rare, edge): right[wb].append((wa, n)); ctx[wa].append((("R", wb), n)); spread[("R", wb)] += 1
        del bi
        self.left = {k: sorted(v, key=lambda x: (-x[1], x[0]))[:self.keep] for k, v in left.items()}
        self.right = {k: sorted(v, key=lambda x: (-x[1], x[0]))[:self.keep] for k, v in right.items()}
        cut = sorted(spread.values(), reverse=True)[max(0, int(len(spread) * self.spread_cut) - 1)] if spread else 0
        self.ctx = {}
        for w, cs in ctx.items():
            good = sorted((c for c in cs if spread[c[0]] < cut), key=lambda x: (-x[1], x[0]))[:self.n_ctx]
            if good: self.ctx[w] = good
        self.index = collections.defaultdict(set)
        for w, cs in self.ctx.items():
            for c, n in cs: self.index[c].add(w)
        return dict(vocab=len(vocab), both=len(self.both), contexts=len(self.index), spread_cut=cut)

    # ---- fill a blank ------------------------------------------------------------------------------------------------
    def norm(self, w):
        return EDGE if w is None else (w if w in self.uni else RARE)

    def fill(self, left, right, k=5):
        """-> [(symbol, (context kind, context, count))] best first; left/right None at a sentence edge."""
        l, r = self.norm(left), self.norm(right)
        for kind, key, table in (("both", (l, r), self.both), ("left", l, self.left), ("right", r, self.right)):
            got = table.get(key)
            if got: return [(w, (kind, key, n)) for w, n in got[:k]]
        return [(w, ("common", None, n)) for w, n in self.uni.most_common(k)]

    # ---- similar symbols -----------------------------------------------------------------------------------------------
    def similar(self, w, k=10):
        """-> [(symbol, shared contexts)] most shared first (ties by the symbol); [] for a symbol without contexts."""
        mine = [c for c, n in self.ctx.get(w, [])]
        if not mine: return []
        shared = collections.Counter()
        for c in mine:
            for v in self.index.get(c, ()):
                if v != w: shared[v] += 1
        return sorted(shared.items(), key=lambda x: (-x[1], x[0]))[:k]

    # ---- persistence ---------------------------------------------------------------------------------------------------
    def save(self, path):
        enc = lambda d: [[list(k) if isinstance(k, tuple) else k, v] for k, v in d.items()]
        data = dict(params=[self.min_count, self.keep, self.n_ctx, self.spread_cut], uni=dict(self.uni),
                    both=enc(self.both), left=enc(self.left), right=enc(self.right),
                    ctx=[[w, [[list(c), n] for c, n in cs]] for w, cs in self.ctx.items()])
        with open(path, "w", encoding="utf-8") as fh: json.dump(data, fh, ensure_ascii=False)

    @classmethod
    def load(cls, path):
        d = json.load(open(path, encoding="utf-8")); m = cls(*d["params"])
        m.uni = collections.Counter(d["uni"])
        m.both = {tuple(k): [tuple(x) for x in v] for k, v in d["both"]}
        m.left = {k: [tuple(x) for x in v] for k, v in d["left"]}
        m.right = {k: [tuple(x) for x in v] for k, v in d["right"]}
        m.ctx = {w: [(tuple(c), n) for c, n in cs] for w, cs in d["ctx"]}
        for w, cs in m.ctx.items():
            for c, n in cs: m.index[c].add(w)
        return m
