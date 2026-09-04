"""VERBNET + ENTITY-STATE TRACKING (zero-LLM): solve SVAMP Add/Sub possession problems by maintaining nouns as
UNTYPED VARIABLES (it doesn't need to know what an apple is) and updating a table {(owner,item): quantity-expr}
via ONE verb-blind rule: each grammatical role slot X gets VerbNet's possession/exist delta for its ROLE TYPE,
applied to (X, Theme). Answer-blind; role-assignment-shuffle control. See vn_roles_prereg.md + fable thread ac4d1b8.

Atoms GIVEN (owner's steer: give the model the best chance, worry about emergence later): POS/proper-noun from
capitalization + WordNet; crude SVO (subject=noun before verb, object/number after, 'to X'=recipient); pronoun->
last-subject; VerbNet per-role possession/exist deltas; entity-state variables. NO verb-name / per-problem rules."""
import os, re, sys, json, glob, random, xml.etree.ElementTree as ET
sys.path.insert(0, os.path.dirname(__file__))
import vn_roles as VR                                   # reuse morphy + VerbNet paths + gold_op

D = VR.D
NUMTOK = re.compile(r"^\d+\.?\d*$")
TOK = re.compile(r"[A-Za-z]+|\d+\.?\d*")
PRON = {"she", "he", "they", "it", "him", "her", "them"}

# ---- VerbNet: per-ROLE possession/exist delta (not just Agent), + stative vs change ----------------------------
def role_deltas(root):
    """{role: '+'/'-'} for roles whose has_possession/exist CHANGES across events; {} if purely stative (has/own)."""
    poss = {}; exi = {}
    for fr in root.iter("FRAME"):
        sem = fr.find("SEMANTICS")
        if sem is None: continue
        for p in sem:
            val = p.get("value"); neg = (p.get("bool") == "!")
            args = [(a.get("type"), a.get("value")) for a in p.find("ARGS")]
            ev = VR._ev(next((av for at, av in args if at == "Event"), "e2"))
            roles = [av for at, av in args if at == "ThemRole"]
            if val == "has_possession" and len(roles) >= 2:
                poss.setdefault(roles[0], []).append((ev, neg))
            elif val in ("exist", "created", "destroyed") and roles:
                exi.setdefault(roles[0], []).append((ev, neg))
    out = {}
    for role, seq in {**poss, **exi}.items():
        seq = sorted(seq)
        first_true = not seq[0][1]; last_true = not seq[-1][1]
        if first_true and not last_true: out[role] = "-"
        elif not first_true and last_true: out[role] = "+"
    return out

def load_vn():
    members = {}; cls_roles = {}
    for f in sorted(glob.glob(os.path.join(D, "verbnet34", "*.xml"))):
        root = ET.parse(f).getroot(); cid = root.get("ID")
        cls_roles[cid] = role_deltas(root)
        for m in root.iter("MEMBER"): members.setdefault(m.get("name"), []).append(cid)
    return members, cls_roles

# ---- entity-state tracker (nouns as untyped variables) ---------------------------------------------------------
def sentences(text): return [s for s in re.split(r"[.?!]", text) if s.strip()]

def track(text, members, cls_roles, lemmatize, shuffle_roles=None):
    """Return the op-sequence for the queried (owner,item) as a list like [('=',5),('-',3)], or None if unparsed."""
    state = {}                                          # (owner,item) -> [('=',n)/('+',n)/('-',n)...]
    last_subj = None
    sents = sentences(text)
    for si, s in enumerate(sents):
        toks = TOK.findall(s)
        low = [t.lower() for t in toks]
        # verb: first token whose morphy-lemma is a VerbNet possession/change member
        vi = None; vroles = {}
        for i, t in enumerate(low):
            lem = lemmatize(t, members)
            if lem is None: continue
            rd = {}
            for c in members.get(lem, []):
                rd.update(cls_roles.get(c, {}))
            if rd: vi, vroles = i, rd; break
            if any(cls_roles.get(c) == {} and "has_possession" for c in members.get(lem, [])): pass
        # subject = nearest noun/proper-noun/pronoun BEFORE the verb (or last_subj)
        def resolve(tok):
            return last_subj if tok in PRON else tok
        subj = None
        rng = range(vi - 1, -1, -1) if vi is not None else range(len(low) - 1, -1, -1)
        for i in rng:
            if toks[i][0].isupper() and i != 0 or low[i] in PRON:
                subj = resolve(low[i]); break
        if subj is None:
            for i in (rng):
                if not NUMTOK.match(low[i]) and lemmatize(low[i], members) is None and len(low[i]) > 2:
                    subj = low[i]; break
        if subj and subj not in PRON: last_subj = subj
        subj = subj or last_subj or "_"
        # number + its item (noun right after the number)
        pair = None
        for i, t in enumerate(low):
            if NUMTOK.match(t):
                item = next((low[j] for j in range(i + 1, len(low)) if not NUMTOK.match(low[j]) and len(low[j]) > 2), "_")
                pair = (float(t), item); break
        if pair is None: continue
        n, item = pair
        # recipient = noun after 'to'
        recip = None
        if "to" in low:
            k = low.index("to")
            recip = next((resolve(low[j]) if low[j] in PRON else low[j] for j in range(k + 1, len(low))
                          if toks[j][0].isupper() or low[j] in PRON), None)
        # ROLE-ASSIGNMENT: subject->Agent, recipient->Recipient (shuffle control permutes this map)
        rolemap = {"Agent": subj, "Recipient": recip, "Patient": subj, "Theme": subj}
        if shuffle_roles is not None:
            ents = [e for e in (subj, recip) if e]; shuffle_roles.shuffle(ents)
            if ents: rolemap = {"Agent": ents[0], "Recipient": ents[-1], "Patient": ents[0], "Theme": ents[0]}
        if not vroles:                                  # STATIVE (has/own/there are) -> initial assignment
            state.setdefault((subj, item), []).append(("=", n))
        else:                                           # CHANGE -> apply each role's delta to (role-entity,item)
            for role, delta in vroles.items():
                ent = rolemap.get(role)
                if ent: state.setdefault((ent, item), []).append((delta, n))
    # QUESTION = last sentence: find queried (owner,item)
    q = sents[-1] if sents else ""; ql = [t.lower() for t in TOK.findall(q)]; qtoks = TOK.findall(q)
    q_owner = next((ql[i] if ql[i] not in PRON else last_subj for i in range(len(ql))
                    if (qtoks[i][0].isupper() and i != 0) or ql[i] in PRON), None) or last_subj
    q_item = None
    for key in state:
        if key[0] == q_owner and any(key[1] == w for w in ql): q_item = key[1]; break
    if q_item is None:                                  # fall back to any item mentioned in the question
        for key in state:
            if any(key[1] == w for w in ql): q_owner, q_item = key; break
    return state.get((q_owner, q_item))

def ops_of(seq):
    """Reduce an op-sequence to the answer-blind operator(s), ignoring the leading '=' assignment."""
    return tuple(op for op, _ in seq if op in "+-")

if __name__ == "__main__":
    members, cls_roles = load_vn(); lemmatize = VR.load_morphy()
    data = json.load(open(os.path.join(D, "SVAMP.json"), encoding="utf-8"))
    def is_money(d): return "$" in d["Body"] or "dollar" in d["Body"].lower() or "cost" in d["Body"].lower() or "money" in (d["Body"]+d["Question"]).lower()
    poss_verbs = {m for m in members if any(cls_roles.get(c) for c in members[m])}
    def has_poss_verb(d):
        return any(lemmatize(t.lower(), members) in poss_verbs for t in TOK.findall(d["Body"]+" "+d["Question"]) if lemmatize(t.lower(), members))
    inst = [d for d in data if VR.gold_op(d["Equation"]) and len(re.findall(r"\d+\.?\d*", d["Body"])) == 2
            and not is_money(d) and has_poss_verb(d)]
    random.Random(2024).shuffle(inst)
    print(f"ENTITY-STATE TRACKING | instance = {len(inst)} (Add/Sub, 2 nums in Body, non-money, possession verb)\n")

    def run(shuf_seed=None):
        parsed = correct = plus_ok = plus_tot = 0
        for d in inst:
            sr = random.Random(shuf_seed) if shuf_seed is not None else None
            seq = track(d["Body"] + " " + d["Question"], members, cls_roles, lemmatize, shuffle_roles=sr)
            if not seq: continue
            got = ops_of(seq)
            if len(got) != 1: continue                  # single-op answer-blind prediction
            parsed += 1
            g = VR.gold_op(d["Equation"])
            if got[0] == g: correct += 1
            if g == "+": plus_tot += 1; plus_ok += (got[0] == "+")
        return parsed, correct, plus_ok, plus_tot

    p, c, pok, ptot = run()
    sh = [run(shuf_seed=k) for k in (7, 11, 23)]
    sp = sum(x[0] for x in sh) / 3; sc = sum(x[1] for x in sh) / 3
    golds = [VR.gold_op(d["Equation"]) for d in inst]; maj = max("+-", key=golds.count)
    print(f"  parse coverage {p}/{len(inst)} ({100*p//max(1,len(inst))}%)")
    print(f"  ANSWER-BLIND operator accuracy:")
    print(f"    ENTITY-TRACK (real roles) {c}/{p} ({100*c//max(1,p)}%)")
    print(f"    ROLE-SHUFFLE control      {sc:.0f}/{sp:.0f} ({100*sc/max(1,sp):.0f}%)  (avg 3 seeds)")
    print(f"    MAJORITY-op '{maj}'          {golds.count(maj)}/{len(golds)} ({100*golds.count(maj)//len(golds)}%)")
    print(f"  THE prior failure -- '+' predictions on the tracked entity: {pok}/{ptot} correct "
          f"(was 0/5 with VerbNet-only)")
    ratio = (c/max(1,p)) / max(1e-9, sc/max(1,sp))
    win = (c/max(1,p)) >= 2*(sc/max(1,sp)) and c/max(1,p) > golds.count(maj)/len(golds) and pok > 0
    print(f"\n  ENTITY-TRACK / SHUFFLE = {ratio:.2f}x")
    print(f"  RESULT: {'PARTIAL WIN -- symbolic entity-tracking (untyped variables + roles + VerbNet) binds the operator the lexicon could not' if win else 'not yet a win (see numbers)'}.")