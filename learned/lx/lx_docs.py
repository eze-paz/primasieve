"""LR data: the same token streams as lx_data.py plus what long-range context needs -- book and paragraph of every token,
whether the raw text capitalised it inside a sentence (a surface signal of the text, not a label), an identity for
held-out words unseen in training (ids above the unknown id; the models still see one unknown token), and a dev set: held-out
paragraphs after the 1,000 scored ones, from books that share no paragraph with them (for fitting mixing weights).
Asserts it reproduces lx_tokens.npz exactly. Run: py -3.12 lx_docs.py"""
import os, sys, json, time
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); BASE = os.path.join(os.path.dirname(HERE), "base")
sys.path.insert(0, BASE); sys.path.insert(0, os.path.dirname(BASE)); os.chdir(BASE)
import r24_tlm as T, r24_books as B, data as D0
t0 = time.time()
V = json.load(open(os.path.join(HERE, "lx_vocab.json"), encoding="utf-8")); wid = {w: i + 1 for i, w in enumerate(V["words"])}; UNK = len(V["words"]) + 1; EXT = {}
def tagged(bids, n_sent):
    out = []; n = 0
    for b in bids:
        for p in B.paragraphs([b], n_sent - n):
            out.append((p["text"], b)); n += len([s for s in T.SENT.split(p["text"]) if s.strip()])
        if n >= n_sent: break
    return out
def flat(paras):
    ids, sid, para, book, cap, ext = [], [], [], [], [], []; k = 0; pi = 0; bmap = {}
    for text, b in paras:
        ss = []
        for s in T.SENT.split(text):
            w = [x for x in T.TOK.findall(s) if x.isalpha()]
            if len(w) >= 2: ss.append(w)
        if not ss: continue
        for s in ss:
            for i, x in enumerate(s):
                ids.append(wid.get(x.lower(), UNK)); sid.append(k); para.append(pi); book.append(bmap.setdefault(b, len(bmap))); cap.append(i > 0 and x[0].isupper()); ext.append(wid.get(x.lower()) or EXT.setdefault(x.lower(), UNK + 1 + len(EXT)))
            k += 1
        pi += 1
    return [np.array(a, t) for a, t in ((ids, np.int32), (sid, np.int32), (para, np.int32), (book, np.int32), (cap, bool), (ext, np.int32))]
tr_b, te_b = D0.books()
tr, trs, trp, trb, trc, _ = flat(tagged(tr_b, 1000000))
allte = flat(tagged(te_b, 20000)); te_all, tes_all, tep_all, teb_all, tec_all, tex_all = allte
z = np.load(os.path.join(HERE, "lx_tokens.npz"))
assert np.array_equal(tr, z["tr"]) and np.array_equal(trs, z["trs"]), "training stream differs from lx_tokens.npz"
m = tep_all < 1000; assert np.array_equal(te_all[m], z["te"]) and np.array_equal(tep_all[m], z["tep"]), "held-out stream differs"
used = set(teb_all[m].tolist()); dm = (tep_all >= 1000) & ~np.isin(teb_all, list(used))
print(f"training {len(tr):,} tokens in {trb.max() + 1} books; scored held-out {int(m.sum()):,} tokens in {len(used)} books "
      f"(tokens per book {np.bincount(teb_all[m])[sorted(used)].tolist()}); dev {int(dm.sum()):,} tokens in {len(set(teb_all[dm].tolist()))} books ({time.time() - t0:.0f} s)")
json.dump(sorted(EXT, key=EXT.get), open(os.path.join(HERE, "lx_ext_words.json"), "w", encoding="utf-8"))   # held-out words unseen in training, in id order
np.savez_compressed(os.path.join(HERE, "lx_docs.npz"), trp=trp, trb=trb, trc=trc, teb=teb_all[m], tec=tec_all[m], tex=tex_all[m], dvx=tex_all[dm],
                    dv=te_all[dm], dvs=tes_all[dm], dvp=tep_all[dm], dvb=teb_all[dm], dvc=tec_all[dm])
