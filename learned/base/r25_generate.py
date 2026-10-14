"""R25-cx: sample paragraphs from our engine and, for comparison, from the language model, from the same prompts.
Our engine (an approximation of the best mix that can be sampled word by word): the book-scope group network
(r25_ch.pt) gives P(group) x the word's count share; its 300 most likely words are re-scored by the fast Kneser-Ney
counter (o5mxa) and blended 0.55 / 0.45, renormalised over those 300, then sampled (top-p 0.9). The language model:
RWKV-7 0.4B, same prompt in the same lowercase word form, top-p 0.9. Prompts: openings of three held-out paragraphs.
Run: py -3.12 r25_generate.py"""
import os, sys, math, random
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE)); os.chdir(HERE)
sys.argv = ["r25_kn2.py", "--order", "5", "--mkn", "--cross", "--all-text"]
src = open("r25_kn2.py", encoding="utf-8").read(); src = src[:src.index("P, A, Dp = [], [], []")]
KN = {"__name__": "kn", "__file__": os.path.join(HERE, "r25_kn2.py")}; exec(compile(src, "r25_kn2.py", "exec"), KN)
sys.argv = ["r25_rnn.py", "--groups", "--oov-groups", "--lookup", "0", "--groups-file", "r25_classes_wnx.json"]
src = open("r25_rnn.py", encoding="utf-8").read(); src = src[:src.index("net = RNet()")]
R = {"__name__": "rn", "__file__": os.path.join(HERE, "r25_rnn.py")}; exec(compile(src, "r25_rnn.py", "exec"), R)
torch = R["torch"]; torch.set_grad_enabled(False); net = R["RNet"](); net.load_state_dict(torch.load("r25_ch.pt")); net.eval()
vocab, vi, gw, _uni, _cnt = R["vocab"], R["vi"], R["gw"], R["_uni"], R["_cnt"]
words = vocab; gids = torch.tensor([gw(w) for w in words]); share = torch.tensor([(_uni[w] + 0.5) / _cnt[gw(w)] for w in words])
def step(x, h):
    hs, hn = net.rnn(net.inp(net.emb(torch.tensor([[x]]))), h)
    if hasattr(net, "proj"): hs = net.proj(hs)
    return torch.softmax(net.out(net.out_ln(hs))[0, -1], -1), hn
def sample(probs, cands, rng):
    o = np.argsort(-probs); c = np.cumsum(probs[o]); k = int(np.searchsorted(c, 0.9)) + 1; o = o[:k]; p = probs[o] / probs[o].sum()
    return cands[o[rng.choices(range(len(o)), weights=p)[0]]]
def ours(prompt, n, seed):
    rng = random.Random(seed); h = None; ctx = [0]
    for w in prompt: pg, h = step(vi.get(w, 0), h); ctx.append(KN["wid"].get(w, KN["RARE"]))
    out = []
    for _ in range(n):
        pw = (pg[gids] * share).numpy(); top = np.argsort(-pw)[:300]
        kn = np.array([KN["prob"](ctx[-5:], KN["wid"].get(words[i], KN["RARE"]))[0] for i in top])
        mix = 0.55 * pw[top] / pw[top].sum() + 0.45 * kn / kn.sum()
        w = words[sample(mix, top, rng)]; out.append(w)
        pg, h = step(vi.get(w, 0), h); ctx.append(KN["wid"].get(w, KN["RARE"]))
    return " ".join(out)
from rwkv7 import RWKV7, tokenizer
lm = RWKV7.load("ckpt_read1b.pth"); lm.eval(); tok = tokenizer()
def theirs(prompt, n, seed):
    rng = random.Random(seed); st = lm.new_state(); ids = tok.encode(" ".join(prompt)); out = []
    with torch.no_grad():
        logits = lm(torch.tensor([ids]), st)[0, -1].float()
        while len(" ".join(tok.decode(out).split())) < 1 or len(tok.decode(out).split()) < n:
            p = torch.softmax(logits, -1).numpy(); t = sample(p, np.arange(len(p)), rng); out.append(int(t))
            logits = lm(torch.tensor([[t]]), st)[0, -1].float()
    return " ".join(tok.decode(out).split()[:n])
tep = KN["g"]["tep"]
for k, pi in enumerate((503, 650, 801)):
    prompt = [x for s in tep[pi] for x in s][:20]
    print(f"\n=== prompt {k + 1}: {' '.join(prompt)} ...", flush=True)
    print(f"--- our engine: {ours(prompt, 60, k)}", flush=True)
    print(f"--- language model: {theirs(prompt, 60, k)}", flush=True)
