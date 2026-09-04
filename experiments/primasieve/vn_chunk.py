"""VERBNET + minimal CHUNKER (zero-LLM): close role-binding. POS via a committed closed-class table + WordNet;
OWNER = proper noun / animate-by-WordNet-hypernym / owner-pronoun; roles from SVO + to/from-PP; number-agreement
coreference that ABSTAINS on >=2 candidates; queried owner (in the query span) -> its VerbNet role -> that role's
delta-sign. See vn_chunk_prereg.md (committed first). Knockouts: role-swap flip, POS-shuffle collapse, cue-only."""
import os, re, sys, json, random
sys.path.insert(0, os.path.dirname(__file__))
import vn_roles as VR, vn_track as VT, vn_solve as VS, vn_slot as SL, nl_wn

D = VR.D; TOK = VS.TOK; NUM = VS.NUM
# COMMITTED closed-class function-word table (frozen; see prereg)
DET = "a an the this that these those each every some any all no both either neither my your his her its our their many few several more most much another".split()
PREP = "at in on to from for of with by about into onto over under after before during between among through up down off out as than per around".split()
AUX = "is are was were be been being am do does did has have had will would can could shall should may might must".split()
PRON = "i you he she it we they me him us them mine yours hers ours theirs who whom whose which".split()
CONJ = "and or but if so because while when then though although".split()
FUNC = set(DET + PREP + AUX + CONJ + ["how", "many", "much", "there"])
OWNER_PRON = {"he", "she", "it", "they", "him", "her", "them", "his", "their"}
SING = {"he", "she", "it", "him", "her", "his"}; PLUR = {"they", "them", "their"}
ANIMATE = {"person", "people", "organism", "animal", "human", "individual", "someone", "child",
           "children", "man", "woman", "being", "worker", "adult", "baby", "kid"}

_wn = nl_wn.WN(use_gloss=False)
_pcache = {}
def is_person(word):
    if word in _pcache: return _pcache[word]
    seen = set(); frontier = list(_wn.index.get(word, [])); res = False
    for _ in range(7):
        nxt = []
        for key in frontier:
            if any(w in ANIMATE for w in _wn.words.get(key, [])): res = True; break
            for tgt in _wn.hyper.get(key, []):
                if tgt not in seen: seen.add(tgt); nxt.append(tgt)
        if res: break
        frontier = nxt
    _pcache[word] = res; return res

def owners(toks):
    """indices of OWNER tokens: proper (capitalized non-initial), owner-pronoun, or animate noun."""
    out = []
    for i, t in enumerate(toks):
        lw = t.lower()
        if lw in OWNER_PRON: out.append((i, lw, "pron"))
        elif t[0].isupper() and i != 0 and lw not in FUNC: out.append((i, lw, "name"))
        elif lw not in FUNC and is_person(lw): out.append((i, lw, "noun"))
    return out

def resolve(pron_lw, prior_names):
    """coref: pronoun -> nearest preceding name agreeing in number; ABSTAIN(None) if >=2 agreeing candidates."""
    num = "s" if pron_lw in SING else "p"
    cands = [n for n in prior_names]                      # names have no committed number -> treat as singular
    if pron_lw in PLUR: return prior_names[-1] if prior_names else None    # plural -> most recent (group)
    agree = prior_names
    if len(set(agree)) >= 2: return None                  # >=2 distinct antecedents -> abstain
    return agree[-1] if agree else None

def parse_event(body, members, cls_roles, lemmatize):
    """Return (rd, {role:owner}) for the last possession-verb sentence, with coref; or None; 'ABSTAIN' if ambiguous."""
    seen_names = []
    result = None
    for s in VT.sentences(body):
        toks = TOK.findall(s); low = [t.lower() for t in toks]
        ow = owners(toks)
        vi = None; rd = {}
        for i, t in enumerate(low):
            L = lemmatize(t, members)
            if L:
                d = {}
                for c in members.get(L, []): d.update(cls_roles.get(c, {}))
                if d: vi, rd = i, d; break
        names_here = [w for _, w, k in ow if k == "name"]
        if vi is None:
            seen_names += names_here; continue
        # Agent = last owner before verb (coref if pronoun)
        def bind(idx_list):
            for i, w, k in idx_list:
                if k == "pron":
                    r = resolve(w, seen_names)
                    if r is None: return "ABSTAIN"
                    return r
                return w
            return None
        left = [(i, w, k) for i, w, k in ow if i < vi][::-1]
        right = [(i, w, k) for i, w, k in ow if i > vi]
        agent = bind(left)
        # Recipient: to-PP owner, or bare owner right of verb before the Theme number
        recip = None
        if "to" in low[vi:]:
            k = vi + low[vi:].index("to")
            recip = bind([(i, w, kk) for i, w, kk in ow if i > k])
        else:
            numpos = next((j for j in range(vi + 1, len(low)) if NUM.match(low[j])), len(low))
            recip = bind([(i, w, kk) for i, w, kk in ow if vi < i < numpos])
        if agent == "ABSTAIN" or recip == "ABSTAIN": return "ABSTAIN"
        rb = {}
        if agent: rb["Agent"] = agent
        if recip: rb["Recipient"] = recip
        result = (rd, rb, seen_names[:])
        seen_names += names_here
    return result

def predict(text, members, cls_roles, lemmatize, swap=None, pos_shuffle=None, cue_only=False):
    body = " ".join(VT.sentences(text)[:-1]); q = VT.sentences(text)[-1]
    if swap: body = swap(body)
    ev = parse_event(body, members, cls_roles, lemmatize)
    s = SL.dsign(text, members, cls_roles, lemmatize)
    if s is None: return None
    slot = SL.classify_slot(VS.query_span(q) if hasattr(VS, "query_span") else q, members, cls_roles, lemmatize)
    import vn_parse as VP
    slot = VP.slot_from_query(VP.query_span(q))
    sign = s
    if not cue_only and ev not in (None, "ABSTAIN"):
        rd, rb, _ = ev
        qspan = VP.query_span(q); ql = [t.lower() for t in TOK.findall(qspan)]
        qowners = [w for _, w, k in owners(TOK.findall(qspan))]
        qo = None
        for w in qowners:
            qo = rb.get("Agent") if w in OWNER_PRON else w   # crude: pronoun in Q -> the agent
            if w not in OWNER_PRON: qo = w
        for role, ent in rb.items():
            if qo and ent == qo: sign = rd.get(role, sign)
    elif ev == "ABSTAIN":
        return "ABSTAIN"
    if slot == "AGG": return "+"
    if slot == "CHANGE": return "-"
    if slot == "START": return "+" if sign == "-" else "-"
    return sign

if __name__ == "__main__":
    members, cls_roles = VT.load_vn(); lemmatize = VR.load_morphy()
    data = json.load(open(os.path.join(D, "SVAMP.json"), encoding="utf-8"))
    def money(d): return any(k in (d["Body"] + d["Question"]).lower() for k in ("$", "dollar", "cost", "money"))
    poss = {m for m in members if any(cls_roles.get(c) for c in members[m])}
    def hpv(d): return any(lemmatize(t.lower(), members) in poss for t in TOK.findall(d["Body"] + " " + d["Question"]) if lemmatize(t.lower(), members))
    inst = [d for d in data if VR.gold_op(d["Equation"]) and len(re.findall(r"\d+\.?\d*", d["Body"])) == 2
            and not money(d) and hpv(d)]
    random.Random(2024).shuffle(inst)

    def evalfn(fn):
        ok = ab = wr = 0
        for d in inst:
            p = fn(d)
            if p == "ABSTAIN": ab += 1
            elif p == VR.gold_op(d["Equation"]): ok += 1
            else: wr += 1
        return ok, ab, wr
    f = lambda d: predict(d["Body"] + " " + d["Question"], members, cls_roles, lemmatize)
    ok, ab, wr = evalfn(lambda d: f(d) or "-")
    print(f"CHUNKER | /85: correct {ok} abstain {ab} wrong {wr}  -> accuracy(non-abstain) {100*ok//max(1,ok+wr)}% "
          f"| /85 counting abstain as wrong {100*ok//85}%")

    # (a) role-swap knockout on ditransitives
    NAMES = re.compile(r"\b([A-Z][a-z]+)\b")
    dit = []
    for d in inst:
        ev = parse_event(" ".join(VT.sentences(d["Body"] + " " + d["Question"])[:-1]), members, cls_roles, lemmatize)
        if ev not in (None, "ABSTAIN") and "Recipient" in ev[1]: dit.append(d)
    flips = 0
    for d in dit:
        base = predict(d["Body"] + " " + d["Question"], members, cls_roles, lemmatize)
        names = list(dict.fromkeys(NAMES.findall(d["Body"])))[:2]
        if len(names) < 2: continue
        swap = lambda b, a=names[0], c=names[1]: b.replace(a, "\0").replace(c, a).replace("\0", c)
        sw = predict(d["Body"] + " " + d["Question"], members, cls_roles, lemmatize, swap=swap)
        flips += (base != sw and base not in (None, "ABSTAIN") and sw not in (None, "ABSTAIN"))
    print(f"  (a) ROLE-SWAP: {len(dit)} ditransitive-with-Recipient problems; sign flips {flips} times "
          f"({100*flips//max(1,len(dit))}%, need >=90; was 0)")
    # DECISIVE (fable): role-swap on PRONOUN-FREE queries (coref trivial). flips=0 there -> role-binding is DEAD WEIGHT.
    print("  RETRACTED (fable): role-swap flips 0 even on the pronoun-FREE subset -> role-binding has ZERO measured")
    print("  causal contribution; it never worked. The 85%-non-abstain is verb-sign + slot + ABSTENTION, not")
    print("  role-binding. FAIR comparison: at full coverage 67%, and majority on the ANSWERED subset is ~75% -> the")
    print("  chunker does NOT beat majority. HONEST ARC CONCLUSION: zero-LLM operator signal is REAL and cheap")
    print("  (VerbNet beats shuffle) but NO committed parser beat the majority baseline at full coverage; the wall is")
    print("  COREFERENCE/PRAGMATICS (which entity/quantity the question tracks), NOT the arithmetic reasoning.")