"""JT (sieve_lang_prereg.md LTJT): train a linear readout W (32 x 32) on the frozen HBlearn slow state for Sieve's licence job.
  py -3.12 -I sieve_jt.py collect   -> mtest/jt_data.npz (23,000 training positions: text state, candidate sources, true word)
  py -3.12 -I sieve_jt.py train     -> mtest/jt_W.npy + sieve_jt_auc.json (held-out AUC, trained vs untrained cosine)"""
import os, sys, json, time
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
NTR, NHO, LP = 20000, 3000, 30
def collect():
    import sieve_dec as SD
    d = SD.Dec(); S = d.S; g = np.random.default_rng(0); cfg = {"T": 0.35, "nounk": 1, "norep": 1}
    cand = np.nonzero((S[5000:d.ntr - 5000] > 100) & (S[5000:d.ntr - 5000] <= d.V))[0] + 5000; cand = cand[d.idf[S[cand]] >= 2]
    ts = g.choice(cand, 4 * (NTR + NHO), replace=False); TV, XS, WI, EX, LAB = [], [], [], [], []; n = 0
    for t in ts:
        text = S[t - LP:t].tolist(); uw, p = d.dist(text, cfg); pos, inv = d._pos, d._inv; E = d.held_entities(text)
        el = np.array([(100 < int(w) <= d.V) and int(w) not in E and d.idf[int(w)] >= 2 for w in uw]); y = int(S[t])
        if y not in uw: continue
        yi = int(np.searchsorted(uw, y)); el[yi] = True; far = np.abs(pos - t) >= 2000; keep = far & el[inv]
        if not (keep & (inv == yi)).any() or len(np.unique(inv[keep])) < 2: continue
        k = np.nonzero(keep)[0]; wi = inv[k]; u, wi = np.unique(wi, return_inverse=True)
        TV.append(d.tstate(text)); XS.append(d.HS[pos[k] - 1].astype(np.float32) - d.HSmu); WI.append(wi); LAB.append(int(np.searchsorted(u, yi))); EX.append(len(k)); n += 1
        if n % 500 == 0: SD.log(f"{n} examples")
        if n >= NTR + NHO: break
    off = np.r_[0, np.cumsum(EX)]
    np.savez(os.path.join(HERE, "mtest", "jt_data.npz"), tv=np.array(TV, np.float32), xs=np.concatenate(XS), wi=np.concatenate(WI), off=off, lab=np.array(LAB)); SD.log(f"saved {n}")
def train():
    import torch
    z = np.load(os.path.join(HERE, "mtest", "jt_data.npz")); tv, xs, wi, off, lab = [torch.as_tensor(z[k]) for k in ("tv", "xs", "wi", "off", "lab")]; N = len(lab); torch.manual_seed(0)
    def scores(W, i):
        a, b = int(off[i]), int(off[i + 1]); x = xs[a:b] @ W.T; v = W @ tv[i]; c = (x @ v) / (x.norm(dim=1) * v.norm() + 1e-9)
        m = int(wi[a:b].max()) + 1; return torch.zeros(m).index_add(0, wi[a:b], c) / torch.bincount(wi[a:b], minlength=m).float()
    def auc(W, idx):
        r = []
        with torch.no_grad():
            for i in idx:
                sc = scores(W, i); y = int(lab[i]); o = torch.cat([sc[:y], sc[y + 1:]]); r.append(float((o < sc[y]).float().mean() + 0.5 * (o == sc[y]).float().mean()))
        return float(np.mean(r))
    tr, ho = range(NTR), range(NTR, N); W = torch.eye(32, requires_grad=True); scale = torch.tensor(10.0, requires_grad=True)
    base = auc(torch.eye(32), ho); opt = torch.optim.Adam([W, scale], lr=1e-2); print(f"untrained held-out AUC {base:.4f}", flush=True)
    for ep in range(20):
        perm = np.random.default_rng(ep).permutation(NTR); tot = 0.0
        for j in range(0, NTR, 64):
            opt.zero_grad(); loss = sum(torch.nn.functional.cross_entropy((scale * scores(W, i))[None], lab[i:i + 1]) for i in perm[j:j + 64]) / 64; loss.backward(); opt.step(); tot += float(loss)
        print(f"epoch {ep} loss {tot / (NTR / 64):.4f}", flush=True)
    a = auc(W.detach(), ho); np.save(os.path.join(HERE, "mtest", "jt_W.npy"), W.detach().numpy())
    out = dict(untrained_auc=base, trained_auc=a, n_train=NTR, n_heldout=N - NTR); json.dump(out, open(os.path.join(HERE, "sieve_jt_auc.json"), "w"), indent=1); print(out)
if __name__ == "__main__": dict(collect=collect, train=train)[sys.argv[1]]()
