"""MT3/MT4 (sieve_lang_prereg.md): MiniLM sentence neighbours (soft) and MiniLM k-means states (hard) on the MT data.
Context of a sentence = the two complete sentences before it (same document), embedded by all-MiniLM-L6-v2 (mean pooling,
unit length). Index = a fixed sample of training sentences; each votes with the content words of its own sentence (the
sentence that followed its context). Eval: the target's sentence's context; soft N = similarity-weighted (exp(10 cos))
votes of the 50 nearest index contexts; hard H = the nearest of K=1000 k-means centroids, its pooled content counts with
an additive unigram prior (10). Output mtest/<c>_nn.npz (pN, pH at the MT eval positions), mixed in by sieve_mtest eval.
Resumable: embeddings in chunks, 200 s per run. Run: py -3.12 -I sieve_mtnn.py <c>  (repeat until 'done')"""
import os, sys, time
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); import sieve_mtest as MT
T0 = time.time(); NIDX = 300_000; KN = 50; KH = 1000; BUD = 200; V = MT.V; VV = MT.VV
def log(m): print(f"{m} ({time.time() - T0:.0f} s)", flush=True)
def main(c):
    import torch
    from transformers import AutoTokenizer, AutoModel
    torch.set_num_threads(8); z = np.load(MT.fp(c, "data")); S, Dc, ntr, vw = z["S"].astype(np.int64), z["D"], int(z["ntr"]), z["vw"]; con = (S > 100) & (S <= V)
    T = np.nonzero(con[ntr:])[0] + ntr; T = T[T >= ntr + 2]; T = T[np.linspace(0, len(T) - 1, MT.NEV).astype(int)]; y = S[T]   # same positions as sieve_mtest eval
    zs = np.nonzero(S == 0)[0]; st = zs + 1; en = np.r_[zs[1:], len(S)]; sd = Dc[np.minimum(st, len(S) - 1)]                           # sentence i: S[st[i]:en[i]]
    ok = np.r_[False, False, (sd[2:] == sd[1:-1]) & (sd[1:-1] == sd[:-2])]                                                           # two previous sentences in the same document
    trs = np.nonzero(ok & (en <= ntr))[0]; idx = np.sort(np.random.default_rng(2).choice(trs, min(NIDX, len(trs)), replace=False))
    si = np.searchsorted(st, T, side="right") - 1; evs = np.unique(si[ok[si]])
    def text(i): return " ".join(str(vw[w]) if w <= V else "unk" for w in S[st[i]:en[i]])
    ef = MT.fp(c, "nnemb"); need = np.r_[idx, evs]; kd = os.path.join(MT.OUT, "kaggle_nn")
    if EXPORT:                                                                                           # GPU path: texts out, embeddings back from Kaggle
        import gzip; os.makedirs(kd, exist_ok=True)
        with gzip.open(os.path.join(kd, f"{c}_ctx.txt.gz"), "wt", encoding="utf-8") as f:
            for i in need: f.write(text(i - 2) + " " + text(i - 1) + "\n")
        log(f"MT nn {c}: exported {len(need):,} contexts"); return
    kx = os.path.join(kd, "out", f"{c}_X.npy")
    if os.path.exists(kx): X = np.load(kx); assert len(X) == len(need) and not np.isnan(X[:, 0]).any(); log(f"MT nn {c}: GPU embeddings loaded")
    elif os.path.exists(ef): e = np.load(ef); X = e["X"]; assert np.array_equal(e["need"], need)
    else: X = np.full((len(need), 384), np.nan, np.float16)
    if np.isnan(X[:, 0]).any():
        tk = AutoTokenizer.from_pretrained(os.path.join(HERE, "models", "minilm")); md = AutoModel.from_pretrained(os.path.join(HERE, "models", "minilm")).eval(); t1 = time.time(); n0 = 0
        for a0 in range(0, len(need), 512):
            if not np.isnan(X[a0, 0]): continue
            if time.time() - T0 > BUD: break
            b = tk([text(i - 2) + " " + text(i - 1) for i in need[a0:a0 + 512]], padding=True, truncation=True, max_length=128, return_tensors="pt")
            with torch.no_grad(): h = md(**b).last_hidden_state; m = b["attention_mask"].unsqueeze(-1).float(); v = (h * m).sum(1) / m.sum(1)
            X[a0:a0 + 512] = torch.nn.functional.normalize(v, dim=1).numpy().astype(np.float16); n0 += len(v)
        np.savez(ef, X=X, need=need); left = int(np.isnan(X[:, 0]).sum()); log(f"MT nn {c}: embedded {n0:,} contexts at {n0 / max(time.time() - t1, 1):.0f}/s; {left:,} of {len(need):,} left")
        if left: return
    Xi = torch.tensor(X[:len(idx)].astype(np.float32)); Xe = torch.tensor(X[len(idx):].astype(np.float32)); pos = {s: j for j, s in enumerate(evs)}
    lens = np.array([int(con[st[i]:en[i]].sum()) for i in idx]); rows = np.repeat(np.arange(len(idx)), [en[i] - st[i] for i in idx]); ws = np.concatenate([S[st[i]:en[i]] for i in idx])
    m_ = (ws > 100) & (ws <= V); bk, bn = np.unique(rows[m_] * VV + ws[m_], return_counts=True)                                       # each index sentence's content-word counts
    pN = np.zeros(len(T)); pH = np.zeros(len(T)); er = np.array([pos.get(s, -1) for s in si]); has = er >= 0
    uc = np.bincount(S[:ntr][con[:ntr]], minlength=VV).astype(float) + 0.5; uc[:101] = 0; uc[V + 1:] = 0; uc /= uc.sum()
    sf = MT.fp(c, "nnsoft"); a_start = 0                                                                                             # soft part resumable
    if os.path.exists(sf): s_ = np.load(sf); pN = s_["pN"]; a_start = int(s_["a0"])
    for a0 in range(a_start, len(evs), 500):                                                                                         # soft: 50 nearest index contexts
        if time.time() - T0 > 200: np.savez(sf, pN=pN, a0=a0); log(f"MT nn {c}: soft {a0:,} of {len(evs):,}; rerun"); return
        sim, nb = (Xe[a0:a0 + 500] @ Xi.T).topk(KN, dim=1); sim, nb = sim.numpy(), nb.numpy(); wt = np.exp(10 * sim) * (lens[nb] > 0)
        rr = np.nonzero(has & (er >= a0) & (er < a0 + 500))[0]; q = er[rr] - a0; kk = nb[q] * VV + y[rr][:, None]
        i_ = np.minimum(np.searchsorted(bk, kk), len(bk) - 1); cnt = np.where(bk[i_] == kk, bn[i_], 0)
        pN[rr] = (wt[q] * cnt / np.maximum(lens[nb[q]], 1)).sum(1) / np.maximum(wt[q].sum(1), 1e-30)
    g = torch.Generator().manual_seed(0); C = Xi[torch.randperm(len(Xi), generator=g)[:KH]].clone()                                    # hard: spherical k-means
    for _ in range(10):
        a = (Xi @ C.T).argmax(1); C = torch.zeros_like(C).index_add_(0, a, Xi); C = torch.nn.functional.normalize(C + 1e-9, dim=1)
    a = (Xi @ C.T).argmax(1).numpy(); ae = (Xe @ C.T).argmax(1).numpy(); hk, hn = np.unique(a[bk // VV] * VV + bk % VV, return_inverse=True); hn = np.bincount(hn, weights=bn)
    ht = np.bincount(a[bk // VV], weights=bn, minlength=KH); kk = ae[er[has]] * VV + y[has]; i_ = np.minimum(np.searchsorted(hk, kk), len(hk) - 1); cnt = np.where(hk[i_] == kk, hn[i_], 0)
    pH[has] = (cnt + 10 * uc[y[has]]) / (ht[ae[er[has]]] + 10)
    np.savez(MT.fp(c, "nn"), T=T, pN=pN, pH=pH); log(f"MT nn {c}: done; {int(has.sum()):,} of {len(T):,} targets have a context; {len(np.unique(a)):,} hard states in use")
EXPORT = False
if __name__ == "__main__": EXPORT = len(sys.argv) > 2 and sys.argv[2] == "export"; main(sys.argv[1])
