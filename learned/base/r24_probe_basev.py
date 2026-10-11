import os, sys, collections
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE)); os.chdir(HERE); sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(ROOT, "learned"))
import r24_tlm as T, r24_events as E, r24_books as B, data as D
train_b, _ = D.books(); texts = [p["text"] for p in B.paragraphs(train_b, 150000)]; E.induce_verbish(texts, k=200)
tot = collections.Counter(); am = collections.Counter(); ad = collections.Counter()
for t in texts:
    w = [x.lower() for x in T.TOK.findall(t)]
    for i, x in enumerate(w):
        tot[x] += 1
        if i and w[i - 1] in E.MODALS: am[x] += 1
        if i and w[i - 1] in T.DET: ad[x] += 1
rows = sorted(((am[x] / tot[x], x, am[x], tot[x], round(ad[x] / tot[x], 2)) for x in E.BASEV), reverse=True)
print(len(E.BASEV), "base forms; (modal ratio, word, after-modal, total, after-det ratio)")
for r in rows: print(f"{r[0]:.3f} {r[1]} {r[2]} {r[3]} {r[4]}")
