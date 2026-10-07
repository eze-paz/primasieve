"""BOOKWORLD -- every book its own world (bookworld_prereg.md, bookdoers_prereg.md; the owner's ruling of 2026-10-07:
"every source should have its own context unless we know we are talking about the real world"). Zero LLM; holds no
word of any language.

A Book reads one text. Its people are found in the text itself (capitalised names, textworld.find_entities); its
propositions are events with a NAMED doer (or a pronoun the book itself resolves to a name) and roles by apposition,
each kept with its context (the book, the sentence) and said "according to <book>". Nothing here is a world fact:
`real` is False unless a bridge finds evidence that the source speaks of the real world. Data from outside: the event
reader's verb tables, the closed class, the learned abbreviations, determiners, chain heads, skippable, noun-like and
preposition-like symbols (emergence/kb_bookworld.py)."""
import re, collections
from core.textworld import find_entities

TOKEN = re.compile(r"[^\W_]+|[^\w\s]")
SPLIT = re.compile(r"(?<=[.!?])\s+")


def tokens(s): return TOKEN.findall(s)


def is_word(t): return t[:1].isalnum()


def abbreviations(texts, least=20, share=0.9):
    """symbols followed by "." in >= `share` of their >= `least` occurrences (counted, case kept)"""
    dot = collections.Counter(); allc = collections.Counter()
    for text in texts:
        toks = tokens(text)
        for a, b in zip(toks, toks[1:]):
            if a[:1].isalpha(): allc[a] += 1; dot[a] += b == "."
    return {w for w, n in allc.items() if n >= least and dot[w] >= share * n}


def split(text, abbr):
    """sentences; a split right after "<abbreviation>." is undone"""
    out = []
    for p in SPLIT.split(text):
        p = " ".join(p.split())
        if not p: continue
        if out:
            t = tokens(out[-1])
            if len(t) >= 2 and t[-1] == "." and t[-2] in abbr: out[-1] += " " + p; continue
        out.append(p)
    return out


def paragraphs(text):
    """bookvoice (1), amended: a paragraph break is a run of line breaks LONGER than the text's commonest run (some
    texts break every line twice and paragraphs four times)"""
    text = text.replace("\r", "")
    runs = collections.Counter(len(m.group(0)) for m in re.finditer(r"\n+", text))
    if not runs: return [text]
    line = runs.most_common(1)[0][0]
    return [p for p in re.split(r"\n{%d,}" % (line + 1), text) if p.strip()]


def heading(t): return len(t) > 1 and t.isupper()


class Book:
    def __init__(self, bid, text, closed, abbr, reader, determiners=(), chain_heads=(), title=None, least=5, verbish=(),
                 skippable=(), nounish=(), preplike=(), det2=(), subjects=(), pronouns=False, knockout=False, quotes=False,
                 version=1, complementizers=(), chains=True, speaker=None, narrator_label=None, quote_default=None):
        self.verbish = set(verbish); self.skip = set(skippable); self.nounish = set(nounish); self.prep = set(preplike)
        self.bid = bid; self.closed = set(closed); self.R = reader; self.det = set(determiners); self.heads = set(chain_heads)
        self.det2 = set(det2); self.subjects = set(subjects) & self.closed
        self.abbr = set(abbr); self.v = version; self.comp = set(complementizers); self.chains = chains and version >= 3; self._resolved = {}
        self.speaker = speaker; self.narrator_label = narrator_label; self.narrated = False
        self.use_pronouns = pronouns; self.knockout = knockout; self.use_quotes = quotes; self.quote = None
        self.title = title or ("book " + str(bid)); self.real = False
        if version >= 4:
            # bookvoice (1): paragraphs first; sentences within them; the first sentence of each paragraph is marked
            self.sents, self.par_start = [], []
            for par in paragraphs(text):
                ss = split(par, abbr); self.sents += ss; self.par_start += [True] + [False] * (len(ss) - 1)
        else:
            self.sents = split(text, abbr); self.par_start = [False] * len(self.sents)
        self.toks = [tokens(s) for s in self.sents]
        self.play = False
        if version >= 4:
            # bookvoice (2): a play -- >= 20 % of paragraphs open with a capitalised heading token followed by "."
            heads = [ts for ts, ps in zip(self.toks, self.par_start) if ps]
            lab = sum(1 for ts in heads if len(ts) >= 2 and heading(ts[0]) and ts[1] == ".")
            self.play = lab >= 0.2 * max(1, len(heads))
        raw = [[t for t in ts if t[:1].isalpha() and not heading(t)] for ts in self.toks] if not pronouns else self.segments(abbr)
        self.entities = find_entities(raw, least=least, closed=self.closed)
        # titles: an entity symbol followed (past an abbreviation's ".") by another capitalised symbol >= 80 % of the time
        cap = collections.Counter(); nxt = collections.Counter(); low = collections.Counter()
        for ts in self.toks:
            for k, t in enumerate(ts):
                if t[:1].islower(): low[t.lower()] += 1
                if t.lower() in self.entities and t[:1].isupper():
                    cap[t.lower()] += 1; j = k + 1
                    if j < len(ts) and ts[j] == ".": j += 1
                    if j < len(ts) and ts[j][:1].isupper() and is_word(ts[j]): nxt[t.lower()] += 1
        self.titles = {e for e in cap if nxt[e] >= 0.8 * cap[e]}
        self.low = low
        if version >= 3:
            # bookcheck (2): a capital followed by a lower-case open-class non-verb symbol in >= 50 % of its capitalised
            # uses is an adjective ("English essays"), not a name head
            adj = collections.Counter()
            for ts in self.toks:
                for k, t in enumerate(ts[:-1]):
                    if t.lower() in self.entities and t[:1].isupper():
                        n = ts[k + 1]
                        if (n[:1].islower() and n.isalpha() and n.lower() not in self.closed and n.lower() not in reader.verbs
                                and n.lower() not in reader.participles): adj[t.lower()] += 1
            self.adjectives = {e for e in cap if adj[e] >= (0.3 if version >= 4 else 0.5) * cap[e]}
            self.entities -= self.adjectives
        self._names = [self.names(ts) for ts in self.toks]
        if quotes: self.quote = self.learn_quote() or (quote_default if version >= 4 else None)
        self.aff = collections.defaultdict(collections.Counter)
        if pronouns: self.learn_affinity()

    def segments(self, abbr):
        """bookdoers: word runs between punctuation marks (an abbreviation's "." does not cut), so that a capital right
        after a quotation mark or a dash ("Oh") is not counted as a name's capital"""
        out = []
        for ts in self.toks:
            cur = []
            for k, t in enumerate(ts):
                if t[:1].isalpha():
                    if not heading(t): cur.append(t)
                elif t[:1].isdigit(): continue
                elif not (t == "." and k > 0 and ts[k - 1] in abbr):
                    if cur: out.append(cur)
                    cur = []
            if cur: out.append(cur)
        return out

    # ---- names
    def names(self, ts):
        """-> [(start, end, key, text, raw_start)]: maximal runs of capitalised tokens (a title's "." kept inside) holding a
        book entity; key = the run's non-title entity symbols; start skips leading closed or sentence-initial symbols"""
        out = []; k = 0
        cap = lambda t: is_word(t) and t[:1].isupper() and not heading(t)
        while k < len(ts):
            if cap(ts[k]):
                j = k
                while j + 1 < len(ts) and (cap(ts[j + 1]) or (ts[j + 1] == "." and j + 2 < len(ts) and cap(ts[j + 2])
                                                              and (ts[j].lower() in self.titles
                                                                   or (self.v == 5 and ts[j].lower() in self.closed)
                                                                   or (self.v >= 6 and ts[j] in self.abbr)))):
                    j += 1 if cap(ts[j + 1]) else 2
                run = list(range(k, j + 1))
                ents = [i for i in run if ts[i].lower() in self.entities]
                key = tuple(ts[i].lower() for i in ents if ts[i].lower() not in self.titles)
                if key:
                    s = k
                    while s < ents[0] and (ts[s].lower() in self.closed or (s == 0 and ts[s].lower() not in self.entities)): s += 1
                    text = " ".join(ts[s:j + 1]).replace(" .", ".")
                    if self.v >= 6: text = text.lstrip(". ")                       # bookbridge2 (2)
                    out.append((s, j + 1, key, text, k))
                k = j + 1
            else: k += 1
        return out

    # ---- quotations (bookdoers_prereg.md 4)
    def learn_quote(self):
        """the punctuation mark most often right before a dialogue attribution (two marks, a verb, a name)"""
        c = collections.Counter()
        for ts, ns in zip(self.toks, self._names):
            starts = {n[0] for n in ns}
            for k in range(2, len(ts) - 1):
                if not is_word(ts[k - 1]) and not is_word(ts[k - 2]) and k + 1 in starts:
                    v = self.verb_at(ts, k)
                    if v and v[1] == k: c[ts[k - 1]] += 1
        return c.most_common(1)[0][0] if c and c.most_common(1)[0][1] >= 3 else None

    def parity(self):
        """bookvoice (1): quotation marks open at the start of each sentence, carried within a paragraph"""
        self.qopen = []; q = 0
        for ts, ps in zip(self.toks, self.par_start):
            if ps: q = 0
            self.qopen.append(q)
            if self.quote is not None: q = (q + ts.count(self.quote)) % 2

    def inside(self, ts, k, i=None):
        if self.v >= 4 and i is not None and self.use_quotes and self.quote is not None:
            if not hasattr(self, "qopen"): self.parity()
            return (self.qopen[i] + ts[:k].count(self.quote)) % 2 == 1
        """position k lies inside an open quotation (an odd number of the book's quotation marks before it)"""
        return self.use_quotes and self.quote is not None and ts[:k].count(self.quote) % 2 == 1

    # ---- the verb chain
    def verb_at(self, ts, k):
        """-> (lemma, position of the content verb) for a finite verb at k, following a learned chain head or auxiliary
        to the verb it carries ("had gone", "did not go", "could have entered", "has been reached")"""
        t = ts[k].lower(); R = self.R; auxs = getattr(R, "auxiliaries", ())
        finite = t in R.verbs and ((t not in self.closed and t not in self.nounish) or t in self.verbish or t in auxs)
        if not finite and t not in self.heads: return None
        if t in auxs or t in self.heads:
            for j in range(k + 1, min(len(ts), k + 4)):
                if not is_word(ts[j]): break
                tj = ts[j].lower()
                if tj in R.participles and t in auxs:
                    vp = j
                    while vp + 1 < len(ts) and ts[vp].lower() in auxs and ts[vp + 1].lower() in R.participles: vp += 1
                    return R.participles[ts[vp].lower()], vp
                if t in self.heads and tj in auxs and self.use_pronouns:
                    r = self.verb_at(ts, j)
                    if r: return r
                if t in self.heads and tj in R.base and tj not in self.closed: return R.base[tj], j
                if tj not in self.skip:
                    if (self.v >= 5 and t in auxs and j + 1 < len(ts) and ts[j + 1].lower() in R.participles
                            and tj not in self.closed): continue            # bookbridge (c): "has never wholly abandoned"
                    break
        if finite: return R.verbs[t], k
        return None

    def outside(self, ts, s):
        """a name (or pronoun) after a learned preposition-like symbol, past determiner-like ones, is not the subject
        ("the coach from Wildairs Hall", "the wisdom of the Egyptians")"""
        j = s - 1
        if self.use_pronouns:
            while j >= 0 and ts[j][:1].islower() and ts[j].lower() in self.det2: j -= 1
        if j < 0: return False
        if self.v >= 3 and ts[j].lower() in self.comp and (ts[j][:1].islower() or j == 0): return True   # bookcheck (3)
        return (ts[j][:1].islower() or (self.v >= 3 and j == 0)) and ts[j].lower() in self.prep

    def doer_of(self, ts, k, vp, ends, starts):
        """-> (doer, end of the doer, how): (a) a name ending before the verb chain, at most two learned skippable symbols
        between, no punctuation; (b) dialogue attribution: two punctuation marks (a quotation closing), verb, name; with
        pronouns, a learned subject symbol in either place (how = 'pronoun:<p>')"""
        for e in range(k, max(-1, k - 3), -1):
            if not all(is_word(x) and x.lower() in self.skip for x in ts[e:k]): continue
            if e in ends:
                n = ends[e]
                if self.outside(ts, n[4] if self.use_pronouns else n[0]): return None, None, None
                return n, e, "name"
            if (self.use_pronouns and e > 0 and ts[e - 1].lower() in self.subjects and not self.outside(ts, e - 1)
                    and self.clause_initial(ts, e - 1)):
                return None, e, "pronoun:" + ts[e - 1].lower()
        if k > 1 and not is_word(ts[k - 1]) and not is_word(ts[k - 2]) and vp == k:
            if k + 1 in starts: return starts[k + 1], k, "dialogue"
            if self.use_pronouns and k + 1 < len(ts) and ts[k + 1].lower() in self.subjects:
                return None, k, "dialogue-pronoun:" + ts[k + 1].lower()
        return None, None, None

    def clause_initial(self, ts, j):
        """position j opens a clause: the sentence's first symbol, after a punctuation mark, or after one closed-class
        symbol that itself follows one (as in: ; but she understood) -- not inside a noun phrase (the target he aimed)"""
        if j == 0 or not is_word(ts[j - 1]): return True
        return ts[j - 1].lower() in self.closed and (j == 1 or not is_word(ts[j - 2]))

    @staticmethod
    def asked(ts, k):
        """the clause holding position k ends in a question mark"""
        for t in ts[k:]:
            if t in ".!?": return t == "?"
        return False

    # ---- pronouns (bookdoers_prereg.md 5)
    def pronoun_doers(self, i):
        """[(position, pronoun)] of pronoun doers of sentence i, outside quotations"""
        ts = self.toks[i]; out = []; ns = self._names[i]
        ends = {n[1]: n for n in ns}; starts = {n[0]: n for n in ns}
        for k in range(len(ts)):
            if not is_word(ts[k]) or self.inside(ts, k, i): continue
            v = self.verb_at(ts, k)
            if v is None: continue
            doer, e, how = self.doer_of(ts, k, v[1], ends, starts)
            if how and how.split(":")[0] in ("pronoun", "dialogue-pronoun"): out.append((k, how.split(":")[1]))
        return out

    def named_doers(self, i):
        """[(position, name)] of the named doers of sentence i (rules a and b), outside quotations"""
        ts = self.toks[i]; ns = self._names[i]; out = []
        ends = {n[1]: n for n in ns}; starts = {n[0]: n for n in ns}
        for k in range(len(ts)):
            if not is_word(ts[k]) or self.inside(ts, k, i): continue
            v = self.verb_at(ts, k)
            if v is None: continue
            doer, e, how = self.doer_of(ts, k, v[1], ends, starts)
            if doer is not None: out.append((k, doer))
        return out

    def learn_affinity(self):
        """AFFINITY(e, p): p is the first pronoun doer of a sentence right after a sentence naming only e; a name is
        PERSON-LIKE when it is a named doer >= 5 times in the book"""
        self._doers = [self.named_doers(i) for i in range(len(self.toks))]
        self.doer_count = collections.Counter(n[2] for ds in self._doers for _, n in ds)
        for i in range(1, len(self.toks)):
            keys = {n[2] for n in self._names[i - 1]}
            if len(keys) != 1: continue
            pd = self.pronoun_doers(i)
            if pd and not any(n[0] < pd[0][0] for n in self._names[i]): self.aff[next(iter(keys))][pd[0][1]] += 1
        if self.v >= 3 and self.speaker:
            # bookcheck, amended before the run: the first-person symbol (learned: the commonest subject opening a
            # quotation) used as a doer OUTSIDE quotations in >= 15 % of the pronoun doers -> the book has a narrator
            outside = collections.Counter(p for i in range(len(self.toks)) for _, p in self.pronoun_doers(i))
            self.narrated = outside[self.speaker] >= 0.15 * max(1, sum(outside.values())) and not self.play
        if self.v >= 3:
            # bookcheck, amended before the run: a name's pronoun from SAME-SENTENCE evidence -- a sentence whose only
            # named doer is e, with a later pronoun doer p ("Temple bowed; ... he left the house"); a story told around
            # one character fills the next sentence with her pronoun whoever was named
            self.aff3 = collections.defaultdict(collections.Counter)
            for i in range(len(self.toks)):
                ds = self._doers[i]
                if len({n[2] for _, n in ds}) != 1: continue
                later = [p for pos, p in self.pronoun_doers(i) if pos > ds[0][0]]
                if later: self.aff3[ds[0][1][2]][later[0]] += 1

    def top_pronoun(self, key):
        if self.v >= 3:
            a = self.aff3.get(key)
            if not a: return None
            p, n = a.most_common(1)[0]
            return p if n >= 3 and n >= 0.6 * sum(a.values()) else None
        return self.top_pronoun2(key)

    def top_pronoun2(self, key):
        """the pronoun whose share after this name most exceeds its share after any name (lift), seen >= 5 times and
        >= 40 % of this name's sightings, lift >= 1.1"""
        a = self.aff.get(key)
        if not a: return None
        if not hasattr(self, "_base"):
            self._base = collections.Counter()
            for c in self.aff.values(): self._base.update(c)
        tot = sum(a.values()); btot = sum(self._base.values())
        lift = {p: (n / tot) / (self._base[p] / btot) for p, n in a.items() if n >= 5 and n >= 0.4 * tot}
        if not lift: return None
        p = max(lift, key=lift.get)
        return p if lift[p] >= 1.1 else None

    def resolve(self, i, pos, p):
        """the one name in the window (previous sentence, this sentence before pos) whose most frequent pronoun is p"""
        window = ([n for n in self._names[i - 1]] if i > 0 else []) + [n for n in self._names[i] if n[1] <= pos]
        if not window: return None
        if self.knockout: return window[-1]
        # bookdoers run 2 (declared): the previous sentence's named DOERS and this sentence's names before pos; only
        # person-like names count; any person-like name whose pronoun is unknown makes the reading abstain
        window = ([n for _, n in self._doers[i - 1]] if i > 0 else []) + [n for n in self._names[i] if n[1] <= pos]
        if self.v >= 3:
            # bookcheck (1), amended before the run: the last three sentences' named doers and resolved pronouns, then
            # this sentence's names before pos, walked from the most recent: names that are not person-like are passed;
            # a person-like name with an unknown pronoun stops the walk (abstain); the first whose pronoun is p is it
            seq = []
            for d in (3, 2, 1):
                if i - d < 0: continue
                ents = [(pos, n) for pos, n in self._doers[i - d]] + ([(-1, n) for n in self._resolved.get(i - d, [])] if self.chains else [])
                seq += [n for _, n in sorted(ents, key=lambda x: x[0])]
            seq += [n for n in self._names[i] if n[1] <= pos and not (self.v >= 6 and self.inside(self.toks[i], n[0], i))]
            for n in reversed(seq):
                if self.doer_count[n[2]] < 5: continue
                t = self.top_pronoun(n[2])
                if t is None: return None
                if t == p:
                    if self.v >= 5 and any(m[2] != n[2] and self.doer_count[m[2]] >= 5 and self.top_pronoun(m[2]) == p for m in seq):
                        return None
                    if self.v >= 6 and any(m[2] != n[2] and self.doer_count[m[2]] >= 5 and self.top_pronoun(m[2]) is None for m in seq):
                        return None                                       # bookbridge (b): two names share the pronoun
                    return n
            return None
        window = [n for n in window if self.doer_count[n[2]] >= 5]
        tops = {n[2]: self.top_pronoun(n[2]) for n in window}
        if not window or None in tops.values(): return None
        hits = {n[2]: n for n in window if tops[n[2]] == p}
        return next(iter(hits.values())) if len(hits) == 1 else None

    # ---- the bridge to the real world (bookbridge_prereg.md)
    def bridge(self, lookup, related, common, max_cands=20, label=None, norm=None):
        """lookup(name text) -> candidate items; related(a, b) -> the store relates items a and b. A name is bridged
        when exactly one of its candidates is related to a candidate of another name it shares a sentence with."""
        texts = collections.defaultdict(set); co = collections.defaultdict(set)
        for ns in self._names:
            keys = {n[2] for n in ns}
            for n in ns: texts[n[2]].add(n[3])
            for a in keys: co[a] |= keys - {a}
        cand = {}
        for key, ts in texts.items():
            if len(key) == 1 and key[0] in common: continue
            c = set()
            for t in ts: c |= set(lookup(t))
            if c: cand[key] = sorted(c)[:max_cands]
        self.bridges = {}
        for a, ca in cand.items():
            ev = {}
            for b in co[a]:
                for qa in ca:
                    for qb in cand.get(b, ()):
                        if qa != qb and related(qa, qb): ev.setdefault(qa, (b, qb))
            if self.v >= 6 and label is not None:
                # bookbridge2 (1): the item's own label must be one of the name's texts; a one-symbol name needs two
                # different partner names as evidence
                ev2 = {}
                for b in co[a]:
                    for qa in ca:
                        if norm(label(qa)) not in {norm(t) for t in texts[a]}: continue
                        for qb in cand.get(b, ()):
                            if qa != qb and related(qa, qb): ev2.setdefault(qa, []).append((b, qb))
                ev = {q: v[0] for q, v in ev2.items() if len(a) > 1 or any(len(b) > 1 for b, _ in v) or len({b for b, _ in v}) >= 2}
            if len(ev) == 1:
                q, (b, qb) = next(iter(ev.items())); self.bridges[a] = (q, b, qb)
        return self.bridges

    # ---- propositions of one sentence
    def read(self, i):
        ts = self.toks[i]; ns = self._names[i]; out = []
        ends = {n[1]: n for n in ns}; starts = {n[0]: n for n in ns}
        used = set(); auxs = getattr(self.R, "auxiliaries", ())
        for k in range(len(ts)):
            if k in used or not is_word(ts[k]): continue
            v = self.verb_at(ts, k)
            if v is None: continue
            lemma, vp = v
            doer, e, how = self.doer_of(ts, k, vp, ends, starts)
            if how is None or self.asked(ts, vp) or self.inside(ts, k, i): continue
            # bookdescribe run 2: a learned negative symbol in the verb group ("does not need") -- the event is not told
            negs = getattr(self.R, "negatives", ()); j0 = max(0, min(vp, k) - 3)
            if any(ts[j].lower() in negs for j in range(j0, min(len(ts), k + 3))): continue      # "does not need": after, too
            # bookhave run 2: an event in a clause opened by the learned conditional opener is not told as happened
            jj = min(vp, k) - 1; conds = getattr(self.R, "cond", ())
            while jj >= 0 and (is_word(ts[jj]) or (ts[jj] == "." and jj > 0 and ts[jj - 1] in self.abbr)) and ts[jj].lower() not in conds: jj -= 1
            if jj >= 0 and ts[jj].lower() in conds: continue
            if self.v >= 4 and vp + 2 < len(ts) and ts[vp + 1] in "'’" and ts[vp + 2].lower() in self.closed: continue   # bookvoice (3)
            via = None
            if doer is None:
                p = how.split(":")[1]
                if self.play: continue                                              # bookvoice (2)
                if self.narrated and p == self.speaker:
                    at = e - 1 if how.startswith("pronoun") else k + 1
                    doer = (at, at + 1, ("#" + p,), ts[at], at); via = self.narrator_label
                else:
                    doer = self.resolve(i, k, p)
                    if doer is None: continue
                    via = p; self._resolved.setdefault(i, []).append(doer)

            used.update(range(k, vp + 1))
            dialogue = how.startswith("dialogue")
            obj = None if dialogue else self.object(ts, vp, starts)
            if self.use_pronouns and obj is None and not dialogue and ts[vp].lower() in self.closed: continue   # "she could", "Royall had once"
            rel = " ".join(ts[e:vp + 1]) if (self.use_pronouns and not dialogue) else " ".join(ts[k:vp + 1])
            out.append(self.prop("event", doer, rel, obj, i, lemma=lemma, via=via))
            out[-1]["dialogue"] = dialogue
        out += self.roles(ts, ns, starts, i)
        return out

    def object(self, ts, vp, starts):
        """the patient after the content verb at vp (or None)"""
        obj = None
        pa = self.R.run_at(ts, vp, 1 if self.R.side == "L" else -1, 2)
        if pa:
            between = ts[vp + 1:pa[0][0]]; end = pa[0][1]
            if self.v >= 3:                                                  # bookcheck (4): "several references"
                while end < len(ts) and ts[end].lower() in self.nounish: end += 1
            if not self.use_pronouns or all(x.lower() in self.det2 for x in between):
                obj = " ".join(ts[vp + 1:end])
        if self.use_pronouns and vp + 1 < len(ts):
            j = vp + 1
            while j < len(ts) and ts[j][:1].islower() and ts[j].lower() in self.det2: j += 1
            if j in starts: obj = " ".join(ts[vp + 1:j]) + (" " if j > vp + 1 else "") + starts[j][3]
        return obj

    def roles(self, ts, ns, starts, i):
        """roles by apposition: NAME , [closed] w1..w3 <closed> NAME2 ; NAME , <determiner> w1..w3 ,"""
        out = []
        for n in ns:
            s, e = n[0], n[1]
            if not (e < len(ts) and ts[e] == ",") or self.outside(ts, n[4] if self.use_pronouns else s): continue
            j = e + 1
            if j < len(ts) and ts[j].lower() in getattr(self.R, "negatives", ()): continue   # ", not listening to Porbus": no role
            if j < len(ts) and ts[j].lower() in self.closed: j += 1
            w = j
            while (w < len(ts) and w - j < 3 and is_word(ts[w]) and ts[w][:1].islower() and ts[w].lower() not in self.closed
                   and ts[w].lower() not in self.entities): w += 1
            if w == j or w >= len(ts): continue
            if ts[w].lower() in self.closed and w + 1 in starts:
                n2 = starts[w + 1]; out.append(self.prop("role", n, " ".join(ts[j:w + 1]), n2[3], i, okey=n2[2]))
            elif ts[w] == "," and e + 1 < j and ts[e + 1].lower() in self.det:
                out.append(self.prop("role", n, "is", " ".join(ts[e + 1:w]), i))
        return out

    def prop(self, kind, subj, rel, obj, i, lemma=None, okey=None, via=None):
        br = getattr(self, "bridges", {}).get(subj[2])
        return dict(ref=br[0] if br else None, ref_evidence=br[1:] if br else None,kind=kind, subj=subj[3], skey=subj[2], rel=rel, obj=obj, okey=okey, lemma=lemma, sent=i, via=via,
                    context=self.bid, title=self.title, real=self.real)

    @staticmethod
    def claim_key(p, v=3):
        if v >= 4:                                     # bookvoice (5): repetition needs content
            if p["kind"] != "event" or not p.get("obj") or p.get("dialogue"): return None
            return ("event", p["skey"], p["lemma"], p["obj"].split()[-1].lower())
        """what a repetition must share: subject key, verb lemma (or role relation), patient head (or object key)"""
        if p["kind"] == "event": return ("event", p["skey"], p["lemma"], " ".join((p["obj"] or "").split()[-1:]).lower())
        return ("role", p["skey"], p["rel"].lower(), p["okey"] or (p["obj"] or "").lower())

    @staticmethod
    def check(by_sentence, v=3):
        """bookcheck (6): {sentence: [propositions]} of one book -> each proposition gets check = SUPPORTED (with the
        other sentence) when another sentence of the book yields the same claim key, else UNCHECKED"""
        where = collections.defaultdict(set)
        for i, ps in by_sentence.items():
            for p in ps:
                key = Book.claim_key(p, v)
                if key is not None: where[key].add(i)
        for i, ps in by_sentence.items():
            for p in ps:
                key = Book.claim_key(p, v)
                others = sorted(where[key] - {i}) if key is not None else []
                p["check"] = "SUPPORTED" if others else "UNCHECKED"
                if others: p["support"] = min(others, key=lambda j: abs(j - i))

    @staticmethod
    def say(p, template="{title}: {body}"):
        """a book proposition is always said in its book's context (the template, with its words, is data from
        emergence/kb_bookworld.py); a resolved pronoun is shown"""
        subj = p["subj"] + (f" ({p['via']})" if p.get("via") else "")
        body = " ".join(x for x in (subj, p["rel"], p["obj"]) if x)
        return body if p.get("real") else template.format(title=p["title"], body=body)
