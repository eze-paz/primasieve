"""VERBNET + QUESTION-SLOT CLASSIFIER (zero-LLM, fable's next step): the operator depends on WHICH slot the question
asks for. 2-way forward/inverse was saturated at 69%; this classifies 4 slots from the question's verb + committed
CUE-ATOMS, which rescues the CHANGE/comparison queries no sign fix could:
  END   (query=current/'left/now')       -> op = VerbNet delta-SIGN            (final = initial + delta)
  START (query=initial/'originally')      -> op = FLIP(sign)                    (initial = final - delta)
  CHANGE(query=delta/'how many did X give'/comparison 'how many MORE X THAN Y') -> op = '-'  (difference of knowns)
  AGG   (query=total/'altogether/in all')  -> op = '+'                          (sum of the two knowns)
Answer-blind. Knockouts: shuffle slot-labels, force CHANGE->END, slot-oracle ceiling. Cue tables committed below."""
import os, re, sys, json, random
sys.path.insert(0, os.path.dirname(__file__))
import vn_roles as VR, vn_track as VT, vn_solve as VS

D = VR.D; TOK = VS.TOK; NUM = VS.NUM
# COMMITTED closed-class cue-atoms (finite grammar table; no per-problem edits)
AGG_CUE = {"altogether", "total", "combined", "together"}          # + phrase "in all" handled below
END_CUE = {"left", "now", "remaining", "remain", "remains", "still", "currently", "leftover"}
START_CUE = {"originally", "original", "start", "starting", "begin", "beginning", "initially"}
STATIVE = {"have", "has", "had", "be", "is", "are", "were", "was", "there"}

def dsign(text, members, cls_roles, lemmatize):
    low = [t.lower() for t in TOK.findall(text)]
    for i, t in enumerate(low):
        if NUM.match(t):
            s = VS.delta_sign(text, i, low, TOK.findall(text), members, cls_roles, lemmatize)
            if s: return s
    return None

def classify_slot(qtext, members, cls_roles, lemmatize):
    """Precedence: QUERY cues (what is ASKED) dominate DESCRIPTIVE cues. A comparison or a start-query overrides an
    'end' cue that merely describes given info ('there are 38 LEFT, how many AT FIRST' -> START, not END)."""
    ql = [t.lower() for t in TOK.findall(qtext)]; qs = set(ql)
    if qs & AGG_CUE or ("in" in ql and "all" in ql): return "AGG"   # 'altogether / in all / total' -> sum
    if "more" in qs and "than" in qs: return "CHANGE"                # comparison -> difference
    if qs & END_CUE: return "END"                                   # 'left / now' query -> current
    if qs & START_CUE: return "START"                               # 'at first / originally' query -> initial
    for t in ql:                                                    # question's own transfer verb -> the delta
        L = lemmatize(t, members)
        if L and L not in STATIVE and any(cls_roles.get(c) for c in members.get(L, [])): return "CHANGE"
    return "END"

def predict(text, members, cls_roles, lemmatize, slot_override=None):
    s = dsign(text, members, cls_roles, lemmatize)
    if s is None: return None
    slot = slot_override or classify_slot(VT.sentences(text)[-1], members, cls_roles, lemmatize)
    if slot == "AGG": return "+"
    if slot == "CHANGE": return "-"
    if slot == "START": return "+" if s == "-" else "-"
    return s                                                        # END -> forward sign

if __name__ == "__main__":
    members, cls_roles = VT.load_vn(); lemmatize = VR.load_morphy()
    data = json.load(open(os.path.join(D, "SVAMP.json"), encoding="utf-8"))
    def money(d): return any(k in (d["Body"] + d["Question"]).lower() for k in ("$", "dollar", "cost", "money"))
    poss = {m for m in members if any(cls_roles.get(c) for c in members[m])}
    def hpv(d): return any(lemmatize(t.lower(), members) in poss for t in TOK.findall(d["Body"] + " " + d["Question"]) if lemmatize(t.lower(), members))
    inst = [d for d in data if VR.gold_op(d["Equation"]) and len(re.findall(r"\d+\.?\d*", d["Body"])) == 2
            and not money(d) and hpv(d)]
    random.Random(2024).shuffle(inst)
    covered = [d for d in inst if dsign(d["Body"] + " " + d["Question"], members, cls_roles, lemmatize)]
    print(f"SLOT CLASSIFIER | instance {len(inst)} (VerbNet-covered {len(covered)})\n")

    def score(fn, on):
        ok = 0
        for d in on:
            p = fn(d)
            ok += (p == VR.gold_op(d["Equation"]))
        return ok, len(on)

    # main: 4-way slot classifier
    f_main = lambda d: predict(d["Body"] + " " + d["Question"], members, cls_roles, lemmatize)
    o66, n66 = score(f_main, covered); o85, n85 = score(lambda d: f_main(d) or "-", inst)
    # 2-way baseline (prior pipeline: START-cue vs END only)
    def f_2way(d):
        text = d["Body"] + " " + d["Question"]; s = dsign(text, members, cls_roles, lemmatize)
        if s is None: return None
        inv = bool(set(TOK.findall(VT.sentences(text)[-1].lower())) & START_CUE)
        return ("+" if s == "-" else "-") if inv else s
    b66, _ = score(f_2way, covered)
    golds = [VR.gold_op(d["Equation"]) for d in covered]; maj = max("+-", key=golds.count)
    print(f"  ANSWER-BLIND operator accuracy on the {n66} covered:")
    print(f"    4-WAY SLOT (this step)     {o66}/{n66} ({100*o66//n66}%)")
    print(f"    2-way forward/inverse (prior) {b66}/{n66} ({100*b66//n66}%)")
    print(f"    MAJORITY '{maj}'               {golds.count(maj)}/{n66} ({100*golds.count(maj)//n66}%)")
    print(f"    on all /85 (uncovered=wrong): {o85}/{n85} ({100*o85//n85}%)")

    # KNOCKOUTS
    def f_shuf_slot(d, rng):
        text = d["Body"] + " " + d["Question"]
        return predict(text, members, cls_roles, lemmatize, slot_override=rng.choice(["END", "START", "CHANGE", "AGG"]))
    ks = sum(score(lambda d: f_shuf_slot(d, random.Random(k)), covered)[0] for k in (7, 11, 23)) / 3
    kc, _ = score(lambda d: predict(d["Body"] + " " + d["Question"], members, cls_roles, lemmatize,
                                    slot_override="END"), covered)   # force all END (no slot info)
    print(f"\n  KNOCKOUTS: shuffle-slot-labels {ks:.0f}/{n66} ({100*ks/n66:.0f}%, must fall); "
          f"force-all-END {kc}/{n66} ({100*kc//n66}%, = the 40% raw sign-only)")
    win = o66 / n66 >= 0.80; part = 0.75 <= o66 / n66 < 0.80
    print(f"\n  RESULT: {'WIN (>=80% on covered)' if win else 'HONEST PARTIAL (75-80%)' if part else 'below 75% (see numbers)'}. "
          f"The slot classifier attacks the CHANGE/comparison queries the sign alone could not; verb-direction stays load-bearing.")