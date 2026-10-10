"""R24 run 1c: pronouns as REFERENCES in the generative story. Run 1b showed why resolution did not emerge: named
fillers at a sentence's first slot are mostly the SECOND most recent person (a name marks a switch), while the most
recent person is referred to by a pronoun 182/185 times -- names and pronouns are complementary forms of one choice.
So the story is: pick a referent from the state by rank; then pick its FORM (name or pronoun) given the rank; a
pronoun's word (he/she/him/her/his) depends on the referent's (latent) gender class. The referent of a pronoun is
never given -- it is inferred by expectation-maximisation over the three parameters P(rank), P(form | rank),
P(word | name). Resolution = the posterior's argmax. Still no labels: the gold agents score only.
Run: python learned/base/r24_em.py"""
import os, sys, json, math, random, collections
HERE = os.path.dirname(os.path.abspath(__file__)); os.chdir(HERE); sys.path.insert(0, HERE)
sys.argv = [sys.argv[0]]
import r24_tlm as T

GENDER_PRON = {"he", "she", "him", "her", "his"}; TOPK = 4; ITERS = 6


def occurrences(stories, names):
    """per story: the sequence of (pos, kind, filler-key or pronoun word, recency list snapshot) for REF slots, with the
    state advanced by names only (a pronoun does not change the recency order in this version)"""
    out = []
    for text in stories:
        persons = []; seq = []
        for s in T.SENT.split(text):
            toks = T.TOK.findall(s)
            if not toks: continue
            items = T.slotify(toks, names)
            for k, (sym, filler) in enumerate(items):
                pos = "first" if k == 0 else "later"
                if sym == "PERSON":
                    key = filler[0]; seq.append((pos, "name", key, list(persons)))
                    if key in persons: persons.remove(key)
                    persons.insert(0, key)
                elif sym == "PRON" and filler[0] in GENDER_PRON:
                    seq.append((pos, "pron", filler[0], list(persons)))
        out.append(seq)
    return out


class EM:
    def __init__(self):
        self.rank = collections.defaultdict(collections.Counter)      # pos -> rank -> expected count (known referents only)
        self.form = collections.defaultdict(collections.Counter)      # (pos, rank) -> form -> expected count
        self.word = collections.defaultdict(collections.Counter)      # name -> pronoun word -> expected count
        self.new = collections.defaultdict(lambda: [0.0, 0.0])        # pos -> [new names, total]

    def p_rank(self, pos, r): c = self.rank[pos]; return (c[r] + 0.5) / (sum(c.values()) + 0.5 * TOPK)
    def p_form(self, pos, r, f): c = self.form[(pos, r)]; return (c[f] + 0.5) / (sum(c.values()) + 1.0)
    def p_word(self, name, w): c = self.word[name]; return (c[w] + 0.5) / (sum(c.values()) + 0.5 * len(GENDER_PRON))

    def posterior(self, pos, word, persons):
        cands = persons[:TOPK]
        if not cands: return []
        ws = [self.p_rank(pos, r) * self.p_form(pos, r, "pron") * self.p_word(name, word) for r, name in enumerate(cands)]
        z = sum(ws); return [(name, r, w / z) for r, (name, w) in enumerate(zip(cands, ws))]

    def fit(self, seqs):
        for it in range(ITERS):
            rank = collections.defaultdict(collections.Counter); form = collections.defaultdict(collections.Counter)
            word = collections.defaultdict(collections.Counter); new = collections.defaultdict(lambda: [0.0, 0.0]); ll = 0.0
            for seq in seqs:
                for pos, kind, x, persons in seq:
                    if kind == "name":
                        new[pos][1] += 1
                        if x in persons[:TOPK]:
                            r = persons.index(x); rank[pos][r] += 1; form[(pos, r)]["name"] += 1
                        else: new[pos][0] += 1
                    else:
                        post = self.posterior(pos, x, persons) if it else [(n, r, 1.0 / len(persons[:TOPK])) for r, n in enumerate(persons[:TOPK])]
                        for name, r, p in post:
                            rank[pos][r] += p; form[(pos, r)]["pron"] += p; word[name][x] += p
            self.rank, self.form, self.word, self.new = rank, form, word, new
        return self

    def resolve(self, pos, word, persons):
        post = self.posterior(pos, word, persons)
        return max(post, key=lambda t: t[2])[0] if post else None


def main():
    data = json.load(open("stories_train_v2.json", encoding="utf-8")); random.Random(24).shuffle(data); train = data[:7000]; held = data[7000:]
    names = T.mid_caps([s["text"] for s in train])
    M = EM().fit(occurrences([s["text"] for s in train], names))
    print("learned P(form = pronoun | rank) at a sentence's first slot:", {r: round(M.p_form("first", r, "pron"), 2) for r in range(TOPK)})
    print("learned P(rank) at the first slot:", {r: round(M.p_rank("first", r), 2) for r in range(TOPK)})
    some = sorted(M.word.items(), key=lambda kv: -sum(kv[1].values()))[:6]
    print("learned pronoun words per name (gender emerges?):", [(n, {w: round(c, 1) for w, c in cnt.most_common(2)}) for n, cnt in some])
    ok = tot = 0; by = collections.Counter()
    for s in held:
        if not s.get("events"): continue
        persons = []; sents = [x for x in T.SENT.split(s["text"]) if x.strip()]
        for k, sent in enumerate(sents):
            toks = T.TOK.findall(sent)
            if not toks: continue
            items = T.slotify(toks, names)
            if items and items[0][0] == "PRON" and items[0][1][0] in ("he", "she"):
                gold = [e[1] for e in s["events"] if e[0] == k]
                if gold:
                    guess = M.resolve("first", items[0][1][0], persons); tot += 1; ok += (guess == gold[0]); by["most-recent"] += (persons[:1] == [gold[0]])
            for sym, filler in items:
                if sym == "PERSON":
                    if filler[0] in persons: persons.remove(filler[0])
                    persons.insert(0, filler[0])
    print(f"R24-b (run 1c, EM resolver, no labels): pronoun subject -> gold agent on held-out {ok}/{tot} = {ok / max(1, tot):.2f} (bar >= 0.80 -> {'PASS' if tot and ok / tot >= 0.8 else 'MISS'}); the plain most-recent rule would score {by['most-recent']}")
    json.dump(dict(pron=(ok, tot), p_form_first={r: M.p_form("first", r, "pron") for r in range(TOPK)}), open("r24_em_results.json", "w"))


if __name__ == "__main__":
    main()
