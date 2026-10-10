"""R24: the next-word game through the epistemic layers (R24_prereg.md). A template language model with no n-gram
memory: sentences are templates over PERSON / PRON / ENT slots, fillers come from a ranked state of the story so far,
and everything is learned from raw text by counting. Scored by bits per token on held-out text against unigram and
bigram baselines, plus pronoun resolution against the generator's gold agents (scoring only).
Run 1b: the state keeps TWO rankings of persons -- by recency of any mention, and by recency as a sentence-initial
slot (the last subject) -- and the filler weights are learned per slot position (first item of the sentence or later);
the mixture of the two rankings is the learner's resolver.
Run: python learned/base/r24_tlm.py [--data stories_train_v2.json] [--min-count 2]"""
import os, sys, re, json, math, random, collections
HERE = os.path.dirname(os.path.abspath(__file__)); os.chdir(HERE)
TOK = re.compile(r"[A-Za-z][A-Za-z'-]*|[.,;!?]")
SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'])")
PRON = {"he", "she", "him", "her", "his", "they", "them", "it", "i", "you", "we", "me", "my", "your", "us", "our"}   # run 2d: first/second person are pronoun forms too
DET = {"the", "a", "an", "his", "her", "their", "its"}
STOP = {"and", "to", "of", "at", "in", "on", "by", "near", "with", "for", "from", "into", "back", "down", "up", "home", "there", "then", "when", "while", "under", "behind", "over", "across", "through", "toward", "towards", "inside", "outside", "onto",
        "was", "were", "is", "had", "who", "that", "which", "but", "so", "because", "without", "until", "after", "before", "first", "second", "last", "away", "together"}
FLOOR = 0.01; RANKS = ("recency", "subject"); K = 20


def arg(name, default):
    return type(default)(sys.argv[sys.argv.index(name) + 1]) if name in sys.argv else default


COMMON = set()
NOT_NAME = {"then", "right", "after", "before", "when", "while", "one", "later", "meanwhile", "there", "here", "now", "so", "but", "and", "everyone", "someone", "no"}


def mid_caps(stories):
    """words seen capitalised NOT at a sentence start -> names (surface cue, no lexicon); also records the common
    lower-case vocabulary so that an UNKNOWN capitalised word at a sentence start counts as a name too"""
    caps = collections.Counter(); low = collections.Counter()
    for text in stories:
        for s in SENT.split(text):
            t = TOK.findall(s)
            for w in t[1:]:
                if w[0].isupper() and w.lower() not in PRON: caps[w] += 1
            for w in t:
                if w.islower(): low[w] += 1
    COMMON.clear(); COMMON.update(w for w, c in low.items() if c >= 3)
    return {w for w, c in caps.items() if c >= 2}


def slotify(tokens, names):
    """tokens -> list of (symbol, filler-tokens); symbol is a literal word or PERSON / PRON / ENT"""
    out = []; i = 0
    while i < len(tokens):
        w = tokens[i]; wl = w.lower()
        if wl not in PRON and wl not in COMMON and wl not in NOT_NAME and (w in names or (w[0].isupper() and (i > 0 or len(w) > 2))): out.append(("PERSON", [w])); i += 1; continue
        if wl in PRON and not (i > 0 and tokens[i - 1].lower() in DET): out.append(("PRON", [wl])); i += 1; continue
        if wl in DET and i + 1 < len(tokens) and tokens[i + 1].islower() and tokens[i + 1] not in ("and", "to", "of"):
            j = i + 2
            if j < len(tokens) and tokens[j].islower() and tokens[j] not in STOP and tokens[j] not in DET and tokens[j] not in PRON: j += 1   # 'the morning the sled': a determiner ends the span
            out.append(("ENT", [wl] + [x.lower() for x in tokens[i + 1:j]])); i = j; continue
        out.append((wl, [wl])); i += 1
    return out


def key_of(sym, filler): return " ".join(filler[1:]) if sym == "ENT" else filler[0]


class State:
    def __init__(self): self.persons = []; self.subjects = []; self.ents = []

    def mention(self, sym, filler, first=False):
        key = key_of(sym, filler)
        for lst, on in ((self.persons if sym == "PERSON" else self.ents, True), (self.subjects, sym == "PERSON" and first)):
            if not on: continue
            if key in lst: lst.remove(key)
            lst.insert(0, key)

    def ranking(self, name):
        return {"recency": self.persons, "subject": self.subjects}[name]


class TLM:
    def __init__(self, min_count=2):
        self.min_count = min_count; self.templates = collections.Counter()
        self.rank = collections.defaultdict(collections.Counter)         # (kind, pos, ranking) -> rank or "none" -> count
        self.new = collections.defaultdict(lambda: [0, 0])               # (kind, pos) -> [new, total]
        self.slot_uni = {"PERSON": collections.Counter(), "ENT": collections.Counter(), "PRON": collections.Counter()}
        self.floor = collections.Counter(); self.det_uni = collections.Counter(); self.ent_len = collections.Counter()

    def learn(self, stories, names):
        for text in stories:
            st = State()
            for s in SENT.split(text):
                toks = TOK.findall(s)
                if not toks: continue
                items = slotify(toks, names); self.templates[tuple(sym for sym, _ in items)] += 1
                for k, (sym, filler) in enumerate(items):
                    pos = "first" if k == 0 else "later"
                    for w in filler: self.floor[w] += 1
                    if sym in ("PERSON", "ENT"):
                        key = key_of(sym, filler); known = st.persons if sym == "PERSON" else st.ents
                        self.new[(sym, pos)][1] += 1
                        if key in known:
                            self.rank[(sym, pos, "recency")][known.index(key)] += 1
                            if sym == "PERSON": self.rank[(sym, pos, "subject")][st.subjects.index(key) if key in st.subjects else "none"] += 1
                        else:
                            self.new[(sym, pos)][0] += 1
                            if sym == "ENT": self.det_uni[filler[0]] += 1; self.ent_len[len(filler) - 1] += 1
                            for w in (filler[1:] if sym == "ENT" else filler): self.slot_uni[sym][w] += 1
                        st.mention(sym, filler, first=(k == 0))
                    elif sym == "PRON": self.slot_uni["PRON"][filler[0]] += 1
        self.templates = collections.Counter({t: c for t, c in self.templates.items() if c >= self.min_count})
        self.T = sum(self.templates.values()); self.F = sum(self.floor.values()); self.V = len(self.floor) + 1

    def p_floor(self, w): return (self.floor[w] + 0.5) / (self.F + 0.5 * self.V)

    def p_rank(self, sym, pos, ranking, key, st):
        c = self.rank[(sym, pos, ranking)]; R = sum(c.values()); lst = st.ranking(ranking) if sym == "PERSON" else st.ents
        if key in lst: return (c[lst.index(key)] + 0.5) / (R + 0.5 * K)
        others = [x for x in st.persons if x not in lst] if sym == "PERSON" else []
        return (c["none"] + 0.5) / (R + 0.5 * K) / max(1, len(others))

    def p_known(self, sym, pos, key, st):
        if sym == "ENT": return self.p_rank(sym, pos, "recency", key, st)
        return 0.5 * self.p_rank(sym, pos, "recency", key, st) + 0.5 * self.p_rank(sym, pos, "subject", key, st)

    def p_filler(self, sym, filler, st, pos):
        """probability of a whole filler at a slot of kind sym, given the state"""
        if sym == "PRON":
            n = sum(self.slot_uni["PRON"].values()); return (self.slot_uni["PRON"][filler[0]] + 0.5) / (n + 0.5 * len(PRON))
        key = key_of(sym, filler); known = st.persons if sym == "PERSON" else st.ents
        new0, new1 = self.new[(sym, pos)]; p_new = (new0 + 1) / (new1 + 2)
        if key in known: return (1 - p_new) * self.p_known(sym, pos, key, st)
        uni = self.slot_uni[sym]; n = sum(uni.values()); V = len(uni) + 1; p = p_new
        if sym == "ENT":
            d = sum(self.det_uni.values()); p *= (self.det_uni[filler[0]] + 0.5) / (d + 0.5 * len(DET))
            L = sum(self.ent_len.values()); p *= (self.ent_len[len(filler) - 1] + 0.5) / (L + 1)
            for w in filler[1:]: p *= (uni[w] + 0.5) / (n + 0.5 * V)
        else: p *= (uni[filler[0]] + 0.5) / (n + 0.5 * V)
        return p

    def score_sentence(self, toks, names, st):
        """bits for the sentence under the template mixture (fillers charged at their slot); updates the state"""
        items = slotify(toks, names); syms = tuple(sym for sym, _ in items)
        n = len(toks); bits = 0.0; covered = syms in self.templates
        alive = {t: c for t, c in self.templates.items() if len(t) == len(syms)}
        for k, (sym, filler) in enumerate(items):
            pos = "first" if k == 0 else "later"; p_struct = 0.0; w_alive = sum(alive.values())
            if w_alive:
                match = {t: c for t, c in alive.items() if t[k] == sym}
                if match:
                    pi = self.p_filler(sym, filler, st, pos) if sym in ("PERSON", "ENT", "PRON") else 1.0
                    p_struct = (sum(match.values()) / w_alive) * pi; alive = match
                else: alive = {}
            p_floor = 1.0
            for w in filler: p_floor *= self.p_floor(w)
            bits += -math.log2((1 - FLOOR) * p_struct + FLOOR * p_floor)
            if sym in ("PERSON", "ENT"): st.mention(sym, filler, first=(k == 0))
        return bits, n, covered, items

    def best_person(self, st, pos="first"):
        """the learner's most probable known PERSON at a slot in this position (its resolver)"""
        if not st.persons: return None
        return max(st.persons, key=lambda key: self.p_known("PERSON", pos, key, st))


def ngram_bits(train, held, order):
    """add-0.1 unigram / bigram baselines, bits per token on held-out"""
    uni = collections.Counter(); bi = collections.Counter(); ctx = collections.Counter()
    for text in train:
        prev = "<s>"
        for w in [x.lower() for x in TOK.findall(text)]:
            uni[w] += 1; bi[(prev, w)] += 1; ctx[prev] += 1; prev = w
    V = len(uni) + 1; N = sum(uni.values()); bits = 0.0; n = 0
    for text in held:
        prev = "<s>"
        for w in [x.lower() for x in TOK.findall(text)]:
            pu = (uni[w] + 0.1) / (N + 0.1 * V)
            p = pu if order == 1 else 0.7 * (bi[(prev, w)] + 0.1) / (ctx[prev] + 0.1 * V) + 0.3 * pu      # interpolated bigram: a real shortcut
            bits += -math.log2(p); n += 1; prev = w
    return bits / n


def main():
    data = json.load(open(arg("--data", "stories_train_v2.json"), encoding="utf-8"))
    random.Random(24).shuffle(data); split = int(len(data) * 0.875); train = data[:split]; held = data[split:]
    names = mid_caps([s["text"] for s in train])
    M = TLM(arg("--min-count", 2)); M.learn([s["text"] for s in train], names)
    bits = n = cov = ns = 0
    for s in held:
        st = State()
        for sent in SENT.split(s["text"]):
            toks = TOK.findall(sent)
            if not toks: continue
            b, k, c, _ = M.score_sentence(toks, names, st); bits += b; n += k; cov += c; ns += 1
    tlm = bits / n; uni = ngram_bits([s["text"] for s in train], [s["text"] for s in held], 1); bi = ngram_bits([s["text"] for s in train], [s["text"] for s in held], 2)
    print(f"held-out {len(held)} stories, {ns} sentences, {n} tokens")
    print(f"bits/token: template learner {tlm:.2f} | unigram {uni:.2f} | bigram {bi:.2f}   (R24-a: template <= bigram + 0.5 -> {'PASS' if tlm <= bi + 0.5 else 'MISS'})")
    print(f"template coverage of held-out sentences: {cov}/{ns} = {cov / ns:.2f} (bar >= 0.80 -> {'PASS' if cov / ns >= 0.8 else 'MISS'})")
    ok = tot = 0; by = collections.Counter()
    for s in held:
        if not s.get("events"): continue
        st = State(); sents = [x for x in SENT.split(s["text"]) if x.strip()]
        for k, sent in enumerate(sents):
            toks = TOK.findall(sent)
            if not toks: continue
            items = slotify(toks, names)
            if items and items[0][0] == "PRON" and items[0][1][0] in ("he", "she"):
                gold = [e[1] for e in s["events"] if e[0] == k]
                if gold:
                    guess = M.best_person(st, "first"); tot += 1; ok += (guess == gold[0])
                    by["recency0"] += (st.persons[:1] == [gold[0]]); by["subject0"] += (st.subjects[:1] == [gold[0]])
            M.score_sentence(toks, names, st)
    print(f"R24-b: pronoun subject -> gold agent on held-out: {ok}/{tot} = {ok / max(1, tot):.2f} (bar >= 0.80 -> {'PASS' if tot and ok / tot >= 0.8 else 'MISS'}); plain most-recent {by['recency0']}, plain last-subject {by['subject0']}")
    w = {f"{k[0]}/{k[1]}/{k[2]}": dict(sorted(c.items(), key=lambda kv: str(kv[0]))[:5]) for k, c in M.rank.items()}
    print(f"R24-c: {len(M.templates)} templates (count >= {M.min_count}); rank weights {w}")
    for t, c in M.templates.most_common(8): print("   ", c, " ".join(t))
    json.dump(dict(bits=tlm, unigram=uni, bigram=bi, coverage=(cov, ns), pron=(ok, tot), templates=len(M.templates)), open("r24_results.json", "w"))


if __name__ == "__main__":
    main()
