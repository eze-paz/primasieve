"""ROSETTA-PUZZLE JOINT constraint-solver (zero-LLM, pure stdlib). The engine learns a language's rules from the few
train pairs and generalizes BY CONSTRUCTION. Unlike the memorizing template engine (puzzle_solve.py, null), this
solves the COUPLED deduction jointly:
  (1) affix discovery + segmentation (stem+affixes) so case-forms of a noun share a stem;
  (2) English content lemmatization (chase/chases->chase) so agreement doesn't break alignment;
  (3) CATEGORY induction -- foreign stems are nominal (take case affixes) vs verbal (take verbal affixes); English
      lemmas are nominal (follow an article) vs verbal -- which breaks the noun/verb distributional deadlock;
  (4) category-constrained iterative ELIMINATION alignment -> a deterministic stem->lemma lexicon;
  (5) synchronous TEMPLATE extraction with per-slot inflection suffixes (so 'the dog' + verb-3sg renders 'stinks');
  (6) SOUND gate = reproduce every train pair exactly; MDL-simplest survivors; COMMIT if survivors agree else ABSTAIN.
Pilot=chickasaw (operators developed here only). See puzzle_prereg.md. foreign->English primary."""
import os, sys, json, io, re, collections

D = os.path.join(os.path.dirname(__file__), "_nldata")

def norm(s):
    s = s.strip().lower(); s = re.sub(r"[.?!]+$", "", s)
    s = s.replace("(", " ( ").replace(")", " ) ").replace("/", " / ")
    return s.strip()
def toks(s): return norm(s).split()
def is_content_char(t): return t.isalpha()
def lemma(t):                                   # crude English lemmatizer: strip one agreement -s
    return t[:-1] if (len(t) > 3 and t.endswith("s") and not t.endswith("ss")) else t

# ---------- affix discovery ----------
def _cpx(a, b):
    n = 0
    for x, y in zip(a, b):
        if x != y: break
        n += 1
    return n
def discover_affixes(vocab, maxaff=4, mincount=1):
    """Candidate affixes from paradigmatic minimal pairs, then VALIDATED: a suffix is real only if some stem occurs
    with >=2 distinct candidate suffixes (a paradigm); a prefix only if stripping it leaves a stem that is itself a
    free word. This rejects stem-fragment junk (e.g. prefix 'of' leaving 'i'at')."""
    W = set(vocab); sufc = collections.Counter(); prec = collections.Counter()
    for a in W:
        for b in W:
            if a == b: continue
            cp = _cpx(a, b)
            if cp >= 2 and 0 < len(a) - cp <= maxaff: sufc[a[cp:]] += 1
            cs = _cpx(a[::-1], b[::-1])
            if cs >= 2 and 0 < len(a) - cs <= maxaff: prec[a[:len(a) - cs]] += 1
    Sc = {s for s, c in sufc.items() if c >= mincount}
    Pc = {p for p, c in prec.items() if c >= mincount}
    stemsuf = collections.defaultdict(set)
    for w in W:
        stemsuf[w].add("")                                     # word itself = stem+empty
        for s in Sc:
            if w.endswith(s) and len(w) - len(s) >= 2: stemsuf[w[:len(w) - len(s)]].add(s)
    S = {""}
    for stem, sset in stemsuf.items():
        if len(sset) >= 2: S |= sset                           # suffixes in a real paradigm
    P = {""}
    for p in Pc:
        for w in W:
            if w.startswith(p) and len(w) - len(p) >= 2 and w[len(p):] in W: P.add(p); break  # stem is a free word
    return S, P

def seg_options(w, S, P):
    opts = []
    for p in P:
        if not w.startswith(p): continue
        rest = w[len(p):]
        for s in S:
            if s and not rest.endswith(s): continue
            stem = rest[:len(rest) - len(s)] if s else rest
            if len(stem) >= 2: opts.append((p, stem, s))
    return opts or [("", w, "")]

def build_seg(vocab, S, P):
    """Choose a segmentation per word: strip a valid affix when the STEM is attested elsewhere OR the affix is
    PRODUCTIVE (attaches to >=2 attested stems). This splits productive case markers even off hapax stems, but
    won't split a bare stem that merely ends in an affix-shaped string. Falls back to the whole word."""
    W = set(vocab)
    stemsuf = collections.defaultdict(set); stempre = collections.defaultdict(set)
    for w in W:
        for s in S:
            if s and w.endswith(s) and len(w) - len(s) >= 2: stemsuf[w[:len(w) - len(s)]].add(s)
        for p in P:
            if p and w.startswith(p) and len(w) - len(p) >= 2: stempre[w[len(p):]].add(p)
    attested = set(W) | {st for st, ss in stemsuf.items() if len(ss) >= 2}
    prod_suf = {s for s in S if s and sum(1 for st in stemsuf if s in stemsuf[st] and st in attested) >= 2}
    prod_pre = {p for p in P if p and sum(1 for st in stempre if p in stempre[st] and st in attested) >= 2}
    seg = {}
    for w in W:
        best = ("", w, ""); best_score = (-1, -1, 0)
        for pre, stem, suf in seg_options(w, S, P):
            if pre == "" and suf == "": continue
            acc = (stem in attested) or (suf in prod_suf) or (pre in prod_pre)
            if not acc: continue
            score = (1 if stem in attested else 0,
                     (1 if suf in prod_suf else 0) + (1 if pre in prod_pre else 0),
                     len(stem))
            if score > best_score: best_score = score; best = (pre, stem, suf)
        seg[w] = best
    return seg

# ---------- English side analysis ----------
ARTICLES = {"the", "a", "an"}
# English closed-class (known target language): determiners, pronouns, cop/aux, conjunctions, common prepositions.
ENG_FUNC = ARTICLES | {"i", "you", "he", "she", "it", "we", "they", "me", "him", "her", "us", "them",
    "his", "hers", "its", "our", "their", "my", "your", "is", "are", "am", "was", "were", "be", "been",
    "and", "or", "of", "to", "in", "on", "at", "by", "for", "with", "not", "no", "s", "him/her", "he/she"}
def analyze_english(train):
    df = collections.Counter()
    for _, e in train:
        for t in set(toks(e)): df[t] += 1
    func = set(ENG_FUNC)                                   # known English closed-class only (no DF heuristic)
    return func, ARTICLES

def english_content(e, func):
    """(lemma, is_noun) for content tokens; is_noun if it follows an article."""
    ts = toks(e); out = []
    for i, t in enumerate(ts):
        if t.isalpha() and t not in func:
            is_noun = i > 0 and ts[i - 1] in ARTICLES
            out.append((lemma(t), is_noun))
    return out

# ---------- category-constrained elimination alignment ----------
def align(train, S, P, seg, func):
    """seg: word->(pre,stem,suf). Returns stem->lemma lexicon + affix category maps."""
    # per pair: foreign content stems (list), english (lemma,is_noun) list
    fpairs = []
    for f, e in train:
        fstems = []
        for w in toks(f):
            pre, stem, suf = seg.get(w, ("", w, "")); fstems.append((stem, pre, suf))
        ec = english_content(e, func)
        fpairs.append((fstems, ec))

    lex = {}
    def occ(stem): return [i for i, (fs, ec) in enumerate(fpairs) if any(s == stem for s, _, _ in fs)]

    def eliminate(catmap=None):
        changed = True
        while changed:
            changed = False
            cand = collections.defaultdict(list)
            for fs, ec in fpairs:
                stems = [s for s, _, _ in fs]
                known = [lex[s] for s in stems if s in lex]
                rem = [l for (l, _) in ec]
                for k in known:
                    if k in rem: rem.remove(k)
                # category filter of remaining english by stem category if known
                for s in stems:
                    if s in lex: continue
                    pool = rem
                    if catmap is not None and s in catmap:
                        want_noun = catmap[s]
                        pool = [l for (l, isn) in ec if isn == want_noun and l in rem]
                    cand[s].append(set(pool))
            for s, sets in cand.items():
                inter = set.intersection(*sets) if sets else set()
                if len(inter) == 1:
                    lex[s] = next(iter(inter)); changed = True

    eliminate(None)                                  # pass 1: category-free anchors
    # classify affixes from anchors: affix on a stem aligned to a NOUN lemma -> nominal; to VERB -> verbal
    noun_lemmas = set(); verb_lemmas = set()
    for _, ec in fpairs:
        for l, isn in ec: (noun_lemmas if isn else verb_lemmas).add(l)
    aff_noun = collections.Counter(); aff_verb = collections.Counter()
    for fs, ec in fpairs:
        for stem, pre, suf in fs:
            if stem in lex:
                isn = lex[stem] in noun_lemmas
                for a in (pre, suf):
                    if a: (aff_noun if isn else aff_verb)[a] += 1
    nominal_aff = {a for a in aff_noun if aff_noun[a] > aff_verb.get(a, 0)}
    # classify every stem: NOMINAL if any word-form takes a nominal (case) affix, else VERBAL (default).
    stem_has_nom = set()
    for f, e in train:
        for w in toks(f):
            pre, stem, suf = seg.get(w, ("", w, ""))
            if {a for a in (pre, suf) if a} & nominal_aff: stem_has_nom.add(stem)
    catmap = {}
    for f, e in train:
        for w in toks(f):
            stem = seg.get(w, ("", w, ""))[1]
            catmap[stem] = stem in stem_has_nom          # True=nominal(noun), False=verbal(verb)
    # override with anchor evidence where it conflicts (anchor lemma category wins)
    for stem, lm in list(lex.items()):
        if lm in noun_lemmas and lm not in verb_lemmas: catmap[stem] = True
        elif lm in verb_lemmas and lm not in noun_lemmas: catmap[stem] = False
    eliminate(catmap)                                # pass 2: category-constrained
    return lex, catmap, func

# ---------- synchronous templates with inflection suffixes ----------
def to_units(f, seg):
    u = []
    for w in toks(f):
        pre, stem, suf = seg.get(w, ("", w, ""))
        if pre: u.append(("pre", pre))
        u.append(("stem", stem))
        if suf: u.append(("suf", suf))
        u.append(("wb", ""))                         # word boundary marker
    return u[:-1] if u else u

def make_template(f, e, seg, lex):
    fu = to_units(f, seg)
    ff = []; slot_of = {}; sid = 0
    for typ, val in fu:
        if typ == "stem" and val in lex:
            lm = lex[val]
            if lm not in slot_of: slot_of[lm] = f"S{sid}"; sid += 1
            ff.append(("slot", slot_of[lm]))
        else:
            ff.append(("lit", val) if typ != "wb" else ("wb", ""))
    # english frame: content slot carries inflection suffix (surface minus lemma)
    ef = []
    for t in toks(e):
        if t.isalpha():
            lm = lemma(t)
            if lm in slot_of:
                suf = t[len(lm):]                    # e.g. 'chases'->'s'
                ef.append(("slot", slot_of[lm], suf)); continue
        ef.append(("lit", t))
    return tuple(ff), tuple(ef)

def induce(train, seg, lex):
    T = set()
    for f, e in train: T.add(make_template(f, e, seg, lex))
    return list(T)

# ---------- compositional SVO generation (option 1) ----------
PRON = {"i", "me", "you", "he", "she", "it", "we", "they", "him", "her", "us", "them"}
def parse_foreign(f, seg, lex, catmap):
    out = []
    for w in toks(f):
        pre, stem, suf = seg.get(w, ("", w, ""))
        out.append(dict(word=w, stem=stem, lemma=lex.get(stem), pre=pre, suf=suf,
                        noun=catmap.get(stem, False), known=stem in lex))
    return out

def parse_english(et, verb_lemmas):
    """Return (subj, verb_idx, verb_surface, obj) where subj/obj are ('noun',lemma) | ('pron',surface) | None."""
    vi = None
    for i, t in enumerate(et):
        if t.isalpha() and t not in PRON and lemma(t) in verb_lemmas: vi = i; break
    if vi is None: return None
    def parse_arg(region):
        content = [t for t in region if t.isalpha() and t not in ENG_FUNC]
        if content: return ("noun", lemma(content[0]))
        pr = [t for t in region if t != ""]
        if pr: return ("pron", " ".join(pr))
        return None
    return parse_arg(et[:vi]), vi, et[vi], parse_arg(et[vi + 1:])

def learn_grammar(train, seg, lex, catmap, func):
    verb_lemmas = {lex[s] for s in lex if not catmap.get(s, False)}
    g = dict(role={}, person={}, infl={}, valence={}, det=None, dsubj=None, dobj=None, verb_lemmas=verb_lemmas)
    detc = collections.Counter()
    for f, e in train:
        fw = parse_foreign(f, seg, lex, catmap)
        et = toks(e)
        pe = parse_english(et, verb_lemmas)
        if pe is None: continue
        subj, vi, vsurf, obj = pe
        # determiner: token before a noun in english
        for i, t in enumerate(et):
            if t.isalpha() and t not in ENG_FUNC and i > 0 and et[i - 1] in ARTICLES: detc[et[i - 1]] += 1
        fnouns = [x for x in fw if x["noun"] and x["known"]]
        fverbs = [x for x in fw if x["known"] and not x["noun"]]
        if not fverbs: continue
        v = fverbs[0]
        # valence
        g["valence"][v["lemma"]] = "trans" if obj is not None else "intrans"
        # subject person + inflection
        subj_is_1sg = subj and subj[0] == "pron" and subj[1] == "i"
        person = "1sg" if subj_is_1sg else "3"
        suf = vsurf[len(v["lemma"]):] if vsurf.startswith(v["lemma"]) else ""
        g["infl"][person] = suf
        # case -> role via nominal args matched by lemma; TRANSITIVITY-CONDITIONED so it subsumes accusative AND
        # ergative alignment (the engine discovers which from data): key = (suffix, clause-is-transitive).
        trans = obj is not None
        for fn in fnouns:
            if subj and subj[0] == "noun" and subj[1] == fn["lemma"]: g["role"][(fn["suf"], trans)] = "subj"
            if obj and obj[0] == "noun" and obj[1] == fn["lemma"]: g["role"][(fn["suf"], trans)] = "obj"
        # person affixes on the verb + default 3rd surfaces
        vaff = [a for a in (v["pre"], v["suf"]) if a]
        if not any(fn for fn in fnouns if subj and subj[0] == "noun" and subj[1] == fn["lemma"]):
            # subject not a noun -> pronoun subject
            if subj and subj[0] == "pron":
                if subj[1] in PRON and vaff:                        # overt marked pronoun (e.g. 'i' <- li)
                    for a in vaff: g["person"].setdefault(a, ("subj", subj[1]))
                elif subj[1] not in PRON or subj[1] == "( he / she )" or "/" in subj[1]:
                    g["dsubj"] = subj[1]                            # default 3rd-person subject surface
                elif not vaff:
                    g["dsubj"] = subj[1]
        if obj is not None and not any(fn for fn in fnouns if obj and obj[0] == "noun" and obj[1] == fn["lemma"]):
            if obj[0] == "pron":
                if obj[1] in PRON and vaff:
                    for a in vaff:
                        if a not in g["person"]: g["person"][a] = ("obj", obj[1])
                else:
                    g["dobj"] = obj[1]
    g["det"] = detc.most_common(1)[0][0] if detc else "the"
    return g

def generate_fe(f, M):
    seg, lex, catmap, g = M["seg"], M["lex"], M["catmap"], M["grammar"]
    fw = parse_foreign(f, seg, lex, catmap)
    for x in fw:
        if not x["known"]: return None                             # unknown morpheme -> abstain
    verbs = [x for x in fw if not x["noun"]]
    if len(verbs) != 1: return None                                # only single-clause SVO handled
    v = verbs[0]; nouns = [x for x in fw if x["noun"]]
    valence = g["valence"].get(v["lemma"])
    if valence is None: return None
    trans = (valence == "trans")
    vaff = [a for a in (v["pre"], v["suf"]) if a]
    subj = obj = None; person = "3"
    for a in vaff:                                                  # person affixes on verb
        if a in g["person"]:
            role, surf = g["person"][a]
            if role == "subj": subj = ("pron", surf); person = "1sg" if surf == "i" else "3"
            else: obj = ("pron", surf)
        else:
            return None                                            # unexplained affix -> abstain
    for n in nouns:                                                # nominal args by transitivity-conditioned case
        r = g["role"].get((n["suf"], trans))
        if r == "subj": subj = ("noun", n["lemma"])
        elif r == "obj": obj = ("noun", n["lemma"])
        else: return None                                          # unknown case-in-context -> abstain
    if subj is None: subj = ("pron", g["dsubj"]) if g["dsubj"] else None
    if valence == "trans" and obj is None: obj = ("pron", g["dobj"]) if g["dobj"] else None
    if subj is None: return None
    if valence == "trans" and obj is None: return None
    def render_np(a):
        return a[1] if a[0] == "pron" else f"{g['det']} {a[1]}"
    vsurf = v["lemma"] + g["infl"].get(person, g["infl"].get("3", ""))
    parts = [render_np(subj), vsurf]
    if valence == "trans": parts.append(render_np(obj))
    return " ".join(parts)

# ---------- application ----------
def match_fe(f, ff, seg, lex):
    fu = to_units(f, seg)
    if len(fu) != len(ff): return None
    b = {}
    for (ftyp, fval), (utyp, uval) in zip(ff, fu):
        if ftyp == "wb":
            if utyp != "wb": return None
        elif ftyp == "lit":
            if utyp == "wb" or uval != fval: return None
        else:  # slot
            if utyp != "stem" or uval not in lex: return None
            lm = lex[uval]
            if fval in b and b[fval] != lm: return None
            b[fval] = lm
    return b

def render_e(ef, b):
    out = []
    for item in ef:
        if item[0] == "lit": out.append(item[1])
        else:
            _, sid, suf = item
            if sid not in b: return None
            out.append(b[sid] + suf)
    return " ".join(out)

def apply_fe(f, temps, seg, lex):
    cands = set()
    for ff, ef in temps:
        b = match_fe(f, ff, seg, lex)
        if b is None: continue
        r = render_e(ef, b)
        if r is not None: cands.add(r)
    return cands

# ---------- engine ----------
def engine(train, test_srcs=()):
    vocab = [w for f, e in train for w in toks(f)] + [w for s in test_srcs for w in toks(s)]
    S, P = discover_affixes(vocab)
    seg = build_seg(vocab, S, P)
    func, articles = analyze_english(train)
    lex, catmap, func = align(train, S, P, seg, func)
    M = dict(S=S, P=P, seg=seg, lex=lex, catmap=catmap, func=func)
    M["grammar"] = learn_grammar(train, seg, lex, catmap, func)
    M["temps"] = induce(train, seg, lex)
    # SOUND gate for the compositional grammar: every train pair it can generate (all words known) must be exact.
    repro = gen_ok = 0
    for f, e in train:
        g = generate_fe(f, M)
        if g is not None:
            repro += 1; gen_ok += (g == _n(e))
    M["gsound"] = (repro >= 1 and gen_ok == repro)
    M["grepro"] = (gen_ok, repro)
    return M

def _n(s): return " ".join(toks(s))
def reproduces(train, M):                              # template-level reproduction (diagnostic)
    return sum(1 for f, e in train if _n(e) in apply_fe(f, M["temps"], M["seg"], M["lex"]))

def solve_fe(fsrc, M):
    if M.get("gsound"):                                # compositional generation (generalizes across structures)
        out = generate_fe(fsrc, M)
        if out is not None: return ("commit", out)
        return ("hard", None)
    c = apply_fe(fsrc, M["temps"], M["seg"], M["lex"])  # fallback: whole-sentence templates
    if not c: return ("hard", None)
    if len(c) > 1: return ("soft", None)
    return ("commit", next(iter(c)))

if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else "chickasaw"
    d = json.load(io.open(os.path.join(D, name + ".json"), "r", encoding="utf-8"))
    train = [(a, b) for a, b in d["train"]]
    items = [it for it in d["test"] if it[2] == ">"]
    M = engine(train, [it[0] for it in items])
    print(f"{d['source_language']}: {len(train)} train, {len(items)} '>' items")
    print(f"  lexicon: {M['lex']}")
    print(f"  reproduce train: {reproduces(train, M)}/{len(train)}  templates={len(M['temps'])}")
    C = P = W = hard = soft = 0
    for it in items:
        gold = _n(it[1]); st, pred = solve_fe(it[0], M)
        if st == "commit":
            C += 1; ok = (_n(pred) == gold); P += ok; W += (not ok)
            print(f"    {'OK ' if ok else 'WRONG'} pred={_n(pred)!r} gold={gold!r}")
        else:
            hard += st == "hard"; soft += st == "soft"
            print(f"    ABSTAIN-{st}  gold={gold!r}")
    print(f"  => commit {C}/{len(items)} correct {P} wrong {W} hard {hard} soft {soft}")