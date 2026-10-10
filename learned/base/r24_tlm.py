"""R24: the next-word game through the epistemic layers (R24_prereg.md). A template language model with no n-gram
memory: sentences are templates over PERSON / PRON / ENT slots, fillers come from a recency-ranked state of the
story so far, and everything is learned from raw text by counting. Scored by bits per token on held-out text
against unigram and bigram baselines, plus pronoun resolution against the generator's gold agents (scoring only).
Run: python learned/base/r24_tlm.py [--data stories_train_v2.json] [--min-count 2]"""
import os, sys, re, json, math, random, collections
HERE = os.path.dirname(os.path.abspath(__file__)); os.chdir(HERE)
TOK = re.compile(r"[A-Za-z][A-Za-z'-]*|[.,;!?]")
SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'])")
PRON = {"he", "she", "him", "her", "his", "they", "them", "it"}
DET = {"the", "a", "an", "his", "her", "their", "its"}
FLOOR = 0.01


def arg(name, default):
    return type(default)(sys.argv[sys.argv.index(name) + 1]) if name in sys.argv else default


def mid_caps(stories):
    """words seen capitalised NOT at a sentence start -> names (surface cue, no lexicon)"""
    caps = collections.Counter()
    for text in stories:
        for s in SENT.split(text):
            t = TOK.findall(s)
            for w in t[1:]:
                if w[0].isupper() and w.lower() not in PRON: caps[w] += 1
    return {w for w, c in caps.items() if c >= 2}


def slotify(tokens, names):
    """tokens -> list of (symbol, filler-tokens); symbol is a literal word or PERSON / PRON / ENT"""
    out = []; i = 0
    while i < len(tokens):
        w = tokens[i]; wl = w.lower()
        if w in names or (w[0].isupper() and i > 0 and wl not in PRON): out.append(("PERSON", [w])); i += 1; continue
        if wl in PRON and not (i > 0 and tokens[i - 1].lower() in DET): out.append(("PRON", [wl])); i += 1; continue
        if wl in DET and i + 1 < len(tokens) and tokens[i + 1].islower() and tokens[i + 1] not in ("and", "to", "of"):
            j = i + 2
            if j < len(tokens) and tokens[j].islower() and tokens[j] not in STOP: j += 1
            out.append(("ENT", [wl] + [x.lower() for x in tokens[i + 1:j]])); i = j; continue
        out.append((wl, [wl])); i += 1
    return out


STOP = {"and", "to", "of", "at", "in", "on", "by", "near", "with", "for", "from", "into", "back", "down", "up", "home", "there", "then", "when", "while",
        "was", "were", "is", "had", "who", "that", "which", "but", "so", "because", "without", "until", "after", "before", "first", "second", "last", "away", "together"}


class State:
    def __init__(self): self.persons = []; self.ents = []

    def mention(self, kind, filler):
        key = " ".join(filler[1:]) if kind == "ENT" else filler[0]
        lst = self.persons if kind == "PERSON" else self.ents
        if key in lst: lst.remove(key)
        lst.insert(0, key)

    def ranked(self, kind): return self.persons if kind == "PERSON" else self.ents


class TLM:
    def __init__(self, min_count=2):
        self.min_count = min_count; self.templates = collections.Counter(); self.rank = {"PERSON": collections.Counter(), "ENT": collections.Counter()}
        self.new = {"PERSON": [0, 0], "ENT": [0, 0]}; self.slot_uni = {"PERSON": collections.Counter(), "ENT": collections.Counter(), "PRON": collections.Counter()}
        self.floor = collections.Counter(); self.det_uni = collections.Counter(); self.ent_len = collections.Counter()

    def learn(self, stories, names):
        for text in stories:
            st = State()
            for s in SENT.split(text):
                toks = TOK.findall(s)
                if not toks: continue
                items = slotify(toks, names); self.templates[tuple(sym for sym, _ in items)] += 1
                for sym, filler in items:
                    for w in filler: self.floor[w] += 1
                    if sym in ("PERSON", "ENT"):
                        key = " ".join(filler[1:]) if sym == "ENT" else filler[0]; ranked = st.ranked(sym)
                        if key in ranked: self.rank[sym][ranked.index(key)] += 1; self.new[sym][1] += 1
                        else:
                            self.new[sym][0] += 1; self.new[sym][1] += 1
                            if sym == "ENT": self.det_uni[filler[0]] += 1; self.ent_len[len(filler) - 1] += 1
                            for w in (filler[1:] if sym == "ENT" else filler): self.slot_uni[sym][w] += 1
                        st.mention(sym, filler)
                    elif sym == "PRON": self.slot_uni["PRON"][filler[0]] += 1
        self.templates = collections.Counter({t: c for t, c in self.templates.items() if c >= self.min_count})
        self.T = sum(self.templates.values()); self.F = sum(self.floor.values()); self.V = len(self.floor) + 1

    def p_floor(self, w): return (self.floor[w] + 0.5) / (self.F + 0.5 * self.V)

    def p_filler(self, sym, filler, st):
        """probability of a whole filler at a slot of kind sym, given the state"""
        if sym == "PRON":
            n = sum(self.slot_uni["PRON"].values()); return (self.slot_uni["PRON"][filler[0]] + 0.5) / (n + 0.5 * len(PRON))
        key = " ".join(filler[1:]) if sym == "ENT" else filler[0]; ranked = st.ranked(sym)
        new0, new1 = self.new[sym]; p_new = (new0 + 1) / (new1 + 2); R = sum(self.rank[sym].values())
        if key in ranked:
            k = ranked.index(key); return (1 - p_new) * (self.rank[sym][k] + 0.5) / (R + 0.5 * 20)
        uni = self.slot_uni[sym]; n = sum(uni.values()); V = len(uni) + 1; p = p_new
        if sym == "ENT":
            d = sum(self.det_uni.values()); p *= (self.det_uni[filler[0]] + 0.5) / (d + 0.5 * len(DET))
            L = sum(self.ent_len.values()); p *= (self.ent_len[len(filler) - 1] + 0.5) / (L + 1)
            for w in filler[1:]: p *= (uni[w] + 0.5) / (n + 0.5 * V)
        else: p *= (uni[filler[0]] + 0.5) / (n + 0.5 * V)
        return p

    def score_sentence(self, toks, names, st):
        """bits for the sentence under the template mixture, per-token accounting (fillers charged at their slot);
        returns (bits, ntokens, covered, items)"""
        items = slotify(toks, names); syms = tuple(sym for sym, _ in items)
        n = len(toks); bits = 0.0; covered = syms in self.templates
        # mixture over templates consistent with the prefix, item by item
        cands = {t: c for t, c in self.templates.items() if len(t) == len(syms)} if True else {}
        alive = dict(cands); total = self.T
        for k, (sym, filler) in enumerate(items):
            # probability of this item = sum over alive templates whose k-th symbol matches, of template weight * item prob
            p_struct = 0.0; w_alive = sum(alive.values()) or 0.0
            if w_alive:
                match = {t: c for t, c in alive.items() if t[k] == sym}
                if match:
                    pi = self.p_filler(sym, filler, st) if sym in ("PERSON", "ENT", "PRON") else 1.0
                    p_struct = (sum(match.values()) / w_alive) * pi
                    alive = match
                else: alive = {}
            p_floor = 1.0
            for w in filler: p_floor *= self.p_floor(w)
            p = (1 - FLOOR) * p_struct + FLOOR * p_floor
            bits += -math.log2(p)
            if sym in ("PERSON", "ENT"): st.mention(sym, filler)
        return bits, n, covered, items

    def best_person(self, st):
        """the learner's most probable PERSON at a slot given the state (pronoun resolution by recency weights)"""
        ranked = st.ranked("PERSON")
        if not ranked: return None
        k = max(range(len(ranked)), key=lambda k: self.rank["PERSON"][k])
        return ranked[k]


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
            if order == 1: p = (uni[w] + 0.1) / (N + 0.1 * V)
            else: p = (bi[(prev, w)] + 0.1) / (ctx[prev] + 0.1 * V)
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
    # R24-b: pronoun-subject sentences, gold agent from the exact events (scoring only)
    ok = tot = 0
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
                    guess = M.best_person(st); tot += 1; ok += (guess == gold[0])
            M.score_sentence(toks, names, st)
    print(f"R24-b: pronoun subject -> gold agent on held-out: {ok}/{tot} = {ok / max(1, tot):.2f} (bar >= 0.80 -> {'PASS' if tot and ok / tot >= 0.8 else 'MISS'})")
    print(f"R24-c: {len(M.templates)} templates (count >= {M.min_count}); recency weights PERSON {dict(sorted(M.rank['PERSON'].items())[:6])} ENT {dict(sorted(M.rank['ENT'].items())[:6])}; new-rate PERSON {M.new['PERSON'][0] / max(1, M.new['PERSON'][1]):.2f} ENT {M.new['ENT'][0] / max(1, M.new['ENT'][1]):.2f}")
    for t, c in M.templates.most_common(10): print("   ", c, " ".join(t))
    json.dump(dict(bits=tlm, unigram=uni, bigram=bi, coverage=(cov, ns), pron=(ok, tot), templates=len(M.templates)), open("r24_results.json", "w"))


if __name__ == "__main__":
    main()
