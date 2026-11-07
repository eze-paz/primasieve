"""ED (sieve_lang_prereg.md): error-driven (delta-rule) log-linear next-word model with the count model's feature families.
Class-factored softmax (256 classes x 235 words by frequency), 14 binary hashed features per position, one online pass
(AdaGrad, written out), learning rate from a pilot on training text only. One corpus per run (ED_CORPUS). Writes <out>/<c>_ed.npz.
Smoke: ED_SMOKE=1 ED_DATA=mtest/kaggle_py ED_OUT=<dir> ED_CORPUS=books py -3.12 -I sieve_ed_kernel.py"""
import glob, os, time, numpy as np, torch
SMOKE = bool(os.environ.get("ED_SMOKE")); c = os.environ.get("ED_CORPUS", "books"); dev = "cuda" if torch.cuda.is_available() else "cpu"
V = 60000; VV = V + 2; NC = 256; CS = 235; NF = 14; NEV = 1_000 if SMOKE else 120_000
HC = 2 ** (18 if SMOKE else 24); HW = 2 ** (19 if SMOKE else 25); BS = 1024 if SMOKE else 8192; PIL, PEV = (60_000, 10_000) if SMOKE else (3_000_000, 300_000)
OUTD = "/kaggle/working" if os.path.isdir("/kaggle/working") else os.environ.get("ED_OUT", "."); T0 = time.time(); torch.manual_seed(0)
def log(m): print(f"{m} ({time.time() - T0:.0f} s)", flush=True)
f = (glob.glob("/kaggle/input/**/*_data.npz", recursive=True) or glob.glob(os.path.join(os.environ.get("ED_DATA", "."), "*_data.npz")))
z = np.load([x for x in f if os.path.basename(x).startswith(c)][0]); S = z["S"].astype(np.int64); Dc = z["D"].astype(np.int64); ntr = int(z["ntr"])
if SMOKE: S = np.r_[S[:300_000], S[ntr:ntr + 200_000]]; Dc = np.r_[Dc[:300_000], Dc[ntr:ntr + 200_000]]; ntr = 300_000
N = len(S); con = (S > 100) & (S <= V); T = np.nonzero(con[ntr:])[0] + ntr; T = T[T >= ntr + 2]; T = T[np.linspace(0, len(T) - 1, NEV).astype(int)]
tr = np.arange(2, ntr); tr = tr[S[tr] != 0]; n1 = np.bincount(S[tr], minlength=VV); order = np.argsort(-n1, kind="stable"); rank = np.empty(VV, np.int64); rank[order] = np.arange(VV)
cls = rank // CS; wpos = rank % CS; M = np.full((NC, CS), -1, np.int64); M[cls[order], wpos[order]] = order
# features for every position t >= 2 (int32 keys < 2^31 - 1)
p = np.arange(N); w1 = S[np.maximum(p - 1, 0)]; w2 = S[np.maximum(p - 2, 0)]; kp = np.nonzero(con)[0]; k = np.searchsorted(kp, p - 1)
def key(tag, val): return ((np.int64(tag) * 1_000_000_007 + val.astype(np.int64)) % 2_147_483_647).astype(np.int32)
F = np.zeros((N, NF), np.int32); F[:, 0] = key(0, np.zeros(N, np.int64)); F[:, 1] = key(1, w1); F[:, 2] = key(2, w2 * VV + w1)
ix = k - 1; ok = (ix >= 0) & (Dc[kp[np.maximum(ix, 0)]] == Dc); F[:, 3] = key(3, np.where(ok, S[kp[np.maximum(ix, 0)]], 0) * VV + w1)
for j in range(10):
    ix = k - 1 - j; ok = (ix >= 0) & (Dc[kp[np.maximum(ix, 0)]] == Dc); F[:, 4 + j] = key(4, np.where(ok, S[kp[np.maximum(ix, 0)]], 0))
log(f"{c}: {N:,} tokens, {len(tr):,} training positions, features built")
Ft = torch.tensor(F); St = torch.tensor(S); clsT = torch.tensor(cls, device=dev); wposT = torch.tensor(wpos, device=dev); MT_ = torch.tensor(M, device=dev); arC = torch.arange(NC, device=dev)
class LL:
    """weights = hashed scalars; delta-rule updates written out: gradient of each gathered weight = predicted minus actual"""
    def __init__(s):
        s.tc = torch.zeros(HC, device=dev); s.ac = torch.zeros(HC, device=dev); s.tw = torch.zeros(HW, device=dev); s.aw = torch.zeros(HW, device=dev)
    def fwd(s, fk, y):
        fk = fk.long(); cy = clsT[y]; wd = MT_[cy]; pad = wd < 0
        ic = (fk[:, :, None] * 1_000_003 + arC[None, None, :] * 97) % HC; iw = (fk[:, :, None] * 1_000_003 + wd.clamp(min=0)[:, None, :] * 97 + 13) % HW
        lc = torch.log_softmax(s.tc[ic].sum(1), 1); lw = torch.log_softmax(s.tw[iw].sum(1).masked_fill(pad, -1e9), 1); wp = wposT[y]
        return lc.gather(1, cy[:, None])[:, 0] + lw.gather(1, wp[:, None])[:, 0], (ic, iw, lc, lw, cy, wp, pad)
    def step(s, st, lr):
        ic, iw, lc, lw, cy, wp, pad = st; ar = torch.arange(len(cy), device=dev)
        gc = lc.exp(); gc[ar, cy] -= 1; gw = lw.exp().masked_fill(pad, 0); gw[ar, wp] -= 1
        for th, ac, ix, g in ((s.tc, s.ac, ic, gc), (s.tw, s.aw, iw, gw)):
            ix = ix.reshape(-1); g = g[:, None, :].expand(-1, NF, -1).reshape(-1); ac.index_add_(0, ix, g * g); th.index_add_(0, ix, -lr * g / torch.sqrt(ac[ix] + 1e-8))
def train(pos, lr):
    m = LL(); tot = 0.0
    for a in range(0, len(pos), BS):
        q = torch.tensor(pos[a:a + BS]); lp, st = m.fwd(Ft[q].to(dev), St[q].to(dev)); m.step(st, lr); tot += float(-lp.sum())
        assert np.isfinite(tot), "non-finite loss"
    return m, tot / len(pos) / np.log(2)
@torch.no_grad()
def score(m, pos):
    out = np.zeros(len(pos))
    for a in range(0, len(pos), BS):
        q = torch.tensor(pos[a:a + BS]); out[a:a + BS] = m.fwd(Ft[q].to(dev), St[q].to(dev))[0].cpu().numpy()
    return out
pil = {}
for lr in (0.01, 0.03, 0.1, 0.3):
    m, _ = train(tr[:PIL], lr); pil[lr] = float(-score(m, tr[PIL:PIL + PEV]).mean() / np.log(2)); log(f"{c} pilot lr {lr}: {pil[lr]:.4f} bits/word on training positions {PIL:,}..{PIL + PEV:,}")
lr = min(pil, key=pil.get); m, trb = train(tr, lr); lp = score(m, T); log(f"{c}: full pass lr {lr}, online training bits/word {trb:.4f}; eval content targets {-lp.mean() / np.log(2):.4f}")
np.savez(os.path.join(OUTD, f"{c}_ed.npz"), T=T, P=np.exp(lp), lr=lr, pilot=np.array([pil[x] for x in (0.01, 0.03, 0.1, 0.3)]), train_bits=trb)
