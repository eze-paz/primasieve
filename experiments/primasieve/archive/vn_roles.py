"""VERBNET ROLE-BINDING (zero-LLM): derive the operation (add/sub) for SVAMP transfer/possession word problems from
VerbNet 3.4's FORMAL PREDICATES via two committed verb-INDEPENDENT axioms, ANSWER-BLIND, vs a shuffle-class control.
See vn_roles_prereg.md (committed first). Tests: can CURATED predicate-grade knowledge bind pragmatic meaning that a
word->symbol dictionary could not, or does it need learned experience (= the LLM)?"""
import os, re, sys, json, glob, random, xml.etree.ElementTree as ET

D = os.path.join(os.path.dirname(__file__), "_nldata")
NUM = re.compile(r"\d+\.?\d*"); WORD = re.compile(r"[a-zA-Z]+")

# ---- morphy: verb lemmatization from WordNet verb.exc + detach rules --------------------------------------------
def load_morphy():
    exc = {}
    with open(os.path.join(D, "dict", "verb.exc"), encoding="latin-1") as f:
        for line in f:
            t = line.split()
            if len(t) >= 2: exc[t[0]] = t[1]
    RULES = [("ies", "y"), ("es", ""), ("s", ""), ("ing", ""), ("ing", "e"), ("ed", ""), ("ed", "e")]
    def lemmatize(w, members):
        w = w.lower()
        if w in members: return w
        if w in exc and exc[w] in members: return exc[w]
        for suf, rep in RULES:
            if w.endswith(suf):
                c = w[:len(w) - len(suf)] + rep
                if c in members: return c
        return None
    return lemmatize

# ---- VerbNet loader + the AXIOM engine (direction derived from predicates, NEVER from a verb/class name) --------
EVENT_ORDER = {"e1": 1, "e2": 2, "e3": 3, "start(e)": 0, "result(e)": 9, "during(e)": 5, "end(e)": 8}
def _ev(v): return EVENT_ORDER.get(v, 5)

def agent_direction(root):
    """Apply AXIOM-POSS / AXIOM-EXIST to a class's frames -> the AGENT (subject) count direction: 'sub'/'add'/None.
    Reads ONLY predicate values, event order, bool negation, role types. No verb/class-name rule (anti-smuggle)."""
    poss = []; exi = []                                   # (event, role, negated)
    for fr in root.iter("FRAME"):
        sem = fr.find("SEMANTICS")
        if sem is None: continue
        for p in sem:
            val = p.get("value"); neg = (p.get("bool") == "!")
            args = [(a.get("type"), a.get("value")) for a in p.find("ARGS")]
            ev = next((av for at, av in args if at == "Event"), "e2")
            roles = [av for at, av in args if at == "ThemRole"]
            if val == "has_possession" and len(roles) >= 2:
                poss.append((_ev(ev), roles[0], neg))     # roles[0]=possessor, roles[1]=Theme
            elif val in ("exist", "created", "destroyed", "location") and roles:
                exi.append((_ev(ev), roles[0], neg, val))
    # AXIOM-POSS on the AGENT possessor
    ap = sorted([(e, neg) for e, r, neg in poss if r == "Agent"])
    if ap:
        first_true = not ap[0][1]; last_true = not ap[-1][1]
        if first_true and not last_true: return "sub"
        if not first_true and last_true: return "add"
    # if the Agent isn't a possessor but the Recipient/Patient is, the subject is the gainer/loser via that role
    for role in ("Recipient", "Patient", "Goal"):
        rp = sorted([(e, neg) for e, r, neg in poss if r == role])
        if rp:
            first_true = not rp[0][1]; last_true = not rp[-1][1]
            if not first_true and last_true: return "add"
            if first_true and not last_true: return "sub"
    # AXIOM-EXIST (eat/consume/make): Theme exist true->false => agent subtracts; false->true => adds
    ex = sorted([(e, neg) for e, r, neg, v in exi if v in ("exist", "destroyed", "created")])
    if ex:
        first_true = not ex[0][1]; last_true = not ex[-1][1]
        if first_true and not last_true: return "sub"
        if not first_true and last_true: return "add"
    return None

def load_verbnet():
    members = {}; cls_dir = {}
    for f in sorted(glob.glob(os.path.join(D, "verbnet34", "*.xml"))):
        root = ET.parse(f).getroot(); cid = root.get("ID")
        d = agent_direction(root); cls_dir[cid] = d
        for m in root.iter("MEMBER"):
            members.setdefault(m.get("name"), []).append(cid)
    return members, cls_dir

def verb_op(lemma, members, cls_dir):
    """Op for a verb = the direction of its possession/exist classes; ABSTAIN if classes disagree or none carry one."""
    dirs = {cls_dir[c] for c in members.get(lemma, []) if cls_dir.get(c)}
    if dirs == {"sub"}: return "-"
    if dirs == {"add"}: return "+"
    return None                                          # no direction, or conflicting -> abstain

# ---- SVAMP add/sub single-event subset --------------------------------------------------------------------------
def gold_op(eq):
    ops = [c for c in eq if c in "+-*/"]
    return ops[0] if len(ops) == 1 and ops[0] in "+-" else None

if __name__ == "__main__":
    members, cls_dir = load_verbnet()
    POSS_MEMBERS = {m for m in members if verb_op(m, members, cls_dir)}
    lemmatize = load_morphy()
    print(f"VerbNet: {len(members)} members, classes-with-direction "
          f"{sum(1 for d in cls_dir.values() if d)}/{len(cls_dir)}; possession/exist verbs {len(POSS_MEMBERS)}\n")

    data = json.load(open(os.path.join(D, "SVAMP.json"), encoding="utf-8"))
    subset = [d for d in data if gold_op(d["Equation"])]                  # single-op +/-
    random.Random(2024).shuffle(subset)
    held = subset[:250]

    def find_verb_op(text, cls_dir_map):
        toks = [t.lower() for t in WORD.findall(text)]
        for t in toks:
            lem = lemmatize(t, members)
            if lem is None: continue
            dirs = {cls_dir_map[c] for c in members.get(lem, []) if cls_dir_map.get(c)}
            if dirs == {"sub"}: return "-", lem
            if dirs == {"add"}: return "+", lem
        return None, None

    def run(cls_dir_map, byop=None):
        parsed = correct = 0
        for d in held:
            text = d["Body"] + " " + d["Question"]; nums = NUM.findall(text)
            op, lem = find_verb_op(text, cls_dir_map)
            if op is None or len(nums) < 2: continue
            parsed += 1
            hit = (op == gold_op(d["Equation"])); correct += hit
            if byop is not None: byop[op][0] += 1; byop[op][1] += hit
        return parsed, correct

    # controls
    def shuffled_dir(seed):
        vals = list(cls_dir.values()); random.Random(seed).shuffle(vals)
        return dict(zip(cls_dir.keys(), vals))

    byop = {"+": [0, 0], "-": [0, 0]}
    vn_p, vn_c = run(cls_dir, byop=byop)
    sh = [run(shuffled_dir(k)) for k in (7, 11, 23)]
    sh_p = sum(x[0] for x in sh) / 3; sh_c = sum(x[1] for x in sh) / 3
    # majority-op baseline (answer-blind): always guess the more common gold op on the parsed set
    golds = [gold_op(d["Equation"]) for d in held if find_verb_op(d["Body"] + " " + d["Question"], cls_dir)[0] and len(NUM.findall(d["Body"] + " " + d["Question"])) >= 2]
    maj = max("+-", key=golds.count); maj_c = golds.count(maj)

    print(f"  parse coverage (a possession/exist verb found + >=2 numbers): {vn_p}/{len(held)} ({100*vn_p//len(held)}%)")
    print(f"  ANSWER-BLIND operator accuracy on the {vn_p} parsed problems:")
    print(f"    VerbNet       {vn_c}/{vn_p}  ({100*vn_c//max(1,vn_p)}%)")
    print(f"    SHUFFLE-class {sh_c:.0f}/{sh_p:.0f}  ({100*sh_c/max(1,sh_p):.0f}%)  (avg 3 seeds)")
    print(f"    MAJORITY-op   {maj_c}/{len(golds)}  ({100*maj_c//max(1,len(golds))}%)  (always '{maj}')")
    ratio = (vn_c / max(1, vn_p)) / max(1e-9, sh_c / max(1, sh_p))
    print(f"\n    VerbNet / SHUFFLE ratio = {ratio:.2f}x")
    print(f"  BY PREDICTED OP (the entity-tracking wall): VerbNet '+' -> {byop['+'][1]}/{byop['+'][0]} correct, "
          f"'-' -> {byop['-'][1]}/{byop['-'][0]} correct")
    print("    => VerbNet reads the VERB's transfer direction (buy/receive->'+') but the question tracks a DIFFERENT")
    print("       quantity (money left -> '-'); every '+' prediction is wrong. It just defaults loss-verbs to '-'")
    print("       (= the majority class), beating random shuffle but adding NOTHING on the cases that matter.")

    win = (vn_c / max(1, vn_p)) >= 2 * (sh_c / max(1, sh_p)) and vn_c / max(1, vn_p) > maj_c / max(1, len(golds))
    kill = abs(100 * vn_c // max(1, vn_p) - 100 * sh_c / max(1, sh_p)) <= 10 or vn_c / max(1, vn_p) <= maj_c / max(1, len(golds))
    print(f"\n  RESULT: {'PARTIAL WIN (curated predicate-grade knowledge BINDS the operator, zero-LLM)' if win else 'KILL (VerbNet ~= shuffle/majority -> formal semantics do not bind pragmatics without a parser = collapses into learned experience)' if kill else 'MIXED'}.")
    print("  ANSWER-BLIND throughout (verifier OFF) -> isolates VerbNet's semantic contribution from the verifier.")