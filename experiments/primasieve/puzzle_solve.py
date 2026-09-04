"""ROSETTA-PUZZLE rule-induction engine (zero-LLM, pure stdlib) -- the engine learns a language's rules from the few
train pairs (mini-textbook) and generalizes BY CONSTRUCTION. Mechanism: (O1) discover foreign affixes by MDL-ish
recurrence -> segment words into stem+affixes; (O2) build a DETERMINISTIC stem<->english-content-word lexicon by
CONSISTENCY (co-occurrence intersection, function words filtered); (O3/O4) induce synchronous TEMPLATES by replacing
aligned stems with typed slots (affixes + english function words + order become frame literals); (O5) SOUND gate =
templates+lexicon must EXACTLY reproduce every train pair; (O6) apply to a held-out item -> COMMIT if a unique
template+fill produces one output, ABSTAIN if none match (hard) or candidates disagree (soft). See puzzle_prereg.md.
Pilot = chickasaw (operators developed here only). Metrics P/C/W + hard/soft abstain, foreign->English primary."""
import os, sys, json, io, re, collections, itertools

D = os.path.join(os.path.dirname(__file__), "_nldata")

def norm(s):
    s = s.strip().lower()
    s = re.sub(r"[.?!]+$", "", s)
    s = s.replace("(", " ( ").replace(")", " ) ")
    return s.strip()

def toks(s): return norm(s).split()

def load(path):
    d = json.load(io.open(path, "r", encoding="utf-8"))
    return d

# ---------- O1: affix segmentation over the foreign vocab ----------
def _cpx(a, b):
    n = 0
    for x, y in zip(a, b):
        if x != y: break
        n += 1
    return n

def discover_affixes(vocab, maxaff=4):
    """Discover affixes from PARADIGMATIC minimal pairs: two words sharing a long stem (common prefix) differ by a
    suffix; sharing a common suffix differ by a prefix. Recorded edges (len<=maxaff) are candidate affixes."""
    V = list(set(vocab)); suf = collections.Counter(); pre = collections.Counter()
    for a in V:
        for b in V:
            if a == b: continue
            cp = _cpx(a, b)
            if cp >= 2 and len(a) - cp <= maxaff: suf[a[cp:]] += 1          # differing suffix of a
            cs = _cpx(a[::-1], b[::-1])
            if cs >= 2 and len(a) - cs <= maxaff: pre[a[:len(a) - cs]] += 1  # differing prefix of a
    S = {s for s in suf} | {""}; P = {p for p in pre} | {""}
    return S, P

def _seg_options(w, S, P):
    opts = []
    for p in P:
        if not w.startswith(p): continue
        rest = w[len(p):]
        for s in S:
            if s and not rest.endswith(s): continue
            stem = rest[:len(rest) - len(s)] if s else rest
            if len(stem) >= 2: opts.append((p, stem, s))
    return opts

def build_segmenter(vocab, S, P):
    """Choose, per word, the (prefix,stem,suffix) whose STEM is most shared across the vocab (MDL-ish: reuse stems).
    Returns a dict word -> (pre,stem,suf)."""
    stemcount = collections.Counter()
    for w in set(vocab):
        for p, stem, s in _seg_options(w, S, P): stemcount[stem] += 1
    seg = {}
    for w in set(vocab):
        opts = _seg_options(w, S, P) or [("", w, "")]
        seg[w] = max(opts, key=lambda o: (stemcount[o[1]], len(o[1])))   # most-shared stem, then longest
    return seg

_SEGCACHE = {}
def segment(w, S, P):
    return _SEGCACHE.get(w, ("", w, ""))

# ---------- O2: deterministic stem<->english content lexicon by consistency ----------
def function_words(train, side):
    """English tokens appearing in a large fraction of pairs = likely function words (the, a, ...)."""
    df = collections.Counter()
    for f, e in train:
        for t in set(toks(e if side == "e" else f)): df[t] += 1
    n = len(train)
    return {t for t, c in df.items() if c >= max(3, 0.6 * n)}

def build_lexicon(train, S, P):
    """stem -> english content word, accepted only if the english candidate is CONSISTENT (same across all pairs
    containing the stem). Uses co-occurrence intersection minus english function words."""
    fw = function_words(train, "e")
    stem_e = collections.defaultdict(list)     # stem -> list of english content-token sets per pair
    for f, e in train:
        estems = set(t for t in toks(e) if t not in fw and t.isalpha())
        for w in toks(f):
            _, stem, _ = segment(w, S, P)
            stem_e[stem].append(estems)
    lex = {}
    for stem, sets in stem_e.items():
        inter = set.intersection(*sets) if sets else set()
        if len(inter) == 1: lex[stem] = next(iter(inter))
        # if intersection ambiguous, leave unknown (engine will abstain rather than guess)
    return lex, fw

# ---------- O3/O4: synchronous template induction ----------
def to_units(f, S, P):
    """foreign sentence -> list of ('stem',stem)/('aff',affix) units preserving order (prefix,stem,suffix per word)."""
    u = []
    for w in toks(f):
        pre, stem, suf = segment(w, S, P)
        if pre: u.append(("pre", pre))
        u.append(("stem", stem))
        if suf: u.append(("suf", suf))
    return u

def make_template(f, e, S, P, lex):
    """Replace aligned stems (known content) with slots on both sides -> a synchronous template.
    Foreign frame keeps affixes as literals + slot markers; English frame keeps function words + verb + slots."""
    fu = to_units(f, S, P)
    et = toks(e)
    # slots: stems whose english is known; map slot id by english word
    fframe = []; slotmap = {}; sid = 0
    used_e = {}
    for typ, val in fu:
        if typ == "stem" and val in lex:
            ew = lex[val]
            key = ew
            if key not in slotmap: slotmap[key] = f"S{sid}"; sid += 1
            fframe.append(("slot", slotmap[key])); used_e[ew] = slotmap[key]
        else:
            fframe.append(("lit", val))
    eframe = []
    for t in et:
        if t in used_e: eframe.append(("slot", used_e[t]))
        else: eframe.append(("lit", t))
    return tuple(fframe), tuple(eframe)

def induce(train, S, P, lex):
    """Set of synchronous templates (foreign-frame, english-frame). Deduplicated; each records example fills."""
    temps = collections.Counter()
    for f, e in train:
        ff, ef = make_template(f, e, S, P, lex)
        temps[(ff, ef)] += 1
    return list(temps.keys())

# ---------- O5: sound reproduction gate ----------
def render_e(ff, ef, fill_stems, S, P, lex):
    """Given a foreign-frame + a concrete foreign sentence's stems, produce english via the english-frame."""
    # match ff against fill (list of ('stem',v)/('aff',v)); bind slots by english word of stem
    return None  # rendering handled in apply()

def apply_fe(f, temps, S, P, lex):
    """foreign -> english. Find templates whose foreign-frame matches f (affix literals + known/unknown stems).
    Fill english-frame slots via lexicon. Return set of candidate english strings (for survivor-set)."""
    fu = to_units(f, S, P)
    cands = set()
    for ff, ef in temps:
        b = match_frame(fu, ff, lex)      # returns dict slotid->english word, or None
        if b is None: continue
        out = []
        ok = True
        for typ, val in ef:
            if typ == "lit": out.append(val)
            else:
                if val in b: out.append(b[val])
                else: ok = False; break
        if ok: cands.add(" ".join(out))
    return cands

def match_frame(fu, ff, lex):
    """Match foreign units fu against foreign-frame ff. Literals must equal; slots bind to the english word of that
    stem (must be in lexicon). Returns slot->english binding or None."""
    if len([1 for t, _ in ff]) != len(fu): return None
    b = {}
    for (ftyp, fval), (utyp, uval) in zip(ff, fu):
        if ftyp == "lit":
            if uval != fval: return None
        else:  # slot: the unit must be a stem with known english
            if utyp != "stem" or uval not in lex: return None
            ew = lex[uval]
            if fval in b and b[fval] != ew: return None
            b[fval] = ew
    return b

def apply_ef(e, temps, S, P, lex):
    """english -> foreign. Match english-frame literals; bind slots from english content words via reverse lexicon;
    render foreign-frame. Return candidate foreign strings."""
    rlex = {}
    for stem, ew in lex.items():
        rlex.setdefault(ew, set()).add(stem)
    et = toks(e)
    cands = set()
    for ff, ef in temps:
        if len(ef) != len(et): continue
        b = {}; ok = True
        for (etyp, eval_), t in zip(ef, et):
            if etyp == "lit":
                if t != eval_: ok = False; break
            else:
                if t not in rlex or len(rlex[t]) != 1: ok = False; break
                b[eval_] = next(iter(rlex[t]))
        if not ok: continue
        # render foreign frame
        out = []
        for typ, val in ff:
            if typ == "lit": out.append(("aff", val))
            else:
                if val not in b: ok = False; break
                out.append(("stem", b[val]))
        if not ok: continue
        cands.add(units_to_str(out))
    return cands

def units_to_str(units):
    """Reassemble ('stem'/'aff') units into words: affixes attach to adjacent stem within a word. Heuristic: a run
    stem(+suf) or (pre+)stem forms one word; use spaces between stems."""
    words = []; cur = ""
    for typ, val in units:
        if typ == "stem":
            if cur: words.append(cur)
            cur = val
        else:  # affix glues onto current
            cur += val
    if cur: words.append(cur)
    return " ".join(words)

# ---------- engine ----------
def engine(train, test_srcs=()):
    vocab = [w for f, e in train for w in toks(f)]
    vocab += [w for src in test_srcs for w in toks(src)]     # segment test source words too (no gold seen)
    S, P = discover_affixes(vocab)
    seg = build_segmenter(vocab, S, P)
    _SEGCACHE.clear(); _SEGCACHE.update(seg)
    lex, fw = build_lexicon(train, S, P)
    temps = induce(train, S, P, lex)
    return dict(S=S, P=P, lex=lex, temps=temps, seg=seg)

def _n(s): return " ".join(toks(s))
def reproduces(train, M):
    """SOUND gate: every train foreign->english reproduced (gold among candidates)."""
    ok = 0
    for f, e in train:
        c = apply_fe(f, M["temps"], M["S"], M["P"], M["lex"])
        if _n(e) in c: ok += 1
    return ok

def solve_item(item, M):
    """test item = [foreign, english, dir]. '>' foreign->english (predict english); '<' predict foreign.
    Returns ('commit', pred) / ('soft', None) / ('hard', None)."""
    fsrc, egold, d = item[0], item[1], item[2]
    if d == ">":
        cands = apply_fe(fsrc, M["temps"], M["S"], M["P"], M["lex"])
    else:
        cands = apply_ef(egold if False else item[1], M["temps"], M["S"], M["P"], M["lex"]) if False else \
                apply_ef(item[1], M["temps"], M["S"], M["P"], M["lex"])
    if not cands: return ("hard", None)
    if len(cands) > 1: return ("soft", None)
    return ("commit", next(iter(cands)))

if __name__ == "__main__":
    pz = sys.argv[1] if len(sys.argv) > 1 else "chickasaw"
    # find pilot chickasaw file (root data/chickasaw.json has gold in train+test)
    path = os.path.join(D, "chickasaw.json")
    d = load(path)
    train = [(a, b) for a, b in d["train"]]
    test_srcs = [it[0] for it in d["test"] if it[2] == ">"]
    M = engine(train, test_srcs)
    print(f"PILOT {d['source_language']}: {len(train)} train pairs")
    print(f"  affixes suf={sorted(M['S'])} pre={sorted(M['P'])}")
    print(f"  lexicon: {M['lex']}")
    print(f"  templates: {len(M['temps'])}")
    rep = reproduces(train, M)
    print(f"  SOUND reproduction of train: {rep}/{len(train)}")
    print("  TEST:")
    P = C = W = hard = soft = 0
    for it in d["test"]:
        gold = _n(it[0]) if it[2] == "<" else _n(it[1])
        st, pred = solve_item(it, M)
        pred = _n(pred) if pred else pred
        C += (st == "commit")
        if st == "commit":
            corr = (pred == gold)
            P += corr; W += (not corr)
            print(f"    [{it[2]}] {'OK ' if corr else 'WRONG'} pred={pred!r} gold={gold!r}")
        else:
            hard += (st == "hard"); soft += (st == "soft")
            print(f"    [{it[2]}] ABSTAIN-{st}  (gold={gold!r})")
    n = len(d["test"])
    print(f"  => commit {C}/{n} (P={P}/{C if C else 1}={P/C if C else 0:.2f}) wrong={W} hard={hard} soft={soft}")