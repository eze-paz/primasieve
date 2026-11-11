"""TTL (sieve_lang_prereg.md): surprise-gated test-time learning vs uniform, pythia-70m-deduped on a T4.
Writes /kaggle/working/<c>_ttl.npz with per-segment bits, words, tokens, k, document index for each arm."""
import glob, os, time, math, numpy as np, torch
from transformers import AutoTokenizer, GPTNeoXForCausalLM
print("cuda", torch.cuda.is_available(), flush=True); assert torch.cuda.is_available()
dev = "cuda"; NAME = "EleutherAI/pythia-70m-deduped"; SEG, CTX = 128, 896; T0 = time.time()
tk = AutoTokenizer.from_pretrained(NAME); md = GPTNeoXForCausalLM.from_pretrained(NAME, torch_dtype=torch.float32).to(dev).eval()
for p in md.parameters(): p.requires_grad_(False)
TP = list(md.gpt_neox.layers[-2].parameters()) + list(md.gpt_neox.layers[-1].parameters()) + list(md.gpt_neox.final_layer_norm.parameters())
for p in TP: p.requires_grad_(True)
INIT = [p.detach().clone() for p in TP]
files = glob.glob("/kaggle/input/**/*_data.npz", recursive=True); print(files, flush=True)
def reset():
    with torch.no_grad():
        for p, q in zip(TP, INIT): p.copy_(q)
def docs(c, cap, maxdocs):
    z = np.load([f for f in files if os.path.basename(f).startswith(c)][0]); S = z["S"].astype(np.int64); D = z["D"]; ntr = int(z["ntr"]); vw = z["vw"]
    strs = ["."] + [" " + str(w) for w in vw[1:]] + [" unk"]; enc = tk(strs, add_special_tokens=False)["input_ids"]
    L = np.array([len(e) for e in enc]); off = np.r_[0, np.cumsum(L)[:-1]]; flat = np.array([p for e in enc for p in e], np.int64)
    s, d = S[ntr:], D[ntr:]; out = []
    for di in np.unique(d)[:maxdocs]:
        w = s[d == di]; lens = L[w]; ends = np.cumsum(lens) - 1; starts = ends - lens + 1; tot = int(lens.sum())
        toks = flat[np.repeat(off[w], lens) + (np.arange(tot) - np.repeat(starts, lens))]
        isend = np.zeros(tot, bool); isend[ends[w != 0]] = True; out.append((toks[:cap], isend[:cap]))
    return out
def run_doc(toks, isend, mode, lr, thr=None, rng=None):
    reset(); opt = torch.optim.Adam(TP, lr=lr); T = torch.tensor(toks, device=dev); res = []
    for s0 in range(1, len(toks), SEG):
        s1 = min(s0 + SEG, len(toks)); a = max(0, s0 - CTX); x = T[a:s1 - 1][None]; y = T[a + 1:s1]; sl = slice(s0 - a - 1, None)
        with torch.no_grad(): lp = torch.log_softmax(md(x).logits[0][sl].float(), -1).gather(1, y[sl][:, None])[:, 0]
        bits = float(-lp.sum() / math.log(2)); ntok = s1 - s0; sur = bits / ntok
        if mode == 0: k = 0
        elif mode == 1: k = 1
        elif mode == 2: k = 0 if sur < thr[0] else (1 if sur < thr[1] else 4)
        else: k = int(rng.choice([0, 1, 4], p=[0.45, 0.40, 0.15]))
        for _ in range(k):
            opt.zero_grad(); loss = torch.nn.functional.cross_entropy(md(x).logits[0][sl], y[sl]); assert torch.isfinite(loss), "non-finite loss"; loss.backward(); opt.step()
        res.append((bits, int(isend[s0:s1].sum()), ntok, k, sur))
    return res
def arm(dd, ids, mode, lr, thr=None, seed=0):
    rng = np.random.default_rng(seed); rows = []
    for i in ids:
        for r in run_doc(*dd[i], mode, lr, thr, rng): rows.append((i,) + r)
    return np.array(rows)
LR = None
for c, cap, mx in (("books", 8192, 55), ("wiki", 2048, 220)):
    dd = docs(c, cap, mx); odd = [i for i in range(len(dd)) if i % 2 == 1]; even = [i for i in range(len(dd)) if i % 2 == 0]; out = {}
    print(c, "docs", len(dd), "tokens", sum(len(t) for t, _ in dd), f"{time.time() - T0:.0f} s", flush=True)
    if LR is None:                                                                                        # learning rate: arm 1 on the first 10 odd book documents
        sc = {lr: (lambda r: r[:, 1].sum() / r[:, 2].sum())(arm(dd, odd[:10], 1, lr)) for lr in (3e-5, 1e-4, 3e-4)}; LR = min(sc, key=sc.get)
        print("lr scores (bits/word)", {k: round(float(v), 4) for k, v in sc.items()}, "chosen", LR, f"{time.time() - T0:.0f} s", flush=True)
    a0o = arm(dd, odd, 0, LR); thr = (float(np.percentile(a0o[:, 5], 45)), float(np.percentile(a0o[:, 5], 85))); print(c, "thresholds", thr, f"{time.time() - T0:.0f} s", flush=True)
    for nm, mode in (("arm0", 0), ("arm1", 1), ("arm2", 2), ("arm3", 3)):
        r = arm(dd, even, mode, LR, thr, seed=7); out[nm] = r
        print(c, nm, f"bits/word {r[:, 1].sum() / r[:, 2].sum():.4f} mean k {r[:, 4].mean():.3f}", f"{time.time() - T0:.0f} s", flush=True)
    np.savez(f"/kaggle/working/{c}_ttl.npz", lr=LR, thr=np.array(thr), **out)
