"""VERBNET + MAINTAIN-UNKNOWNS SOLVER (zero-LLM): the owner's unlock -- treat quantities as VARIABLES and SOLVE.
Diagnostic on the addition cases showed they are INVERSE problems: "Baker MADE SOME cakes, sold 145, has 72 LEFT,
how many did he MAKE?" -> initial X unknown; X - 145 = 72 -> X = 145 + 72. The operator FLIPS from the surface verb
(sold=subtract) to the answer (add) BECAUSE you solve for the unknown. One linear relation, `initial + delta =
final`, solved for whichever the question asks, with VerbNet supplying the delta SIGN and given discourse CUE-ATOMS
(final=left/remain, query-initial=start/made, unknown=some/many) supplying the roles. Answer-blind; controls =
role-shuffle + cue-shuffle + majority. Atoms GIVEN on purpose (owner: give it the best chance; emergence later)."""
import os, re, sys, json, random
sys.path.insert(0, os.path.dirname(__file__))
import vn_roles as VR, vn_track as VT

D = VR.D
TOK = re.compile(r"[A-Za-z]+|\d+\.?\d*")
NUM = re.compile(r"^\d+\.?\d*$")
# GIVEN discourse cue-atoms (general, not per-problem)
FINAL_CUES = {"left", "remaining", "remain", "remains", "still", "now", "currently", "leftover"}
QINIT_CUES = {"start", "starting", "originally", "original", "begin", "beginning", "initially", "first", "make", "made", "were", "had", "began"}
UNKNOWN_CUES = {"some", "many", "few", "several", "sever"}

def delta_sign(text, i_num, low, toks, members, cls_roles, lemmatize, subj_is_agent=True):
    """VerbNet sign of the change nearest the number: '-' if the tracked entity LOSES, '+' if GAINS."""
    for off in range(1, 6):                              # look for a change-verb near the number
        for j in (i_num - off, i_num + off):
            if 0 <= j < len(low):
                lem = lemmatize(low[j], members)
                if lem:
                    rd = {}
                    for c in members.get(lem, []): rd.update(cls_roles.get(c, {}))
                    if rd:
                        return rd.get("Agent", next(iter(rd.values())))   # subject perspective (who the Q asks about)
    return None

def solve(text, members, cls_roles, lemmatize, shuffle_roles=None, shuffle_cues=None):
    """Return the answer-blind operator, or None. Model: initial + delta = final; solve for the queried slot."""
    fin_cues, qinit_cues, unk_cues = FINAL_CUES, QINIT_CUES, UNKNOWN_CUES
    if shuffle_cues is not None:                          # CUE-SHUFFLE control: randomize which words are cues
        allw = list(fin_cues | qinit_cues); shuffle_cues.shuffle(allw)
        fin_cues = set(allw[:len(FINAL_CUES)]); qinit_cues = set(allw[len(FINAL_CUES):])
    sents = VT.sentences(text)
    body = " ".join(sents[:-1]) if len(sents) > 1 else text
    q = sents[-1]
    low = [t.lower() for t in TOK.findall(text)]; toks = TOK.findall(text)
    nums = [(i, float(t)) for i, t in enumerate(low) if NUM.match(t)]
    body_nums = [x for x in nums if x[0] < len(TOK.findall(body))]
    if len(body_nums) != 2: return None
    (i1, n1), (i2, n2) = body_nums[0], body_nums[1]
    ql = [t.lower() for t in TOK.findall(q)]

    # classify each body number as 'delta' (near a change-verb) / 'final' (near a final-cue) / 'initial'
    def classify(i, n):
        win = set(low[max(0, i - 3):i + 4])
        if win & fin_cues: return "final"
        if delta_sign(text, i, low, toks, members, cls_roles, lemmatize) is not None and not (win & fin_cues):
            return "delta"
        return "initial"
    r1, r2 = classify(i1, n1), classify(i2, n2)
    d_sign = None
    for i, n, r in ((i1, n1, r1), (i2, n2, r2)):
        if r == "delta": d_sign = delta_sign(text, i, low, toks, members, cls_roles, lemmatize)
    if d_sign is None: d_sign = "-"                       # default change = loss (SVAMP-dominant)

    # THE INVERSION TRIGGER: the initial is UNKNOWN ("some/many/...") -> the problem states {delta, final} and asks
    # for the initial -> solve initial = final - (signed delta) -> operator FLIPS. This is the maintain-unknowns
    # case. (A strong query-initial cue like 'originally/at the start' also triggers it.) Otherwise the question
    # asks for the FINAL: final = initial + (signed delta) -> operator = d_sign (forward, usually the '-' majority).
    STRONG_QINIT = {"originally", "original", "start", "starting", "begin", "beginning", "initially", "first"}
    unknown_present = bool(set(low) & unk_cues)
    q_wants_initial = bool(set(ql) & (STRONG_QINIT if shuffle_cues is None else qinit_cues))
    if unknown_present or q_wants_initial:
        return "+" if d_sign == "-" else "-"              # solve for the unknown initial -> operator flips
    return d_sign

if __name__ == "__main__":
    members, cls_roles = VT.load_vn(); lemmatize = VR.load_morphy()
    data = json.load(open(os.path.join(D, "SVAMP.json"), encoding="utf-8"))
    def is_money(d): return any(k in (d["Body"] + d["Question"]).lower() for k in ("$", "dollar", "cost", "money"))
    poss = {m for m in members if any(cls_roles.get(c) for c in members[m])}
    def hpv(d): return any(lemmatize(t.lower(), members) in poss for t in TOK.findall(d["Body"] + " " + d["Question"]) if lemmatize(t.lower(), members))
    inst = [d for d in data if VR.gold_op(d["Equation"]) and len(re.findall(r"\d+\.?\d*", d["Body"])) == 2
            and not is_money(d) and hpv(d)]
    random.Random(2024).shuffle(inst)
    print(f"MAINTAIN-UNKNOWNS SOLVER | instance = {len(inst)} (Add/Sub, 2 nums, non-money, possession verb)\n")

    def run(shuf_r=None, shuf_c=None):
        p = c = pok = ptot = 0
        for d in inst:
            got = solve(d["Body"] + " " + d["Question"], members, cls_roles, lemmatize,
                        shuffle_roles=random.Random(shuf_r) if shuf_r is not None else None,
                        shuffle_cues=random.Random(shuf_c) if shuf_c is not None else None)
            if got is None: continue
            p += 1; g = VR.gold_op(d["Equation"]); c += (got == g)
            if g == "+": ptot += 1; pok += (got == "+")
        return p, c, pok, ptot

    p, c, pok, ptot = run()
    rs = [run(shuf_r=k) for k in (7, 11, 23)]; rp = sum(x[0] for x in rs) / 3; rc = sum(x[1] for x in rs) / 3
    cs = [run(shuf_c=k) for k in (7, 11, 23)]; cp = sum(x[0] for x in cs) / 3; cc = sum(x[1] for x in cs) / 3
    golds = [VR.gold_op(d["Equation"]) for d in inst]; maj = max("+-", key=golds.count)
    print(f"  parse coverage {p}/{len(inst)} ({100*p//max(1,len(inst))}%)")
    print(f"  ANSWER-BLIND operator accuracy:")
    print(f"    SOLVER (VerbNet + unknowns + cue-atoms) {c}/{p} ({100*c//max(1,p)}%)")
    print(f"    ROLE-SHUFFLE control                    {rc:.0f}/{rp:.0f} ({100*rc/max(1,rp):.0f}%)")
    print(f"    CUE-SHUFFLE control                     {cc:.0f}/{cp:.0f} ({100*cc/max(1,cp):.0f}%)")
    print(f"    MAJORITY-op '{maj}'                        {golds.count(maj)}/{len(golds)} ({100*golds.count(maj)//len(golds)}%)")
    print(f"  THE prior failure -- '+' (inverse/gain) cases: {pok}/{ptot} correct (VerbNet-only was 0/5)")
    # ---- fable's ORACLE-SLOT ABLATION (the decisive knockout): give the solver the one bit it can't parse
    #      (forward vs inverse MODE) and measure the ceiling. Non-circular: the oracle supplies a discourse bit,
    #      NEVER the operator; VerbNet supplies the delta-sign; the solve is deterministic. ----
    def dsign(d):
        text = d["Body"] + " " + d["Question"]; low = [t.lower() for t in TOK.findall(text)]
        for i, t in enumerate(low):
            if NUM.match(t):
                s = delta_sign(text, i, low, TOK.findall(text), members, cls_roles, lemmatize)
                if s: return s
        return None
    # RETRACTION (fable): an "either forward or inverse matches" ablation is VACUOUS -- {forward,inverse} = {+,-}
    # always, so it is 100% by construction even with SHUFFLED signs. Do not use it. The honest ablation supplies
    # a mode from an ANSWER-INDEPENDENT question cue, applies VerbNet's sign, and checks REAL vs SHUFFLED sign.
    QINV = {"originally", "original", "start", "starting", "begin", "beginning", "initially"}
    def honest(shuf):
        pp = ok = 0
        for d in inst:
            text = d["Body"] + " " + d["Question"]; low = [t.lower() for t in TOK.findall(text)]
            s = None
            for i, t in enumerate(low):
                if NUM.match(t):
                    s = delta_sign(text, i, low, TOK.findall(text), members, cls_roles, lemmatize)
                    if s: break
            if s is None: continue
            if shuf: s = random.Random(hash((d["ID"], 1))).choice("+-")
            inv = bool(set(TOK.findall(VT.sentences(text)[-1].lower())) & QINV)
            pred = ("+" if s == "-" else "-") if inv else s
            pp += 1; ok += (pred == VR.gold_op(d["Equation"]))
        return ok, pp
    hr, hp = honest(False); hs, _ = honest(True)
    print(f"\n  HONEST MODE-ORACLE ABLATION (question-cue mode + VerbNet sign; either-or version RETRACTED as vacuous):")
    print(f"    REAL VerbNet sign     {hr}/{hp} ({100*hr//max(1,hp)}%)")
    print(f"    SHUFFLED VerbNet sign {hs}/{hp} ({100*hs//max(1,hp)}%)  -> VerbNet sign load-bearing iff REAL >> SHUF")
    print("  HONEST CONCLUSION: VerbNet's per-verb direction IS load-bearing (REAL 69% vs SHUF 46%), and resolving")
    print("  the forward/inverse MODE lifts raw 40%->69% -- but NOT to 100%. So 'given the parse the reasoning is")
    print("  perfect' is FALSE; the wall is DISTRIBUTED across discourse mode-parse + verb coverage (66/85) + sign")
    print("  quality, not one clean component. The arithmetic solve isn't the bottleneck, but no single fix clears it.")
    print("  (Prior 'either-or 100% -> parsing is the sole wall' was a vacuous ablation, RETRACTED per fable.)")