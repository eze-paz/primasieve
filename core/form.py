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
from .verdict import COMMIT, ABSTAIN, CONJECTURED

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


# ================================================================ Stage 9b: COMPOSITIONAL form (phrase units)
class PhraseGrammar:
    """(class map, unit inventory). A UNIT is a class sequence adopted because it recurs; a sentence derives as
    the cheapest segmentation into symbols (bare classes or units). Under the fixed uniform symbol code the
    cheapest segmentation is the one with the FEWEST symbols; a tie is an ABSTAIN (the set is returned).
    Every adoption (class merge or unit) is judged by FULL recomputation of the two-part code -- exact."""

    def __init__(self, train):
        self.train = [tuple(s) for s in train]
        self.N = len(self.train)
        self.vocab = sorted({w for s in self.train for w in s})
        self.V = len(self.vocab)
        self.lmax = max(len(s) for s in self.train)
        self.cls = {w: i for i, w in enumerate(self.vocab)}
        self.members = {i: {w} for w, i in self.cls.items()}
        self.ntok = collections.Counter(w for s in self.train for w in s)
        self.ctok = collections.Counter({i: self.ntok[w] for w, i in self.cls.items()})
        self.units = set()                       # flat class tuples, len >= 2
        self.ulen = set()
        tot = sum(self.ntok.values())
        self.uni = {w: -math.log2((self.ntok[w] + 1) / (tot + self.V + 1)) for w in self.vocab}
        self.uni_unk = -math.log2(1 / (tot + self.V + 1))
        self.trainset = set(self.train)
        self._seg_cache = {}

    @property
    def K(self): return len(self.members)

    def seq(self, s): return tuple(self.cls[w] for w in s)

    # ---- segmentation: fewest symbols; returns (n_symbols, set of segmentations) with a cap on the set
    def segment(self, seq, cap=8):
        hit = self._seg_cache.get(seq)
        if hit is not None: return hit
        n = len(seq)
        best = [None] * (n + 1); ways = [None] * (n + 1)
        best[0] = 0; ways[0] = [()]
        lens = [1] + sorted(self.ulen)
        for i in range(1, n + 1):
            for L in lens:
                if L > i: continue
                sym = seq[i - L:i]
                if L > 1 and sym not in self.units: continue
                if best[i - L] is None: continue
                c = best[i - L] + 1
                if best[i] is None or c < best[i]:
                    best[i] = c; ways[i] = [w + (sym,) for w in ways[i - L]][:cap]
                elif c == best[i]:
                    ways[i] = (ways[i] + [w + (sym,) for w in ways[i - L]])[:cap]
        res = (best[n], set(ways[n]))
        self._seg_cache[seq] = res
        return res

    def derive(self, s):
        """-> (state, segs): (COMMIT, {seg}) unique | (ABSTAIN, set) tie | (None, None) unknown word."""
        if any(w not in self.cls for w in s): return None, None
        n, segs = self.segment(self.seq(s))
        return (COMMIT if len(segs) == 1 else ABSTAIN), segs

    # ---- the code
    def sym_bits(self): return math.log2(self.K + len(self.units))

    def dl_grammar(self):
        return self.V * math.log2(max(self.K, 2)) + sum(len(u) * self.sym_bits() + math.log2(self.lmax) for u in self.units)

    def dl_sentence(self, s):
        if any(w not in self.cls for w in s): return 1 + self.unigram(s)
        n, _ = self.segment(self.seq(s))
        return math.log2(self.lmax) + n * self.sym_bits() + sum(math.log2(len(self.members[self.cls[w]])) for w in s)

    def dl_train(self): return sum(self.dl_sentence(s) for s in self.train)

    def dl_total(self): return self.dl_grammar() + self.dl_train()

    def unigram(self, s): return sum(self.uni.get(w, self.uni_unk) for w in s) + math.log2(self.lmax)

    def dl_memory(self, s): return math.log2(self.N) if tuple(s) in self.trainset else 1 + self.unigram(s)

    # ---- edits (each followed by a full recompute by the caller)
    def snapshot(self):
        return (dict(self.cls), {k: set(v) for k, v in self.members.items()}, collections.Counter(self.ctok),
                set(self.units), set(self.ulen))

    def restore(self, snap):
        self.cls, self.members, self.ctok, self.units, self.ulen = snap[0], snap[1], snap[2], snap[3], snap[4]
        self._seg_cache = {}

    def merge(self, a, b):
        for w in self.members[b]: self.cls[w] = a
        self.members[a] |= self.members.pop(b)
        self.ctok[a] += self.ctok.pop(b)
        self.units = {tuple(a if c == b else c for c in u) for u in self.units}
        self._seg_cache = {}

    def add_unit(self, flat):
        self.units.add(flat); self.ulen.add(len(flat)); self._seg_cache = {}

    # ---- candidates
    def unit_candidates(self):
        """adjacent symbol pairs in the (first) cheapest segmentation of every train sentence, by frequency."""
        cnt = collections.Counter()
        for s in self.train:
            n, segs = self.segment(self.seq(s))
            seg = sorted(segs)[0]
            for i in range(len(seg) - 1): cnt[seg[i] + seg[i + 1]] += 1
        return [u for u, c in cnt.most_common() if c >= 2 and u not in self.units]


def grow_phrases(g, sig, budget_s, use_units=True, cand_similar=40, cand_random=40, rng=None, log=None,
                 pair_classes=1500, pair_cap=20000):
    """alternate class-merge rounds and unit adoption until a full cycle adopts nothing or the budget is spent.
    -> dict(rounds, merges, units, evaluated, spent: bool, dl)."""
    import time
    rng = rng or random.Random(0)
    t0 = time.time(); merges = units = evaluated = rounds = 0; spent = False
    dl = g.dl_total()
    while True:
        rounds += 1; got = 0
        # ---- class merges: most-similar pairs + random pairs, exact full-DL evaluation
        csig = class_signatures(g, sig)
        ids = [c for c in g.members if sum(csig[c].values()) >= 2]
        ids = sorted(ids, key=lambda c: -g.ctok[c])[:pair_classes]          # declared cap on candidate classes
        by_key = collections.defaultdict(list)
        for c in ids:
            for k in csig[c]: by_key[k].append(c)
        pairs = set()
        for k, cs in by_key.items():
            if len(cs) > 60: continue
            for i in range(len(cs)):
                for j in range(i + 1, len(cs)): pairs.add((min(cs[i], cs[j]), max(cs[i], cs[j])))
        pairs = list(pairs)
        if len(pairs) > pair_cap: pairs = rng.sample(pairs, pair_cap)           # declared cap on scored pairs
        scored = sorted(((_cosine(csig[a], csig[b]), a, b) for a, b in pairs), reverse=True)[:cand_similar]
        cands = [(a, b) for _, a, b in scored]
        if cand_random and pairs: cands += rng.sample(pairs, min(cand_random, len(pairs)))
        alive = set(g.members)
        for a, b in cands:
            if time.time() - t0 > budget_s: spent = True; break
            if a not in alive or b not in alive: continue
            snap = g.snapshot(); g.merge(a, b); evaluated += 1
            d = g.dl_total()
            if d < dl: dl = d; merges += 1; got += 1; alive.discard(b)
            else: g.restore(snap)
        # ---- unit adoption: most frequent adjacent pair first, until none drops DL
        if use_units:
            while time.time() - t0 <= budget_s:
                adopted_here = False
                for u in g.unit_candidates()[:30]:
                    if time.time() - t0 > budget_s: spent = True; break
                    snap = g.snapshot(); g.add_unit(u); evaluated += 1
                    d = g.dl_total()
                    if d < dl: dl = d; units += 1; got += 1; adopted_here = True; break
                    g.restore(snap)
                if not adopted_here: break
        if log: log(f"    round {rounds}: adopted {got} (merges so far {merges}, units {units}), K={g.K}, |P|={len(g.units)}, DL={dl:.0f}  [{time.time()-t0:.0f}s]")
        if got == 0 or spent or time.time() - t0 > budget_s:
            spent = spent or time.time() - t0 > budget_s
            break
    return dict(rounds=rounds, merges=merges, units=units, evaluated=evaluated, spent=spent, dl=dl)


def realize_phrase(g, rng, synonyms=None):
    """sample a train sentence's cheapest segmentation as the generating symbol sequence, fill every class slot
    with a member type. -> (generating segmentation, words)."""
    s = rng.choice(g.train)
    n, segs = g.segment(g.seq(s))
    seg = rng.choice(sorted(segs))
    out = []
    for sym in seg:
        for c in sym:
            w = rng.choice(sorted(g.members[c]))
            if synonyms and w in synonyms and rng.random() < 0.5: w = rng.choice(sorted(synonyms[w]))
            out.append(w)
    return seg, out


# ================================================================ loop it.1: INCREMENTAL description length (exact)
class IncPhraseGrammar(PhraseGrammar):
    """PhraseGrammar with the two-part code maintained incrementally: per-sentence symbol counts are cached and
    only the sentences a merge or a unit can touch are re-segmented. The code itself is unchanged and the total is
    verified equal to PhraseGrammar.dl_total on a small run (LOOP.md I1-a)."""

    def __init__(self, train):
        super().__init__(train)
        self.seqs = [self.seq(s) for s in self.train]
        self.nsym = [len(q) for q in self.seqs]                       # no units yet: one symbol per token
        self.total_syms = sum(self.nsym)
        self.cls_sents = collections.defaultdict(set)
        for i, q in enumerate(self.seqs):
            for c in set(q): self.cls_sents[c].add(i)
        self.fill_bits = 0.0                                          # every class is a singleton: log2(1) = 0

    def dl_train(self):
        return self.N * math.log2(self.lmax) + self.total_syms * self.sym_bits() + self.fill_bits

    def _reseg(self, idxs):
        for i in idxs:
            n, _ = self.segment(self.seqs[i])
            self.total_syms += n - self.nsym[i]; self.nsym[i] = n

    def snapshot(self):
        return (dict(self.cls), {k: set(v) for k, v in self.members.items()}, collections.Counter(self.ctok),
                set(self.units), set(self.ulen), list(self.nsym), self.total_syms, self.fill_bits,
                {k: set(v) for k, v in self.cls_sents.items()}, self.seqs)

    def restore(self, snap):
        (self.cls, self.members, self.ctok, self.units, self.ulen, self.nsym, self.total_syms, self.fill_bits,
         self.cls_sents, seqs) = snap
        if seqs is not self.seqs: self.seqs = seqs
        self._seg_cache = {}

    def merge(self, a, b):
        na, nb = len(self.members[a]), len(self.members[b])
        self.fill_bits += (self.ctok[a] + self.ctok[b]) * math.log2(na + nb) - self.ctok[a] * math.log2(na) - self.ctok[b] * math.log2(nb)
        for w in self.members[b]: self.cls[w] = a
        self.members[a] |= self.members.pop(b)
        self.ctok[a] += self.ctok.pop(b)
        self.units = {tuple(a if c == b else c for c in u) for u in self.units}
        affected = self.cls_sents[a] | self.cls_sents.pop(b)
        self.cls_sents[a] = affected
        seqs = list(self.seqs)
        for i in self.cls_sents[a]:
            seqs[i] = tuple(a if c == b else c for c in seqs[i])
        self.seqs = seqs
        self._seg_cache = {}                                          # units changed: cached segmentations may be stale
        self._reseg(affected)

    def add_unit(self, flat):
        self.units.add(flat); self.ulen.add(len(flat)); self._seg_cache = {}
        L = len(flat)
        cand = self.cls_sents[flat[0]]
        affected = [i for i in cand if any(self.seqs[i][j:j + L] == flat for j in range(len(self.seqs[i]) - L + 1))]
        self._reseg(affected)

    def unit_candidates(self):
        cnt = collections.Counter()
        for q in self.seqs:
            n, segs = self.segment(q)
            seg = sorted(segs)[0]
            for i in range(len(seg) - 1): cnt[seg[i] + seg[i + 1]] += 1
        return [u for u, c in cnt.most_common() if c >= 2 and u not in self.units]


# ================================================================ loop it.2: scoring levers -- ADAPTIVE code, OOV by class CONJECTURE
class AdaptiveCode:
    """frequency code fitted on the train segmentation: symbol and filler costs with add-one smoothing.
    Count tables are uncharged (declared in LOOP.md it.2; the unigram baseline is a fitted table too)."""

    def __init__(self, g):
        self.g = g
        self.sym = collections.Counter(); self.fill = collections.Counter(); self.ctot = collections.Counter()
        seqs = getattr(g, "seqs", None) or [g.seq(s) for s in g.train]
        for s, q in zip(g.train, seqs):
            n, segs = g.segment(q)
            for x in sorted(segs)[0]: self.sym[x] += 1
            for w in s: c = g.cls[w]; self.fill[(c, w)] += 1; self.ctot[c] += 1
        self.nsym_total = sum(self.sym.values())
        self.nsyms = g.K + len(g.units)

    def sym_cost(self, x): return -math.log2((self.sym[x] + 1) / (self.nsym_total + self.nsyms))

    def fill_cost(self, c, w):
        if w is None: return self.g.uni_unk                                  # unknown word: identity paid as unigram-unknown
        return -math.log2((self.fill[(c, w)] + 1) / (self.ctot[c] + len(self.g.members[c])))


def oov_survivors(g, s, ctx):
    """for each unknown word position: the classes attested in train with the same LEFT or RIGHT neighbour class.
    `ctx` = (left: class -> set(classes), right: class -> set(classes)) built once from the train seqs.
    -> list of (position, survivor set); an empty survivor set means neutral scoring for the sentence."""
    left, right = ctx
    out = []
    for i, w in enumerate(s):
        if w in g.cls: continue
        surv = set()
        if i > 0 and s[i - 1] in g.cls: surv |= right.get(g.cls[s[i - 1]], set())
        if i + 1 < len(s) and s[i + 1] in g.cls: surv |= left.get(g.cls[s[i + 1]], set())
        out.append((i, surv))
    return out


def neighbour_context(g):
    left, right = collections.defaultdict(set), collections.defaultdict(set)     # left[c] = classes seen BEFORE c
    seqs = getattr(g, "seqs", None) or [g.seq(s) for s in g.train]
    for q in seqs:
        for i in range(1, len(q)):
            left[q[i]].add(q[i - 1]); right[q[i - 1]].add(q[i])
    return left, right


def sentence_cost(g, s, code=None, ctx=None, max_survivors=None):
    """held-out code length of one sentence under the chosen levers.
    code=None -> the registered uniform code; ctx=None -> OOV neutral (escape + unigram).
    -> (bits, state, n_survivor_product)  state in {COMMIT, ABSTAIN, CONJECTURED, None}"""
    unknown = [i for i, w in enumerate(s) if w not in g.cls]
    if unknown and ctx is None:
        return 1 + g.unigram(s), None, 0
    slots = []
    if unknown:
        surv = dict(oov_survivors(g, s, ctx))
        if any(not surv[i] for i in unknown):
            return 1 + g.unigram(s), None, 0
        prod = 1
        for i in unknown: prod *= len(surv[i])
        if prod > 512:                                                          # too many assignments to enumerate: guess -> neutral
            return 1 + g.unigram(s), None, prod
        import itertools
        combos = list(itertools.product(*[sorted(surv[i]) for i in unknown]))
    else:
        combos = [()]; prod = 1
    best = None; best_segs = None
    for combo in combos:
        q = list(g.cls.get(w, -1) for w in s)
        for i, c in zip(unknown, combo): q[i] = c
        q = tuple(q)
        n, segs = g.segment(q)
        seg = sorted(segs)[0]
        if code is None:
            bits = math.log2(g.lmax) + n * g.sym_bits() + sum(
                (g.uni_unk if s[i] not in g.cls else math.log2(len(g.members[q[i]]))) for i in range(len(s)))
        else:
            bits = math.log2(g.lmax) + sum(code.sym_cost(x) for x in seg) + sum(
                code.fill_cost(q[i], s[i] if s[i] in g.cls else None) for i in range(len(s)))
        if unknown: bits += math.log2(prod)                                     # the conjecture's choice must be paid
        if best is None or bits < best: best, best_segs = bits, segs
    if unknown: state = CONJECTURED
    else: state = COMMIT if len(best_segs) == 1 else ABSTAIN
    return best, state, prod
