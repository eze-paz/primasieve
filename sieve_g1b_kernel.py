"""G1B (sieve_lang_prereg.md, BIG1B): E2E's BEST generator (exact-match weight 8, K reversed-prefix candidates, power on
the word distribution, repeat guard, never <unk>, copy cap 8) with storage that fits ~1B training words:
uint16 tokens on the host, int32 tokens and positions on the GPU, the 4-word key index built one first-word range at a
time (same order as the stable argsort), the 8-gram copy table filled in chunks and sorted in place.
G1_MODE=sanity: BIG's 191M stream (four PG-19 half-shards), BEST only -> must equal E2E's BEST texts.
G1_MODE=1b: MT 27M + tok1b shards 0..11 (extended vocabulary), arms B1G6 / B1G12.
Smoke: G1_SMOKE=1 G1_DATA=.. G1_OUT=.. (MT 2M + 300k eval, K 256, 3 prompts; compare with e2b.py's smoke)."""
import glob, os, time, json, math, numpy as np, torch
SMOKE = bool(os.environ.get("G1_SMOKE")); SA = bool(os.environ.get("G1_SA")); JX = bool(os.environ.get("G1_JX")); MODE = os.environ.get("G1_MODE", "1b"); dev = "cuda" if torch.cuda.is_available() else "cpu"; T0 = time.time()
V = 60000; UNK = V + 1; LP, LG = 30, 50; M64 = np.uint64(0x9E3779B97F4A7C15); K = 256 if SMOKE else 3072; MW = 4; LAM0 = 8.0; CHUNK = int(os.environ.get("G1_CHUNK", 60_000_000))
OUTD = "/kaggle/working" if os.path.isdir("/kaggle/working") else os.environ.get("G1_OUT", ".")
def log(m): print(f"{m} ({time.time() - T0:.0f} s)", flush=True)
def find(pat, env): return glob.glob(f"/kaggle/input/**/{pat}", recursive=True) or glob.glob(os.path.join(os.environ.get(env, "."), pat))
CORPUS = os.environ.get("G1_CORPUS", "books"); z = np.load([x for x in find(f"{CORPUS}_data.npz", "G1_DATA")][0]); S0 = z["S"]; ntr0 = int(z["ntr"]); vw = [str(w) for w in z["vw"]]; del z
if SMOKE: S0 = np.r_[S0[:2_000_000], S0[ntr0:ntr0 + 300_000]]; ntr0 = 2_000_000
if SMOKE: parts = []
elif os.environ.get("G1_LOCAL"): parts = []                                                                      # local bench: MT 27M only
elif MODE in ("sanity", "sa", "jx"): parts = [glob.glob(f"/kaggle/input/**/tok_books_{p}.npz", recursive=True)[0] for p in ("0_0", "0_1", "1_0", "1_1")]
else:
    parts = [glob.glob(f"/kaggle/input/**/tok1b_{k}.npz", recursive=True)[0] for k in range(12)]
    vw = vw + [None] * (V + 2 - len(vw)) if len(vw) < V + 2 else vw[:V + 2]; vw = vw + json.load(open(glob.glob("/kaggle/input/**/tok1b_vocab.json", recursive=True)[0]))
VV = max(len(vw), V + 2)
lens = [len(np.load(p)["S"]) for p in parts]; ntr = ntr0 + sum(lens); N = ntr + (len(S0) - ntr0)
S = np.empty(N, np.uint16); S[:ntr0] = S0[:ntr0]; o_ = ntr0
for p, l in zip(parts, lens): S[o_:o_ + l] = np.load(p)["S"]; o_ += l
S[ntr:] = S0[ntr0:]; del S0; fine = np.load([x for x in find("books_cls.npz", "G1_CLS")][0])["fine"]; FINE = torch.tensor(np.r_[fine, np.full(max(0, VV - len(fine)), fine[UNK])].astype(np.int64), device=dev); log(f"stream: {ntr:,} training tokens, {N:,} total, vocabulary {VV:,}")
St = torch.empty(N, dtype=torch.int32, device=dev)
for a in range(0, N, CHUNK): St[a:a + CHUNK] = torch.from_numpy(S[a:a + CHUNK].astype(np.int32)).to(dev)
# 4-word key index: KEYS sorted (host uint64), ORD = positions (GPU int32), positions P = 200..ntr-1, key = (S[P-1], S[P-2], S[P-3], S[P-4]) packed high to low
w1 = S[199:ntr - 1]; cnt = np.bincount(w1, minlength=1 << 16); NP_ = len(w1); KEYS = np.empty(NP_, np.uint64); KEYS2 = np.empty(NP_ if SA else 0, np.uint64); ORD = torch.empty(NP_, dtype=torch.int32, device=dev)
cum = np.cumsum(cnt); cuts = [0]
while cuts[-1] < (1 << 16):
    b = int(np.searchsorted(cum, (cum[cuts[-1] - 1] if cuts[-1] else 0) + CHUNK, side="right")); cuts.append(min(max(b, cuts[-1] + 1), 1 << 16))
off = 0
for a, b in zip(cuts[:-1], cuts[1:]):
    P = np.nonzero((w1 >= a) & (w1 < b))[0] + 200
    if not len(P): continue
    kk = np.zeros(len(P), np.uint64)
    for i in range(4): kk = (kk << np.uint64(16)) | S[P - 1 - i].astype(np.uint64)
    if SA:                                                                                                   # ties on the 4-word key ordered by words 5-8 back (longest shared history adjacent)
        k2 = np.zeros(len(P), np.uint64)
        for i in range(4): k2 = (k2 << np.uint64(16)) | S[P - 5 - i].astype(np.uint64)
        o = np.lexsort((k2, kk)); KEYS2[off:off + len(P)] = k2[o]; del k2
    else: o = np.argsort(kk, kind="stable")
    KEYS[off:off + len(P)] = kk[o]; ORD[off:off + len(P)] = torch.from_numpy(P[o].astype(np.int32)).to(dev); off += len(P); del kk, o, P
assert off == NP_; del w1; log(f"key index: {NP_:,} positions in {len(cuts) - 1} ranges")
if JX:                                                                                                         # Brown-objective classes (exchange, on the MT 27M text) and class 5-gram table over the training stream
    if "brown" not in globals(): import sys as _s; _s.path.insert(0, os.path.dirname(os.path.abspath(__file__))); from sieve_brown import brown
    BC = 64; _bc = os.environ.get("G1_BCACHE")
    if _bc and os.path.exists(_bc): BCL = np.load(_bc)["BCL"]; log(f"Brown classes from cache {_bc}")
    else:
        BCL = brown(S[:ntr0], VV, C=BC, iters=3 if SMOKE else 15, log=log)
        if _bc: np.savez(_bc, BCL=BCL)
    BCLu = BCL.astype(np.uint32); NJ = min(ntr, int(os.environ.get("G1_JXN", ntr))); CLS_ = BCLu[S[:NJ]]               # class tables over the first NJ training tokens
    TB = {}
    for J in sorted({int(c.get("jn", 4)) for c in json.loads(os.environ.get("G1_ARMS", "{}")).values()} | {4}):            # class (J+1)-gram and J-gram counts over the training stream
        kf = np.zeros(NJ - J, np.uint64)
        for i in range(J + 1): kf = (kf << np.uint64(6)) | CLS_[i:NJ - J + i].astype(np.uint64)
        uf, nf = np.unique(kf, return_counts=True); uc, nc = np.unique(kf >> np.uint64(6), return_counts=True); TB[J] = (uf, nf, uc, nc); del kf
        log(f"class {J + 1}-gram table: {len(uf):,} distinct of {NJ - J:,}")
    PRON = [i for i, w_ in enumerate(vw[:V + 2]) if w_ in ("i", "he", "she", "they", "we", "you", "it")]                  # verb-like classes: what follows subject pronouns
    nxt = BCL[S[1:NJ][np.isin(S[:NJ - 1], PRON)]]; cf = np.bincount(nxt, minlength=BC) / max(len(nxt), 1); VCL = np.nonzero(cf > 0.02)[0]; VCL = VCL[VCL != 0]
    VSET = np.zeros(BC, bool); VSET[VCL] = True; log(f"verb-like classes {VCL.tolist()} (share after pronouns {cf[VCL].round(3).tolist()})")
    del CLS_
    WT = {}
    for n in sorted({int(c["wn"]) for c in json.loads(os.environ.get("G1_ARMS", "{}")).values() if c.get("wn")} | ({3, 5} if any(c.get("gibbs") for c in json.loads(os.environ.get("G1_ARMS", "{}")).values())  else set()) | {5} | ({3} if any(c.get("gen") == "ssm" for c in json.loads(os.environ.get("G1_ARMS", "{}")).values()) else set())):     # word n-gram tables (sorted hashes) over the first NJ tokens
        h = np.zeros(NJ - n + 1, np.uint64)
        with np.errstate(over="ignore"):
            for i in range(n): h = h * M64 + S[i:NJ - n + 1 + i].astype(np.uint64) + np.uint64(1)
        h.sort(); WT[n] = h; log(f"word {n}-gram table: {len(h):,}")
    JSTAT = [0, 0, 0]
H8 = np.empty(ntr - 8, np.uint64)                                                                             # copy table = sorted hseq(8) of e2b.py
with np.errstate(over="ignore"):
    for a in range(0, ntr - 8, CHUNK):
        b = min(a + CHUNK, ntr - 8); h = np.zeros(b - a, np.uint64)
        for i in range(8): h = h * M64 + S[a + i:b + i].astype(np.uint64) + np.uint64(1)
        H8[a:b] = h
H8.sort(); log(f"copy table {len(H8):,}")
def hn(arr2d):
    h = np.zeros(arr2d.shape[0], np.uint64)
    with np.errstate(over="ignore"):
        for i in range(arr2d.shape[1]): h = h * M64 + arr2d[:, i].astype(np.uint64) + np.uint64(1)
    return h
def pack(Q):
    k = np.zeros(len(Q), np.uint64)
    for i in range(4): k = (k << np.uint64(16)) | Q[:, i].astype(np.uint64)
    return k
def cands(Qrev, Q2=None):
    q = pack(Qrev); i0 = np.searchsorted(KEYS, q).astype(np.int64)
    if SA:
        hi = np.searchsorted(KEYS, q, side="right"); q2 = pack(Q2)
        for j in range(len(q)):
            if hi[j] > i0[j]: i0[j] = i0[j] + np.searchsorted(KEYS2[i0[j]:hi[j]], q2[j])
    i0 = torch.tensor(i0, device=dev); r = torch.arange(K // 2, device=dev)
    idx = torch.cat([i0[:, None] - 1 - r, i0[:, None] + r], 1); ok = (idx >= 0) & (idx < NP_); return ORD[idx.clamp(0, NP_ - 1)].long(), ok
LSTAT = []; HM = {}; SVDTH = None; HG = torch.Generator(); LIN = None
if any(c.get("lin") for c in json.loads(os.environ.get("G1_ARMS", "{}")).values()):                             # trained linear readout on the fitted harmonic state (HLIN2), next fine class
    _lp = glob.glob("/kaggle/input/**/hlin_readout.pt", recursive=True) or [os.environ.get("G1_LIN", "hlin_readout.pt")]
    _r = torch.load(_lp[0], map_location=dev); LIN = dict(W=_r["W"].to(dev).float(), sc=float(_r["cfg"]["sc"]), om=_r["omega"].to(dev), TH={int(t): v.to(dev) for t, v in _r["TH"].items()}, TAUS=tuple(int(t) for t in _r["TAUS"]))
    log(f"linear readout loaded: {_r['cfg']}")
LW = None
if any(c.get("linw") for c in json.loads(os.environ.get("G1_ARMS", "{}")).values()):                            # next-word log-bilinear readout (HWORD2)
    _lp = glob.glob("/kaggle/input/**/hword_readout.pt", recursive=True) or [os.environ.get("G1_LW", "hword_readout.pt")]
    _r = torch.load(_lp[0], map_location=dev); _vid = _r["vid"].to(dev); _cw = np.bincount(S[:ntr0], minlength=VV).astype(np.float64); _oov = (_r["vid"].cpu().numpy()[:VV] == _r["NV"] - 1)
    _lin_oov = torch.tensor(np.log(np.maximum(_cw, 1) / max(_cw[_oov].sum(), 1)), dtype=torch.float32, device=dev)
    LW = dict(W=_r["W"].to(dev).float(), b=_r["b"].to(dev).float(), vid=_vid, NV=int(_r["NV"]), om=_r["omega"].to(dev), TH={int(t): v.to(dev) for t, v in _r["TH"].items()}, TAUS=tuple(int(t) for t in _r["TAUS"]), loov=_lin_oov)
    log("next-word readout loaded")
SSMM = None
if any(c.get("ssm") or c.get("gen") == "ssm" for c in json.loads(os.environ.get("G1_ARMS", "{}")).values()):                             # trained harmonic-start state-space LM (HSSM) as a candidate scorer
    import torch.nn as nn
    def _load_hssm():
        VVh = int(max(S[:ntr0].max(), S[ntr:].max())) + 1; NVh = 8192; cw = np.bincount(S[:ntr0].astype(np.int64), minlength=VVh); topw = np.argsort(-cw)[:NVh - 1]
        vid = np.full(VVh, NVh - 1, np.int64); vid[topw] = np.arange(NVh - 1); oov = cw[vid == NVh - 1].sum(); poo = np.log(np.maximum(cw, 1) / max(oov, 1))
        TA = (2, 4, 8, 16, 32, 64, 128); DB = 64; NN = DB * len(TA); fn = os.environ.get("G1_SSMF", "hssm_harm.pt")
        mp = glob.glob(f"/kaggle/input/**/{fn}", recursive=True) or [os.environ.get("G1_SSM", fn)]; sd = torch.load(mp[0], map_location=dev); DM = int(sd["emb.weight"].shape[1]); NLy = len({k.split(".")[1] for k in sd if k.startswith("layers.")})
        class SSM(nn.Module):
            def __init__(s):
                super().__init__(); s.nu = nn.Parameter(torch.zeros(NN)); s.th = nn.Parameter(torch.zeros(NN)); s.B = nn.Parameter(torch.zeros(NN, DM, 2)); s.C = nn.Parameter(torch.zeros(DM, NN, 2)); s.Dd = nn.Parameter(torch.ones(DM))
                s.ln = nn.LayerNorm(DM); s.ff = nn.Sequential(nn.Linear(DM, 4 * DM), nn.GELU(), nn.Linear(4 * DM, DM)); s.ln2 = nn.LayerNorm(DM)
            def forward(s, x):
                u = s.ln(x); Bc = torch.complex(s.B[..., 0], s.B[..., 1]); Bu = torch.einsum("btd,nd->btn", u.to(torch.complex64), Bc)
                lam = torch.exp(-torch.exp(s.nu) + 1j * s.th); Tn = x.shape[1]; j = torch.arange(Tn, device=x.device, dtype=torch.float32)
                k = torch.exp(j[:, None] * torch.log(lam)[None, :]); n_ = 2 * Tn
                h = torch.fft.ifft(torch.fft.fft(Bu, n=n_, dim=1) * torch.fft.fft(k, n=n_, dim=0)[None], dim=1)[:, :Tn]
                Cc = torch.complex(s.C[..., 0], s.C[..., 1]); y = torch.einsum("btn,dn->btd", h, Cc).real + s.Dd * u
                x = x + y; return x + s.ff(s.ln2(x))
        class LM(nn.Module):
            def __init__(s):
                super().__init__(); s.emb = nn.Embedding(VVh, DM); s.layers = nn.ModuleList([SSM() for _ in range(NLy)]); s.lnf = nn.LayerNorm(DM); s.head = nn.Linear(DM, NVh)
            def forward(s, w):
                x = s.emb(w)
                for l in s.layers: x = l(x)
                return s.head(s.lnf(x))
        m = LM().to(dev); m.load_state_dict(sd); m.eval(); log(f"HSSM scorer {mp[0]}: width {DM}, {NLy} layers")
        return dict(m=m, VV=VVh, NV=NVh, topw=np.r_[topw, UNK].astype(np.int64), vid=torch.tensor(np.r_[vid, np.full(max(0, (1 << 16) - VVh), NVh - 1)][:1 << 16], device=dev), poo=torch.tensor(np.r_[poo, np.zeros(max(0, (1 << 16) - VVh))][:1 << 16], dtype=torch.float32, device=dev))
    SSMM = _load_hssm(); log(f"HSSM scorer loaded (vocabulary {SSMM['VV']:,})")
def ssm_logprob(text, nx):
    """log p(next word) for candidate words nx under the trained HSSM, given the text so far (last 512 words)"""
    x = torch.tensor([text[-512:]], device=dev).clamp(max=SSMM["VV"] - 1)
    with torch.no_grad(): lp = torch.log_softmax(SSMM["m"](x)[0, -1].float(), 0)
    v_ = SSMM["vid"][nx]; return lp[v_] + torch.where(v_ == SSMM["NV"] - 1, SSMM["poo"][nx], torch.zeros_like(SSMM["poo"][nx]))
def linw_logprob(text, nx):
    """log p(next word) for candidate words nx under the HWORD readout (state of words 3+ back + fitted codes of the last two words)"""
    w = torch.tensor(text[::-1][2:], device=dev); vs = []
    for t in LW["TAUS"]:
        J = min(4 * t, len(w)); j = torch.arange(J, device=dev, dtype=torch.float32); k = ((1 - 1 / t) ** j)[:, None] * torch.exp(1j * j[:, None] * LW["om"][None, :])
        z = (torch.exp(1j * LW["TH"][t][w[:J]]) * k).sum(0); v = torch.cat([z.real, z.imag]); vs.append((v / v.norm().clamp(min=1e-9)).half().float())
    e = []
    for t in (2, 4):
        for w_ in (text[-1], text[-2]): e += [torch.cos(LW["TH"][t][w_]), torch.sin(LW["TH"][t][w_])]
    f = torch.cat(vs + [(torch.cat(e) / 8.0).half().float()]); lp = torch.log_softmax(f @ LW["W"] * 10 + LW["b"], 0)
    v_ = LW["vid"][nx]; return lp[v_] + torch.where(v_ == LW["NV"] - 1, LW["loov"][nx], torch.zeros_like(LW["loov"][nx]))
def lin_logits(text):
    """the HLIN state of the next position (words 3 back and older, full 4 tau kernels), times the readout -> (230,) logits"""
    w = torch.tensor(text[::-1][2:], device=dev); vs = []
    for t in LIN["TAUS"]:
        J = min(4 * t, len(w)); j = torch.arange(J, device=dev, dtype=torch.float32); k = ((1 - 1 / t) ** j)[:, None] * torch.exp(1j * j[:, None] * LIN["om"][None, :])
        z = (torch.exp(1j * LIN["TH"][t][w[:J]]) * k).sum(0); v = torch.cat([z.real, z.imag]); vs.append(v / v.norm().clamp(min=1e-9))
    return (torch.cat(vs).half().float() @ LIN["W"]) * LIN["sc"]
if any(c.get("svd") for c in json.loads(os.environ.get("G1_ARMS", "{}")).values()):
    import scipy.sparse as sp
    from scipy.sparse.linalg import svds
    SVDTH = {}
    def _ph(U):
        U = U / np.maximum(np.linalg.norm(U, axis=1, keepdims=True), 1e-12); th = np.arctan2(U[:, 1::2], U[:, 0::2]); dead = np.linalg.norm(U, axis=1) < 1e-9
        th[dead] = np.random.default_rng(7).random((dead.sum(), th.shape[1])) * 2 * np.pi; return th
    NEED = {(c.get("svdsrc", "mt"), int(c.get("D", 64))) for c in json.loads(os.environ.get("G1_ARMS", "{}")).values() if c.get("svd")}
    for src, Dp in sorted(NEED):                                                                                # phases per (fit text, phase count): mt = MT 27M training text, all = whole training stream
        _sc = os.environ.get("G1_SVDCACHE")                                                                      # disk cache of the fitted phases (same text, same D) -> skips minutes of SVD per run
        _scf = f"{_sc}_{src}_D{Dp}_n{ntr0 if src == 'mt' else ntr}.npz" if _sc else None
        if _scf and os.path.exists(_scf):
            _z = np.load(_scf); SVDTH[(src, Dp)] = {int(k[3:]): torch.tensor(_z[k], device=dev) for k in _z.files}; log(f"SVD phases {src} D{Dp} from cache {_scf}"); continue
        Str_ = (S[:ntr0] if src == "mt" else S[:ntr]).astype(np.int64); TH_ = {}
        for tau in (2, 4, 8, 16, 32, 64, 128):
            lam = 1 - 1 / tau
            if tau <= 4:
                M = None
                for j in range(1, (2 if tau == 2 else 4) + 1):
                    u, n = np.unique(Str_[:-j] * VV + Str_[j:], return_counts=True); m = sp.csr_matrix((n * lam ** (j - 1), (u // VV, u % VV)), shape=(VV, VV)); M = m if M is None else M + m; del u, n
                M = M.sqrt(); r = np.asarray(M.sum(1)).ravel(); c_ = np.asarray(M.sum(0)).ravel(); Mt = sp.diags(1 / np.sqrt(np.maximum(r, 1e-12))) @ M @ sp.diags(1 / np.sqrt(np.maximum(c_, 1e-12)))
                U, s_, Vt = svds(Mt.astype(np.float64), k=2 * Dp); V_ = U * s_[None]
            else:
                n_ = len(Str_) // tau; cap = 4_000_000                                                                       # svds keeps a dense basis of rows x ~2k floats: cap rows (memory and LAPACK limit)
                if n_ > cap: keep_ = np.sort(np.random.default_rng(11).choice(n_, cap, replace=False)); log(f"LSA tau {tau}: {cap:,} of {n_:,} chunks sampled")
                else: keep_ = np.arange(n_)
                idx_ = (keep_[:, None] * tau + np.arange(tau)[None]).ravel(); n_ = len(keep_)
                X = sp.csr_matrix((np.ones(n_ * tau, np.float32), (np.repeat(np.arange(n_, dtype=np.int32), tau), Str_[idx_].astype(np.int32))), shape=(n_, VV)); del idx_; X.sum_duplicates(); X.data = np.sqrt(X.data)   # 32-bit to fit 191M
                c_ = np.asarray(X.sum(0)).ravel(); X = (X @ sp.diags((1 / np.sqrt(np.maximum(c_, 1e-12))).astype(np.float32))).astype(np.float32); U, s_, Vt = svds(X, k=2 * Dp); V_ = (Vt.T * s_[None]).astype(np.float64); del X
            TH_[tau] = torch.tensor(_ph(V_), dtype=torch.float32, device=dev); log(f"SVD phases {src} D{Dp} tau {tau}")
        SVDTH[(src, Dp)] = TH_; del Str_
        if _scf: np.savez(_scf, **{f"tau{t}": v.cpu().numpy() for t, v in TH_.items()}); log(f"SVD phases saved to {_scf}")
class Harm:                                                                                                    # harmonic state (from the HSWEEP kernels): damped oscillator bands over the last WIN symbols
    def __init__(s, cfg):
        s.cfg = cfg; g = torch.Generator().manual_seed(1); D = cfg.get("D", 64); s.WIN = cfg.get("WIN", 64); nsym = VV if cfg.get("symbol", "class") == "word" else int(FINE.max()) + 1
        s.theta = (torch.rand(nsym, D, generator=g) * 2 * math.pi).to(dev); no = int(round(D * cfg.get("order", 0.5))); s.omega = torch.cat([torch.zeros(D - no), torch.rand(no, generator=g) * 2 * math.pi]).to(dev)
        j = torch.arange(s.WIN, dtype=torch.float32, device=dev); s.bands = cfg.get("bands", (2, 4, 8, 16, 32, 64, 128)); s.W = torch.stack([(1 - 1 / t) ** j for t in s.bands]); s.rot = torch.exp(1j * j[:, None] * s.omega[None, :])
    def enc(s, w):
        sym = torch.where(w >= 0, w, torch.zeros_like(w)); sym = sym if s.cfg.get("symbol", "class") == "word" else FINE[sym]
        if s.cfg.get("svd"): TH_ = SVDTH[(s.cfg.get("svdsrc", "mt"), int(s.cfg.get("D", 64)))]; zz = torch.stack([((torch.exp(1j * TH_[t][sym]) * s.rot[None] * (w >= 0)[:, :, None]) * s.W[b].to(torch.complex64)[None, :, None]).sum(1) for b, t in enumerate(s.bands)], 1)
        else: u = torch.exp(1j * s.theta[sym]) * s.rot[None] * (w >= 0)[:, :, None]; zz = torch.einsum("njd,bj->nbd", u, s.W.to(u.dtype))
        v = torch.cat([zz.real, zz.imag], 2); v = v / v.norm(dim=2, keepdim=True).clamp(min=1e-9); return v.reshape(len(w), -1) / math.sqrt(v.shape[1])
def inT(n, rows):
    """which rows (word n-grams) occur in the training stream"""
    Wt = WT[n]; hv = hn(rows); return Wt[np.minimum(np.searchsorted(Wt, hv), len(Wt) - 1)] == hv
def inH8(rows):
    hv = hn(rows); return H8[np.minimum(np.searchsorted(H8, hv), len(H8) - 1)] == hv
def class_ok(ctx4, nx, eps):
    uf, nf, uc, nc = TB[4]; c4 = 0
    for x_ in ctx4: c4 = (c4 << 6) | int(BCL[x_])
    k5c = (np.uint64(c4) << np.uint64(6)) | BCLu[nx].astype(np.uint64); j = np.minimum(np.searchsorted(uf, k5c), len(uf) - 1); n5 = np.where(uf[j] == k5c, nf[j], 0)
    jc = min(int(np.searchsorted(uc, np.uint64(c4))), len(uc) - 1); n4 = int(nc[jc]) if uc[jc] == np.uint64(c4) else 0; return n5 >= eps * max(n4, 1)
NG5 = None
if any(c.get("accept") or c.get("flag") or c.get("crit") or c.get("block") or c.get("cdiff") for c in json.loads(os.environ.get("G1_ARMS", "{}")).values()):                                     # interpolated absolute-discount 5-gram model over the training text (whole-text scorer)
    NG5 = {"c1": np.bincount(S[:ntr].astype(np.int64), minlength=VV).astype(np.float64)}; NG5["N"] = NG5["c1"].sum()
    with np.errstate(over="ignore"):
        hc = S[:ntr].astype(np.uint64) + np.uint64(1)                                                          # hash of the 1-word context at each position
        for n in range(2, 6):
            L_ = ntr - n + 1; hcn = hc[:L_]; hf = hcn * M64 + S[n - 1:ntr].astype(np.uint64) + np.uint64(1)
            uf, idx, nf = np.unique(hf, return_index=True, return_counts=True); uc, t = np.unique(hcn[idx], return_counts=True)
            NG5[n] = (uf, nf.astype(np.float64)); NG5[f"t{n}"] = (uc, t.astype(np.float64)); hc = hf[:ntr - n]; log(f"5-gram scorer: order {n}, {len(uf):,} n-grams")
    del hc, hf
def _look(tab, x):
    k, v = tab; i = np.minimum(np.searchsorted(k, x), len(k) - 1); return np.where(k[i] == x, v[i], 0.0)
def ng5_logp(ctx, w):
    """log p(w | last 4 words of ctx) under the interpolated absolute-discount 5-gram model; ctx (m, 4) int, w (m,) int"""
    D = 0.75; p = (NG5["c1"][w] + 0.5) / (NG5["N"] + 0.5 * VV)
    with np.errstate(over="ignore"):
        for n in range(2, 6):                                                                                  # context = the last n-1 words, hashed oldest first
            hh = np.zeros(len(w), np.uint64)
            for j in range(5 - n, 4): hh = hh * M64 + ctx[:, j].astype(np.uint64) + np.uint64(1)
            ch = NG5["c1"][ctx[:, 3]] if n == 2 else _look(NG5[n - 1], hh)
            cw = _look(NG5[n], hh * M64 + w.astype(np.uint64) + np.uint64(1)); t = _look(NG5[f"t{n}"], hh)
            p = np.where(ch > 0, np.maximum(cw - D, 0) / np.maximum(ch, 1) + D * t / np.maximum(ch, 1) * p, p)
    return np.log(np.maximum(p, 1e-300))
def ng5_terms(text, js):
    """log p(text[j] | text[j-4:j]) for each j in js"""
    js = np.array([j for j in js if 4 <= j < len(text)]);
    if len(js) == 0: return 0.0
    ctx = np.array([text[j - 4:j] for j in js]); return ng5_logp(ctx, np.array([text[j] for j in js]))
CRITM = None
if any(c.get("crit") for c in json.loads(os.environ.get("G1_ARMS", "{}")).values()):                                                                 # HREV: frozen human-likeness critic (CRIT's RES+NG5 readout)
    _c = np.load(os.environ.get("G1_CRIT", "sieve_crit.npz")); _d = torch.load(os.environ.get("G1_CRITPH", "hlin_readout.pt"), map_location="cpu")
    CRITM = dict(mu=_c["mu"], sd=_c["sd"], w=_c["coef"], b=float(_c["b"]), om=_d["omega"].numpy().astype(np.float64), TAUS=[int(t) for t in _d["TAUS"]], TH={int(t): v.numpy().astype(np.float64) for t, v in _d["TH"].items()},
                 lu=np.log((NG5["c1"] + 0.5) / (NG5["N"] + 0.5 * VV))); log("human-likeness critic loaded")
def crit_score(w, edge):
    """critic log-odds that sentence w (word ids) is human-written; features exactly as sieve_crit.py"""
    w = np.asarray(w, np.int64)
    if len(w) == 0: return 0.0
    D = 0.75; tm = np.zeros(len(w)); c1_, N_ = NG5["c1"], NG5["N"]
    with np.errstate(over="ignore"):
        for j in range(len(w)):
            p = (c1_[w[j]] + 0.5) / (N_ + 0.5 * VV)
            for n in range(2, min(5, j + 1) + 1):
                hh = np.uint64(0)
                for x in w[j - n + 1:j]: hh = hh * M64 + np.uint64(x) + np.uint64(1)
                ch = c1_[w[j - 1]] if n == 2 else _look(NG5[n - 1], np.array([hh]))[0]
                cw = _look(NG5[n], np.array([hh * M64 + np.uint64(w[j]) + np.uint64(1)]))[0]; t = _look(NG5[f"t{n}"], np.array([hh]))[0]
                if ch > 0: p = max(cw - D, 0) / ch + D * t / ch * p
            tm[j] = np.log(p)
    fn = [tm.sum(), tm.mean(), tm.min(), (tm.sum() - CRITM["lu"][w].sum()) / len(w), len(w), float(edge), np.log1p(len(w))]; v = []
    for seq in (w[::-1], w):
        j = np.arange(len(seq))[:, None]
        for t in CRITM["TAUS"]:
            zz = (((1 - 1 / t) ** j) * np.exp(1j * (CRITM["TH"][t][np.minimum(seq, len(CRITM["TH"][t]) - 1)] + j * CRITM["om"][None]))).sum(0); vv = np.r_[zz.real, zz.imag]; v.append(vv / max(np.linalg.norm(vv), 1e-9))
    x = (np.r_[np.concatenate(v), fn] - CRITM["mu"]) / CRITM["sd"]; return float(x @ CRITM["w"] + CRITM["b"])
def sent_span(text, i):
    a = i
    while a > LP and text[a - 1] != 0: a -= 1
    b = i
    while b < len(text) and text[b] != 0: b += 1
    return a, b, (a == LP) or (b == len(text))
def text_crit(ids):
    """mean critic log-odds over the sentences of a generated passage (split at sentence ends, as the raters see them)"""
    sents, cur = [], []
    for x in ids:
        if x == 0:
            if cur: sents.append(cur)
            cur = []
        else: cur.append(x)
    if cur: sents.append(cur)
    return float(np.mean([crit_score(s_, k == 0 or k == len(sents) - 1) for k, s_ in enumerate(sents)])) if sents else 0.0
MWSTAT = [0, 0]; GSTAT = []; G5STAT = []; EDITS = []; SYMST = [0, 0]; DRIFT = [0, 0]; TRACE = int(os.environ.get("G1_TRACE", 0)); TRL = []; TR_ADD = None; HTRACE = bool(os.environ.get("G1_HTRACE")); HTRACE_STEPS = {0, 1, 2, 10, 25}; HTL = []
def mw_step(text, rng, cfg):
    """MW: the HSSM model proposes (temperature, top-p over the frequent words), the count tables veto"""
    x = torch.tensor([text[-512:]], device=dev).clamp(max=SSMM["VV"] - 1)
    with torch.no_grad(): pr = torch.softmax(SSMM["m"](x)[0, -1].float() / cfg.get("temp", 0.8), 0).cpu().numpy().astype(np.float64)
    pr[SSMM["NV"] - 1] = 0; o = np.argsort(-pr); cs = np.cumsum(pr[o]) / pr.sum(); keep = o[:int(np.searchsorted(cs, cfg.get("topp", 0.9))) + 1]
    nx = SSMM["topw"][keep]; q = pr[keep]; ok_ = nx != UNK
    ok_ &= class_ok(text[-4:], nx, cfg.get("eps", 0.03)); ok_ &= inT(3, np.c_[np.repeat(np.array([text[-2:]]), len(nx), 0), nx])
    ok_ &= ~inH8(np.c_[np.repeat(np.array([text[-7:]]), len(nx), 0), nx]); seen = {tuple(text[i:i + 3]) for i in range(len(text) - 2)}
    ok_ &= np.array([(text[-2], text[-1], int(x_)) not in seen for x_ in nx])
    MWSTAT[0] += 1; MWSTAT[1] += float(ok_.any())
    if ok_.any(): q = q * ok_
    return int(nx[rng.choice(len(nx), p=q / q.sum())])
def cd_fill(text, i, masked, rng, cfg):
    """two-sided count denoiser: candidates matching the left 4 words, scored by left match + right match (masked words are wildcards)"""
    h = text[:i][::-1][:8]; c, ok = cands(np.array([h[:4]]), np.array([h[4:8]])); c = c[0][ok[0]]
    if len(c) == 0: return None, -1.0
    m4 = (St[(c[:, None] - 1 - torch.arange(4, device=dev)).clamp(min=0)].long() == torch.tensor([h[:4]], device=dev)).float().sum(1).cpu().numpy(); nx = St[c].long().cpu().numpy().astype(np.int64)
    r = np.zeros(len(c)); alive = np.ones(len(c), bool); cc = c.cpu().numpy() if hasattr(c, "cpu") else c
    for d in (1, 2):
        if i + d >= len(text) or (i + d) in masked: break
        nxt = St[torch.as_tensor(np.minimum(cc + d, len(St) - 1), device=dev)].long().cpu().numpy(); alive &= nxt == text[i + d]; r += alive
    t = text[:i]; bad = (nx == UNK) | inH8(np.c_[np.repeat(np.array([t[-7:]]), len(nx), 0), nx]); seen = {tuple(text[j:j + 3]) for j in range(len(text) - 2) if not (i - 2 <= j <= i)}
    for d in range(3):
        if i - d >= 0 and i - d + 3 <= len(text):
            t3 = np.repeat(np.array([text[i - d:i - d + 3]]), len(nx), 0); t3[:, d] = nx; bad |= np.array([tuple(x_) in seen for x_ in t3.tolist()])
    for a in range(max(0, i - 7), min(i, len(text) - 8) + 1):
        win = np.repeat(np.array([text[a:a + 8]]), len(nx), 0); win[:, i - a] = nx; bad |= inH8(win)
    sc = 8.0 * m4 + 8.0 * r; w = np.exp(sc - sc.max()) * ~bad
    if w.sum() <= 0: return None, -1.0
    uw, inv = np.unique(nx, return_inverse=True); ww = np.bincount(inv, weights=w) ** cfg.get("pow", 6.0)
    return int(uw[rng.choice(len(uw), p=ww / ww.sum())]), float((sc * ~bad).max())
def count_diffuse(text, rng, cfg):
    """CDIFF: mask the weakest share of generated words (schedule), refill in order of confidence with the two-sided count denoiser"""
    draft = list(text)
    for frac in cfg["cdiff"]:
        pos = list(range(LP, len(text))); con = np.array([float(np.sum(ng5_terms(text, range(i, i + 5)))) for i in pos])
        masked = set(np.array(pos)[np.argsort(con)[:max(1, int(round(frac * len(pos))))]].tolist())
        conf = {i: cd_fill(text, i, masked, np.random.default_rng(0), cfg)[1] for i in masked}                # fill order: most confident first
        for i in sorted(masked, key=lambda k: -conf[k]):
            masked.discard(i); new, _ = cd_fill(text, i, masked, rng, cfg)
            if new is None or new == text[i]: continue
            if cfg.get("cacc"):
                js = range(i, min(i + 5, len(text))); before = float(np.sum(ng5_terms(text, js))); old = text[i]; text[i] = new
                if float(np.sum(ng5_terms(text, js))) < before: text[i] = old
            else: text[i] = new
    GSTAT.append(sum(a != b for a, b in zip(text[LP:], draft[LP:])) / max(len(text) - LP, 1)); return text
def span_propose(text, i, sl, rng, cfg):
    """regenerate text[i:i+sl] left to right with the collage's candidate step (left context only); guards as in decoding"""
    t = text[:i]; new = []
    for k in range(sl):
        h = t[::-1][:8]; c, ok = cands(np.array([h[:4]]), np.array([h[4:8]])); c = c[0][ok[0]]
        if len(c) == 0: return None
        m4 = (St[(c[:, None] - 1 - torch.arange(4, device=dev)).clamp(min=0)].long() == torch.tensor([h[:4]], device=dev)).float().sum(1).cpu().numpy(); nx = St[c].long().cpu().numpy().astype(np.int64)
        bad = (nx == UNK) | inH8(np.c_[np.repeat(np.array([t[-7:]]), len(nx), 0), nx]); seen = {tuple(t[j:j + 3]) for j in range(len(t) - 2)}; bad |= np.array([(t[-2], t[-1], int(x_)) in seen for x_ in nx])
        w = np.exp(8.0 * (m4 - m4.max())) * ~bad
        if w.sum() <= 0: return None
        uw, inv = np.unique(nx, return_inverse=True); ww = np.bincount(inv, weights=w) ** cfg.get("pow", 6.0); x_ = int(uw[rng.choice(len(uw), p=ww / ww.sum())]); t = t + [x_]; new.append(x_)
    full = t + text[i + sl:]
    for a in range(max(0, i - 7), min(i + sl, len(full) - 8) + 1):                                         # copy cap across the right junction too
        if inH8(np.array([full[a:a + 8]]))[0]: return None
    return new
def gibbs_block(text, rng, cfg):
    """GIBBS3: blocked Metropolis revision with simulated annealing on the whole-text 5-gram score"""
    G = [0, 0]; draft = list(text); nsw = int(cfg["block"]); T0, T1 = cfg.get("T0", 0.0), cfg.get("T1", 0.0)
    for sw in range(nsw):
        T = T0 * (T1 / T0) ** (sw / max(nsw - 1, 1)) if T0 > 0 else 0.0
        pos = list(range(LP, len(text)))
        con = np.array([float(np.sum(ng5_terms(text, range(i, i + 5)))) for i in pos]); pos = sorted(np.array(pos)[np.argsort(con)[:max(1, int(round(cfg.get("flag", 0.3) * len(con))))]].tolist())
        for i in pos:
            sl = int(rng.integers(1, 4)); sl = min(sl, len(text) - i)
            new = span_propose(text, i, sl, rng, cfg); G[0] += 1
            if new is None or new == text[i:i + sl]: continue
            js = range(i, min(i + sl + 4, len(text))); before = float(np.sum(ng5_terms(text, js))); old = text[i:i + sl]; text[i:i + sl] = new; after = float(np.sum(ng5_terms(text, js)))
            d = after - before
            if d > 0 or (T > 0 and rng.random() < np.exp(d / T)):
                G[1] += sum(a != b for a, b in zip(new, old)); w0, w1 = max(LP, i - 10), min(len(text), i + sl + 10)
                EDITS.append(dict(d=float(d), T=float(T), sweep=sw, before=list(text[w0:i]) + old + list(text[i + sl:w1]), after=list(text[w0:w1])))
            else: text[i:i + sl] = old
    GSTAT.append(sum(a != b for a, b in zip(text[LP:], draft[LP:])) / max(len(text) - LP, 1)); return text
def gibbs(text, rng, cfg):
    """revision sweeps over the generated words: re-choose each word given 4 words left (collage candidates) and up to 2 words right (training n-grams)"""
    G = [0, 0]
    for sw in range(int(cfg["gibbs"])):
        pos = range(LP, len(text))
        if cfg.get("flag"):                                                                                    # only the weakest generated words (lowest 5-gram contribution of the terms they touch)
            con = np.array([float(np.sum(ng5_terms(text, range(i, i + 5)))) for i in pos]); pos = sorted(np.array(list(pos))[np.argsort(con)[:max(1, int(round(cfg["flag"] * len(con))))]].tolist())
        for i in pos:
            h = text[:i][::-1][:8]; c, ok = cands(np.array([h[:4]]), np.array([h[4:8]])); c = c[0][ok[0]]
            if len(c) == 0: continue
            m4 = (St[(c[:, None] - 1 - torch.arange(4, device=dev)).clamp(min=0)].long() == torch.tensor([h[:4]], device=dev)).float().sum(1).cpu().numpy(); nx = St[c].long().cpu().numpy()
            nx = np.r_[nx, text[i]].astype(np.int64); m4 = np.r_[m4, 4.0]; R = text[i + 1:i + 3]; L2 = text[i - 2:i]; n_ = len(nx)
            sc = 8.0 * m4
            if len(R) == 2:
                sc += 8.0 * inT(3, np.c_[nx, np.repeat(np.array([R]), n_, 0)]) + 8.0 * inT(5, np.c_[np.repeat(np.array([L2]), n_, 0), nx, np.repeat(np.array([R]), n_, 0)])
            if len(R) >= 1:
                sc += 8.0 * inT(3, np.c_[np.repeat(np.array([L2[-1:]]), n_, 0), nx, np.repeat(np.array([R[:1]]), n_, 0)])
            bad = nx == UNK
            for a in range(max(0, i - 7), min(i, len(text) - 8) + 1):                                         # copy cap on every 8-word window containing position i
                win = np.repeat(np.array([text[a:a + 8]]), n_, 0); win[:, i - a] = nx; bad |= inH8(win)
            st_ = {tuple(text[j:j + 3]) for j in range(len(text) - 2) if not (i - 2 <= j <= i)}
            for d in range(3):
                if i - d >= 0 and i - d + 3 <= len(text):
                    t3 = np.repeat(np.array([text[i - d:i - d + 3]]), n_, 0); t3[:, d] = nx; bad |= np.array([tuple(r) in st_ for r in t3.tolist()])
            w = np.exp(sc - sc.max()) * ~bad
            if w.sum() <= 0: continue
            uw, inv = np.unique(nx, return_inverse=True); ww = np.bincount(inv, weights=w) ** cfg.get("ppow", cfg.get("pow", 6.0))
            if cfg.get("ppow") is not None and text[i] in uw: ww[np.searchsorted(uw, text[i])] = 0                      # HREV: propose a different word (the critic decides)
            if ww.sum() <= 0: continue
            new = int(uw[rng.choice(len(uw), p=ww / ww.sum())])
            if cfg.get("crit") and new != text[i]:                                                                # HREV: keep only if the critic finds the sentence more human-like; sentence ends fixed
                if new == 0 or text[i] == 0: new = text[i]
                else:
                    a_, b_, e_ = sent_span(text, i); old = text[i]; before = crit_score(text[a_:b_], e_); text[i] = new; after = crit_score(text[a_:b_], e_); text[i] = old
                    if after <= before: new = old
            if cfg.get("accept") and new != text[i]:                                                              # keep only if the whole-text 5-gram log probability rises (terms i..i+4)
                old = text[i]; before = float(np.sum(ng5_terms(text, range(i, i + 5)))); text[i] = new; after = float(np.sum(ng5_terms(text, range(i, i + 5)))); text[i] = old
                if after <= before: new = old
            G[0] += 1; G[1] += new != text[i]; text[i] = new
    GSTAT.append(G[1] / max(G[0], 1)); return text
def plag(ids):
    """share of the 8-grams of the generated words found in training, and the longest chain of consecutive found 8-grams (as a span length)"""
    if len(ids) < 8: return 0.0, 0, 0.0
    f = inT(5, np.array([ids[i:i + 5] for i in range(len(ids) - 4)])); best = run = 0
    for x_ in f: run = run + 1 if x_ else 0; best = max(best, run)
    return float(f.mean()), (4 + best) if best else 0, float(inH8(np.array([ids[i:i + 8] for i in range(len(ids) - 7)])).mean())
SYMP_ = None
if any(c.get("sym") for c in json.loads(os.environ.get("G1_ARMS", "{}")).values()):                                                                  # SYM: NN-free reader (PARSE's tagger + parser), discourse state, planner, realiser constraints
    _ud = os.environ.get("G1_UD", "mtest/ud"); _src = open(os.environ.get("G1_PARSEPY", "sieve_parse.py"), encoding="utf-8").read().split("# ---- sanity")[0].replace('"mtest/ud/', '_UD + "/')
    SYMP_ = {"_UD": _ud, "__name__": "symparse"}; exec(_src, SYMP_); log("SYM reader (tagger + parser) loaded")
    PRONG = {w: g for g, ws in dict(HE="he him his himself", SHE="she her hers herself", THEY="they them their theirs themselves", IT="it its itself", I="i me my mine myself", YOU="you your yours yourself", WE="we us our ours ourselves").items() for w in ws.split()}
    SUBJ = dict(HE="he", SHE="she", THEY="they", IT="it", I="i", YOU="you", WE="we")
    _wid = {w: i for i, w in enumerate(vw) if w is not None}
    _ptag = SYMP_["ti"]["PROPN"]; _cw = SYMP_["cw"]
    ISPROPN = np.zeros(VV, bool)
    for w, i in _wid.items():
        if w.lower() in _cw and max(range(len(SYMP_["TAGS"])), key=lambda k: _cw[w.lower()][k]) == _ptag: ISPROPN[i] = True
    log(f"SYM: {int(ISPROPN.sum()):,} vocabulary words mostly tagged PROPN in EWT")
FHC = None
if any(c.get("fhrr") for c in json.loads(os.environ.get("G1_ARMS", "{}")).values()):                                                                 # FHRR: harmonic state as phasor-bound roles (who did what), sieve_lang_prereg.md FHRR
    _tw = np.full(VV, SYMP_["ti"]["NOUN"])
    for w__, i__ in _wid.items():
        if w__.lower() in _cw: _tw[i__] = max(range(len(SYMP_["TAGS"])), key=lambda k: _cw[w__.lower()][k])
    FH_NOM = np.isin(_tw, [SYMP_["ti"][t_] for t_ in ("NOUN", "PROPN", "PRON")]); FH_VRB = _tw == SYMP_["ti"]["VERB"]
    FH_ATOM = np.arange(VV)
    for w__, g__ in {w: g for g, ws in dict(he="he him his himself", she="she her hers herself", they="they them their theirs themselves", it="it its itself", i="i me my mine myself", you="you your yours yourself", we="we us our ours ourselves").items() for w in ws.split()}.items():
        if w__ in _wid and g__ in _wid: FH_ATOM[_wid[w__]] = _wid[g__]
    def fh_roles(ids):
        """vectorised role rule: 1 SUBJ (nominal before the sentence's first verb), 2 OBJ (after), 3 VERB; vsub = atom of the verb's subject (-1)"""
        ids = np.asarray(ids, np.int64); n = len(ids); idx = np.arange(n); sid = np.cumsum(ids == 0)
        starts = np.r_[0, np.nonzero(np.diff(sid))[0] + 1]; isv = FH_VRB[ids] & (ids != 0)
        fv = np.minimum.reduceat(np.where(isv, idx, n), starts)[sid - sid[0]]
        nom = FH_NOM[ids] & (ids != 0); role = np.where(nom & (idx < fv), 1, np.where(nom & (idx > fv), 2, np.where(isv, 3, 0))).astype(np.int8)
        last = np.maximum.accumulate(np.where(role == 1, idx, -1)); okk = (last >= 0) & (sid[np.maximum(last, 0)] == sid)
        return role, np.where((role == 3) & okk, FH_ATOM[ids[np.maximum(last, 0)]], -1).astype(np.int32)
    _r, _v = fh_roles(S[:ntr]); FHC = dict(role=torch.tensor(_r, device=dev), vsub=torch.tensor(_v, device=dev), atom=torch.tensor(FH_ATOM, device=dev))
    _rg = np.random.default_rng(3); FHC["rph"] = torch.tensor(np.stack([np.zeros(64)] + [_rg.random(64) * 2 * np.pi for _ in range(3)]), dtype=torch.float32, device=dev)   # role phases (none, SUBJ, OBJ, VERB)
    _rg = np.random.default_rng(5); FHC["rid"] = torch.tensor(_rg.random((VV, 256)) * 2 * np.pi, dtype=torch.float32, device=dev)            # identity band: random near-orthogonal atoms (Test A diagnostic)
    FHC["rph2"] = torch.tensor(np.stack([np.zeros(256)] + [_rg.random(256) * 2 * np.pi for _ in range(3)]), dtype=torch.float32, device=dev)
    log(f"FHRR: corpus roles: SUBJ {(_r == 1).mean():.3f}, OBJ {(_r == 2).mean():.3f}, VERB {(_r == 3).mean():.3f}; verbs with a bound subject {(_v >= 0).sum() / max((_r == 3).sum(), 1):.3f}"); del _r, _v
def fh_enc(A, R, Vs, cfg):
    """FHRR state per band (tau 16..128): sum_j lam^j [R>0] exp(i (TH_tau[atom] + role phase + TH_tau[verb's subject])), normalised per band; A, R, Vs (n, WIN), newest first"""
    TH_ = SVDTH[(cfg.get("svdsrc", "mt"), int(cfg.get("D", 64)))]; WIN = A.shape[1]; j = torch.arange(WIN, dtype=torch.float32, device=dev); out = []
    for t in (16, 32, 64, 128):
        if t == 128: ph = FHC["rid"][FHC["atom"][A]] + FHC["rph2"][R.long()] + torch.where((Vs >= 0)[..., None], FHC["rid"][Vs.clamp(min=0).long()], torch.zeros(1, device=dev))   # identity band
        else: ph = TH_[t][FHC["atom"][A]] + FHC["rph"][R.long()] + torch.where((Vs >= 0)[..., None], TH_[t][Vs.clamp(min=0).long()], torch.zeros(1, device=dev))
        wgt = ((1 - 1 / t) ** j)[None, :] * (R > 0).float(); zz = (wgt[..., None] * torch.exp(1j * ph)).sum(1); v = torch.cat([zz.real, zz.imag], 1); out.append(v / v.norm(dim=1, keepdim=True).clamp(min=1e-9))
    return torch.cat(out, 1) / 2.0
_PP = {}
def plan_positions(prev, w):
    """training positions p (p >= 200) with S[p] == w and S[p-1] == prev (cached)"""
    k = (prev, w)
    if k not in _PP:
        P_ = np.nonzero(S[200:ntr] == w)[0] + 200; _PP[k] = P_[S[P_ - 1] == prev]
    return _PP[k]
EVC = None
if any("v" in str(c.get("sym", "")) for c in json.loads(os.environ.get("G1_ARMS", "{}")).values()):                                                  # SYM3: narrative event chains (Chambers & Jurafsky 2008) from the training text
    GRPS = list(SUBJ); SUBJID = {_wid[SUBJ[g]]: k for k, g in enumerate(GRPS) if SUBJ[g] in _wid}
    AUXW = np.array([_wid[w] for w in "was were is are am be been had has have would could should will shall might may must did do does not then also never only".split() if w in _wid])
    _Str = S[:ntr].astype(np.int64); _pos = np.nonzero(np.isin(_Str[:-3], list(SUBJID)))[0]
    _vt = SYMP_["ti"]["VERB"]; ISVERB = np.zeros(VV, bool)                                                  # verbs = words whose most frequent EWT tag is VERB (Brown verb-like classes also admit prepositions)
    for w__, i__ in _wid.items():
        if w__.lower() in _cw and max(range(len(SYMP_["TAGS"])), key=lambda k: _cw[w__.lower()][k]) == _vt: ISVERB[i__] = True
    def _vl(w): return ISVERB[np.minimum(w, VV - 1)] & ~np.isin(w, AUXW) & (w != 0)
    w1, w2, w3 = _Str[_pos + 1], _Str[_pos + 2], _Str[_pos + 3]; a1, a2 = np.isin(w1, AUXW), np.isin(w2, AUXW)
    _verb = np.where(_vl(w1), w1, np.where(a1 & _vl(w2), w2, np.where(a1 & a2 & _vl(w3), w3, -1))); _k = _verb >= 0
    EP, EV, EG = _pos[_k], _verb[_k], np.array([SUBJID[int(x_)] for x_ in _Str[_pos[_k]]])
    PVG = np.zeros((len(GRPS), VV)); _dir = (_verb == w1)[_k]; np.add.at(PVG, (EG[_dir], EV[_dir]), 1.0)          # verb choice only from verbs directly after the pronoun (agreement: "he goes", not "he go")
    keys = []
    for g_ in range(len(GRPS)):
        m_ = EG == g_; p_, v_ = EP[m_], EV[m_]
        for d in range(1, 5):
            if len(p_) <= d: break
            near = (p_[d:] - p_[:-d]) <= 60; keys.append(v_[:-d][near] * VV + v_[d:][near])
    kk = np.concatenate(keys) if keys else np.zeros(0, np.int64); uk, ck = np.unique(kk, return_counts=True); keep = ck >= 3
    uk, ck = uk[keep], ck[keep]; c1v = np.bincount(uk // VV, weights=ck, minlength=VV); c2v = np.bincount(uk % VV, weights=ck, minlength=VV); NPv = ck.sum()
    EVC = dict(PVG=PVG, uk=uk, pmi=np.log(ck * NPv / np.maximum(c1v[uk // VV] * c2v[uk % VV], 1)))
    log(f"SYM3 events: {len(EP):,} (pronoun subject, verb) events; {len(uk):,} verb pairs with PMI")
def ev_pmi(v1, v2s):
    k_ = v1 * VV + np.asarray(v2s); i_ = np.minimum(np.searchsorted(EVC["uk"], k_), len(EVC["uk"]) - 1); return np.where(EVC["uk"][i_] == k_, EVC["pmi"][i_], 0.0)
def plan_verb(grp, recent, rng):
    """the planned verb for a pronoun-group subject: log P(verb | group) + mean chain PMI with the subject's recent verbs; sample among the top 20"""
    g_ = GRPS.index(grp); pv = EVC["PVG"][g_]; cand = np.argsort(-pv)[:300]; cand = cand[(pv[cand] > 0) & ~np.isin(cand, recent[-3:])]   # no repeat of the subject's last 3 verbs
    if len(cand) == 0: return -1
    sc_ = np.log(pv[cand] / pv.sum())
    if recent: sc_ = sc_ + np.mean([ev_pmi(int(r_), cand) for r_ in recent[-3:]], axis=0)
    top = np.argsort(-sc_)[:20]; pr = np.exp(sc_[top] - sc_[top].max()); return int(cand[top][rng.choice(len(top), p=pr / pr.sum())])
SLEN = None; VOB = None
if any("l" in str(c.get("sym", "")) for c in json.loads(os.environ.get("G1_ARMS", "{}")).values()):                                                  # SENT length plan: human sentence lengths in the training text
    _z0 = np.nonzero(S[:ntr] == 0)[0]; SLEN = np.clip(np.diff(_z0) - 1, 4, 30); SLEN = SLEN[np.diff(_z0) > 1]; log(f"SENT: {len(SLEN):,} sentence lengths, mean {SLEN.mean():.1f}")
    _tw3 = np.full(VV, -1)
    for w__, i__ in _wid.items():
        if w__.lower() in _cw: _tw3[i__] = max(range(len(SYMP_["TAGS"])), key=lambda k: _cw[w__.lower()][k])
    CLOSE = np.isin(_tw3, [SYMP_["ti"][t_] for t_ in ("NOUN", "PROPN", "PRON", "ADJ", "ADV", "VERB", "NUM")])     # trace fix: a sentence may only end after a word that can close it
    CLOSE[[_wid[w_] for w_ in "the a an his her their my your our its of to in on at by for with from and or but that which who was were is are be been had has have would could should will shall not".split() if w_ in _wid]] = False
if any("o" in str(c.get("sym", "")) for c in json.loads(os.environ.get("G1_ARMS", "{}")).values()) and EVC is not None:                                # SENT object plan: verb -> object counts (first noun / object pronoun within 3 words, only fillers between)
    _Str = S[:ntr].astype(np.int64); _tw2 = np.full(VV, -1)
    for w__, i__ in _wid.items():
        if w__.lower() in _cw: _tw2[i__] = max(range(len(SYMP_["TAGS"])), key=lambda k: _cw[w__.lower()][k])
    _fill = np.isin(_tw2, [SYMP_["ti"][t_] for t_ in ("DET", "ADJ", "NUM")]); _fill[[_wid[w_] for w_ in "his her their my your our its".split() if w_ in _wid]] = True
    _objp = np.zeros(VV, bool); _objp[[_wid[w_] for w_ in "him her them it me us you".split() if w_ in _wid]] = True
    _isobj = (_tw2 == SYMP_["ti"]["NOUN"]) | _objp
    _vp = np.nonzero(ISVERB[np.minimum(_Str[:-4], VV - 1)])[0]; _got = np.zeros(len(_vp), bool); _keys = []
    for d in (1, 2, 3):
        w_ = _Str[_vp + d]; between = np.ones(len(_vp), bool)
        for e in range(1, d): between &= _fill[np.minimum(_Str[_vp + e], VV - 1)]
        hit = ~_got & between & _isobj[np.minimum(w_, VV - 1)]; _keys.append(_Str[_vp[hit]] * VV + w_[hit]); _got |= hit
    VOB = np.unique(np.concatenate(_keys), return_counts=True); log(f"SENT: {len(VOB[0]):,} verb-object pairs from {int(_got.sum()):,} verbs with an object")
OBJF = dict(HE="him", SHE="her", THEY="them", I="me", WE="us", YOU="you")
def plan_object(v, DS_, rng):
    """the planned object of verb v: log P(object | verb) + 1 if it is a discourse referent; never the subject's own pronoun; top 20 softmax"""
    lo, hi = np.searchsorted(VOB[0], v * VV), np.searchsorted(VOB[0], (v + 1) * VV)
    if hi <= lo: return -1
    ob = VOB[0][lo:hi] % VV; cn = VOB[1][lo:hi].astype(float); o_ = np.argsort(-cn)[:300]; ob, cn = ob[o_], cn[o_]
    refs = set()
    for r in DS_.sal:
        if r in OBJF and r != DS_.cbname: refs.add(_wid.get(OBJF[r], -1))
        elif r in _wid: refs.add(_wid[r])
    own = _wid.get(OBJF.get(DS_.cbname, ""), -1); keep = ob != own; ob, cn = ob[keep], cn[keep]
    if len(ob) == 0: return -1
    sc_ = np.log(cn / cn.sum()) + 1.0 * np.isin(ob, list(refs)); top = np.argsort(-sc_)[:20]; pr = np.exp(sc_[top] - sc_[top].max())
    return int(ob[top][rng.choice(len(top), p=pr / pr.sum())])
PUNS = set(',;:!?"()') | {"--", "'"}
PUNID = np.zeros(VV + 2, bool)
for _i, _w in enumerate(vw):
    if _w in PUNS: PUNID[_i] = True
UNITS = bool(os.environ.get("G1_UNITS"))
def nunits(seq): return sum(1 for x_ in seq if not (x_ < len(PUNID) and PUNID[x_])) if UNITS else len(seq)
EXTP_ = None
if os.environ.get("G1_PROMPTS"):                                                                               # PUNC: external shared prompts (mtest/books2_prompts.json; key = corpus)
    _pp = json.load(open(os.environ["G1_PROMPTS"], encoding="utf-8")); _pk = os.environ.get("G1_PKEY", CORPUS)
    EXTP_ = [x[_pk]["prompt"] for x in _pp]; EXTT_ = [x[_pk]["truth"] for x in _pp]
class Disc:
    """DRT-lite discourse state: referents (nouns by word, pronoun groups) with Centering salience"""
    def __init__(s): s.sal = {}; s.last = {}; s.k = 0; s.ev = {}; s.vplan = -1; s.pref = set(); s.pw = 1.0; s.R = []; s.VS = []; s.cbw = -1; s.tlen = 0; s.oplan = -1; s.oage = 0; s.odone = False; s.cbname = None
    def read(s, ids, period=False):
        wsf = [vw[i] if i < len(vw) and vw[i] is not None else "<unk>" for i in ids]; keep_ = [k for k, w in enumerate(wsf) if w not in PUNS]   # PUNC: punctuation tokens are not words for the reader
        ws = [wsf[k] for k in keep_]; RR = [0] * len(wsf); VV_ = [-1] * len(wsf)
        if not ws:
            s.R.extend(RR); s.VS.extend(VV_)
            if period: s.R.append(0); s.VS.append(-1)
            return
        tg, _ = SYMP_["tag"]([w.lower() for w in ws]); _, hd = SYMP_["parse"](tg); TAGS_ = SYMP_["TAGS"]
        for r in s.sal: s.sal[r] *= 0.5
        s.k += 1
        for j, (w, t) in enumerate(zip(ws, tg)):
            T_ = TAGS_[t]
            if T_ in ("NOUN", "PROPN"): r = w
            elif w in PRONG or w.lower() in PRONG: r = PRONG.get(w, PRONG.get(w.lower()))
            else: continue
            h = hd[j]; role = (3.0 if j + 1 < h else 2.0) if h > 0 and TAGS_[tg[h - 1]] in ("VERB", "AUX") else 1.0
            s.sal[r] = s.sal.get(r, 0.0) + role; s.last[r] = s.k
            if role == 3.0 and ws[h - 1] in _wid: s.ev.setdefault(r, []).append(_wid[ws[h - 1]])
        for j, (w, t) in enumerate(zip(ws, tg)):                                                                  # COMB: per-token roles from the parse (1 SUBJ, 2 OBJ, 3 VERB + its subject's atom)
            T_ = TAGS_[t]; h = hd[j]; rc = 0; vs = -1
            if (T_ in ("NOUN", "PROPN", "PRON")) and h > 0 and TAGS_[tg[h - 1]] in ("VERB", "AUX"): rc = 1 if j + 1 < h else 2
            elif T_ == "VERB":
                rc = 3; sj = [k for k in range(j) if hd[k] == j + 1 and TAGS_[tg[k]] in ("NOUN", "PROPN", "PRON")]
                if sj and ws[sj[-1]] in _wid and FHC is not None: vs = int(FH_ATOM[_wid[ws[sj[-1]]]])
            RR[keep_[j]] = rc; VV_[keep_[j]] = vs
        s.R.extend(RR); s.VS.extend(VV_)
        if period: s.R.append(0); s.VS.append(-1)
    useverb = False
    def plan(s, rng=None, ptr=None):
        """Centering: CONTINUE (most salient referent), SHIFT (another referent, by salience) or NEW (no plan), sampled with ptr; default always CONTINUE"""
        if not s.sal: return []
        key_ = lambda r: s.sal[r] * (s.pw if r in s.pref else 1.0)                                                # prompt characters weigh pw times more (they should stay the protagonists)
        cands_ = [r for r in s.sal if r != "IT"]                                                                   # "it" is mostly expletive, never the planned protagonist
        if not cands_: return []
        cb = max(cands_, key=key_)
        if ptr is not None:
            u = rng.random()
            if u >= ptr[0] + ptr[1]: return []
            if u >= ptr[0]:
                oth = [r for r in cands_ if r != cb]
                if not oth: return []
                wv = np.array([key_(r) for r in oth]); cb = oth[int(rng.choice(len(oth), p=wv / wv.sum()))]
        s.vplan = plan_verb(cb, s.ev.get(cb, []), rng) if (EVC is not None and s.useverb and cb in SUBJ and rng is not None) else -1
        s.cbw = _wid.get(SUBJ[cb], _wid.get(SUBJ[cb].capitalize(), -1)) if cb in SUBJ else _wid.get(cb, -1); s.cbname = cb
        if cb in SUBJ: return [_wid.get(SUBJ[cb], _wid.get(SUBJ[cb].capitalize(), -1))]
        if cb[:1].isupper(): return [_wid.get(cb, -1)]                                                             # PUNC: a name, not "the" + name
        return [_wid.get("the", -1), _wid.get(cb, -1)]
    def ref_ids(s):
        out = set()
        for r in s.sal:
            if r in SUBJ: out |= {_wid[w] for w, g in PRONG.items() if g == r and w in _wid}
            elif r in _wid: out.add(_wid[r])
        return out
def generate(cfg, pids):
    global LP
    out = {}; LSTAT.clear()
    for pid in pids:
        t = PROMPTS[pid]; text = S[t:t + LP].astype(np.int64).tolist(); rng = np.random.default_rng(1000 * pid + 7)
        if EXTP_ is not None: text = [int(x_) for x_ in EXTP_[pid]]; LP = len(text)
        if cfg.get("sym"):                                                                                   # read the prompt sentence by sentence
            DS = Disc(); DS.useverb = "v" in cfg["sym"]; cur = []
            for x_ in text:
                if x_ == 0: DS.read(cur, period=True); cur = []
                else: cur.append(x_)
            if cur: DS.read(cur)
            DS.pref = set(DS.sal); DS.pw = float(cfg.get("pw", 1.0))
            PLAN = DS.plan(rng, cfg.get("ptr")) if text[-1] == 0 else []; REFS = DS.ref_ids(); SYMST[0] += 1
            if SLEN is not None and "l" in cfg["sym"]: DS.tlen = int(SLEN[rng.integers(len(SLEN))])
            DS.oplan = -1; DS.odone = False
            if TRACE and pid < TRACE: TRL.append(f"   [prompt state p{pid}] top referents: {sorted(DS.sal.items(), key=lambda x: -x[1])[:5]}")
        while nunits(text[LP:]) < LG:
            if cfg.get("gen") == "ssm": text.append(mw_step(text, rng, cfg)); continue
            h = text[::-1][:8]; Qw = torch.tensor([h], device=dev); c, ok = cands(np.array([h[:4]]), np.array([h[4:8]]))
            if cfg.get("hr"):                                                                                    # harmonic retrieval: widen the pool with a sample of all positions sharing the last hr words
                q4 = int(pack(np.array([h[:4]]))[0]); sh_ = 16 * (4 - int(cfg["hr"])); lo_k = (q4 >> sh_) << sh_; hi_k = lo_k + (1 << sh_)
                lo = int(np.searchsorted(KEYS, np.uint64(lo_k))); hi = int(np.searchsorted(KEYS, np.uint64(hi_k - 1), side="right"))
                if hi - lo > K:
                    HG.manual_seed(len(text) * 7919 + int(q4 % 1000003)); extra = torch.randint(lo, hi, (min(int(cfg.get("hrn", 16384)), hi - lo),), generator=HG, device="cpu").to(dev)
                    pos = torch.unique(torch.cat([c[0][ok[0]], ORD[extra].long()])); c = pos[None]; ok = torch.ones_like(c, dtype=torch.bool)
            if cfg.get("sym") and "f" in cfg["sym"] and PLAN:                                                       # SYM2 fix 2: if no candidate carries the planned word, add book positions that start a sentence with it
                lbq = len(text) - 1 - text[::-1].index(0) if 0 in text else None; kq = len(text) - 1 - lbq if lbq is not None else 99
                if kq < len(PLAN) and PLAN[kq] >= 0 and not bool((St[c[0]][ok[0]] == PLAN[kq]).any()):
                    prev = 0 if kq == 0 else PLAN[kq - 1]; ex = plan_positions(prev, PLAN[kq])
                    if len(ex):
                        HG.manual_seed(len(text) * 7919 + PLAN[kq]); ex = ex[torch.randperm(len(ex), generator=HG)[:256].numpy()]
                        c = torch.cat([c[0][ok[0]], torch.tensor(ex, device=dev).long()])[None]; ok = torch.ones_like(c, dtype=torch.bool); SYMST[1] += 1
            VP_ = -1
            if cfg.get("sym") and "v" in cfg["sym"] and DS.vplan >= 0 and PLAN and DS.vplan not in text[-2:]:      # SYM3: realise the planned verb at word 2, or word 3 after an auxiliary
                lbv = len(text) - 1 - text[::-1].index(0) if 0 in text else None; kv = len(text) - 1 - lbv if lbv is not None else 99
                if kv == 1 or (kv == 2 and text[-1] in set(AUXW.tolist())):
                    VP_ = DS.vplan
                    if not bool((St[c[0]][ok[0]] == VP_).any()):
                        ex = plan_positions(text[-1], VP_)
                        if len(ex):
                            HG.manual_seed(len(text) * 7919 + VP_); ex = ex[torch.randperm(len(ex), generator=HG)[:256].numpy()]
                            c = torch.cat([c[0][ok[0]], torch.tensor(ex, device=dev).long()])[None]; ok = torch.ones_like(c, dtype=torch.bool)
                        else: VP_ = -1
            LEND_ = False; OP_ = -1
            if cfg.get("sym") and ("l" in cfg["sym"] or "o" in cfg["sym"]):                                     # SENT: required sentence end at the target length; required object after the verb
                lbs = len(text) - 1 - text[::-1].index(0) if 0 in text else None; ks = len(text) - 1 - lbs if lbs is not None else len(text)
                want = []
                if "l" in cfg["sym"] and DS.tlen > 0 and ks >= DS.tlen and (CLOSE[min(text[-1], VV - 1)] or ks >= DS.tlen + 8): LEND_ = True; want.append(0)
                elif "o" in cfg["sym"] and DS.oplan >= 0 and not DS.odone and DS.oage <= 4 and (text[-1] == DS.vplan or (DS.oage >= 1 and _fill[min(text[-1], VV - 1)] and all(x_ == DS.vplan or _fill[min(x_, VV - 1)] for x_ in text[-DS.oage - 1:]))): OP_ = DS.oplan; want.append(OP_)   # trace fix: object only right after the verb or after fillers that follow it
                for wv in want:
                    if not bool((St[c[0]][ok[0]] == wv).any()):
                        ex = plan_positions(text[-1], wv)
                        if len(ex):
                            HG.manual_seed(len(text) * 7919 + wv); ex = ex[torch.randperm(len(ex), generator=HG)[:256].numpy()]
                            c = torch.cat([c[0][ok[0]], torch.tensor(ex, device=dev).long()])[None]; ok = torch.ones_like(c, dtype=torch.bool)
            if cfg.get("len"):                                                                               # contiguous matched history, up to 8 words
                eq = (St[(c[:, :, None] - 1 - torch.arange(8, device=dev)).clamp(min=0)].long() == Qw[:, None, :8]).float(); m4 = torch.cumprod(eq, 2).sum(2)
            else: m4 = (St[(c[:, :, None] - 1 - torch.arange(MW, device=dev)).clamp(min=0)].long() == Qw[:, None, :MW]).float().sum(2)
            eqL = (St[(c[:, :, None] - 1 - torch.arange(8, device=dev)).clamp(min=0)].long() == Qw[:, None, :8]).float(); LSTAT.append(float(torch.cumprod(eqL, 2).sum(2).max()))
            sc = LAM0 * m4
            if cfg.get("beta"):                                                                                  # harmonic similarity of each candidate's history to the text's (z-scored across candidates)
                hm = HM.setdefault(json.dumps(cfg, sort_keys=True), Harm(cfg)); hw = text[::-1][:hm.WIN]; Qh = torch.tensor([hw + [-1] * (hm.WIN - len(hw))], device=dev)
                tier = ok[0] & (m4[0] >= m4[0][ok[0]].max() - 1); sel = torch.nonzero(tier)[:, 0][:int(cfg.get("htop", 1024))]       # only candidates that can still win
                if cfg.get("fhrr"):                                                                                    # FHRR: compare bound who-did-what states instead of bags of words
                    tr_, tv_ = fh_roles(text)
                    if "d" in str(cfg["fhrr"]) and cfg.get("sym") and len(DS.R) <= len(text):                          # COMB derived: roles of finished sentences from SYM's parse
                        tr_ = np.r_[np.array(DS.R, np.int8), tr_[len(DS.R):]]; tv_ = np.r_[np.array(DS.VS, np.int32), tv_[len(DS.VS):]]
                    Wn = min(hm.WIN, len(text)); qa = torch.tensor([text[::-1][:Wn]], device=dev); qr = torch.tensor([tr_[::-1][:Wn].copy()], device=dev); qv = torch.tensor([tv_[::-1][:Wn].copy()], device=dev)
                    eq_ = fh_enc(qa, qr, qv, cfg)
                    if "p" in str(cfg["fhrr"]) and cfg.get("sym") and DS.cbw >= 0:                                  # COMB plan-guided search: prefer passages whose recent subject is the planned protagonist
                        eq_ = eq_ + 0.5 * fh_enc(torch.tensor([[DS.cbw]], device=dev), torch.tensor([[1]], device=dev), torch.tensor([[-1]], device=dev), cfg)
                    sim = []
                    for b0 in range(0, len(sel), 2048):
                        pp = (c[0, sel[b0:b0 + 2048]][:, None] - 1 - torch.arange(Wn, device=dev)).clamp(min=0)
                        sim.append((fh_enc(St[pp].long(), FHC["role"][pp], FHC["vsub"][pp], cfg) * eq_).sum(1))
                    sim = torch.cat(sim)
                else:
                    eq_ = hm.enc(Qh); sim = torch.cat([(hm.enc(St[(c[0, sel[b0:b0 + 2048]][:, None] - 1 - torch.arange(hm.WIN, device=dev)).clamp(min=0)].long()) * eq_).sum(1) for b0 in range(0, len(sel), 2048)])
                z = torch.zeros_like(sc[0]); z[sel] = (sim - sim.mean()) / sim.std().clamp(min=1e-6) if len(sel) > 1 else 0.0
                sc = sc + cfg["beta"] * z[None]
                if HTRACE and not cfg.get("fhrr") and pid == 0 and len(text) - LP in HTRACE_STEPS:                                         # harmonic trace: per-band similarity of each top-tier candidate's history to the text's
                    def _w(i): return "." if i == 0 else (vw[i] if i < len(vw) and vw[i] is not None else "<unk>")
                    eC = torch.cat([hm.enc(St[(c[0, sel[b0:b0 + 2048]][:, None] - 1 - torch.arange(hm.WIN, device=dev)).clamp(min=0)].long()) for b0 in range(0, len(sel), 2048)])
                    nb = len(hm.bands); pb = (eC.reshape(len(sel), nb, -1) * eq_.reshape(1, nb, -1)).sum(2) * eC.reshape(len(sel), nb, -1).shape[2]
                    nxs = St[c[0, sel]].long().cpu().numpy(); m4s = m4[0, sel].cpu().numpy(); zs = z[sel].cpu().numpy()
                    HTL.append(f"=== step {len(text) - LP}: text so far ends: ...{' '.join(_w(x_) for x_ in text[-12:])}")
                    HTL.append(f"    {int(len(sel))} candidate positions in the top two match tiers (of {int(ok[0].sum())}); best tier m={int(m4s.max())}")
                    words_ = {}
                    for j_ in range(len(sel)):
                        wd_ = _w(int(nxs[j_])); words_.setdefault(wd_, []).append(j_)
                    rows_ = []
                    for wd_, js in words_.items():
                        js = np.array(js); top_ = js[np.argmax(zs[js])]
                        w0 = np.exp(LAM0 * (m4s[js] - m4s.max())).sum(); w1 = np.exp(LAM0 * (m4s[js] - m4s.max()) + zs[js]).sum()
                        rows_.append((wd_, len(js), int(m4s[js].max()), float(zs[js].mean()), w0, w1, pb[top_].cpu().numpy()))
                    t0 = sum(r_[4] for r_ in rows_) ; t1 = sum(r_[5] for r_ in rows_)
                    p0 = np.array([r_[4] for r_ in rows_]) ** cfg["pow"]; p1 = np.array([r_[5] for r_ in rows_]) ** cfg["pow"]; p0 /= p0.sum(); p1 /= p1.sum()
                    for k_ in np.argsort(-p1)[:8]:
                        r_ = rows_[k_]; HTL.append(f"    {r_[0]:>14s}: {r_[1]:4d} positions, tier m{r_[2]}, mean z {r_[3]:+.2f} | P without harmonics {p0[k_]:.3f} -> with {p1[k_]:.3f} | per-band cos of best position (tau 2..128): {' '.join(f'{x_:+.2f}' for x_ in r_[6])}")
            if cfg.get("lamc"):
                qc = FINE[torch.tensor([(text[::-1] + [0] * 8)[:8]], device=dev)]; mc = (FINE[St[(c[:, :, None] - 1 - torch.arange(8, device=dev)).clamp(min=0)].long()] == qc[:, None, :]).float().sum(2); sc = sc + cfg["lamc"] * mc
            if cfg.get("linw"):                                                                                   # next-word readout bonus (log p, nats)
                sc = sc + cfg["linw"] * linw_logprob(text, St[c[0]].long())[None]
            if cfg.get("ssm"):                                                                                    # trained HSSM bonus (log p, nats)
                sc = sc + cfg["ssm"] * ssm_logprob(text, St[c[0]].long())[None]
            if cfg.get("lin"):                                                                                    # readout bonus for each candidate's next-word class (beyond the local state)
                sc = sc + cfg["lin"] * lin_logits(text)[FINE[St[c[0]].long()]][None]
            if cfg.get("sym"):                                                                                    # realiser constraints
                nxc = St[c[0]].long().cpu().numpy(); lb = len(text) - 1 - text[::-1].index(0) if 0 in text[LP:] or text[-1] == 0 else None
                kpos = len(text) - 1 - lb if lb is not None else 99; add = np.zeros(len(nxc))
                if "p" in cfg["sym"] and kpos < len(PLAN): add += (1000.0 if "h" in cfg["sym"] else 8.0) * (nxc == PLAN[kpos])      # "h": the plan is a hard constraint
                if VP_ >= 0: add += 1000.0 * (nxc == VP_)
                if LEND_: add += 1000.0 * (nxc == 0)
                if OP_ >= 0: add += 1000.0 * (nxc == OP_)
                if "e" in cfg["sym"]: add += 2.0 * np.isin(nxc, list(REFS)) - 8.0 * (ISPROPN[np.minimum(nxc, VV - 1)] & ~np.isin(nxc, list(REFS)))
                sc = sc + torch.tensor(add, dtype=sc.dtype, device=sc.device)[None]; TR_ADD = add
            sc = torch.where(ok, sc, torch.full_like(sc, -1e9))[0]
            w = torch.exp(sc - sc.max()).cpu().numpy(); nx = St[c[0]].long().cpu().numpy()
            hv = hn(np.c_[np.repeat(np.array([text[-7:]]), len(nx), 0), nx]); bad = H8[np.minimum(np.searchsorted(H8, hv), len(H8) - 1)] == hv
            bad = bad | (nx == UNK); seen = {tuple(text[i:i + 3]) for i in range(len(text) - 2)}; bad = bad | np.array([(text[-2], text[-1], int(x_)) in seen for x_ in nx])
            if cfg.get("eps"):                                                                                   # junction veto: next word's class must be a plausible continuation of the last 4 classes
                J = int(cfg.get("jn", 4)); uf, nf, uc, nc = TB[J]; c4 = 0
                for x_ in text[-J:]: c4 = (c4 << 6) | int(BCL[x_])
                k5c = (np.uint64(c4) << np.uint64(6)) | BCLu[nx].astype(np.uint64); j = np.minimum(np.searchsorted(uf, k5c), len(uf) - 1); n5 = np.where(uf[j] == k5c, nf[j], 0)
                jc = min(int(np.searchsorted(uc, np.uint64(c4))), len(uc) - 1); n4 = int(nc[jc]) if uc[jc] == np.uint64(c4) else 0
                WPV = w * ~bad if (w * ~bad).sum() > 0 else w; veto = n5 < cfg["eps"] * max(n4, 1); JSTAT[0] += float((w * veto * ~bad).sum() / max((w * ~bad).sum(), 1e-30)); JSTAT[1] += 1; bad = bad | veto
            if cfg.get("wn"):                                                                                    # word junction veto: the n-gram ending in the next word must occur in training
                n_ = int(cfg["wn"]); Wt = WT[n_]; hv2 = hn(np.c_[np.repeat(np.array([text[-(n_ - 1):]]), len(nx), 0), nx]); seen_ = Wt[np.minimum(np.searchsorted(Wt, hv2), len(Wt) - 1)] == hv2
                JSTAT[2] += float((w * ~seen_ * ~bad).sum() / max((w * ~bad).sum(), 1e-30)); bad = bad | ~seen_
            if cfg.get("verbend"):                                                                               # hold the sentence open until it has a verb-like word
                lb = len(text) - 1 - text[::-1].index(0) if 0 in text else -1; cur = text[lb + 1:]
                if not any(VSET[BCL[x_]] for x_ in cur) and len(cur) > 0: bad = bad | (nx == 0)
            if cfg.get("sym") and "h" in cfg["sym"] and kpos < len(PLAN) and (nx == PLAN[kpos]).any(): bad = bad & (nx != PLAN[kpos])   # the planned word is exempt from the vetoes
            if cfg.get("sym") and VP_ >= 0 and (nx == VP_).any(): bad = bad & (nx != VP_)
            if cfg.get("sym") and LEND_ and (nx == 0).any(): bad = bad & (nx != 0)
            if cfg.get("sym") and OP_ >= 0 and (nx == OP_).any(): bad = bad & (nx != OP_)
            if (w * ~bad).sum() > 0: w = w * ~bad
            uw, inv = np.unique(nx, return_inverse=True); ww = np.bincount(inv, weights=w) ** cfg["pow"]
            if cfg.get("keepb") and uw[0] == 0:                                                                  # keep the sentence-end probability at its pre-veto value
                wp = np.bincount(inv, weights=WPV) ** cfg["pow"]; pb = wp[0] / wp.sum(); ww = ww / ww.sum(); rest = ww[1:].sum()
                if rest > 0 and pb < 1: ww[1:] *= (1 - pb) / rest; ww[0] = pb
            text.append(int(uw[rng.choice(len(uw), p=ww / ww.sum())]))
            if cfg.get("fhrr") and cfg.get("sym") and PLAN and len(text) - 1 - (len(text) - 2 - text[-2::-1].index(0) if 0 in text[:-1] else -10**9) == 1:   # COMB drift: phasor protagonist vs SYM's, at the planned sentence start
                tr2, tv2 = fh_roles(text[:-1])
                if "d" in str(cfg["fhrr"]) and len(DS.R) <= len(text) - 1: tr2 = np.r_[np.array(DS.R, np.int8), tr2[len(DS.R):]]; tv2 = np.r_[np.array(DS.VS, np.int32), tv2[len(DS.VS):]]
                ids2 = torch.tensor(text[:-1][::-1][:hm.WIN], device=dev); r2 = torch.tensor(tr2[::-1][:hm.WIN].copy(), device=dev); v2 = torch.tensor(tv2[::-1][:hm.WIN].copy(), device=dev)
                j2 = torch.arange(len(ids2), dtype=torch.float32, device=dev); ph2 = FHC["rid"][FHC["atom"][ids2]] + FHC["rph2"][r2.long()] + torch.where((v2 >= 0)[:, None], FHC["rid"][v2.clamp(min=0).long()], torch.zeros(1, device=dev))
                zst = (((1 - 1 / 128) ** j2) * (r2 > 0).float())[:, None].mul(torch.exp(1j * ph2)).sum(0)
                u2 = zst * torch.exp(-1j * FHC["rph2"][1]) + 0.67 * zst * torch.exp(-1j * FHC["rph2"][2])
                refs2 = [r_ for r_ in DS.sal if r_ != "IT"]; atoms2 = [int(FH_ATOM[_wid[SUBJ[r_]]]) if r_ in SUBJ and SUBJ[r_] in _wid else (int(FH_ATOM[_wid[r_]]) if r_ in _wid else -1) for r_ in refs2]
                okr = [(r_, a_) for r_, a_ in zip(refs2, atoms2) if a_ >= 0]
                if okr and DS.cbw >= 0:
                    scs = [float(torch.real((u2 * torch.exp(-1j * FHC["rid"][a_])).sum())) for _, a_ in okr]; ph_top = okr[int(np.argmax(scs))][1]
                    DRIFT[0] += 1; DRIFT[1] += int(ph_top == int(FH_ATOM[DS.cbw]))
            if TRACE and cfg.get("sym") and pid < TRACE:                                                           # step-by-step trace
                m4n = m4[0].cpu().numpy(); okn = ok[0].cpu().numpy(); o_ = np.argsort(-ww)[:6]; pw_ = ww / ww.sum()
                def _w(i): return "." if i == 0 else (vw[i] if i < len(vw) and vw[i] is not None else "<unk>")
                row = []
                for j in o_:
                    msk = (nx == uw[j]) & okn; row.append(f"{_w(uw[j])}:{pw_[j]:.2f}(m{int(m4n[msk].max()) if msk.any() else -1},+{TR_ADD[msk].max() if msk.any() else 0:.0f})")
                pl = " ".join(_w(i) for i in PLAN) if PLAN else "-"; pv = [int(x_) for x_ in PLAN]
                vetoed = [ _w(x_) for x_ in pv if (nx == x_).any() and bad[nx == x_].all()]; absent = [_w(x_) for x_ in pv if not (nx[okn] == x_).any()]
                TRL.append(f"[{nm_}|p{pid}|k{kpos}] plan={pl} vplan={_w(DS.vplan) if DS.vplan >= 0 else '-'} oplan={_w(DS.oplan) if DS.oplan >= 0 else '-'} tlen={DS.tlen} planned-vetoed={vetoed} planned-absent={absent} -> {_w(text[-1])} | top: {' '.join(row)}")
            if cfg.get("sym") and "o" in cfg["sym"] and VOB is not None:
                if DS.oplan >= 0: DS.oage += 1; DS.odone = DS.odone or text[-1] == DS.oplan
                elif not DS.odone and DS.vplan >= 0 and text[-1] == DS.vplan: DS.oplan = plan_object(DS.vplan, DS, rng); DS.oage = 0
            if cfg.get("sym") and text[-1] == 0:                                                                  # update the discourse state with the finished sentence, re-plan
                lb2 = len(text) - 2 - text[-2::-1].index(0) if 0 in text[:-1] else LP - 1; del DS.R[lb2 + 1:]; del DS.VS[lb2 + 1:]; DS.read(text[lb2 + 1:-1], period=True); PLAN = DS.plan(rng, cfg.get("ptr")); REFS = DS.ref_ids()
                if SLEN is not None and "l" in cfg["sym"]: DS.tlen = int(SLEN[rng.integers(len(SLEN))])
                DS.oplan = -1; DS.odone = False
                if TRACE and pid < TRACE: TRL.append(f"   [state] top referents: {sorted(DS.sal.items(), key=lambda x: -x[1])[:5]}")
                SYMST[1] += 1
        if cfg.get("gibbs"): text = gibbs(text, np.random.default_rng(1000 * pid + 11), cfg)
        if cfg.get("cdiff"): text = count_diffuse(text, np.random.default_rng(1000 * pid + 17), cfg)
        if cfg.get("block"): text = gibbs_block(text, np.random.default_rng(1000 * pid + 13), cfg)
        out[pid] = text[LP:]
    return out
def words(ids):
    out = []
    for i in ids:
        if i == 0:
            if out and out[-1] in ("?", "!"): continue
            out.append(".")
        else: out.append("<unk>" if i == UNK or i >= len(vw) or vw[i] is None else vw[i])
    t = " ".join(out)
    for p_ in (".", ",", ";", ":", "?", "!", ")"): t = t.replace(" " + p_, p_)
    return t.replace("( ", "(")
def words_plain(ids): return " ".join("." if i == 0 else ("<unk>" if i == UNK or i >= len(vw) or vw[i] is None else vw[i].lower()) for i in ids if not (i < len(PUNID) and PUNID[i])).replace(" .", ".")
st40 = np.nonzero((S[ntr + 1:-100] != 0) & (S[ntr:-101] == 0))[0] + ntr + 1; PROMPTS = st40[np.linspace(0, len(st40) - 1, 82).astype(int)[1:-1] + int(os.environ.get("G1_POFF", 13))]
NG = 3 if SMOKE else int(os.environ.get("G1_NG", 80)); GENS = (json.loads(os.environ["G1_ARMS"]) if os.environ.get("G1_ARMS") else {"JX1": dict(pow=6.0, eps=0.01), "JX3": dict(pow=6.0, eps=0.03)}) if JX else {"SA8": dict(pow=6.0), "SA8L": dict(pow=6.0, len=1)} if SA else {"BEST": dict(pow=6.0)} if (SMOKE or MODE == "sanity") else {"B1G6": dict(pow=6.0), "CLS2": dict(pow=6.0, lamc=2.0), "CLS4": dict(pow=6.0, lamc=4.0)}
if SMOKE and not SA and not JX: GENS = dict(GENS, CLS4=dict(pow=6.0, lamc=4.0))
GO = {}
for nm, cfg in GENS.items():
    if JX: JSTAT[0] = JSTAT[1] = JSTAT[2] = 0
    MWSTAT[0] = MWSTAT[1] = 0; GSTAT.clear(); EDITS.clear(); DRIFT[0] = DRIFT[1] = 0
    nm_ = nm; gg = generate(cfg, range(NG)); ext = [i for ids in gg.values() for i in ids if i > UNK]; nw = sum(1 for ids in gg.values() for i in ids if i != 0)
    if JX:                                                                                                    # share of completed sentences without a verb-like word
        sents = [seg for ids in gg.values() for seg in " ".join(map(str, ids)).split(" 0 ")[1:-1]]; nv = [not any(VSET[BCL[int(x_)]] for x_ in seg.split() if x_ != "0") for seg in sents]; VLS = float(np.mean(nv)) if nv else None
    cr = float(np.mean([text_crit(ids) for ids in gg.values()])) if CRITM is not None else None
    g5 = float(np.mean([np.mean(ng5_terms(S[PROMPTS[p]:PROMPTS[p] + LP].astype(np.int64).tolist() + ids, range(LP, LP + len(ids)))) for p, ids in gg.items()])) if NG5 is not None else None
    pl = [plag(ids) for ids in gg.values()]; GO[nm] = dict(drift_agree=[DRIFT[1], DRIFT[0]], edits=[dict(e, before=words(e["before"]), after=words(e["after"])) for e in EDITS], ng5_logp_per_word=g5, plag_share5=float(np.mean([a for a, _, _ in pl])), plag_longest=[b for _, b, _ in pl], plag_share8=float(np.mean([c_ for _, _, c_ in pl])), mw_ok=MWSTAT[1] / max(MWSTAT[0], 1), gibbs_changed=float(np.mean(GSTAT)) if GSTAT else None, verbless=VLS if JX else None, veto_mass=(JSTAT[0] / max(JSTAT[1], 1)) if JX else None, word_veto_mass=(JSTAT[2] / max(JSTAT[1], 1)) if JX else None, ext_share=len(ext) / max(nw, 1), mean_best_history=float(np.mean(LSTAT)), gens=[dict(pid=int(p), prompt=words(EXTP_[p] if EXTP_ is not None else S[PROMPTS[p]:PROMPTS[p] + LP].astype(np.int64)), text=words(ids), text_plain=words_plain(ids), prompt_plain=words_plain(EXTP_[p] if EXTP_ is not None else S[PROMPTS[p]:PROMPTS[p] + LP].astype(np.int64)), ids=[int(i) for i in ids]) for p, ids in gg.items()])
    if DRIFT[0]: log(f"COMB {nm}: phasor protagonist = SYM protagonist at {DRIFT[1]} of {DRIFT[0]} planned sentence starts")
    log(f"NG5 {nm}: 5-gram log p per generated word {g5}; critic log-odds per sentence {cr}"); GO[nm]["critic"] = cr
    log(f"PLAG {nm}: 5-gram share {GO[nm]['plag_share5']:.4f} (8-gram {GO[nm]['plag_share8']:.4f}), longest {GO[nm]['plag_longest']}; MW steps with a surviving word {GO[nm]['mw_ok']:.3f}; Gibbs changed {GO[nm]['gibbs_changed']}")
    log(f"G1B {MODE} {nm}: vetoed candidate mass {GO[nm]['veto_mass']}, longest history among candidates {GO[nm]['mean_best_history']:.3f}, extended-vocabulary share {GO[nm]['ext_share']:.4f} | {GO[nm]['gens'][0]['text'][:100]}")
log(f"CRIT truth: critic log-odds per sentence {np.mean([text_crit(S[PROMPTS[p] + LP:PROMPTS[p] + LP + LG].astype(np.int64).tolist()) for p in range(NG)]) if CRITM is not None else None}")
_TRU = [list(EXTT_[p]) for p in range(NG)] if EXTP_ is not None else [S[PROMPTS[p] + LP:PROMPTS[p] + LP + LG].astype(np.int64).tolist() for p in range(NG)]
_tp = [plag(x_) for x_ in _TRU]; log(f"PLAG truth: 5-gram share {np.mean([a for a, _, _ in _tp]):.4f}, longest {[b for _, b, _ in _tp]}")
GO["truth"] = dict(plag_share5=float(np.mean([a for a, _, _ in _tp])), plag_longest=[b for _, b, _ in _tp], gens=[dict(pid=int(p), prompt=words(EXTP_[p] if EXTP_ is not None else S[PROMPTS[p]:PROMPTS[p] + LP].astype(np.int64)), text=words(_TRU[p][:LG + 30] if EXTP_ is not None else _TRU[p]), text_plain=words_plain(_TRU[p][:LG + 30] if EXTP_ is not None else _TRU[p]), prompt_plain=words_plain(EXTP_[p] if EXTP_ is not None else S[PROMPTS[p]:PROMPTS[p] + LP].astype(np.int64)), ids=[int(x_) for x_ in _TRU[p]]) for p in range(NG)])
if TRL: open(os.path.join(OUTD, "trace.txt"), "w", encoding="utf-8").write(chr(10).join(TRL))
if HTL: open(os.path.join(OUTD, "htrace.txt"), "w", encoding="utf-8").write(chr(10).join(HTL))
json.dump(GO, open(os.path.join(OUTD, f"g1b_{MODE}_gen.json"), "w"), indent=0); log("saved")
