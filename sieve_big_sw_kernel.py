"""BIG generation (sieve_lang_prereg.md): SW2 search-while-writing with the generator index and the verifier's trigram
counts built from the 200M-word books stream (trigger table from the 27M MT protocol, as SW2). Prompts = SW's 40 (shifted
into the combined stream); budgets 1 and 256; PART 0 = prompts 0-19, PART 1 = 20-39. Writes /kaggle/working/big_sw_<part>.json."""
import os, glob, json, time, numpy as np
PART = 0; SIZE = 200; V = 60000; VV = V + 2; D = 0.75; NP, LP, LG, H, COMMIT = 40, 30, 50, 20, 5; BUD = (1, 256); T0 = time.time()
def log(m): print(f"{m} ({time.time() - T0:.0f} s)", flush=True)
def find(name): return glob.glob("/kaggle/input/**/" + name, recursive=True)[0]
def look(u, n, k):
    i = np.minimum(np.searchsorted(u, k), len(u) - 1); return np.where(u[i] == k, n[i], 0)
def k4(S, p):
    k = np.zeros(len(p), np.uint64)
    for i in range(4): k = (k << np.uint64(16)) | S[p + i].astype(np.uint64)
    return k
class Model:
    def __init__(s):
        z = np.load(find("books_data.npz")); S0 = z["S"].astype(np.int64); D0 = z["D"].astype(np.int64); ntr0 = int(z["ntr"]); s.vw = z["vw"]
        parts = [np.load(find(f"tok_books_{p}.npz")) for p in ("0_0", "0_1", "1_0", "1_1")]; new = np.concatenate([p["S"] for p in parts]).astype(np.int64)
        Str = np.r_[S0[:ntr0], new]; s.S = np.r_[Str, S0[ntr0:]]; s.shift = len(Str) - ntr0; s.S0, s.ntr0 = S0, ntr0
        wc = np.cumsum(Str != 0); cut = min(int(np.searchsorted(wc, SIZE * 1_000_000)) + 1, len(Str)); s.ntr = cut; S = s.S; del Str, wc, new
        P = np.arange(cut - 8); a = k4(S, P); o = np.argsort(a, kind="stable"); s.SA = P[o]; s.K1 = a[o]; b = k4(S, P + 4)
        with np.errstate(over="ignore"): s.H8 = np.sort((a * np.uint64(0x9E3779B97F4A7C15)) ^ b)
        del a, b, o, P; log(f"index over {cut:,} positions")
        t = np.arange(2, cut); t = t[S[t] != 0]; yy = S[t]; s.n1 = np.bincount(yy, minlength=VV); s.u2, s.n2 = np.unique(S[t - 1] * VV + yy, return_counts=True)
        s.u3, s.n3 = np.unique((S[t - 2] * VV + S[t - 1]) * VV + yy, return_counts=True); del t, yy
        b2 = s.u2 // VV; s.cb = np.bincount(b2, weights=s.n2, minlength=VV); s.db = np.bincount(b2, minlength=VV)
        x3 = s.u3 // VV; s.ux, st = np.unique(x3, return_index=True); s.cx = np.add.reduceat(s.n3, st); s.dx = np.diff(np.r_[st, len(s.u3)]); log("trigram tables")
        con = (S0 > 100) & (S0 <= V); kp = np.nonzero(con[:ntr0])[0]; g = np.random.default_rng(1); Pq = np.sort(g.choice(kp[kp >= 2], 2_000_000, replace=False)); Dt = D0[:ntr0]; keys = []
        k = np.searchsorted(kp, Pq - 2); ds = np.searchsorted(Dt, Dt[Pq]); kb = np.searchsorted(kp, ds)
        for j in range(50):
            ix = k - 1 - j; ok = ix >= kb; keys.append(S0[kp[ix[ok]]] * VV + S0[Pq[ok]])
        s.tu, s.tn = np.unique(np.concatenate(keys), return_counts=True); s.rc = np.bincount(s.tu // VV, weights=s.tn, minlength=VV); s.pUall = (s.n1 + 0.5) / (s.n1.sum() + 0.5 * VV); log("trigger table (27M protocol)")
    def nxt(s, ctx, rng):
        """ctx: (R, >=4) word ids; sample the next word from the longest suffix (<= 4 words) seen >= 3 times"""
        R = len(ctx); out = np.full(R, -1, np.int64)
        for L in (4, 3, 2, 1):
            q = ctx[:, -L:]; lo = np.zeros(R, np.uint64)
            for i in range(L): lo = lo | (q[:, i].astype(np.uint64) << np.uint64(16 * (3 - i)))
            hi = lo | np.uint64((1 << (16 * (4 - L))) - 1); a = np.searchsorted(s.K1, lo, "left"); b = np.searchsorted(s.K1, hi, "right"); ok = (out < 0) & (b - a >= 3)
            if ok.any(): idx = a[ok] + (rng.random(ok.sum()) * (b[ok] - a[ok])).astype(np.int64); out[ok] = s.S[s.SA[idx] + L]
            if (out >= 0).all(): break
        m = out < 0
        if m.any(): out[m] = s.S[s.SA[rng.integers(0, len(s.SA), m.sum())]]
        return out
    def pL(s, a, b, y):
        pU = s.pUall[y]; c2 = look(s.u2, s.n2, b * VV + y); p2 = np.where(s.cb[b] > 0, np.maximum(c2 - D, 0) / np.maximum(s.cb[b], 1) + D * s.db[b] / np.maximum(s.cb[b], 1) * pU, pU)
        ab = a * VV + b; cab = look(s.ux, s.cx, ab); dab = look(s.ux, s.dx, ab); c3 = look(s.u3, s.n3, ab * VV + y)
        return np.where(cab > 0, np.maximum(c3 - D, 0) / np.maximum(cab, 1) + D * dab / np.maximum(cab, 1) * p2, p2)
    def score(s, text, paths):
        """verifier: per word log P_L + 0.5 x content x log(P_T / P_U), minus 3 per repeated trigram"""
        R, h = paths.shape; full = np.concatenate([np.repeat(np.array(text)[None, -2:], R, 0), paths], 1); y = paths.ravel(); a = full[:, :-2].ravel(); b = full[:, 1:-1].ravel()
        con = (y > 100) & (y <= V); W = [w for w in text if 100 < w <= V][-50:]; pl = s.pL(a, b, y)
        if True:                                                                                                # SW2: cache over the passage's content words
            hist = np.array([w for w in text if 100 < w <= V]); u_, n_ = np.unique(hist, return_counts=True) if len(hist) else (np.zeros(0, np.int64), np.zeros(0, np.int64))
            pc = np.where(con, (look(u_, n_, y) if len(u_) else 0) / max(len(hist), 1), 0.0); sc = np.log(0.7 * pl + 0.3 * pc)
        else: sc = np.log(pl)
        W = [w for w in W if s.rc[w] > 0]; TW = 1.0
        if W and con.any():
            pT = np.zeros(con.sum())
            for w in W: pT += look(s.tu, s.tn, w * VV + y[con]) / s.rc[w]
            pT /= len(W); sc[con] += TW * np.log((pT + 1e-6) / (s.pUall[y[con]] + 1e-6))
        sc = sc.reshape(R, h).sum(1); seen = {tuple(text[i:i + 3]) for i in range(len(text) - 2)}
        for r in range(R):
            tt = seen.copy(); ext = list(text[-2:]) + list(paths[r]); rep = 0
            for i in range(len(ext) - 2):
                g = tuple(ext[i:i + 3]); rep += g in tt; tt.add(g)
            sc[r] -= 3 * rep
        if True:                                                                                                # copy cap: 8-word windows found verbatim in the training text
            ext = np.concatenate([np.repeat(np.array(text)[None, -7:], R, 0), paths], 1); nw = ext.shape[1] - 7
            a8 = np.zeros((R, nw), np.uint64); b8 = np.zeros((R, nw), np.uint64)
            for i in range(4): a8 = (a8 << np.uint64(16)) | ext[:, i:i + nw].astype(np.uint64); b8 = (b8 << np.uint64(16)) | ext[:, 4 + i:4 + i + nw].astype(np.uint64)
            with np.errstate(over="ignore"): h8 = (a8 * np.uint64(0x9E3779B97F4A7C15)) ^ b8
            j = np.minimum(np.searchsorted(s.H8, h8), len(s.H8) - 1); ncp = (s.H8[j] == h8).sum(1); sc = sc - 1e6 * ncp
        return sc
    def generate(s, prompt, B, seed):
        rng = np.random.default_rng(seed); text = list(prompt)
        while len(text) - len(prompt) < LG:
            ctx = np.array(text[-4:])[None]
            if B == 1: text.append(int(s.nxt(ctx, rng)[0])); continue
            paths = np.zeros((B, H), np.int64); cur = np.repeat(ctx, B, 0)
            for j in range(H): paths[:, j] = s.nxt(cur, rng); cur = np.concatenate([cur[:, 1:], paths[:, j:j + 1]], 1)
            text.extend(int(w) for w in paths[np.argmax(s.score(text, paths)), :COMMIT])
        return text[len(prompt):len(prompt) + LG]
    def words(s, ids): return " ".join("." if i == 0 else "<unk>" if i > V else str(s.vw[i]) for i in ids).replace(" .", ".")
m = Model(); S0, ntr0 = m.S0, m.ntr0
st = np.nonzero((S0[ntr0 + 1:-100] != 0) & (S0[ntr0:-101] == 0))[0] + ntr0 + 1; st = st[np.linspace(0, len(st) - 1, NP).astype(int)]; G = []
for pid, t in enumerate(st):
    if pid // 20 != PART: continue
    pr = S0[t:t + LP].tolist()
    for B in BUD:
        ids = m.generate(pr, B, 1000 * pid + B); G.append(dict(pid=pid, B=B, pos=int(t), prompt=m.words(pr), text=m.words(ids), ids=ids))
    log(f"prompt {pid} done")
json.dump(G, open(f"/kaggle/working/big_sw_{PART}.json", "w"), indent=0); log("saved")
