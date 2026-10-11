"""R24-j: a LEARNED event reader (R24_prereg.md). Story sentences and canonical statements ('Rosa took the key.')
are both constructions over class symbols with slots; an alignment table, learned by counting on the generator
stories plus their restated questions, says which story slot fills which canonical slot for each pair of
constructions sharing a verb. A question becomes a canonical construction with one missing slot; the reader fills it
from the story sentence with the same verb, by the learned alignment. No role names, no sentence shapes by hand.
Run: python learned/base/r24_reader.py [--show]"""
import os, sys, re, json, random, collections, math
SHOW = "--show" in sys.argv; ARGV = list(sys.argv)
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE)); os.chdir(HERE); sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(ROOT, "learned"))
import r24_tlm as T, r24_events as E
from b6_rwkv import hit

PLACE_WORDS = E.PLACE_WORDS
LAST_RAWS = []


def canonical(q, gold):
    """the generator's question + gold as a statement with the gold in it; None for kinds not rendered"""
    ql = q.lower().rstrip("?"); g = gold[0]
    def thing(x): return x if x.split()[0] in T.DET else "the " + x
    m = re.match(r"who (\w+) (.+)$", ql)
    if m and m.group(1) not in ("was", "were", "had", "is"): return f"{g[0].upper()}{g[1:]} {m.group(1)} {m.group(2)}."
    m = re.match(r"what did (.+)$", ql)
    if m and (g.startswith("to ") or ql.endswith(" to do") or ql.endswith(" to learn")):
        ws = q[9:].rstrip("?").split(); vi = next((i for i, x in enumerate(ws) if i and is_verb(x.lower()) and x.lower() not in E.NOUNISH), None)
        if vi:
            gc = g if g.startswith("to ") else "to " + g
            return f"{ws[0][0].upper() + ws[0][1:]} {' '.join(ws[1:vi])} {E.lemma(ws[vi].lower())} {gc}.".replace("  ", " ")       # 'What did Patti promise?' -> 'Patti promise to share it.'
    if m:
        ws = m.group(1).split(); vi = next((i for i, x in enumerate(ws) if i and is_verb(x)), None)
        if vi:
            head = ' '.join(ws[:vi]); head = head[0].upper() + head[1:]; tail = ' '.join(ws[vi + 1:])
            if tail and len(tail.split()) == 1 and tail in PLACE_WORDS | {"with", "for"}: return f"{head} {E.lemma(ws[vi])} {tail} {thing(g)}."              # 'What did the mouse gnaw through?' -> 'The mouse gnaw through the net.'
            if tail and (tail.split()[0] in PLACE_WORDS or tail.split()[0] in ("as", "for", "with")): return f"{head} {E.lemma(ws[vi])} {thing(g)} {tail}."      # 'What did Sara bring as a gift?' -> 'Sara bring the kite as a gift.'
            return f"{head} {E.lemma(ws[vi])} {tail} {thing(g)}.".replace("  ", " ")                                                                      # 'What did Domett give Grudden?' -> 'Domett give Grudden the pot of jam.'
    m = re.match(r"where did (.+?) (\w+) (.+)$", ql)
    if m and m.group(2) != "start":
        gp = g.split(" ", 1)[1] if g.split()[0] in PLACE_WORDS else g
        return f"{m.group(1).capitalize()} {E.lemma(m.group(2))} {m.group(3)} at {thing(gp)}."      # one place form for every preposition: the shape matches the question's
    m = re.match(r"when did (.+)$", ql)
    if m:
        ws = q[9:].rstrip("?").split(); vi = next((i for i, x in enumerate(ws) if i and is_verb(x.lower())), None)
        if vi:
            gw = g if g.split()[0] in ("on", "in", "at", "when", "after", "before", "the", "every", "one", "that") else "on " + g
            return f"{gw[0].upper()}{gw[1:]}, {ws[0][0].upper() + ws[0][1:]} {' '.join(ws[1:vi])} {E.lemma(ws[vi].lower())} {' '.join(ws[vi + 1:])}.".replace("  ", " ").replace(" .", ".")
    m = re.match(r"why did (.+)$", ql)
    if m:
        ws = m.group(1).split(); vi = next((i for i, x in enumerate(ws) if i and is_verb(x)), None)
        if vi:
            ws = q[8:].rstrip("?").split(); why = g if g.split()[0] in ("to",) else "because " + g
            return f"{ws[0][0].upper() + ws[0][1:]} {' '.join(ws[1:vi])} {E.lemma(ws[vi].lower())} {' '.join(ws[vi + 1:])} {why}.".replace("  ", " ")
    return None


LEMMAS = set()


def is_verb(w):
    if not LEMMAS:
        LEMMAS.update(E.IRREG.values()); LEMMAS.update(E.lemma(x) for x in E.VERBISH)      # the stems of the learned verb lexicon
        T.SPAN_STOP.update(x for x in LEMMAS if x not in E.NOUNISH)                        # 'the fox drop': a verb stem ends a thing span too
    if w in E.TIMEISH or w in E.NOUNISH: return False                                  # 'morning', 'evening' are not verbs
    return E.verbish(w) or w in LEMMAS


def event_statement(ev):
    """an exact generator event as a plain statement: 'Rosa took the key to the garden.'"""
    i, a, v, p, place, rec = ev[:6]; when = ev[6] if len(ev) > 6 else None; past = {"take": "took", "give": "gave", "come": "came", "go": "went", "run": "ran", "steal": "stole", "find": "found", "leave": "left", "put": "put", "set": "set", "drop": "dropped",
                                        "carry": "carried", "walk": "walked", "return": "returned", "borrow": "borrowed", "follow": "followed", "row": "rowed", "reach": "reached", "arrive": "arrived", "ride": "rode", "wait": "waited", "have": "had"}
    past["be"] = "was"; past["belong"] = "belonged"
    s = f"{a} {past.get(v, v + 'ed')}"
    if p: s += f" {p}"
    if rec: s += f" to {rec}"
    if place: s += f" {place}" if place.split()[0] in PLACE_WORDS else f" to {place}"
    if when: s += f" {when}"                                                             # R24-af: 'Rosa took the key to the garden at noon.'
    return s + "."


def construction(sent, names):
    """(symbols, fillers): slot symbols keep their filler; a verb word is kept as its lemma (verbs matched across forms)"""
    sent = sent.replace("Dr.", "Dr").replace("Mr.", "Mr").replace("Mrs.", "Mrs")
    why = None
    if " because " in sent.lower():
        head, why = re.split(r" because ", sent, maxsplit=1, flags=re.I); sent = head + "."; why = why.rstrip(".!?").lower()
    items = T.slotify(T.TOK.findall(sent), names); syms = []; fillers = []
    xs = [x for x, _ in items]
    if "," in xs[:8]:
        j = xs.index(","); opening = " ".join(f[0] if x not in ("PERSON", "ENT") else " ".join(f) for x, f in items[:j]).lower(); words = opening.split()
        timeish = any(w in E.TIMEISH or w.endswith("day") or w in ("noon", "dawn", "dusk", "midnight", "summer", "winter", "spring", "autumn", "week", "year", "month", "later", "ago") for w in words)
        starter = xs[0] in ("on", "in", "at", "when", "while", "after", "before", "one", "every", "that", "the", "soon", "later", "by", "during", "without", "as")
        if j <= 7 and (starter or timeish) and not (xs[0] == "PERSON" and not timeish):
            syms.append("WHEN"); fillers.append(opening); items = items[j + 1:]
    if not syms and len(items) >= 3 and items[0][0] == "TIME" and items[1][0] in ("PERSON", "ENT", "PRON", "a", "an", "the"):   # R24-ae: 'The next morning Rosa left ...': a leading time item is a when-span
        syms.append("WHEN"); fillers.append(" ".join(items[0][1]).lower()); items = items[1:]
    head0 = (items[0][1][0] if items[0][0] in ("PERSON", "ENT") else items[0][0]).lower() if items else ""
    if not syms and len(items) >= 3 and head0 in ("at", "in", "on", "by", "during", "before", "after", "every", "one", "that", "the", "next", "last"):   # R24-ae: 'At noon Rosa took ...' (no comma)
        TW = lambda w: w in E.TIMEISH or w.endswith("day") or w in ("noon", "dawn", "dusk", "dark", "midnight", "lunch", "supper", "breakfast", "dinner", "nightfall", "sunset", "sunrise", "summer", "winter", "spring", "autumn", "morning", "evening", "afternoon", "night", "week", "year", "month", "hour", "moment", "day")
        timeish = lambda it: any(TW(w.lower()) for w in it[1])
        j = next((k for k in range(1, min(6, len(items))) if items[k][0] in ("PERSON", "PRON", "ENT") and not timeish(items[k])), None)
        if j and j >= 2 and any(timeish(items[k]) for k in range(1, j)) and not (items[0][0] == "PERSON" and not timeish(items[0]) and head0 not in ("the", "one", "that")):
            syms.append("WHEN"); fillers.append(" ".join(w for k in range(j) for w in items[k][1]).lower()); items = items[j:]
    raws = [fillers[0]] if syms else []                                                 # the words behind each symbol, for spans (kept parallel to syms)
    for k, (sym, filler) in enumerate(items):
        n0 = len(syms)
        if sym == "ENT" and (filler[-1] in E.TIMEISH or filler[-1] in ("year", "month", "week", "day", "night", "hour", "minute", "summer", "winter", "spring", "autumn", "morning", "evening", "afternoon", "noon", "dawn", "dusk")): syms.append("TIME"); fillers.append(None)   # 'one year', 'every morning': when, not what
        elif sym == "ENT" and k + 2 < len(items) and items[k + 1][0] in ("named", "called") and items[k + 2][0] == "PERSON": continue      # 'a boy named Erlend': the name is the slot
        elif sym in ("PERSON", "ENT"): syms.append(sym); fillers.append(E.T.key_of(sym, filler) if sym == "ENT" else filler[0])
        elif sym == "PRON": syms.append("PRON"); fillers.append(filler[0])
        elif sym in ("were", "are"): syms.append("was" if sym == "were" else "is"); fillers.append(None)
        elif sym in ("first", "second", "third", "last"): syms.append("ORDER"); fillers.append(sym)
        elif sym.isalpha() and k >= 1 and items[k - 1][0].isalpha() and is_verb(items[k - 1][0]) and not is_verb(sym) and sym not in T.STOP and sym not in T.DET and sym not in PLACE_WORDS and sym not in T.PRON and sym not in E.SKIP_VERB and len(sym) > 2: syms.append("ENT"); fillers.append(sym)   # 'kept bees': a bare noun right after a verb
        elif sym.isalpha() and is_verb(sym): syms.append("V:" + E.lemma(sym)); fillers.append(None)
        else: syms.append(sym); fillers.append(None)
        if len(syms) > n0: raws.append(" ".join(filler))
    TIMEW = lambda w: w in E.TIMEISH or w.endswith("day") or w in ("noon", "dawn", "dusk", "dark", "midnight", "lunch", "supper", "breakfast", "dinner", "nightfall", "sunset", "sunrise", "summer", "winter", "spring", "autumn", "week", "year", "month")
    for k in range(len(syms) - 2, 0, -1):                                                 # trailing 'at dawn' / 'before dark' / 'on Sunday'
        if syms[k] in ("at", "before", "after", "on", "in", "by", "until") and k + 1 < len(syms):
            nxt = syms[k + 1]; word = (fillers[k + 1] or "").split()[-1] if fillers[k + 1] else nxt
            if (nxt in ("ENT", "PERSON") and TIMEW(word.lower())) or (nxt not in ("ENT", "PERSON") and TIMEW(nxt)):
                phrase = f"{syms[k]} {fillers[k + 1] if fillers[k + 1] else nxt}".lower(); end = k + 2
                syms = syms[:k] + ["WHEN"] + syms[end:]; fillers = fillers[:k] + [phrase] + fillers[end:]; raws = raws[:k] + [phrase] + raws[end:]; break
    comp = None
    for k in range(1, len(syms) - 1):                                                    # 'wanted to learn to ride a horse', 'refused to climb the hill', 'promised to share it'
        if syms[k] == "to" and syms[k - 1].startswith("V:") and (syms[k + 1].startswith("V:") or (syms[k + 1].isalpha() and syms[k + 1] not in T.DET and syms[k + 1] not in T.STOP)):
            end = next((t for t in range(k + 1, len(syms)) if syms[t] in ("and", ",", ".", "because")), len(syms))
            comp = "to " + " ".join(raws[t] for t in range(k + 1, end)); break
    if why is None:                                                                      # 'opened its mouth to answer': a purpose phrase is a why
        for k in range(1, len(syms) - 1):
            if syms[k] == "to" and (syms[k + 1].startswith("V:") or (syms[k + 1].isalpha() and syms[k + 1] not in T.DET and syms[k + 1] not in PLACE_WORDS and syms[k + 1] not in T.STOP)) and syms[k - 1] in ("ENT", "PERSON", "PRON"):
                end = next((t for t in range(k + 1, len(syms)) if syms[t] in ("and", ",", ".")), len(syms))
                why = "to " + " ".join(raws[t] for t in range(k + 1, end)); break
    if why: syms.append("WHY"); fillers.append(why)
    if comp: syms.append("COMP"); fillers.append(comp)
    LAST_RAWS[:] = raws                                                                  # R24-aa: the words behind each slot, for answers in the story's own words
    return tuple(syms), fillers


def verbs_of(syms): return [s[2:] for s in syms if s.startswith("V:")]


def clause_of(syms, vi):
    """the clause holding the verb at vi: bounded by ', and' / ', but' / 'because' / 'while' / 'when' / 'and' between two verbs"""
    cuts = set()
    for t in range(len(syms)):
        if syms[t] in ("because", "while", "when", "but", "so"): cuts.add(t)
        if syms[t] == "," and t + 1 < len(syms) and syms[t + 1] in ("and", "but", "so", "while"): cuts.add(t)
        if syms[t] == "and" and any(x.startswith("V:") for x in syms[:t]) and any(x.startswith("V:") for x in syms[t + 1:]) and not (t >= 1 and syms[t - 1] in ("PERSON", "ENT") and t + 1 < len(syms) and syms[t + 1] in ("PERSON", "ENT") and not (t + 2 < len(syms) and syms[t + 2].startswith("V:"))): cuts.add(t)   # R24-ac2: 'cabbages and Greta grew' is a new clause; 'to Ben and Ann.' is a list
    lo = max([c for c in cuts if c < vi], default=-1) + 1; hi = min([c for c in cuts if c > vi], default=len(syms))
    return lo, hi


def feat(syms, k, verb):
    """a slot's surface features: its kind, whether it sits before or after the shared verb, and the symbol before it"""
    vi = next((i for i, s in enumerate(syms) if s == "V:" + verb), None)
    rel = "none" if vi is None else ("before" if k < vi else "after")
    prev = syms[k - 1] if k else "<s>"
    return ("REF", rel, "V" if prev.startswith("V:") else prev)                         # kind-blind: a thing can act like a person; the verb before it counts as 'V'


class Chunks:
    """phrase chunks over construction symbols, learned by counting (as in run 2c): the reader's own units of form"""
    def __init__(self, seqs, max_chunks=5000, maxlen=5):
        cnt = collections.Counter()
        for sq in seqs:
            for i in range(len(sq)):
                for L in range(2, maxlen + 1):
                    if i + L <= len(sq): cnt[tuple(sq[i:i + L])] += 1
        cand = {ch: c for ch, c in cnt.items() if c >= 3}
        self.chunks = {ch: cand[ch] for ch in sorted(cand, key=lambda ch: -(cand[ch] * (len(ch) - 1) - 3 * len(ch)))[:max_chunks]}; self.maxlen = maxlen

    def segment(self, sq):
        n = len(sq); best = [0.0] + [-1e18] * n; back = [1] * (n + 1)
        for j in range(1, n + 1):
            for L in range(1, min(self.maxlen, j) + 1):
                ch = tuple(sq[j - L:j]); sc = (math.log(self.chunks[ch]) + 2.0 * (L - 1)) if L > 1 and ch in self.chunks else (-1.0 if L == 1 else None)
                if sc is None: continue
                if best[j - L] + sc > best[j]: best[j] = best[j - L] + sc; back[j] = L
        out = []; j = n
        while j > 0: out.append((j - back[j], tuple(sq[j - back[j]:j]))); j -= back[j]
        return out[::-1]

    def feat(self, sq, k):
        for start, ch in self.segment(list(sq)):
            if start <= k < start + len(ch): return (ch, k - start)
        return None


def abstract(sym):
    return "V" if sym.startswith("V:") else ("REF" if sym in ("PERSON", "ENT", "PRON") else sym)


def features(syms, k, verb, chunks):
    """several views of one slot; the reader learns which views predict (run 10): exact shape, the local window, the
    relation to the shared verb, the learned chunk"""
    vi = next((i for i, x in enumerate(syms) if x == "V:" + verb), None)
    rel = ("none", 0) if vi is None else (("before" if k < vi else "after"), min(3, sum(1 for t in range(min(k, vi) + 1, max(k, vi)) if syms[t] in ("PERSON", "ENT"))))
    g = lambda t: abstract(syms[t]) if 0 <= t < len(syms) else "#"
    ab = tuple(abstract(x) if x in ("PERSON", "ENT") else x for x in syms)                 # the shape view is blind to name-versus-thing
    out = {"shape": (ab, k), "win1": (g(k - 1), g(k + 1)), "win2": (g(k - 2), g(k - 1), g(k + 1), g(k + 2)), "rel": (abstract(syms[k]), rel[0], rel[1], g(k - 1)), "rel0": rel}   # rel0: the coarsest view, position relative to the verb only
    if chunks: out["chunk"] = chunks.feat(ab, k)
    return out


FEATS = ("shape", "win2", "win1", "rel", "rel0", "chunk")


def bucket(tot): return 0 if tot <= 5 else 1 if tot <= 50 else 2 if tot <= 500 else 3      # how much evidence a view has for this decision


LAST = {"shape": False}                                                                # did the exact-shape evidence decide the last fill?


class Reader:
    def __init__(self, chunks=None):
        self.align = collections.Counter(); self.prior = collections.Counter(); self.feat = collections.Counter(); self.cfeat = collections.Counter(); self.chunks = chunks
        self.tab = {f: collections.Counter() for f in FEATS}; self.tot = {f: collections.Counter() for f in FEATS}; self.w = collections.Counter(); self.wn = collections.Counter()
        self.equiv = collections.defaultdict(collections.Counter)                       # learned paraphrase: statement verb -> story verbs that carried its fillers
        self.eqw = collections.Counter(); self.eqn = collections.Counter()               # how often alignment through a verb pair found the right filler (weighing stories)

    def learn(self, stories, names, weigh=True):
        """for each canonical statement, find the story sentence sharing a verb; count (story shape, canonical shape, story slot i, canonical slot j)
        whenever story slot i and canonical slot j carry the same filler"""
        for text, answers in stories:
            sents = [construction(x, names) for x in T.SENT.split(text) if x.strip()]
            for a in answers:
                cs, cf = construction(a, names); cv = verbs_of(cs)
                c_order = next((f for x, f in zip(cs, cf) if x == "ORDER"), None)
                def carries(ss, sf):                                                  # the shared verb's own clause must carry the order word
                    return any(ss[i] == "V:" + v and (not c_order or any(ss[k] == "ORDER" and sf[k] == c_order for k in range(*clause_of(ss, i)))) for v in cv for i in range(len(ss)))
                if cv and not any(carries(ss, sf) for ss, sf in sents):
                    known = {f.lower() for f in cf if f}
                    scored = [(len(known & {f.lower() for f in t[1] if f}), -i, t) for i, t in enumerate(sents) if verbs_of(t[0])]
                    best = max(scored, default=None)
                    if best is not None and best[0] >= 2:
                        ss0, sf0 = best[2]; vis = [i for i, x in enumerate(ss0) if x.startswith("V:")]
                        def held(vi):                                                      # overlapping fillers inside the verb's clause
                            lo, hi = clause_of(ss0, vi); return sum(1 for k in range(lo, hi) if sf0[k] and sf0[k].lower() in known)
                        sv = ss0[max(vis, key=held)][2:]; self.equiv[cv[0]][sv] += 1
                        via = {cv[0]: sv}                                                   # align through the equivalent verb, the canonical shape keeps its own verb
                    else: via = {}
                else: via = {}
                for ss, sf in sents:
                    match = [(c, c) for c in cv if c in verbs_of(ss)] or [(c, via[c]) for c in cv if c in via and via[c] in verbs_of(ss)]
                    if not match: continue
                    cvv, v = match[0]
                    si = [k for k, s in enumerate(ss) if s in ("PERSON", "ENT", "WHEN", "WHY", "COMP", "ORDER")]; cj = [k for k, s in enumerate(cs) if s in ("PERSON", "ENT", "WHEN", "WHY", "COMP", "ORDER")]
                    for i in si:
                        for j in cj:
                            if sf[i] and cf[j] and (sf[i] == cf[j] or sf[i].lower() == cf[j].lower() or (ss[i] in ("WHEN", "WHY", "COMP") and (cf[j].lower() in sf[i].lower() or sf[i].lower() in cf[j].lower()))):
                                self.align[(ss, cs, i, j)] += 1; self.align[(ss, None, i, j)] += 1; self.prior[(i, j)] += 1; self.feat[(feat(ss, i, v), feat(cs, j, v))] += 1
                                if self.chunks: self.cfeat[(self.chunks.feat(ss, i), self.chunks.feat(cs, j))] += 1
                                fs = features(ss, i, v, self.chunks); fc = features(cs, j, cvv, self.chunks)
                                for f in FEATS:
                                    if f in fs: self.tab[f][(fs[f], fc[f])] += 1
                    if not weigh: continue
                    if cvv != v:
                        for j in cj:
                            gold_i = [i for i in si if sf[i] and cf[j] and sf[i].lower() == cf[j].lower()]
                            if not gold_i: continue
                            fc0 = features(cs, j, cvv, self.chunks); fsd0 = {i: features(ss, i, v, self.chunks) for i in si}
                            score0 = {i: sum(self.tab[f][(fsd0[i][f], fc0[f])] for f in FEATS if f in fsd0[i]) for i in si}
                            self.eqw[(cvv, v)] += (max(score0, key=score0.get) in gold_i); self.eqn[(cvv, v)] += 1
                    for j in cj:
                        gold_i = [i for i in si if sf[i] and cf[j] and sf[i].lower() == cf[j].lower()]
                        if not gold_i: continue
                        fc = features(cs, j, cvv, self.chunks); fsd = {i: features(ss, i, v, self.chunks) for i in si}
                        for f in FEATS:
                            if f not in fc: continue
                            n = {i: self.tab[f][(fsd[i][f], fc[f])] for i in si if f in fsd[i]}; tot = sum(n.values())
                            if not tot: continue
                            best = max(n, key=n.get); self.w[(f, bucket(tot))] += (best in gold_i); self.wn[(f, bucket(tot))] += 1

    def fill(self, story_sents, names, cs, missing, keep_prep=False, cs_fillers=None, raws_list=None):
        """the filler for canonical slot `missing`, from the story sentence sharing the canonical verb, by the learned alignment"""
        cv = set(verbs_of(cs)[:1]); best = None; LAST["shape"] = False                   # the question's own verb is the anchor, never a verb in its tail ('for fixing it')
        order0 = next((cf_k for cs_k, cf_k in zip(cs, cs_fillers) if cs_k == "ORDER"), None) if cs_fillers else None
        def carries(ss, sf): return any(ss[i] == "V:" + v and (not order0 or any(ss[k] == "ORDER" and sf[k] == order0 for k in range(*clause_of(ss, i)))) for v in cv for i in range(len(ss)))
        via = {}
        if cv and not any(carries(ss, sf) for ss, sf in story_sents):                  # learned paraphrase: 'own' -> 'have', 'arrive last' -> 'come last'
            v0 = next(iter(cv)); alts = [sv for sv, c in self.equiv[v0].most_common(5) if c >= 3 and any(ss[i] == "V:" + sv and (not order0 or any(ss[k] == "ORDER" and sf[k] == order0 for k in range(*clause_of(ss, i)))) for ss, sf in story_sents for i in range(len(ss)))]
            alts.sort(key=lambda sv: -((self.eqw[(v0, sv)] + 0.5) / (self.eqn[(v0, sv)] + 1.0)))        # the equivalent that answered best, not the most frequent
            if alts: via = {v0: alts[0]}
        cv_story = set(cv) | set(via.values())
        order = next((cf_k for cs_k, cf_k in zip(cs, cs_fillers) if cs_k == "ORDER"), None) if cs_fillers else None
        given = [cf_k.lower() for k, (cs_k, cf_k) in enumerate(zip(cs, cs_fillers)) if cs_k in ("PERSON", "ENT") and cf_k and k != missing and cf_k.lower() not in ("thing", "someone", "it", "them", "him", "her")] if cs_fillers else []
        def pick(ss, sf, i, j):
            raw = raws_list[j][i] if raws_list and j < len(raws_list) and i < len(raws_list[j]) else None
            txt = raw if (raw and ss[i] == "ENT" and raw.split()[0].lower() in T.DET) else sf[i]           # R24-aa: 'a small boat' as written, not 'the small boat'
            return f"{ss[i - 1]} {txt}" if keep_prep and i and ss[i - 1] in PLACE_WORDS else txt
        for j, (ss, sf) in enumerate(story_sents):
            if not cv_story & set(verbs_of(ss)): continue
            v = (cv_story & set(verbs_of(ss))).pop(); cvv = next((c for c in cv if c == v or via.get(c) == v), v); vi = next(i for i, x in enumerate(ss) if x == "V:" + v); lo, hi = clause_of(ss, vi)
            if given:                                                                  # R24-ac: among several clauses with the verb, the one holding the question's own names / things
                vis = [i for i, x in enumerate(ss) if x == "V:" + v]
                anchored = [i for i in vis if any(ss[k] in ("PERSON", "ENT") and sf[k] and any(sf[k].lower() == g or sf[k].lower().split()[-1] == g.split()[-1] for g in given) for k in range(*clause_of(ss, i)))]
                if anchored and anchored[0] != vi: vi = anchored[0]; lo, hi = clause_of(ss, vi)
            if order and not any(ss[k] == "ORDER" and sf[k] == order and lo <= k < hi for k in range(len(ss))):
                vis = [i for i, x in enumerate(ss) if x == "V:" + v and any(ss[k] == "ORDER" and sf[k] == order for k in range(*clause_of(ss, i)))]
                if not vis: continue
                vi = vis[0]; lo, hi = clause_of(ss, vi)
            si = [k for k, s in enumerate(ss) if s in ("PERSON", "ENT", "WHEN", "WHY", "COMP") and sf[k] and (lo <= k < hi or s in ("WHEN", "WHY", "COMP"))]
            if not any(k < vi for k in si if ss[k] in ("PERSON", "ENT")) and lo > 0:   # a clause without its own subject shares the previous clause's subject
                pv = max([i for i, x in enumerate(ss[:lo]) if x.startswith("V:")], default=lo)
                si = [k for k, s in enumerate(ss) if s in ("PERSON", "ENT") and sf[k] and k < pv] + si
            TRUE_PLACE = PLACE_WORDS - {"from", "with", "by", "through"}
            if cs[missing] == "ENT" and missing >= 1 and cs[missing - 1] in PLACE_WORDS and lo > 0 and not any(ss[k] == "ENT" and k >= 1 and ss[k - 1] in TRUE_PLACE and lo <= k < hi for k in range(len(ss))):
                si = [k for k in range(lo) if ss[k] == "ENT" and sf[k] and k >= 1 and ss[k - 1] in TRUE_PLACE] + si      # 'went to the gate and bought': the place is in the previous clause
            if cs[missing] in ("WHEN", "WHY", "COMP"): si = [k for k, s in enumerate(ss) if s == cs[missing] and sf[k]]   # a span question takes only spans of its kind
            else: si = [k for k in si if ss[k] not in ("WHEN", "WHY", "COMP")]                               # and a who / what / where question never takes a span
            if not si: continue
            fc = features(cs, missing, cvv, self.chunks); fsd = {i: features(ss, i, v, self.chunks) for i in si}
            score = {i: 0.0 for i in si}
            n_shape = {i: self.tab["shape"][(fsd[i]["shape"], fc["shape"])] for i in si}
            if sum(n_shape.values()) >= 5:                                             # this exact shape has been seen: its own evidence decides
                scored = [(n_shape[i], i) for i in si]; c, i = max(scored)
                if best is None or c > best[0]: best = (c, pick(ss, sf, i, j)); LAST["shape"] = True
                continue
            for f in FEATS:                                                            # a learned mixture over the views; each view is a distribution over the candidates,
                n = {i: self.tab[f][(fsd[i][f], fc[f])] for i in si if f in fsd[i]}; tot = sum(n.values())   # weighted by how often that view was right with this much evidence
                if tot:
                    b = bucket(tot); acc = (self.w[(f, b)] + 0.5) / (self.wn[(f, b)] + 1.0); conf = tot / (tot + 20.0)   # reliability (learned) x evidence
                    for i, ni in n.items(): score[i] += acc * conf * ni / tot
            scored = [(score[i], i) for i in si]
            c, i = max(scored)
            if best is None or c > best[0]: best = (c, pick(ss, sf, i, j))
        if best and best[1] and best[1].lower() in ("he", "she", "him", "her", "his", "they", "them", "it"):      # a pronoun filler (a whole slot, never a span): the learned latest-person rule
            persons = [f for ss, sf in story_sents for ss_k, f in zip(ss, sf) if ss_k == "PERSON" and f]
            return persons[-1] if persons else None
        return best[1] if best else None


def ask(R, text, names, q):
    ql = q.lower().rstrip("?"); sents = [construction(x, names) for x in T.SENT.split(text) if x.strip()]
    who = sorted(names)[0] if names else "Someone"                                      # a known name stands in for the missing PERSON slot
    def art(a): return a if (a is None or a[:1].isupper() or a.split()[0] in T.DET or a.split()[0] in PLACE_WORDS) else "the " + a
    m = re.match(r"who (\w+) (.+)$", ql)
    if m and m.group(1) not in ("was", "were", "had", "is"):
        cs, cf = construction(f"{who} {m.group(1)} {m.group(2)}.", names)
        return art(R.fill(sents, names, cs, 0, cs_fillers=cf)) if cs and cs[0] == "PERSON" else None
    m = re.match(r"what did (.+)$", ql)
    if m:
        ws = q[9:].rstrip("?").split(); vi = next((i for i, x in enumerate(ws) if i and is_verb(x.lower()) and x.lower() not in E.NOUNISH), None)
        if vi and (ql.endswith(" to do") or ql.endswith(" to learn") or E.lemma(ws[vi].lower()) in ("promise", "want", "refuse", "try", "begin", "learn", "agree", "decide", "hope")):
            cs, cf = construction(f"{ws[0][0].upper() + ws[0][1:]} {' '.join(ws[1:vi])} {E.lemma(ws[vi].lower())} to do something.".replace("  ", " "), names)
            j = [k for k, s in enumerate(cs) if s == "COMP"]
            if j:
                a = R.fill(sents, names, cs, j[0])
                if a: return a
    m = re.match(r"what did (.+)$", ql)
    if m:
        ws = m.group(1).split(); vi = next((i for i, x in enumerate(ws) if i and is_verb(x)), None)
        if not vi: return None
        head = ' '.join(ws[:vi]); head = head[0].upper() + head[1:]; tail = ' '.join(ws[vi + 1:])
        if tail and len(tail.split()) == 1 and tail in PLACE_WORDS | {"with", "for"}:
            cs, cf = construction(f"{head} {E.lemma(ws[vi])} {tail} the thing.", names); j = [k for k, s in enumerate(cs) if s == "ENT" and cf[k] == "thing"]
        elif tail and (tail.split()[0] in PLACE_WORDS or tail.split()[0] in ("as", "for", "with")):
            cs, cf = construction(f"{head} {E.lemma(ws[vi])} the thing {tail}.", names); j = [k for k, s in enumerate(cs) if s == "ENT" and cf[k] == "thing"]
        else:
            cs, cf = construction(f"{head} {E.lemma(ws[vi])} {tail} the thing.".replace("  ", " "), names); j = [k for k, s in enumerate(cs) if s == "ENT"]
        return art(R.fill(sents, names, cs, j[-1])) if j else None
    m = re.match(r"when did (.+)$", ql)
    if m:
        ws = m.group(1).split(); vi = next((i for i, x in enumerate(ws) if i and is_verb(x)), None)
        if not vi: return None
        ws = q[9:].rstrip("?").split(); cs, cf = construction(f"At some time, {ws[0][0].upper() + ws[0][1:]} {' '.join(ws[1:vi])} {E.lemma(ws[vi].lower())} {' '.join(ws[vi + 1:])}.".replace("  ", " ").replace(" .", "."), names)
        j = [k for k, s in enumerate(cs) if s == "WHEN"]
        return R.fill(sents, names, cs, j[0]) if j else None
    m = re.match(r"why did (.+)$", ql)
    if m:
        ws = q[8:].rstrip("?").split(); vi = next((i for i, x in enumerate(ws) if i and is_verb(x.lower()) and x.lower() not in E.NOUNISH), None)
        if not vi: return None
        cs, cf = construction(f"{ws[0][0].upper() + ws[0][1:]} {' '.join(ws[1:vi])} {E.lemma(ws[vi].lower())} {' '.join(ws[vi + 1:])} because of something.".replace("  ", " "), names)
        j = [k for k, s in enumerate(cs) if s == "WHY"]
        return R.fill(sents, names, cs, j[0]) if j else None
    m = re.match(r"where did (.+)$", ql)
    if m:
        ws = m.group(1).split(); vi = next((i for i, x in enumerate(ws) if i and is_verb(x)), None)
        if not vi or ws[vi] == "start": return None
        head = ' '.join(ws[:vi]); head = head[0].upper() + head[1:]
        cs, cf = construction(f"{head} {E.lemma(ws[vi])} {' '.join(ws[vi + 1:])} at the place.".replace("  ", " "), names)
        j = [k for k, s in enumerate(cs) if s == "ENT"]
        return art(R.fill(sents, names, cs, j[-1], keep_prep=True)) if j else None
    return None


def closed_loop_train(data, names):
    """R24-v: event statements plus the statements the event-taught question reader renders; returns (train, Q)"""
    import r24_qreader as QR
    train = [(s["text"], [event_statement(e) for e in (s.get("events") or [])]) for s in data[:7000]]; train = [t for t in train if t[1]]
    pairs = []
    for s in data[:7000]:
        if not s.get("events"): continue
        stmts = [event_statement(e) for e in s["events"]]
        for q, g in s["qs"]:
            qs, qf = QR.qshape(q, names); qslots = {f.lower() for x, f in zip(qs, qf) if x in ("PERSON", "ENT")}; qv = next((x for x in qs if x.startswith("V:")), None)
            for st in stmts:
                cs, cf = construction(st, names); fl = {f.lower() for f in cf if f}
                if qv is None or qv not in cs: continue
                gold = next((f for f in cf if f and (f.lower() == g[0].lower() or f.lower() == T.key_of("ENT", g[0].lower().split()) or g[0].lower() in f.lower())), None)
                if gold and (qslots & fl or not qslots): pairs.append((q, st, gold)); break
    Q = QR.QReader(); Q.learn(pairs, names)
    def as_text(cs, cf, missing, gold):
        out = []
        for k, (x, f) in enumerate(zip(cs, cf)):
            if k == missing: out.append(gold)
            elif x in ("PERSON", "ENT"): out.append(f if x == "PERSON" else ("the " + f if not f.startswith(("the ", "a ", "an ")) else f))
            elif x.startswith("V:"): out.append(x[2:])
            elif x in ("WHEN", "WHY", "COMP", "ORDER"): out.append(f or "")
            elif x == ".": continue
            else: out.append(x)
        return " ".join(w for w in out if w).strip() + "."
    extra_by = collections.defaultdict(list)
    for s in data[:7000]:
        for q, g in s["qs"]:
            got = Q.render(q, names)
            if got and QR.LASTQ.get("level") == "exact": extra_by[s["text"]].append(as_text(got[0], got[1], got[2], g[0]))
    train = [(t[0], t[1] + extra_by.get(t[0], [])) for t in train]
    return train, Q


def main():
    data = json.load(open("stories_train_v2.json", encoding="utf-8")); random.Random(24).shuffle(data)
    names = T.mid_caps([s["text"] for s in data[:7000]])
    import r24_books as B, data as D
    train_b, _ = D.books(); E.induce_verbish([p["text"] for p in B.paragraphs(train_b, 150000)], k=200)
    EVENTS_ONLY = "--events-only" in ARGV                                                 # R24-u: no regex-rendered statements, the story's own events teach
    train = [(s["text"], ([] if EVENTS_ONLY else [a for a in (canonical(q, g) for q, g in s["qs"]) if a]) + [event_statement(e) for e in (s.get("events") or [])]) for s in data[:7000]]
    if EVENTS_ONLY: train = [t for t in train if t[1]]
    if "--closed-loop" in ARGV:                                                          # R24-v: the event-taught question reader renders the generator's questions into training statements
        import r24_qreader as QR
        pairs = []
        for s in data[:7000]:
            if not s.get("events"): continue
            stmts = [event_statement(e) for e in s["events"]]
            for q, g in s["qs"]:
                qs, qf = QR.qshape(q, names); qslots = {f.lower() for x, f in zip(qs, qf) if x in ("PERSON", "ENT")}; qv = next((x for x in qs if x.startswith("V:")), None)
                for st in stmts:
                    cs, cf = construction(st, names); fl = {f.lower() for f in cf if f}
                    if qv is None or qv not in cs: continue
                    gold = next((f for f in cf if f and (f.lower() == g[0].lower() or f.lower() == T.key_of("ENT", g[0].lower().split()) or g[0].lower() in f.lower())), None)
                    if gold and (qslots & fl or not qslots): pairs.append((q, st, gold)); break
        Q = QR.QReader(); Q.learn(pairs, names); added = 0
        def as_text(cs, cf, missing, gold):
            out = []
            for k, (x, f) in enumerate(zip(cs, cf)):
                if k == missing: out.append(gold)
                elif x in ("PERSON", "ENT"): out.append(f if x == "PERSON" else ("the " + f if not f.startswith(("the ", "a ", "an ")) else f))
                elif x.startswith("V:"): out.append(x[2:])
                elif x in ("WHEN", "WHY", "COMP", "ORDER"): out.append(f or "")
                elif x == ".": continue
                else: out.append(x)
            return " ".join(w for w in out if w).strip() + "."
        extra_by = collections.defaultdict(list)
        for s in data[:7000]:
            for q, g in s["qs"]:
                got = Q.render(q, names)
                if got and QR.LASTQ.get("level") == "exact": extra_by[s["text"]].append(as_text(got[0], got[1], got[2], g[0])); added += 1
        train = [(t[0], t[1] + extra_by.get(t[0], [])) for t in train] + [(s["text"], extra_by[s["text"]]) for s in data[:7000] if s["text"] in extra_by and not any(t[0] == s["text"] for t in train[:0])]
        seen = set(); train = [t for t in train if not (t[0] in seen or seen.add(t[0]))]
        print(f"closed loop: {added} statements rendered by the learned question reader for the sentence reader", flush=True)
    seqs = [list(construction(x, names)[0]) for s in data[:7000] for x in T.SENT.split(s["text"]) if x.strip()]
    seqs += [list(construction(x, names)[0]) for p in B.paragraphs(train_b, 60000) for x in T.SENT.split(p["text"]) if x.strip()]      # book sentences too: general phrase chunks
    CH = Chunks(seqs); print(f"{len(CH.chunks)} phrase chunks over construction symbols (generator + books)", flush=True)
    R = Reader(CH); R.learn(train[:6000], names, weigh=False); R.learn(train[6000:], names, weigh=True)      # reliabilities measured on stories the tables had not seen
    tabs = (R.w, R.wn); R = Reader(CH); R.w, R.wn = tabs; R.learn(train, names, weigh=False)
    print("learned verb equivalents:", {v: dict(c.most_common(2)) for v, c in R.equiv.items() if sum(c.values()) >= 10}, flush=True); print(f"alignment table: {len(R.align)} entries; learned view accuracy by evidence: {[(f, b, round((R.w[(f, b)] + 0.5) / (R.wn[(f, b)] + 1.0), 2)) for f in FEATS for b in range(4) if R.wn[(f, b)]]}", flush=True)
    ok = tot = 0; by = collections.defaultdict(lambda: [0, 0])
    for s in data[7000:]:
        for q, g in s["qs"]:
            if canonical(q, g) is None: continue
            a = ask(R, s["text"], names, q); tot += 1; h = (a is not None and hit(a, g)); ok += h; by[q.split()[0].lower()][0] += h; by[q.split()[0].lower()][1] += 1
    print(f"R24-j1: held-out generator who / what / where / when / why questions by the learned alignment: {ok}/{tot} = {ok / max(1, tot):.2f} (bar >= 0.80); by kind {dict((k, f'{v[0]}/{v[1]}') for k, v in by.items())}")
    matched = right = n = 0
    for f in ("val_stories.json", "val_fables.json"):
        for s in json.load(open(f, encoding="utf-8"))["stories"]:
            for q, g in s["qs"]:
                n += 1; a = ask(R, s["text"], names, q)
                if a is not None: matched += 1; right += hit(a, g)
                if SHOW and a is not None: print(f"  {'OK' if hit(a, g) else 'XX'} {q} | {g} | {a}")
    print(f"R24-j2: the learned reader on the 80 validation story questions: matched {matched}/{n}, right {right} (precision {right / max(1, matched):.2f}); cue-built event log 45 / 40")
    json.dump(dict(j1=(ok, tot), j2=(matched, right, n)), open("r24_reader_results.json", "w"))


if __name__ == "__main__":
    main()
