"""SN diagnostics (sieve_lang_prereg.md) for a program read online on the 50,114 scored positions:
D  bits by function word (100 most frequent) / content word, by sentence position 1-10 / 11+, by repeat (answer already
   used in this book) / first use;
D2 long-context final word: sentence-final answers present in the previous 200 tokens but not in the sentence so far:
   bits and top-1 accuracy;
D3 minimal pairs: answers in is/are, was/were, has/have, he/she, his/her, him/her with both words on the shortlist:
   share where the answer gets more probability than its pair.
Run: SZ_EXACT=1 py -3.12 -W ignore sieve_diag.py [state.json] [selector eta] -> sieve_diag_<state>.json"""
import os, sys, json, math, time
import numpy as np
argv = sys.argv[:]
import sieve_online as OL
F, P = OL.F, OL.P
def positions():
    s, T, b = F.ctx("eval"); y = s[T]; n = len(T)
    cnt = np.bincount(F.tr, minlength=F.Vt); cnt[0] = 0; func = np.zeros(F.Vt, bool); func[np.argsort(-cnt)[:100]] = True
    z = np.nonzero(s == 0)[0]; last0 = z[np.searchsorted(z, T) - 1]; spos = T - last0                     # 1 = first word of the sentence
    rep = np.zeros(n, bool); seen = {}
    for i, t in enumerate(T):
        bk = int(b[t]); st = seen.setdefault(bk, set()); rep[i] = int(y[i]) in st; st.add(int(y[i]))
    final = (np.r_[s, 0][T + 1] == 0); d2 = np.zeros(n, bool)
    for i, t in enumerate(T):
        if final[i]: w = s[max(0, t - 200):t]; d2[i] = (y[i] in w) and (y[i] not in s[last0[i] + 1:t])
    return y, func[y], spos, rep, d2
PAIRS = [("is", "are"), ("was", "were"), ("has", "have"), ("he", "she"), ("his", "her"), ("him", "her")]
def main():
    stf = argv[1] if len(argv) > 1 else "sieve_l7_offer.json"; sel = None if len(argv) < 3 or argv[2] in ("none", "paq") else int(argv[2]); eta = float(argv[3]) if len(argv) > 3 else 0.2
    import sieve_l1 as L1, sieve_l2 as L2, sieve_dict as SDi; L1.install(); L2.install(); SDi.install(); OL.O.setup_attrs(); import sieve_dict2 as SD2; SD2.load(F); import sieve_l5 as L5; L5.install(); import sieve_sg as SGx; SGx.install(); import sieve_bilin as BLx; BLx.install(); import sieve_attn as SAx; SAx.install(); import sieve_attn2 as SA2x; SA2x.install(); import sieve_knn as KNx; KNx.install()
    for v, c in (("scene", "s"), ("frame", "f")):
        f = os.path.join(F.SC.LX, "sieve_tree", f"attrs_{v}.npz")
        if os.path.exists(f):
            z = np.load(f)
            for k in range(1, 14): F.AT[f"h{c}{k}"] = z[f"k{k}"]
    ST = json.load(open(os.path.join(F.HERE, stf))); words = json.load(open(os.path.join(F.SC.LX, "lx_vocab.json"), encoding="utf-8"))["words"]; wid = {w: i + 1 for i, w in enumerate(words)}
    y, fn, spos, rep, d2 = positions(); SL, _ = P.shortlist("eval"); n, K = SL.shape
    alt = {}
    for a, b in PAIRS:
        if a in wid and b in wid: alt.setdefault(wid[a], []).append(wid[b]); alt.setdefault(wid[b], []).append(wid[a])
    d3 = np.array([int(w) in alt for w in y]); keep = np.nonzero(d2 | d3)[0]
    if len(argv) > 2 and argv[2] == "paq":                                                          # the full online stack (sieve_paq.py's chosen settings)
        import sieve_paq as SPQ; bp = json.load(open(os.path.join(F.HERE, f"sieve_paq_best_{stf.replace('.json', '')}.json"))); sel = "paq"
        data = OL.arrays("eval", ST); Du, _, _ = P.base("eval"); data["LL"] = SPQ.finite(SPQ.lifts("eval", ST, Du)); SEL, pb = SPQ.selectors("eval")
        bits, kept = SPQ.run(data, SEL, pb, bp["sels"], bp["eta"], eta_t=bp["eta_tau"], eta_b=bp["eta_lift"], keep=set(int(i) for i in keep))
    else: data = OL.arrays("eval", ST); bits, kept = OL.run("eval", sel, eta, data, keep=keep)
    ans = data["ans"]
    top1 = [int(np.argmax(kept[i][:K]) == ans[i]) for i in np.nonzero(d2)[0]]
    wins, tot = 0, 0
    for i in np.nonzero(d3)[0]:
        col = lambda w: (lambda c: c if c < K and SL[i, c] == w else None)(int(np.searchsorted(SL[i], w)))
        ca = col(int(y[i]))
        for w2 in alt[int(y[i])]:
            cb = col(w2)
            if ca is not None and cb is not None: tot += 1; wins += int(kept[i][ca] > kept[i][cb])
    r = dict(state=stf, selector=sel, eta=eta, all=bits.mean(), function=bits[fn].mean(), content=bits[~fn].mean(), pos1_10=bits[spos <= 10].mean(), pos11=bits[spos > 10].mean(),
             repeat=bits[rep].mean(), first=bits[~rep].mean(), n_repeat=int(rep.sum()), d2_n=int(d2.sum()), d2_bits=bits[d2].mean(), d2_top1=float(np.mean(top1)), d3_n=tot, d3_share=wins / max(tot, 1))
    json.dump(r, open(os.path.join(F.HERE, f"sieve_diag_{stf.replace('.json', '')}_{sel}.json"), "w"), indent=1)
    F.log("diag " + "; ".join(f"{k} {v:.4f}" if isinstance(v, float) else f"{k} {v}" for k, v in r.items()))
if __name__ == "__main__": main()
