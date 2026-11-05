"""PY (sieve_lang_prereg.md): pythia-70m-deduped over the MT corpora on a T4. Per corpus writes
<c>_st1000.npy / <c>_st4096.npy (int16 state for predicting word t, from the hidden state at the last BPE piece of word t-1)
and <c>_pybits.npy (Pythia's own bits for word t, eval part only; NaN elsewhere)."""
import glob, os, time, math, numpy as np, torch
from transformers import AutoTokenizer, GPTNeoXForCausalLM
print("cuda", torch.cuda.is_available(), flush=True); assert torch.cuda.is_available()
dev = "cuda"; NAME = "EleutherAI/pythia-70m-deduped"; WIN, STR, B = 1024, 512, 16
tk = AutoTokenizer.from_pretrained(NAME); md = GPTNeoXForCausalLM.from_pretrained(NAME, torch_dtype=torch.float16).to(dev).eval()
files = [f for f in glob.glob("/kaggle/input/**/*_data.npz", recursive=True)]; print(files, flush=True)
def kmeans(X, K, it=20):
    g = torch.Generator(device=dev).manual_seed(0); C = X[torch.randperm(len(X), generator=g, device=dev)[:K]].clone()
    for _ in range(it):
        a = assign(X, C); C2 = torch.zeros_like(C).index_add_(0, a, X); n = torch.bincount(a, minlength=K).float()[:, None]
        C = torch.where(n > 0, C2 / n.clamp(min=1), C)
    return C
def assign(X, C):
    out = torch.empty(len(X), dtype=torch.long, device=dev); cn = (C * C).sum(1) / 2
    for a0 in range(0, len(X), 65536): out[a0:a0 + 65536] = (X[a0:a0 + 65536] @ C.T - cn).argmax(1)
    return out
for c in ("books", "wiki"):
    t0 = time.time(); z = np.load([f for f in files if os.path.basename(f).startswith(c)][0]); S = z["S"].astype(np.int64); ntr = int(z["ntr"]); vw = z["vw"]
    strs = ["."] + [" " + str(w) for w in vw[1:]] + [" unk"]; enc = tk(strs, add_special_tokens=False)["input_ids"]
    L = np.array([len(e) for e in enc]); off = np.r_[0, np.cumsum(L)[:-1]]; flat = np.array([p for e in enc for p in e], np.int64)
    lens = L[S]; ends = np.cumsum(lens) - 1; starts = ends - lens + 1; tot = int(lens.sum())
    stream = flat[np.repeat(off[S], lens) + (np.arange(tot) - np.repeat(starts, lens))]
    nwin = math.ceil(max(tot - WIN, 0) / STR) + 1; padlen = (nwin - 1) * STR + WIN; st = np.zeros(padlen, np.int64); st[:tot] = stream; ST = torch.tensor(st, device=dev)
    keep_a = np.array([0] + [w * STR + STR for w in range(1, nwin)]); keep_b = np.array([w * STR + WIN for w in range(nwin)]); keep_b[:-1] = np.minimum(keep_b[:-1], keep_a[1:])
    print(c, "words", len(S), "bpe", tot, "windows", nwin, f"{time.time() - t0:.0f} s", flush=True)
    def run(ws, logits=False):
        ids = torch.stack([ST[w * STR:w * STR + WIN] for w in ws])
        with torch.no_grad():
            h = md.gpt_neox(input_ids=ids).last_hidden_state
            return h, (md.get_output_embeddings()(h) if logits else None)
    ntrain_end = ends[ntr - 1]; trw = [w for w in range(nwin) if keep_b[w] <= ntrain_end]                     # pass 1: k-means sample from every 64th training window
    samp = []
    for b0 in range(0, len(trw[::64]), B):
        ws = trw[::64][b0:b0 + B]; h, _ = run(ws)
        for k, w in enumerate(ws):
            i0, i1 = np.searchsorted(ends, keep_a[w]), np.searchsorted(ends, keep_b[w]); samp.append(h[k, torch.tensor(ends[i0:i1] - w * STR, device=dev)].float())
    X = torch.cat(samp); X = X[torch.randperm(len(X), generator=torch.Generator(device=dev).manual_seed(1), device=dev)[:300_000]]
    C1, C4 = kmeans(X, 1000), kmeans(X, 4096); del X, samp; print(c, "kmeans done", f"{time.time() - t0:.0f} s", flush=True)
    s1 = np.zeros(len(S), np.int16); s4 = np.zeros(len(S), np.int16); lp = np.zeros(padlen, np.float32); eval_a = starts[ntr] - 1
    for b0 in range(0, nwin, B):                                                                                  # pass 2: every word's state; logits in the eval part
        ws = list(range(b0, min(b0 + B, nwin))); lg = keep_b[ws[-1]] > eval_a; h, lo = run(ws, lg)
        for k, w in enumerate(ws):
            i0, i1 = np.searchsorted(ends, keep_a[w]), np.searchsorted(ends, keep_b[w]); i1 = min(i1, len(S) - 1)
            if i1 > i0:
                hh = h[k, torch.tensor(ends[i0:i1] - w * STR, device=dev)].float(); s1[i0 + 1:i1 + 1] = assign(hh, C1).cpu().numpy(); s4[i0 + 1:i1 + 1] = assign(hh, C4).cpu().numpy()
            if lg:
                a, b = keep_a[w], keep_b[w]; nxt = ST[a + 1:b + 1] if b + 1 <= padlen else torch.cat([ST[a + 1:b], ST[:1]])
                l_ = torch.log_softmax(lo[k, a - w * STR:b - w * STR].float(), -1).gather(1, nxt[:, None])[:, 0]; lp[a:b] = l_.cpu().numpy()
        if b0 % (B * 400) == 0: print(c, "window", b0, "of", nwin, f"{time.time() - t0:.0f} s", flush=True)
    cs = np.r_[0, np.cumsum(lp[:tot].astype(np.float64))]; bits = np.full(len(S), np.nan, np.float32); t = np.arange(ntr, len(S))
    bits[t] = -(cs[ends[t]] - cs[starts[t] - 1]) / math.log(2)                                                 # sum over the word's pieces of log P(piece | before)
    np.save(f"/kaggle/working/{c}_st1000.npy", s1); np.save(f"/kaggle/working/{c}_st4096.npy", s4); np.save(f"/kaggle/working/{c}_pybits.npy", bits)
    print(c, "done", f"{time.time() - t0:.0f} s; eval word bits mean (non-boundary) {np.nanmean(bits[t][S[t] != 0]):.4f}", flush=True)
