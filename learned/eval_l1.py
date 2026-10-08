"""L1_prereg.md gates. Run after train_lm.py: python learned/eval_l1.py -> learned/L1_samples.json (judgments filled by hand)
L1a: held-out bits per character, model vs an interpolated (Witten-Bell) bigram over the same tokens
L1b: 20 continuations of 20 held-out sentence openings (fixed seeds) for judging
L1c: parameters, training FLOPs, inference FLOPs per token against a 7 B-parameter LLM"""
import os, re, json, math, random, numpy as np, torch, torch.nn.functional as F
from data import BPE, read, CACHE
from train_lm import LM

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    tok = BPE.load(); V = tok.size
    ck = torch.load(os.path.join(CACHE, "lm.pt")); m = LM(**ck["cfg"]); m.load_state_dict(ck["state"]); m.eval()
    train = np.fromfile(os.path.join(CACHE, "train.bin"), dtype=np.uint16).astype(np.int64)
    held = np.fromfile(os.path.join(CACHE, "held.bin"), dtype=np.uint16).astype(np.int64)
    T = ck["cfg"]["ctx"]; rng = np.random.default_rng(7)
    starts = rng.integers(0, len(held) - T - 1, 240)                    # ~200 k characters of held-out text
    clen = np.array([len(tok.vocab[i]) if i < len(tok.vocab) else 1 for i in range(V)])
    # ---- bigram, Witten-Bell interpolated with the unigram
    uni = np.bincount(train, minlength=V).astype(np.float64); pu = (uni + 1) / (uni.sum() + V)
    big = {}; pair = train[:-1] * V + train[1:]
    keys, cnt = np.unique(pair, return_counts=True)
    prev_tot = np.bincount(keys // V, weights=cnt, minlength=V); prev_types = np.bincount(keys // V, minlength=V)
    bigd = dict(zip(keys.tolist(), cnt.tolist()))
    nll_m = nll_b = chars = 0.0
    with torch.no_grad():
        for s in starts:
            x = torch.from_numpy(held[s:s + T][None]); y = held[s + 1:s + T + 1]
            lp = F.log_softmax(m(x)[0], -1).numpy()
            nll_m -= lp[np.arange(T), y].sum()
            for a, b in zip(held[s:s + T], y):
                n_a = prev_tot[a]; t_a = prev_types[a]
                lam = n_a / (n_a + t_a) if n_a else 0.0
                p = lam * (bigd.get(int(a) * V + int(b), 0) / n_a if n_a else 0) + (1 - lam) * pu[b]
                nll_b -= math.log(p)
            chars += clen[y].sum()
    bpc_m = nll_m / math.log(2) / chars; bpc_b = nll_b / math.log(2) / chars
    print(f"L1a: model {bpc_m:.3f} bits/char, bigram {bpc_b:.3f} bits/char, ratio {bpc_m / bpc_b:.3f} (bar <= 0.8) over {chars:.0f} characters")
    # ---- L1b: openings from held-out books (fixed seed): the first 8 words of narrative sentences
    split = json.load(open(os.path.join(CACHE, "split.json")))
    R = random.Random(11); opens = []
    while len(opens) < 20:
        b = R.choice(split["held"]); paras = [p for p in read(b).split("\n") if len(p) > 200 and p[:1].isalpha()]
        if not paras: continue
        p = R.choice(paras); sents = re.split(r"(?<=[.!?])\s+(?=[A-Z])", p)
        sn = [s for s in sents if len(s.split()) >= 12]
        if not sn: continue
        opens.append((b, " ".join(R.choice(sn).split()[:8])))
    gen = torch.Generator().manual_seed(0); out = []
    for b, o in opens:
        ids = torch.tensor([tok.encode(o)])
        cont = tok.decode(m.generate(ids, 60, gen=gen)[0, ids.shape[1]:].tolist())
        out.append(dict(book=b, opening=o, continuation=cont, fluent=None, note=""))
        print(f"\n[{b}] {o} || {cont}")
    # ---- L1c
    lg = json.load(open(os.path.join(CACHE, "train_log.json")))
    n = lg["params"]; inf = 2 * n
    eff = dict(params=n, train_tokens=lg["tokens"], train_flops=lg["train_flops"], train_seconds=lg["seconds"],
               inference_flops_per_token=inf, llm7b_flops_per_token=2 * 7e9, ratio_vs_7b=2 * 7e9 / inf)
    print(f"\nL1c: {n / 1e6:.2f} M parameters; training {lg['train_flops']:.2e} FLOPs in {lg['seconds'] / 3600:.1f} h on the laptop CPU; "
          f"inference {inf:.2e} FLOPs/token vs 7 B LLM {2 * 7e9:.2e} -> {2 * 7e9 / inf:.0f}x cheaper per token")
    json.dump(dict(L1a=dict(model_bpc=bpc_m, bigram_bpc=bpc_b, ratio=bpc_m / bpc_b, chars=chars), L1b=out, L1c=eff),
              open(os.path.join(HERE, "L1_samples.json"), "w", encoding="utf-8"), indent=1)


if __name__ == "__main__":
    main()
