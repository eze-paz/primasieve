"""FORM -- word classes and sentence skeletons from RAW TEXT under a two-part MDL code (Stage 9 mechanism).

No logical forms, no paired supervision, no word of any language, no part-of-speech name, no glyph. The module
knows three things (cogs_stage9_prereg.md, "Mechanism"):

  SEGMENT   symbols are maximal runs of one Unicode major category (core.resolve.segment); a SENTENCE ends
            after a punctuation-category symbol when the next letter symbol starts upper-case (category Lu).
            That is the ONE declared segmentation bias, and it is a category rule, not a glyph list.
  CLASSES   a word's SIGNATURE is the multiset of its 1-token left/right neighbours (boundary included).
            Words with an IDENTICAL signature collide into one class through core.generate.SignatureBank
            (collision-extend first, the Stage 7 ordering). Classes are then MERGED greedily, most-similar pair
            first, and a merge is ADOPTED only if the total description length DROPS.
  SKELETONS every train sentence's class sequence is a skeleton; two sentences that agree everywhere but at
            positions whose words share a class anti-unify into the SAME skeleton (core.resolve's LEARN rule,
            applied to form). So the grammar is (class map, skeleton set) and nothing else.

THE CODE (fixed before the run; both baselines use the same token alphabet):
  DL(G)          = V*log2(K)  +  sum over skeletons of ( len*log2(K) + log2(Lmax) )
  DL(train | G)  = sum over sentences of ( log2(|S|) + sum over tokens of log2(|class(tok)|) )
  DL(text | G)   = derived sentence -> the same; no derivation -> 1 escape bit + the UNIGRAM cost
  UNIGRAM        = -log2 p(tok) with add-one smoothing on train, log2(V+1) for an unseen token, + length
  MEMORY         = log2(N_train) if the sentence is verbatim in train, else 1 escape bit + UNIGRAM

Output on a sentence is COMMIT (a derivation exists) or ABSTAIN. No probabilities leave the module."""
import collections
import math
import random
import unicodedata

from .generate import SignatureBank
from .resolve import segment

BOUND = ("<",)      # the boundary pseudo-symbol in signatures; a tuple so it can never equal a corpus word


# ---------------------------------------------------------------- SEGMENT
def sentences(text, lo=2, hi=12):
    """raw text -> list of sentences (lists of lower-cased letter symbols) with lo <= len <= hi.
    Boundary rule: after a punctuation symbol (category P*), when the next letter symbol starts with Lu."""
    syms = segment(text)
    out, cur, pend = [], [], False
    for s in syms:
        cat = unicodedata.category(s[0])
        if cat[0] == "L":
            if pend and cat == "Lu" and cur:
                out.append(cur); cur = []
            pend = False
            cur.append(s.lower())
        elif cat[0] == "P":
            pend = True
    if cur: out.append(cur)
    return [s for s in out if lo <= len(s) <= hi]


# ---------------------------------------------------------------- the grammar
class FormGrammar:
    """(class map, skeleton multiset) with incremental MDL bookkeeping."""

    def __init__(self, train, lmax=None):
        self.train = [tuple(s) for s in train]
        self.N = len(self.train)
        self.vocab = sorted({w for s in self.train for w in s})
        self.V = len(self.vocab)
        self.lmax = lmax or max(len(s) for s in self.train)
        self.cls = {w: i for i, w in enumerate(self.vocab)}          # word -> class id (one class per word)
        self.members = {i: {w} for w, i in self.cls.items()}         # class id -> set of word TYPES
        self.ntok = collections.Counter(w for s in self.train for w in s)
        self.ctok = collections.Counter({i: self.ntok[w] for w, i in self.cls.items()})   # class -> token count
        self.skel = collections.Counter(self._seq(s) for s in self.train)   # skeleton -> #train sentences
        self.by_class = collections.defaultdict(set)                  # class -> skeletons containing it
        for sk in self.skel:
            for c in set(sk): self.by_class[c].add(sk)
        self.uni = {w: -math.log2((self.ntok[w] + 1) / (sum(self.ntok.values()) + self.V + 1)) for w in self.vocab}
        self.uni_unk = -math.log2(1 / (sum(self.ntok.values()) + self.V + 1))
        self.trainset = set(self.train)

    # ---- codes
    @property
    def K(self): return len(self.members)

    def _seq(self, s): return tuple(self.cls[w] for w in s)

    def dl_grammar(self):
        lk, ll = math.log2(max(self.K, 2)), math.log2(self.lmax)
        return self.V * lk + sum(len(sk) * lk + ll for sk in self.skel)

    def dl_train(self):
        ls = math.log2(len(self.skel))
        return self.N * ls + sum(self.ctok[c] * math.log2(len(self.members[c])) for c in self.members)

    def dl_total(self): return self.dl_grammar() + self.dl_train()

    def unigram(self, s): return sum(self.uni.get(w, self.uni_unk) for w in s) + math.log2(self.lmax)

    def derive(self, s):
        """-> skeleton (COMMIT) or None (ABSTAIN): every word known and the class sequence is a skeleton."""
        if any(w not in self.cls for w in s): return None
        sk = self._seq(s)
        return sk if sk in self.skel else None

    def dl_sentence(self, s):
        sk = self.derive(s)
        if sk is None: return 1 + self.unigram(s)
        return math.log2(len(self.skel)) + sum(math.log2(len(self.members[c])) for c in sk)

    def dl_memory(self, s):
        return math.log2(self.N) if tuple(s) in self.trainset else 1 + self.unigram(s)

    # ---- merging under MDL (exact incremental delta)
    def merge_delta(self, a, b):
        """DL change from merging classes a and b, computed on the affected skeletons only."""
        na, nb = len(self.members[a]), len(self.members[b])
        ta, tb = self.ctok[a], self.ctok[b]
        lk_old, lk_new = math.log2(max(self.K, 2)), math.log2(max(self.K - 1, 2))
        # token filler cost
        d = (ta + tb) * math.log2(na + nb) - ta * math.log2(na) - tb * math.log2(nb)
        # skeletons: those touching a or b are rewritten; count how many collapse
        touched = self.by_class[a] | self.by_class[b]
        new = collections.Counter()
        for sk in touched:
            new[tuple(a if c == b else c for c in sk)] += self.skel[sk]
        n_old, n_new = len(self.skel), len(self.skel) - len(touched) + len(new)
        len_old = sum(len(sk) for sk in self.skel)
        len_new = len_old - sum(len(sk) for sk in touched) + sum(len(sk) for sk in new)
        d += len_new * lk_new - len_old * lk_old + (n_new - n_old) * math.log2(self.lmax)   # skeleton code
        d += self.V * (lk_new - lk_old)                                                       # class map code
        d += self.N * (math.log2(n_new) - math.log2(n_old))                                   # skeleton choice
        return d, new, touched

    def merge(self, a, b, new=None, touched=None):
        if new is None: _, new, touched = self.merge_delta(a, b)
        for sk in touched:
            for c in set(sk): self.by_class[c].discard(sk)
            del self.skel[sk]
        for sk, n in new.items():
            self.skel[sk] += n
            for c in set(sk): self.by_class[c].add(sk)
        for w in self.members[b]: self.cls[w] = a
        self.members[a] |= self.members.pop(b)
        self.ctok[a] += self.ctok.pop(b)
        self.by_class.pop(b, None)


# ---------------------------------------------------------------- CLASSES
def signatures(train):
    """word -> Counter of (side, neighbour) over the corpus, boundary included."""
    sig = collections.defaultdict(collections.Counter)
    for s in train:
        padded = (BOUND,) + tuple(s) + (BOUND,)
        for i in range(1, len(padded) - 1):
            sig[padded[i]][(0, padded[i - 1])] += 1
            sig[padded[i]][(1, padded[i + 1])] += 1
    return sig


def collide(g, sig):
    """collision-extend: words with an IDENTICAL signature are one class. -> number of merges."""
    bank, n = SignatureBank(), 0
    for w in g.vocab:
        key = frozenset(sig[w].items())
        if not bank.add(w, key):
            a, b = g.cls[bank.hit(key)], g.cls[w]
            if a != b: g.merge(a, b); n += 1
    return n


def _cosine(u, v):
    num = sum(c * v[k] for k, c in u.items() if k in v)
    if not num: return 0.0
    return num / math.sqrt(sum(c * c for c in u.values()) * sum(c * c for c in v.values()))


def class_signatures(g, sig):
    out = {}
    for c, ws in g.members.items():
        acc = collections.Counter()
        for w in ws: acc.update(sig[w])
        out[c] = acc
    return out


def merge_mdl(g, sig, top=300, epochs=40, order="similar", rng=None, log=None):
    """Greedy MDL merging. Each epoch: recompute class signatures, rank candidate pairs by cosine (or shuffle
    them for the K3 ablation), evaluate the exact DL delta of the top `top`, adopt every drop. Stops when an
    epoch adopts nothing. -> (#adopted, #evaluated)."""
    rng = rng or random.Random(0)
    adopted = evaluated = 0
    for ep in range(epochs):
        csig = class_signatures(g, sig)
        ids = [c for c in g.members if sum(csig[c].values()) >= 2]         # classes with any context to compare
        # candidate pairs: for speed, index by shared context key
        by_key = collections.defaultdict(list)
        for c in ids:
            for k in csig[c]: by_key[k].append(c)
        pairs = set()
        for k, cs in by_key.items():
            if len(cs) > 60: continue                                     # a context shared by everything says nothing
            for i in range(len(cs)):
                for j in range(i + 1, len(cs)): pairs.add((min(cs[i], cs[j]), max(cs[i], cs[j])))
        scored = [(_cosine(csig[a], csig[b]), a, b) for a, b in pairs]
        if order == "similar": scored.sort(reverse=True)
        else: rng.shuffle(scored)
        got = 0
        alive = set(g.members)
        for _, a, b in scored[:top]:
            if a not in alive or b not in alive: continue
            d, new, touched = g.merge_delta(a, b); evaluated += 1
            if d < 0:
                g.merge(a, b, new, touched); alive.discard(b); got += 1
        adopted += got
        if log: log(f"    epoch {ep:2d}: {len(pairs)} candidate pairs, adopted {got}, K={g.K}, |S|={len(g.skel)}, DL={g.dl_total():.0f}")
        if got == 0: break
    return adopted, evaluated


# ---------------------------------------------------------------- GENERATE / ROUND TRIP (form)
def realize(g, rng, synonyms=None):
    """sample a skeleton, fill each slot with a member type; optionally swap in an accepted synonym."""
    sk = rng.choice(list(g.skel))
    out = []
    for c in sk:
        w = rng.choice(sorted(g.members[c]))
        if synonyms and w in synonyms and rng.random() < 0.5: w = rng.choice(sorted(synonyms[w]))
        out.append(w)
    return sk, out


def corrupt(g, s, rng):
    """swap one filler for a word of a DIFFERENT class (G9d). -> corrupted sentence or None."""
    i = rng.randrange(len(s))
    others = [w for w in g.vocab if g.cls[w] != g.cls[s[i]]]
    if not others: return None
    t = list(s); t[i] = rng.choice(others)
    return t
