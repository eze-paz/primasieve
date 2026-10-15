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
ARGV = list(sys.argv); WIDE = "--wide" in ARGV
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE)); os.chdir(HERE)
sys.argv = ["r25_rwg.py"]
src = open("r25_rwg.py", encoding="utf-8").read(); src = src[:src.index("tot = collections.Counter()")]
R = {"__name__": "rwg", "__file__": os.path.join(HERE, "r25_rwg.py")}; exec(compile(src, "r25_rwg.py", "exec"), R)
COMMON, rar, stem, sentences, toks, norm = R["COMMON"], R["rar"], R["stem"], R["sentences"], R["toks"], R["norm"]
GROUPS = json.load(open("r25_classes.json", encoding="utf-8"))
import numpy as np
_wn = {}                                                                                          # R25-et: word -> WordNet class (from r25_wn_groups.py's reading of the dictionary)
_g = {"__name__": "wn", "__file__": os.path.join(HERE, "r25_wn_groups.py")}
_src = open("r25_wn_groups.py", encoding="utf-8").read(); _src = _src[:_src.index("cl = json.load")]
exec(compile(_src, "r25_wn_groups.py", "exec"), _g); DCLASS = _g["dict_class"]
def wtype(w, raw):
    if raw[:1].isupper(): return "name"
    if R["isnum"](w): return "number"
    if w not in _wn: _wn[w] = DCLASS(w) or "none"
    return _wn[w]
_z = np.load("r25_vectors_all.npz"); VEC = {w: v / (np.linalg.norm(v) + 1e-9) for w, v in zip(_z["vocab"].tolist(), _z["vecs"])}   # R25-er
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
    qv = [VEC[w] for w in key if w in VEC]; qv = (np.mean(qv, 0) / (np.linalg.norm(np.mean(qv, 0)) + 1e-9)) if qv else None
    for rank, (sc, raw, ws) in enumerate(scored[:(99 if WIDE else 2)]):
        if sc <= 0: continue
        hits = [i for i, w in enumerate(ws) if stem(w) in qst and w not in COMMON]
        i = 0
        while i < len(ws):
            if ws[i] in COMMON or stem(ws[i]) in qst: i += 1; continue
            j = i
            while j + 1 < len(ws) and ws[j + 1] not in COMMON and stem(ws[j + 1]) not in qst: j += 1
            ends = {j}
            if WIDE and j + 2 < len(ws) and ws[j + 1] in {"of", "and"}:                        # R25-eq: extend through 'of' / 'and' + a noun phrase
                k = j + 2
                while k < len(ws) and ws[k] in ART: k += 1
                e = k
                while e + 1 < len(ws) and ws[e + 1] not in COMMON: e += 1
                if k < len(ws) and ws[k] not in COMMON: ends.add(e)
            for jj in sorted(ends):
              j_ = jj
              for b in {i, i - 1 if i > 0 and ws[i - 1] in ART else i}:
                for bb in {b, b - 1 if b > 0 and ws[b - 1] in PLACE else b}:
                    text = " ".join(ws[bb:j_ + 1]); prev = ws[bb - 1] if bb > 0 else "<s>"
                    d = min([abs(i - h) for h in hits] or [99]); side = "L" if hits and i < min(hits) else "R"
                    db = "1" if d <= 1 else "2" if d <= 2 else "3" if d <= 4 else "4" if d <= 7 else "5"
                    f = [("k", kind(q)), ("kd", kind(q) + "|" + side + db), ("kp", kind(q) + "|" + (prev if prev in COMMON or prev == "<s>" else "C")),
                         ("kcap", kind(q) + "|" + str(raw[i][:1].isupper())), ("knum", kind(q) + "|" + str(any(R["isnum"](w) for w in ws[i:j + 1]))),
                         ("klen", kind(q) + "|" + str(min(j - i + 1, 4))), ("krank", kind(q) + "|" + str(rank)),
                         ("kgrp", kind(q) + "|" + str(GROUPS.get(ws[j], -1))), ("ktype", kind(q) + "|" + wtype(ws[j_], raw[j_])), ("vtype", (R["EXC"].get(key[-1], key[-1]) if key else "-") + "|" + wtype(ws[j_], raw[j_])), ("ksim", kind(q) + "|" + (str(int(4 * max(-0.99, min(0.99, float(VEC[ws[j_]] @ qv))) + 4)) if (qv is not None and ws[j_] in VEC) else "none")), ("kstart", kind(q) + "|" + ws[bb] if ws[bb] in ART | PLACE else kind(q) + "|-")]
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
# R25-eo: answer only when confident -- per kind, a threshold on the top candidate's score chosen on training (right - 3 x wrong)
def scored(data):
    out = []
    for text, q, g in data:
        cs = candidates(text, q); k = kind(q).split()[0] if not kind(q).startswith("how ") else kind(q)
        if not cs: out.append((k, None, False)); continue
        best = max(cs, key=lambda c: score(c[1])); s2 = sorted((score(c[1]) for c in cs), reverse=True)
        conf = s2[0] - (s2[1] if len(s2) > 1 else s2[0] - 5)
        out.append((k, conf, gold_hit(best[0], g)))
    return out
TR, TE = scored(train), scored(test); th = {}
for k in {x[0] for x in TR}:
    rows = sorted([(c, h) for kk, c, h in TR if kk == k and c is not None], reverse=True); best = (0, None); a = w = 0
    for c, h in rows:
        a += h; w += (not h)
        if a - 3 * w > best[0]: best = (a - 3 * w, c)
    if best[1] is not None: th[k] = best[1]
a = sum(1 for k, c, h in TE if k in th and c is not None and c >= th[k] and h); w = sum(1 for k, c, h in TE if k in th and c is not None and c >= th[k] and not h)
print(f"R25-eo confident answers only (thresholds per kind from training: {len(th)} kinds): test {a} right / {w} wrong (fitness {a - 3 * w})", flush=True)
# R25-ep: candidate recall -- is a gold answer among the candidates, and among the top 3 by score?
inc = top3 = n = 0
for text, q, g in test:
    cs = candidates(text, q); n += 1
    if any(gold_hit(c[0], g) for c in cs): inc += 1
    if any(gold_hit(c[0], g) for c in sorted(cs, key=lambda c: -score(c[1]))[:3]): top3 += 1
print(f"R25-ep test: gold among candidates {inc}/{n} = {inc / n:.2f}; among the top 3 {top3}/{n} = {top3 / n:.2f}", flush=True)
if "--show" in ARGV:                                                                            # R25-es
    shown = 0
    for text, q, g in test:
        cs = candidates(text, q)
        if not cs or not any(gold_hit(c[0], g) for c in cs): continue
        best = max(cs, key=lambda c: score(c[1]))
        if gold_hit(best[0], g): continue
        print(f"   R25-es {q} | chose {best[0]!r} | gold {g[0]!r}", flush=True); shown += 1
        if shown >= 25: break
