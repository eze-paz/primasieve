"""R25-en: a learned answer-finder for story questions -- learned by counting, no gradients.
For each question: the story sentences that best cover the question's rare words (top 2) give candidate answers --
every run of content words, with an optional leading article / possessive / title and, for where-questions, an
optional place word before it. Each candidate is described by a few features:
  kind (who / what / where / when / how-many ...), side and distance to the nearest matched question word,
  the word just before the candidate, whether it starts with a capital, whether it holds a number, its length,
  whether the sentence is the best-covering one, and the learner's word group of its last word.
From practice questions the learner counts, per feature value, how often candidates with that value were the gold
answer versus not, and scores a candidate by the summed log odds (naive Bayes with add-one smoothing). The top
candidate is the answer. Trust per kind: right - 3 x wrong > 0 on the training questions.
Run: py -3.12 r25_ans.py --train A,B,C,D --test E,F   (letters = practice sets; or file names)"""
import os, sys, re, json, math, collections
ARGV = list(sys.argv)
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE)); os.chdir(HERE)
sys.argv = ["r25_rwg.py"]
src = open("r25_rwg.py", encoding="utf-8").read(); src = src[:src.index("tot = collections.Counter()")]
R = {"__name__": "rwg", "__file__": os.path.join(HERE, "r25_rwg.py")}; exec(compile(src, "r25_rwg.py", "exec"), R)
COMMON, rar, stem, sentences, toks, norm = R["COMMON"], R["rar"], R["stem"], R["sentences"], R["toks"], R["norm"]
GROUPS = json.load(open("r25_classes.json", encoding="utf-8"))
ART = {"the", "a", "an", "his", "her", "their", "its", "my", "our", "your", "mr", "mrs", "ms", "dr"}
PLACE = {"in", "on", "at", "under", "into", "onto", "near", "behind", "beside", "inside", "across", "over", "by", "from", "to", "through", "along"}
def files(arg): return [f"val_practice_{x.lower()}.json" if len(x) == 1 else x for x in arg.split(",")]
def kind(q):
    w = q.lower().split()
    if not w: return "?"
    if w[0] == "how" and len(w) > 1: return "how " + w[1]
    return w[0]
def candidates(story, q):
    qw = [w.lower() for w in toks(q)]; key = [w for w in qw[1:] if w not in COMMON]; qst = {stem(w) for w in qw}
    if not key: return []
    scored = []
    for s_ in sentences(story):
        raw = toks(s_); ws = [w.lower() for w in raw]; st = {stem(w) for w in ws}
        scored.append((sum(rar(w) for w in key if stem(w) in st), raw, ws))
    scored.sort(key=lambda x: -x[0]); out = []
    for rank, (sc, raw, ws) in enumerate(scored[:2]):
        if sc <= 0: continue
        hits = [i for i, w in enumerate(ws) if stem(w) in qst and w not in COMMON]
        i = 0
        while i < len(ws):
            if ws[i] in COMMON or stem(ws[i]) in qst: i += 1; continue
            j = i
            while j + 1 < len(ws) and ws[j + 1] not in COMMON and stem(ws[j + 1]) not in qst: j += 1
            for b in {i, i - 1 if i > 0 and ws[i - 1] in ART else i}:
                for bb in {b, b - 1 if b > 0 and ws[b - 1] in PLACE else b}:
                    text = " ".join(ws[bb:j + 1]); prev = ws[bb - 1] if bb > 0 else "<s>"
                    d = min([abs(i - h) for h in hits] or [99]); side = "L" if hits and i < min(hits) else "R"
                    db = "1" if d <= 1 else "2" if d <= 2 else "3" if d <= 4 else "4" if d <= 7 else "5"
                    f = [("k", kind(q)), ("kd", kind(q) + "|" + side + db), ("kp", kind(q) + "|" + (prev if prev in COMMON or prev == "<s>" else "C")),
                         ("kcap", kind(q) + "|" + str(raw[i][:1].isupper())), ("knum", kind(q) + "|" + str(any(R["isnum"](w) for w in ws[i:j + 1]))),
                         ("klen", kind(q) + "|" + str(min(j - i + 1, 4))), ("krank", kind(q) + "|" + str(rank)),
                         ("kgrp", kind(q) + "|" + str(GROUPS.get(ws[j], -1))), ("kstart", kind(q) + "|" + ws[bb] if ws[bb] in ART | PLACE else kind(q) + "|-")]
                    out.append((text, f))
            i = j + 1
    return out
def gold_hit(text, gold): return norm(text) in {norm(g) for g in gold}
pos, neg = collections.Counter(), collections.Counter(); npos = nneg = 0
train = [(st["text"], q, g) for f in files(ARGV[ARGV.index("--train") + 1]) for st in json.load(open(f, encoding="utf-8"))["stories"] for q, g in st["qs"]]
test = [(st["text"], q, g) for f in files(ARGV[ARGV.index("--test") + 1]) for st in json.load(open(f, encoding="utf-8"))["stories"] for q, g in st["qs"]]
for text, q, g in train:
    for c, f in candidates(text, q):
        if gold_hit(c, g): npos += 1; pos.update(f)
        else: nneg += 1; neg.update(f)
def score(f): return sum(math.log((pos[x] + 1) / (npos + 2)) - math.log((neg[x] + 1) / (nneg + 2)) for x in f)
def answer(text, q):
    cs = candidates(text, q)
    return max(cs, key=lambda c: score(c[1]))[0] if cs else None
def evaluate(data):
    c = collections.defaultdict(lambda: [0, 0, 0])
    for text, q, g in data:
        a = answer(text, q); k = kind(q).split()[0] if not kind(q).startswith("how ") else kind(q)
        c[k][2 if a is None else (0 if gold_hit(a, g) else 1)] += 1
    return c
tr = evaluate(train); keep = {k for k, (a, w, s) in tr.items() if a - 3 * w > 0}
te = evaluate(test)
print(f"R25-en learned answer-finder: {npos} gold / {nneg} other candidates counted on {len(train)} training questions", flush=True)
print("R25-en training kinds (right, wrong, silent):", {k: tuple(v) for k, v in sorted(tr.items(), key=lambda kv: -sum(kv[1]))}, "| kept:", sorted(keep), flush=True)
print("R25-en test kinds (right, wrong, silent):", {k: tuple(v) for k, v in sorted(te.items(), key=lambda kv: -sum(kv[1]))}, flush=True)
a = sum(v[0] for k, v in te.items() if k in keep); w = sum(v[1] for k, v in te.items() if k in keep)
print(f"R25-en test, trusted kinds only: {a} right / {w} wrong (fitness {a - 3 * w}); all kinds {sum(v[0] for v in te.values())} / {sum(v[1] for v in te.values())}", flush=True)
