"""R25-db: rare-word graph reader for story questions (owner's design, 2026-10-14).
1. Rarity: every word's surprise against general English (training-book counts), -log2 P(word).
2. Graph: the story's content words (not among the 300 most frequent) are nodes; words in the same sentence are linked,
   the common words between them kept as the 'glue' on the link.
3. A question is read the same way: its rare words select the story sentence whose words cover them best (weighted by
   rarity; word forms matched by shared stems), the wh-word picks the kind of answer, and the answer is taken from
   that sentence's remaining rare words and the glue around them:
     who   -> a name or a person word nearest the matched words
     where -> the phrase after a place word (in, on, at, to, into, under, near, behind, inside, outside, across, from)
     when  -> a time phrase (number, o'clock, day, morning, ...)
     what  -> the phrase right after the matched verb
   other questions, and weak matches, are left unanswered.
Development only on practice sets A and B (val_practice_a/b.json); scored as right / wrong / silent against all gold
forms. Run: py -3.12 r25_rwg.py [files...]"""
import os, sys, re, json, math, collections
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE)); os.chdir(HERE)
FILES = [a for a in sys.argv[1:] if a.endswith(".json")] or ["val_practice_a.json", "val_practice_b.json"]
sys.argv = ["r25_attn.py", "--minutes", "0"]
src = open("r25_attn.py", encoding="utf-8").read(); src = src[:src.index("class Net(nn.Module)")]
g = {"__name__": "x", "__file__": os.path.join(HERE, "r25_attn.py")}; exec(compile(src, "r25_attn.py", "exec"), g)
uni = g["uni"]; N = sum(uni.values()); COMMON = set(w for w, _ in uni.most_common(300))
def rar(w): return -math.log2((uni[w] + 1) / N)
PLACE = {"in", "on", "at", "to", "into", "under", "near", "behind", "inside", "outside", "across", "from", "onto", "beside", "by", "over", "beneath"}
DET = {"the", "a", "an", "his", "her", "their", "its", "my", "our", "your", "this", "that", "these", "those", "some"}
TIME = {"morning", "evening", "night", "noon", "midnight", "afternoon", "monday", "tuesday", "wednesday", "thursday", "friday",
        "saturday", "sunday", "o'clock", "dawn", "dusk", "week", "day", "year", "month", "spring", "summer", "autumn", "winter", "hour", "minutes"}
PERSONW = {"man", "woman", "boy", "girl", "mother", "father", "grandmother", "grandfather", "sister", "brother", "aunt", "uncle",
           "teacher", "friend", "baker", "doctor", "king", "queen", "farmer", "child", "children", "wife", "husband", "neighbour", "neighbor"}
def toks(s): return re.findall(r"[A-Za-z][A-Za-z']*|\d+", s)
EXC = {}
for f_ in ("verb.exc", "noun.exc", "adj.exc"):
    for line in open(os.path.join(os.path.dirname(os.path.dirname(HERE)), "_nldata", "dict", f_), encoding="utf-8", errors="replace"):
        q_ = line.split()
        if len(q_) >= 2: EXC.setdefault(q_[0], q_[1])
def stem(w):                                                                                    # dictionary base form first (built -> build), then a 5-letter prefix
    w = EXC.get(w, w); return w[:5] if len(w) > 5 else w
def sentences(text): return [t for t in re.split(r"(?<=[.!?])\s+", text) if t.strip()]
def match_score(qrare, sent):
    ws = [w.lower() for w in toks(sent)]; st = {stem(w) for w in ws}
    return sum(rar(w) for w in qrare if stem(w) in st), ws
def phrase_at(ws, i, raw=None):
    if raw is not None and raw[i][0].isupper():                                                # a name: the name alone (plus a following capitalised word)
        j = i
        while j + 1 < len(ws) and raw[j + 1][0].isupper(): j += 1
        return " ".join(ws[i:j + 1])
    return ws[i]
def answer(story, q):
    qw = [w.lower() for w in toks(q)]; wh = qw[0] if qw else ""
    qrare = [w for w in qw[1:] if w not in COMMON and w not in {"did", "does", "was", "were", "is", "do"}]
    if not qrare or wh not in ("who", "where", "when", "what"): return None
    best = max((match_score(qrare, s) + (s,) for s in sentences(story)), key=lambda x: x[0])
    sc, ws, sent = best
    if sc < 0.5 * sum(rar(w) for w in qrare): return None                                  # weak match: stay silent
    raw = toks(sent); qst = {stem(w) for w in qw}
    hits = [i for i, w in enumerate(ws) if stem(w) in qst and w not in COMMON]
    if not hits: return None
    def near(cands):
        return min(cands, key=lambda i: min(abs(i - h) for h in hits)) if cands else None
    if wh == "who":
        c = [i for i, w in enumerate(ws) if stem(w) not in qst and (raw[i][0].isupper() and i > 0 and ws[i - 1] not in PLACE or w in PERSONW)]
        i = near(c); return None if i is None else phrase_at(ws, i, raw)
    if wh == "where":
        c = [i for i, w in enumerate(ws) if w in PLACE and i + 1 < len(ws)]
        after = [i for i in c if i > max(hits)]; c = after or c
        for i in sorted(c, key=lambda i: (abs(i - max(hits)))):
            k = i + 1
            while k < len(ws) and ws[k] in DET: k += 1
            j = k
            while j + 1 < len(ws) and ws[j + 1] not in COMMON and ws[j + 1] not in PLACE: j += 1
            if k < len(ws) and ws[k] not in COMMON: return " ".join(ws[i + 1:j + 1])
        return None
    if wh == "when":
        c = [i for i, w in enumerate(ws) if w in TIME or w.isdigit()]
        i = near(c)
        if i is None: return None
        k = i
        while k - 1 >= 0 and (ws[k - 1].isdigit() or ws[k - 1] in {"one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve", "every", "next", "last", "early", "late", "that", "the", "this"}): k -= 1
        return " ".join(ws[k:i + 1])
    if wh == "what":
        if "do" in qw or "doing" in qw: return None                                             # questions about actions: not this reader
        if len(qw) > 1 and qw[1] not in {"did", "does", "was", "were", "is", "had", "has", "do"}:  # 'what burst ...?': the thing before the verb
            h = min(hits); j = h - 1
            while j >= 0 and ws[j] in COMMON - DET: j -= 1
            k = j
            while k - 1 >= 0 and ws[k - 1] not in COMMON: k -= 1
            if k - 1 >= 0 and ws[k - 1] in DET: k -= 1
            return " ".join(ws[k:j + 1]) if j >= 0 and ws[j] not in COMMON else None
        h = max(hits); k = h + 1
        while k < len(ws) and ws[k] in DET | PLACE | {"with", "for", "of"}: k += 1
        j = k
        while j + 1 < len(ws) and ws[j + 1] not in COMMON and ws[j + 1] not in PLACE: j += 1
        if k < len(ws) and ws[k] not in COMMON: return " ".join(ws[(k - 1) if ws[k - 1] in DET else k:j + 1])
    return None
def norm(s): return " ".join(re.findall(r"[a-z0-9']+", s.lower()))
tot = collections.Counter(); per = collections.defaultdict(collections.Counter); shown = 0
for f in FILES:
    for st in json.load(open(f, encoding="utf-8"))["stories"]:
        for q, gold in st["qs"]:
            a = answer(st["text"], q); wh = q.split()[0].lower(); gs = {norm(x) for x in gold}
            r = "silent" if a is None else ("right" if norm(a) in gs else "wrong")
            tot[r] += 1; per[wh][r] += 1
            if r == "wrong" and shown < 12: print(f"   wrong: {q} -> {a!r} (gold {gold[:2]})"); shown += 1
n = sum(tot.values())
print(f"R25-db rare-word graph reader on {', '.join(FILES)}: {n} questions -- right {tot['right']}, wrong {tot['wrong']}, silent {tot['silent']}; precision {tot['right'] / max(1, tot['right'] + tot['wrong']):.3f}")
for wh, c in sorted(per.items(), key=lambda x: -sum(x[1].values())): print(f"   {wh:6s} right {c['right']:3d} wrong {c['wrong']:3d} silent {c['silent']:3d}")
