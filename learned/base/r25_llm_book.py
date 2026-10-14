"""R25-cq: the language model (RWKV-7, 0.4B, ckpt_read1b) on exactly the mix's test: the first 1,000 held-out
paragraphs read in order with its recurrent state carried across paragraphs (book scope, as our components), the same
lowercase word text, the same 50,114 predictions (every word after the first of its sentence); a word's cost is the sum
over its sub-word tokens. Reported on paragraphs 500-999 (the mix's test half) and on all 1,000; per-prediction
probabilities saved as r25_llm_book_probs.npz. Measurement only, no training. Run: py -3.12 r25_llm_book.py"""
import os, sys, math, time
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE)); os.chdir(HERE)
sys.argv = ["r25_attn.py", "--minutes", "0"]
src = open("r25_attn.py", encoding="utf-8").read(); src = src[:src.index("class Net(nn.Module)")]
g = {"__name__": "r25_attn_defs", "__file__": os.path.join(HERE, "r25_attn.py")}; exec(compile(src, "r25_attn.py", "exec"), g)
import torch
from rwkv7 import RWKV7, tokenizer
m = RWKV7.load(os.path.join(HERE, "ckpt_read1b.pth")); m.eval(); tok = tokenizer(); st = m.new_state(); t0 = time.time()
P, A = [], []
with torch.no_grad():
    for pi, p in enumerate(g["tep"][:1000]):
        pieces, want = [], []
        for s in p:
            for i, w in enumerate(s): pieces.append(tok.encode(" " + w)); want.append(i >= 1)
        ids = [t for pc in pieces for t in pc]
        logp = torch.log_softmax(m(torch.tensor([ids]), st)[0].float(), -1); pos = 0
        for pc, wnt in zip(pieces, want):
            if wnt: P.append(sum(logp[pos + j - 1, t].item() for j, t in enumerate(pc)) / math.log(2)); A.append(pi)
            pos += len(pc)
        if pi % 100 == 0: print(f"  {pi} paragraphs ({time.time() - t0:.0f} s)", flush=True)
P = -np.array(P); A = np.array(A); np.savez("r25_llm_book_probs.npz", p=2.0 ** -P, para=A)
print(f"R25-cq language model, book scope: paragraphs 500-999 {P[A >= 500].mean():.4f} bits/word; all 1,000 {P.mean():.4f} over {len(P)} predictions ({time.time() - t0:.0f} s)", flush=True)
