"""R26 T22: wh-to-statement match (R26_prereg.md). The question's content words (verbs by base form) must all occur in
exactly one story sentence; the gap is filled from that sentence by the question word's slot: who-subject -> the noun
phrase before the matched verb; what / who-object -> the phrase after it; where -> a place phrase; when -> a time phrase.
Run: py -3.12 r26_stmatch.py"""
import os, sys, re, json, collections
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE)); os.chdir(HERE)
import r24_dict as Dct
from b6_rwkv import hit
AUX = {"did", "does", "do", "was", "were", "is", "are", "had", "has", "have", "will", "would", "could", "can"}
DET = {"the", "a", "an", "his", "her", "their", "its", "my", "your", "our", "this", "that", "these", "those"}
PREP = {"in", "on", "at", "to", "into", "onto", "near", "under", "behind", "by", "inside", "outside", "beside", "across", "over", "through", "from", "up", "down"}
PLACEP = {"in", "on", "at", "into", "onto", "near", "under", "behind", "by", "inside", "outside", "beside", "across", "to", "over", "through"}
STOP = AUX | DET | {"who", "what", "where", "when", "whom", "of", "for", "with", "and", "or", "but", "it", "he", "she", "they", "him", "them", "there", "then", "so"} | PREP
TIMEW = set("morning evening night noon dawn dusk midnight afternoon day days week weeks month months year years winter summer spring autumn monday tuesday wednesday thursday friday saturday sunday january february march april may june july august september october november december yesterday today tomorrow tonight hour hours minute minutes later o clock christmas birthday holiday".split())
CLAUSE_END = {"and", "but", "because", "while", "when", "so", "then", "who", "which", "that", "after", "before", "until"}
FIX3 = "--fix3" in sys.argv; FIX2 = "--fix2" in sys.argv or FIX3; FIX = "--fix" in sys.argv or FIX2
WEEKMONTH = set("monday tuesday wednesday thursday friday saturday sunday january february march april may june july august september october november december".split())
NUMW = set("one two three four five six seven eight nine ten eleven twelve twenty thirty a few several".split())
PRONS = {"he", "she", "it", "they", "him", "her", "them", "his", "its", "their"}
TOK = re.compile(r"[A-Za-z0-9]+(?:'[a-z]+)?|[,.;:!?]")
nb = {}
def norm(w):
    w = w.lower()
    if w not in nb: nb[w] = (Dct.verb_base(w) if Dct.mainly_verb(w) else None) or w
    return nb[w]


def np_after(toks, k, stop_at_prep=True):
    out = []
    for t in toks[k:k + 7]:
        tl = t.lower()
        if not t[0].isalnum() or tl in CLAUSE_END or (stop_at_prep and tl in PREP and out): break
        if tl in AUX and out: break
        out.append(t)
    while out and out[0].lower() in DET: out = out[1:]
    return " ".join(out) if out else None


def np_before(toks, k):
    out = []
    for t in reversed(toks[max(0, k - 5):k]):
        tl = t.lower()
        if not t[0].isalnum() or tl in CLAUSE_END or tl in PREP or tl in AUX: break
        out.insert(0, t)
    while out and out[0].lower() in DET: out = out[1:]
    return " ".join(out) if out else None


def answer(text, q, relax=False):
    qw = [w for w in TOK.findall(q) if w[0].isalnum()]
    if len(qw) < 2: return None
    wh = qw[0].lower(); rest = qw[1:]
    if wh not in ("who", "what", "where", "when", "whom"): return None
    obj_q = rest[0].lower() in AUX
    if obj_q: rest = rest[1:]
    content = [norm(w) for w in rest if w.lower() not in STOP]
    if not content: return None
    sents = [s for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    hits = []
    for s in sents:
        toks = TOK.findall(s); nt = [norm(t) for t in toks]
        pos = [next((i for i, x in enumerate(nt) if x == c), None) for c in content]
        if all(p is not None for p in pos): hits.append((toks, nt, pos))
    if not hits and relax:                                                               # T22d: all but one content word (not a name)
        for s in sents:
            toks = TOK.findall(s); nt = [norm(t) for t in toks]
            pos = [next((i for i, x in enumerate(nt) if x == c), None) for c in content]
            miss = [c for c, p in zip(content, pos) if p is None]
            if len(miss) == 1 and len(content) >= 2 and not any(w[0].isupper() and norm(w) == miss[0] for w in rest):
                hits.append((toks, nt, [p for p in pos if p is not None]))
        content = [c for c in content]
    if len(hits) != 1: return None
    toks, nt, pos = hits[0]
    if len(pos) < len(content): content = [c for c in content if c in nt]
    qset = {w.lower() for w in qw}
    verb_i = next((p for c, p in zip(content, pos) if Dct.verb_base(toks[p]) and toks[p].lower() not in DET), None)
    subj_q = (wh == "who" and not obj_q) or (FIX and wh == "what" and not obj_q)       # T22e (3): 'what' + non-auxiliary verb asks for the subject
    if FIX2 and wh == "who" and obj_q and qw[1].lower() in ("was", "is", "were", "are"):  # T22f (d): 'Who was the cook?' -> the phrase before the copula
        cop = next((i for i in range(min(pos) - 1, -1, -1) if toks[i].lower() in ("was", "is", "were", "are")), None)
        a = np_before(toks, cop) if cop is not None else None
        if a and not any(w[0].isupper() for w in a.split()) and not (cop - len(a.split()) >= 1 and toks[cop - len(a.split()) - 1].lower() in DET): a = None
    elif subj_q:
        if verb_i is None: return None
        a = np_before(toks, verb_i)
        if FIX and a:                                                                     # T22e (5): a capitalised word, or a phrase after a determiner
            k0 = verb_i - len(a.split())
            if not any(w[0].isupper() for w in a.split()) and not (k0 >= 1 and toks[k0 - 1].lower() in DET): a = None
    elif wh in ("what", "who", "whom"):
        if verb_i is None: return None
        k = max(pos) + 1 if max(pos) > verb_i else verb_i + 1
        a = np_after(toks, k)
        if FIX2 and a and a.split()[0].lower() in PREP | {"of", "for", "with", "from", "about"}: a = None   # T22f (f): an object is not a prepositional phrase
    elif wh == "where":
        a = None
        order = list(range(min(pos), len(toks))) + list(range(0, min(pos))) if FIX2 else range(len(toks))   # T22f (c): after the matched words first
        for i in order:
            t = toks[i]
            if t.lower() in PLACEP and i + 1 < len(toks):
                if FIX2 and (toks[i + 1].lower() in NUMW or toks[i + 1].isdigit() or toks[i + 1].lower() in PREP): continue   # T22f (c): 'at nine' is a time; 'in at' skipped
                cand = np_after(toks, i + 1)
                if FIX and cand:                                                          # T22e (2): no time phrases; stop at a capital or a time word
                    ws = cand.split()
                    cut = next((j for j, w in enumerate(ws) if j > 0 and (w.lower() in TIMEW or (w[0].isupper() and not (FIX2 and ws[j - 1][0].isupper())))), len(ws)); cand = " ".join(ws[:cut])   # T22f (b)
                    if any(w.lower() in TIMEW for w in cand.split()): cand = None
                if FIX2 and cand:                                                         # T22f (a): keep the determiner the story used
                    j0 = i + 1; cand = " ".join(toks[j0:j0 + len(cand.split()) + (1 if toks[j0].lower() in DET else 0)])
                if cand and not set(cand.lower().split()) <= qset: a = t.lower() + " " + cand; break
    else:
        a = None
        if FIX3:                                                                          # T22j (a): clock time, then weekday / month, then other time words
            low = [t.lower() for t in toks]
            def phrase(i, e):
                j = i
                if j > 0 and low[j - 1] in ("at", "on", "before", "by", "after", "until", "in"): j -= 1
                return " ".join(toks[j:e])
            for i, t in enumerate(low):
                if (t in NUMW or t.isdigit()) and t not in ("a", "few", "several") and ((i + 1 < len(low) and low[i + 1] in ("o'clock", "am", "pm")) or (i > 0 and low[i - 1] in ("at", "before", "by", "after", "until"))):
                    a = phrase(i, i + 2 if i + 1 < len(low) and low[i + 1] in ("o'clock", "am", "pm") else i + 1); break
            if a is None:
                for i, t in enumerate(low):
                    if t in WEEKMONTH: a = phrase(i, i + 1); break
        for i, t in enumerate(toks if a is None else []):
            if t.lower() in TIMEW or (t.lower() in ("at", "on", "in") and i + 1 < len(toks) and (toks[i + 1].lower() in TIMEW or toks[i + 1].isdigit())):
                j = i
                while j > 0 and toks[j - 1].lower() in DET | {"in", "on", "at", "the", "next", "last", "every", "one", "that"} | (NUMW if FIX else set()): j -= 1
                e = i + 1
                if FIX and e < len(toks) and toks[e].lower() in ("later", "ago", "earlier"): e += 1   # T22e (4)
                a = " ".join(toks[j:e] if toks[i].lower() in TIMEW else toks[i:i + 3]); break
    if FIX and a and a.lower() in PRONS:                                                  # T22e (1): pronoun answers
        if a.lower() in ("he", "she"):
            before = text[:text.find(" ".join(toks[:3]))] if " ".join(toks[:3]) in text else ""
            names = [w for w in TOK.findall(before) if w[0].isupper() and w.lower() not in STOP and w.lower() not in PRONS]
            a = names[-1] if names else None
        else: a = None
    if FIX2 and a and a.split()[0].lower() in PRONS: a = None                              # T22f (e)
    if FIX3 and a and wh in ("who", "what", "whom"):                                      # T22j (b): junk subject / object answers
        ws = [w.lower() for w in a.split()]
        if any(w in PRONS for w in ws) or any(w in TIMEW for w in ws) or (len(ws) == 1 and (ws[0].endswith("ly") or ws[0] in ("not", "instead", "than", "then", "also", "too", "very"))): a = None
    if not a or set(a.lower().split()) <= qset: return None
    return a


def main():
    SF = sys.argv[sys.argv.index("--stories") + 1] if "--stories" in sys.argv else "val_all13.json"
    st = json.load(open(SF, encoding="utf-8"))["stories"]; items = [(s["text"], q, g) for s in st for q, g in s["qs"]]
    if SF != "val_all13.json":
        A = [answer(t, q, False) for t, q, g in items]; json.dump(A, open(sys.argv[sys.argv.index("--out") + 1], "w", encoding="utf-8")); print("answers", sum(a is not None for a in A)); return
    RELAX = "--relax" in sys.argv
    A = [answer(t, q, RELAX) for t, q, g in items]; json.dump(A, open("r26_stmatch_fix3_answers.json" if FIX3 else "r26_stmatch_fix2_answers.json" if FIX2 else "r26_stmatch_fix_answers.json" if FIX else "r26_stmatch_relax_answers.json" if RELAX else "r26_stmatch_answers.json", "w", encoding="utf-8"))
    gold = [g for _, _, g in items]
    L = [l for l in open("r24_diag_asA.txt", encoding="utf-8", errors="replace") if l.startswith("VAL |")]
    route = [l.split("| route ")[1].split(" |")[0] for l in L]; ans = [l.split("| ans ")[1].split(" |")[0] for l in L]; ans = [None if a == "None" else a for a in ans]
    PR = list(range(310)) + list(range(510, 910)); UN = list(range(310, 510)) + list(range(910, 2510))
    fr = collections.defaultdict(lambda: [0, 0])
    for i in PR:
        if ans[i]: fr[route[i]][0 if hit(ans[i], gold[i]) else 1] += 1
    trust = {r for r, (a, w) in fr.items() if a - 3 * w > 0}
    def fit(idx, f):
        r = w = 0
        for i in idx:
            x = f(i)
            if x is None: continue
            if hit(x, gold[i]): r += 1
            else: w += 1
        return r - 3 * w, r, w
    base = lambda i: ans[i] if (ans[i] and route[i] in trust) else None
    alone = lambda i: A[i]
    silent_only = lambda i: A[i] if base(i) is None else None
    use = fit(PR, silent_only)[0] > 0
    pol = lambda i: base(i) if base(i) is not None else (A[i] if use else None)
    print(f"T22 statement match alone: practice {fit(PR, alone)}, untouched {fit(UN, alone)}  (fitness, right, wrong)")
    print(f"T22 on silent questions: practice {fit(PR, silent_only)}, untouched {fit(UN, silent_only)}; trusted on practice: {use}")
    print(f"T22 policy: practice {fit(PR, pol)}, untouched {fit(UN, pol)} (baseline practice {fit(PR, base)}, untouched {fit(UN, base)})")
    for wh in ("who", "what", "where", "when"):
        idx = [i for i in PR if items[i][1].lower().startswith(wh) and base(i) is None]
        print(f"  practice silent {wh}: {fit(idx, alone)}")


if __name__ == "__main__":
    main()
