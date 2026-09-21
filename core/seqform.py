"""SEQFORM -- sequential form: word classes induced by the EXCHANGE algorithm under a class-bigram code
(fluency loop it.3, LOOP.md). Pure stdlib. No word of any language, no part-of-speech name.

INDUCTION objective (declared): the maximum-likelihood class-bigram code of the training text,
    f = sum_{c,c'} g(N(c,c')) - sum_c g(N_left(c)) - sum_c g(N_right(c)),   g(x) = x log2 x,
which is the standard exchange criterion; the word-emission term is constant under a fixed class map and drops.
Each word moves to the class that raises f most; passes until no move or the budget ends.

EVALUATION code, per sentence (add-one smoothed, boundary class at both ends):
    log2(Lmax) + sum_i [ -log2 P(c_i | c_{i-1}) - log2 P(w_i | c_i) ]
K=1 is exactly the unigram code and K=V exactly the word bigram: the two baselines are the two ends of this
family, so a gain over BOTH at some K is generalization, not a change of alphabet.

Verdicts: all words known -> COMMIT (class sequence determined); an unknown word -> CONJECTURED (class by max
P(c|prev)P(next|c), the choice paid at log2 K). No probabilities leave the module."""
import collections
import math
import time

from .verdict import COMMIT, ABSTAIN, CONJECTURED

B = -1     # boundary class


def _g(x): return x * math.log2(x) if x > 0 else 0.0


class ClassBigram:
    def __init__(self, train, K):
        self.train = [tuple(s) for s in train]
        self.N = len(self.train)
        self.lmax = max(len(s) for s in self.train)
        self.wc = collections.Counter(w for s in self.train for w in s)
        self.vocab = [w for w, _ in self.wc.most_common()]
        self.V = len(self.vocab)
        self.K = min(K, self.V)
        self.cls = {w: i % self.K for i, w in enumerate(self.vocab)}      # init: frequency rank mod K (declared)
        # word-keyed neighbour counters (fixed) and class-keyed ones (maintained under moves)
        self.wl = collections.defaultdict(collections.Counter)   # w -> Counter(left WORD or B)
        self.wr = collections.defaultdict(collections.Counter)
        for s in self.train:
            for i, w in enumerate(s):
                self.wl[w][s[i - 1] if i > 0 else B] += 1
                self.wr[w][s[i + 1] if i + 1 < len(s) else B] += 1
        self._rebuild()
        tot = sum(self.wc.values())
        self.uni = {w: -math.log2((self.wc[w] + 1) / (tot + self.V + 1)) for w in self.vocab}
        self.uni_unk = -math.log2(1 / (tot + self.V + 1))
        self.wb = collections.Counter(); self.wbl = collections.Counter()
        for s in self.train:
            prev = B
            for w in s + (B,):
                self.wb[(prev, w)] += 1; self.wbl[prev] += 1; prev = w

    def _c(self, x): return B if x == B else self.cls[x]

    def _rebuild(self):
        self.cb = collections.Counter(); self.nl = collections.Counter(); self.nr = collections.Counter()
        self.cn = collections.Counter()
        for s in self.train:
            prev = B
            for w in s:
                c = self.cls[w]; self.cb[(prev, c)] += 1; self.nl[prev] += 1; self.nr[c] += 1; self.cn[c] += 1; prev = c
            self.cb[(prev, B)] += 1; self.nl[prev] += 1; self.nr[B] += 1
        self.members = collections.defaultdict(set)
        for w, c in self.cls.items(): self.members[c].add(w)
        self.cl_left = {w: collections.Counter() for w in self.vocab}     # w -> Counter(class of left neighbour)
        self.cl_right = {w: collections.Counter() for w in self.vocab}
        for w in self.vocab:
            for x, k in self.wl[w].items(): self.cl_left[w][self._c(x)] += k
            for x, k in self.wr[w].items(): self.cl_right[w][self._c(x)] += k

    # ---- exchange
    def _delta(self, w, a, b):
        """exact change in f when w moves from class a to b (O(distinct neighbour classes of w))."""
        L, R, n = self.cl_left[w], self.cl_right[w], self.wc[w]
        sw = self.wl[w].get(w, 0)                          # w immediately followed by w
        d = collections.Counter()
        for x, k in L.items():
            if x == a: k -= sw
            if k: d[(x, a)] -= k; d[(x, b)] += k
        for y, k in R.items():
            if y == a: k -= sw
            if k: d[(a, y)] -= k; d[(b, y)] += k
        if sw: d[(a, a)] -= sw; d[(b, b)] += sw
        df = 0.0
        for pair, k in d.items():
            if k: old = self.cb[pair]; df += _g(old + k) - _g(old)
        for c, k in ((a, -n), (b, n)):
            df -= _g(self.nl[c] + k) - _g(self.nl[c]) + _g(self.nr[c] + k) - _g(self.nr[c])
        return df

    def _move(self, w, a, b):
        L, R, n = self.cl_left[w], self.cl_right[w], self.wc[w]
        sw = self.wl[w].get(w, 0)
        for x, k in L.items():
            if x == a: k -= sw
            if k: self.cb[(x, a)] -= k; self.cb[(x, b)] += k
        for y, k in R.items():
            if y == a: k -= sw
            if k: self.cb[(a, y)] -= k; self.cb[(b, y)] += k
        if sw: self.cb[(a, a)] -= sw; self.cb[(b, b)] += sw
        self.nl[a] -= n; self.nl[b] += n; self.nr[a] -= n; self.nr[b] += n; self.cn[a] -= n; self.cn[b] += n
        self.cls[w] = b; self.members[a].discard(w); self.members[b].add(w)
        for x, k in self.wl[w].items():                    # words to the LEFT of w see their right-class change
            if x != B: self.cl_right[x][a] -= k; self.cl_right[x][b] += k
        for x, k in self.wr[w].items():
            if x != B: self.cl_left[x][a] -= k; self.cl_left[x][b] += k

    def exchange(self, budget_s, passes=12, min_count=2, log=None):
        t0 = time.time(); total = 0
        words = [w for w in self.vocab if self.wc[w] >= min_count]
        rare = [w for w in self.vocab if self.wc[w] < min_count]
        spent = False
        for p in range(passes):
            moves = 0
            for w in words:
                if time.time() - t0 > budget_s: spent = True; break
                a = self.cls[w]; best = (1e-9, a)
                for b in range(self.K):
                    if b != a:
                        d = self._delta(w, a, b)
                        if d > best[0]: best = (d, b)
                if best[1] != a: self._move(w, a, best[1]); moves += 1
            total += moves
            if log: log(f"    exchange pass {p}: {moves} moves of {len(words)} words   [{time.time()-t0:.0f}s]")
            if moves == 0 or spent: break
        for w in rare:                                      # one assignment each, not exchanged (declared cap)
            if time.time() - t0 > budget_s * 1.25: spent = True; break
            a = self.cls[w]; best = (1e-9, a)
            for b in range(self.K):
                if b != a:
                    d = self._delta(w, a, b)
                    if d > best[0]: best = (d, b)
            if best[1] != a: self._move(w, a, best[1]); total += 1
        return dict(moves=total, spent=spent, secs=time.time() - t0, exchanged=len(words), rare=len(rare))

    # ---- evaluation code
    def p_cc(self, a, b): return (self.cb[(a, b)] + 1) / (self.nl[a] + self.K + 1)

    def p_wc(self, w, c): return (self.wc[w] + 1) / (self.cn[c] + len(self.members[c]))

    def sentence(self, s, conjecture=True):
        s = tuple(s)
        unknown = [i for i, w in enumerate(s) if w not in self.cls]
        if unknown and not conjecture: return 1 + self.unigram(s), None
        classes = [self.cls.get(w) for w in s]
        state = COMMIT
        if unknown:
            state = CONJECTURED
            for i in unknown:
                prev = B if i == 0 else classes[i - 1]
                nxt = B if i + 1 == len(s) else classes[i + 1]
                if prev is None: prev = B
                best = None
                for c in range(self.K):
                    sc = math.log2(self.p_cc(prev, c)) + (math.log2(self.p_cc(c, nxt)) if nxt is not None else 0.0)
                    if best is None or sc > best[0]: best = (sc, c)
                classes[i] = best[1]
        bits = math.log2(self.lmax) + len(unknown) * math.log2(self.K)
        prev = B
        for i, w in enumerate(s):
            c = classes[i]
            bits -= math.log2(self.p_cc(prev, c))
            bits += self.uni_unk if w not in self.cls else -math.log2(self.p_wc(w, c))
            prev = c
        bits -= math.log2(self.p_cc(prev, B))
        return bits, state

    def unigram(self, s): return sum(self.uni.get(w, self.uni_unk) for w in s) + math.log2(self.lmax)

    def wordbigram(self, s):
        bits = math.log2(self.lmax); prev = B
        for w in tuple(s) + (B,):
            if w != B and w not in self.wc:
                bits += self.uni_unk; prev = B; continue
            bits -= math.log2((self.wb[(prev, w)] + 1) / (self.wbl[prev] + self.V + 1)); prev = w
        return bits


# ================================================================ it.4: zero-bit OOV class by induced suffix signature
class SuffixTable:
    """suffix (length 1..4, attested on >= min_types distinct train word types) -> class counts over those types.
    Read off the induced class map; nothing authored. `shuffle` permutes the tables across suffixes (I4-d)."""

    def __init__(self, m, min_types=5, shuffle=None):
        tab = collections.defaultdict(collections.Counter)
        for w, c in m.cls.items():
            for L in range(1, 5):
                if len(w) > L: tab[w[-L:]][c] += 1
        self.tab = {sfx: cnt for sfx, cnt in tab.items() if sum(cnt.values()) >= min_types}
        if shuffle is not None:
            keys = list(self.tab); vals = [self.tab[k] for k in keys]; shuffle.shuffle(vals)
            self.tab = dict(zip(keys, vals))
        self.K = m.K

    def longest(self, w):
        for L in (4, 3, 2, 1):
            if len(w) > L and w[-L:] in self.tab: return self.tab[w[-L:]]
        return None


def sentence_oov(m, s, table=None, use_suffix=True):
    """class-bigram code with a DETERMINISTIC zero-bit class for unknown words:
    argmax_c P(c | longest attested suffix) * P(c | prev class), or P(c | prev) alone without a suffix / table.
    -> (bits, state); state CONJECTURED when any word is unknown."""
    s = tuple(s)
    classes = [m.cls.get(w) for w in s]
    unknown = [i for i, w in enumerate(s) if classes[i] is None]
    prev = B; bits = math.log2(m.lmax)
    for i, w in enumerate(s):
        c = classes[i]
        if c is None:
            cnt = table.longest(w) if (table is not None and use_suffix) else None
            best = None
            for k in range(m.K):
                sc = math.log2(m.p_cc(prev, k))
                if cnt is not None: sc += math.log2((cnt[k] + 1) / (sum(cnt.values()) + m.K))
                if best is None or sc > best[0]: best = (sc, k)
            c = best[1]; classes[i] = c
        bits -= math.log2(m.p_cc(prev, c))
        bits += m.uni_unk if w not in m.cls else -math.log2(m.p_wc(w, c))
        prev = c
    bits -= math.log2(m.p_cc(prev, B))
    return bits, (CONJECTURED if unknown else COMMIT)


# ================================================================ it.5: checkpointed class maps (resumable build)
def save_classes(m, path):
    import json
    json.dump({"K": m.K, "cls": m.cls}, open(path, "w", encoding="utf-8"))


def load_classes(m, path):
    """install a saved class map into a ClassBigram built on the SAME train (vocabulary must match)."""
    import json, os
    if not os.path.exists(path): return False
    d = json.load(open(path, encoding="utf-8"))
    if d["K"] != m.K or set(d["cls"]) != set(m.cls): return False
    m.cls = {w: int(c) for w, c in d["cls"].items()}
    m._rebuild()
    return True


# ================================================================ it.6: learned UNK symbol + Witten-Bell transitions
UNK = "\x00unk"      # a symbol no corpus word can equal (contains a control character)


def unkify(train, min_count=2):
    """collapse every word with corpus count < min_count into UNK. -> (train', vocabulary set of kept words,
    number of rare TYPES collapsed). The same map must be applied to held-out text (unseen words -> UNK)."""
    wc = collections.Counter(w for s in train for w in s)
    keep = {w for w, n in wc.items() if n >= min_count}
    out = [[w if w in keep else UNK for w in s] for s in train]
    return out, keep, len(wc) - len(keep)


def apply_unk(sents, keep): return [[w if w in keep else UNK for w in s] for s in sents]


class ClassBigramWB(ClassBigram):
    """ClassBigram with Witten-Bell smoothing on transitions: P(c|a) = (N(a,c) + T(a) * P_bg(c)) / (N(a) + T(a)),
    T(a) = number of distinct classes seen after a, P_bg(c) = (N(c)+1)/(N+K+1). Fillers stay add-one.
    `identity_bits` = the cost of naming which unseen word an UNK token is; paid identically by the unigram baseline."""

    def __init__(self, train, K, identity_bits=0.0):
        super().__init__(train, K)
        self.identity_bits = identity_bits
        self._wb_ready = False

    def _wb_tables(self):
        self.T = collections.Counter()
        for (a, c), n in self.cb.items():
            if n > 0: self.T[a] += 1
        tot = sum(self.nr.values())
        self.bg = {c: (self.nr[c] + 1) / (tot + self.K + 1) for c in list(range(self.K)) + [B]}
        self._wb_ready = True

    def p_cc(self, a, b):
        if not self._wb_ready: self._wb_tables()
        Ta = self.T[a]
        return (self.cb[(a, b)] + Ta * self.bg.get(b, 1 / (self.K + 1))) / (self.nl[a] + Ta) if (self.nl[a] + Ta) > 0 else 1 / (self.K + 1)

    def sentence(self, s, conjecture=True):
        """UNK is an ordinary word here; every UNK token additionally pays identity_bits (as the baseline does)."""
        s = tuple(s)
        bits, state = super().sentence(s, conjecture=True)
        n_unk = sum(1 for w in s if w == UNK)
        return bits + n_unk * self.identity_bits, (CONJECTURED if n_unk else COMMIT)

    def unigram(self, s):
        return super().unigram(s) + sum(1 for w in s if w == UNK) * self.identity_bits
