import os, sys, json, random, collections
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE)); os.chdir(HERE); sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(ROOT, "learned"))
import r24_tlm as T, r24_events as E, r24_reader as R, r24_qreader as QR
data = json.load(open("stories_train_v2.json", encoding="utf-8")); random.Random(24).shuffle(data); names = T.mid_caps([s["text"] for s in data[:7000]])
import r24_books as B, data as D
train_b, _ = D.books(); E.induce_verbish([p["text"] for p in B.paragraphs(train_b, 150000)], k=200)
print("is_verb:", {w: R.is_verb(w) for w in "use teach sew charge grow stand buy take carry mark gnaw serve invite fix pull skate sing beg ask hire refuse put get".split()})
print("in VERBISH:", {w: (w in E.VERBISH, E.CLASS.get(w)) for w in "use used teach taught sew sewed charge charged grow grew stand stood buy bought".split()})
train, QRD = R.closed_loop_train(data, names)
keys = collections.Counter()
for (lvl, k), c in QRD.map.items():
    if lvl == "exact" and k and k[0] in ("what", "where", "who", "when", "why", "how", "whose", "which"): keys[k] += sum(c.values())
for k, n in sorted(keys.items(), key=lambda x: -x[1])[:60]: print(n, k, "->", QRD.map[("exact", k)].most_common(1)[0][0])
# the generator's what-did questions that failed to teach
miss = collections.Counter()
for s in data[:3000]:
    for q, g in s["qs"]:
        if q.lower().startswith("what did"):
            qs, qf = QR.qshape(q, names); miss[QR.abstract_q(qs)] += 1
print("generator what-did shapes:", miss.most_common(12))
