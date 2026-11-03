"""SE5 generated text (sieve_lang_prereg.md): the L5 program (static, no online stack) continues held-out passages
word by word. Each sample is its own book: the 300 held-out tokens before a sentence start, then the words generated so
far. Every step builds a context whose scored positions are the samples' next positions (a placeholder answer, the
step's top bigram successor, so the exact column stays empty) and samples from the program's distribution over the
shortlist + rest (rest: a word outside the shortlist by unigram). Votes for these contexts are not kept on disk.
Run: SZ_EXACT=1 py -3.12 -W ignore sieve_gen.py [n_words] [samples] [seed]"""
import os, sys, json, glob, time
import numpy as np
def main(argv):
    import sieve_l5 as L5; F, P, P3, O = L5.setup(); import sieve_fast as FS
    nw = int(argv[1]) if len(argv) > 1 else 20; ns = int(argv[2]) if len(argv) > 2 else 4; rng = np.random.default_rng(int(argv[3]) if len(argv) > 3 else 0)
    ST = json.load(open(os.path.join(F.HERE, "sieve_l5_offer.json"))); words = json.load(open(os.path.join(F.SC.LX, "lx_vocab.json"), encoding="utf-8"))["words"]
    S = P.corpus(); uk, nN, nT, pairs, cnt = FS.static_cached("corpus", S, (("id", 1),)); topu = np.argsort(-P.uni())[:64]; u = P.uni()
    ev, NT = F.ev_s, F.NT; st0 = np.nonzero(ev[NT + 400:] == 0)[0] + NT + 400; starts = st0[np.linspace(0, len(st0) - 1, ns + 2).astype(int)[1:-1]]
    segs = [list(ev[a - 299:a + 1]) for a in starts]; gen = [[] for _ in range(ns)]
    def succ(k):
        lo, hi = np.searchsorted(pairs, np.int64(k) * F.SH), np.searchsorted(pairs, (np.int64(k) + 1) * F.SH); ys = pairs[lo:hi] & (F.SH - 1); return ys[np.argsort(-cnt[lo:hi], kind="stable")]
    _sl = P.shortlist
    def shortlist(cx):
        if not cx.startswith("gen"): return _sl(cx)
        s, T, _ = F.ctx(cx); rows = [np.unique(np.r_[succ(s[t - 1])[:128], s[max(0, t - 256):t], topu]) for t in T]; K = max(len(r) for r in rows)
        SL = np.full((len(T), K), F.Vt + 10, np.int64)
        for i, r in enumerate(rows): SL[i, :len(r)] = r
        ans = np.array([np.searchsorted(SL[i], s[t]) for i, t in enumerate(T)]); return SL, ans
    P.shortlist = shortlist; t0 = time.time()
    for step in range(nw):
        cx = f"gen{step}"; parts = [F.tr]; T = []; b = [np.full(F.NT, -1)]; off = F.NT
        for i in range(ns):
            x = np.array(segs[i] + gen[i], np.int64); ph = succ(x[-1])[:1]; ph = ph if len(ph) else topu[:1]; x = np.r_[x, ph]
            parts.append(x); b.append(np.full(len(x), 10_000 + i)); T.append(off + len(x) - 1); off += len(x)
        F.CTX[cx] = (np.concatenate(parts), np.array(T), np.concatenate(b))
        M = P3.Model(cx, ST); M.gact = ST["gact"]; A, logL, W = M.parts(); L = np.exp(logL - logL.max(1, keepdims=True)); Pd = A * L; Pd /= Pd.sum(1, keepdims=True)
        SL, _ = P.shortlist(cx); K = SL.shape[1]
        for i in range(ns):
            p = Pd[i, :K + 1].astype(float) + np.r_[np.zeros(K), Pd[i, K + 1:].sum()]; p /= p.sum(); c = rng.choice(K + 1, p=p)
            if c < K and SL[i, c] < F.Vt: w = int(SL[i, c])
            else: q = u.copy(); q[SL[i][SL[i] < F.Vt]] = 0; q[0] = 0; q[F.Vt - 1:] = 0; w = int(rng.choice(len(q), p=q / q.sum()))
            gen[i].append(w)
        for f in glob.glob(os.path.join(P.PD, f"{cx}_*")): os.remove(f)
        del F.CTX[cx]; print(f"   step {step + 1}: {time.time() - t0:.0f} s", flush=True)
    tok = lambda w: "|" if w == 0 else (words[w - 1] if w - 1 < len(words) else "?")
    out = []
    for i in range(ns):
        ctxt = " ".join(tok(w) for w in segs[i][-25:]); g = " ".join(tok(w) for w in gen[i]); out.append(dict(context=ctxt, generated=g)); F.log(f"SE5 sample {i + 1}: ...{ctxt} >> {g}")
    json.dump(out, open(os.path.join(F.HERE, "sieve_gen_samples.json"), "w"), indent=1)
if __name__ == "__main__": main(sys.argv[:])
