"""R25-ao: the language model on the next-word game, matched to r25_nextword.py: same lowercase word sentences from
the held-out books, the first N sentences, words 2.. predicted from the earlier words of the same sentence; the
model's cost for a word is the sum over its sub-word tokens. Output: bits per word over the same predictions."""
import os, sys, math, time
ARGV = list(sys.argv)
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE)); os.chdir(HERE)
import torch
import r24_tlm as T, r24_books as B, data as D0
from rwkv7 import RWKV7, tokenizer
N = int(ARGV[ARGV.index("--subset") + 1]) if "--subset" in ARGV else 3000
def sents_of(paras):
    for p in paras:
        for s in T.SENT.split(p["text"]):
            w = [x.lower() for x in T.TOK.findall(s) if x.isalpha()]
            if len(w) >= 2: yield w
_, te_b = D0.books(); te = list(sents_of(B.paragraphs(te_b, 20000)))[:N]
m = RWKV7.load(os.path.join(HERE, "ckpt_read1b.pth")); m.eval(); tok = tokenizer(); t0 = time.time()
tot = 0.0; n = 0
with torch.no_grad():
    for k, w in enumerate(te):
        pieces = [tok.encode(w[0])] + [tok.encode(" " + x) for x in w[1:]]
        ids = [i for p in pieces for i in p]
        logp = torch.log_softmax(m(torch.tensor([ids]), m.new_state())[0].float(), -1)
        pos = len(pieces[0])
        for p in pieces[1:]:
            for j, t in enumerate(p): tot -= logp[pos + j - 1, t].item() / math.log(2)
            pos += len(p); n += 1
        if k % 500 == 0: print(f"  {k} sentences, {n} predictions, running {tot / max(1, n):.4f} bits/word ({time.time() - t0:.0f} s)", flush=True)
print(f"R25-ao language model on the first {N} held-out sentences: {tot / n:.4f} bits/word over {n} predictions ({time.time() - t0:.0f} s)", flush=True)
