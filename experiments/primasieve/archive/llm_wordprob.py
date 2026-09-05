"""IDEA-1b featurizer (Python 3.12 + torch): the TIGHT coupling. Instead of seeding, put the LLM into the MDL
OBJECTIVE. Precompute the LLM's word-probability for EVERY candidate span (contiguous substring up to maxlen that
occurs in the corpus) = -log2 P_LLM(' '+w) summed over its tokens (surprisal of w as a standalone word after a
space). Common English words -> low bits; gibberish -> high bits. The pure-Python solver (llm_mdl.py) uses this as
the lexicon spelling cost in place of the char-model term; the LLM knows the LEXICON, the sound MDL still decides the
segmentation. Output _nldata/llm_wordbits_<corpus>.json. LLM only scores strings, never sees gold."""
import os, sys, re, json, math, random, time
import torch, torch.nn.functional as F
from transformers import AutoTokenizer, AutoModelForCausalLM

D = os.path.join(os.path.dirname(__file__), "_nldata")
MODEL = "Qwen/Qwen2.5-0.5B"
N = int(next((a.split("=")[1] for a in sys.argv if a.startswith("--n=")), 1200))
CORPUS = next((a.split("=")[1] for a in sys.argv if a.startswith("--corpus=")), "alice")
MAXLEN = 10

def load_brp(): return [l.split() for l in open(os.path.join(D, "brent_phono.txt"), encoding="utf-8") if l.strip()]
def load_alice():
    raw = open(os.path.join(D, "alice.txt"), encoding="utf-8", errors="ignore").read()
    m = re.search(r"\*\*\* START OF.*?\*\*\*(.*?)\*\*\* END OF", raw, re.S); body = m.group(1) if m else raw
    out = []
    for s in re.split(r"[.!?]+", body):
        w = re.findall(r"[a-z]+", s.lower())
        if 2 <= len(w) <= 40: out.append(w)
    return out

utts = (load_brp() if CORPUS == "brp" else load_alice())
random.Random(2024).shuffle(utts); utts = utts[:N]
streams = ["".join(w) for w in utts]

# collect contiguous substrings up to MAXLEN occurring >=2x (singletons fall back to char cost in the solver)
import collections
cnt = collections.Counter()
for s in streams:
    L = len(s)
    for i in range(L):
        for j in range(i + 1, min(L, i + MAXLEN) + 1): cnt[s[i:j]] += 1
subs = sorted((w for w, c in cnt.items() if c >= 2), key=len)
print(f"corpus={CORPUS} {len(streams)} utts; {len(subs)} substrings (<= {MAXLEN}, count>=2) to score", flush=True)

t0 = time.time()
tok = AutoTokenizer.from_pretrained(MODEL)
model = AutoModelForCausalLM.from_pretrained(MODEL, dtype=torch.float32); model.eval()
bos = tok.bos_token_id if tok.bos_token_id is not None else tok.eos_token_id
print(f"loaded in {time.time()-t0:.0f}s; scoring...", flush=True)

LN2 = math.log(2)
def score_batch(words):
    seqs = [[bos] + tok(" " + w, add_special_tokens=False)["input_ids"] for w in words]
    mx = max(len(s) for s in seqs)
    ids = torch.full((len(seqs), mx), bos, dtype=torch.long)
    mask = torch.zeros((len(seqs), mx), dtype=torch.float32)
    for r, s in enumerate(seqs): ids[r, :len(s)] = torch.tensor(s); mask[r, 1:len(s)] = 1.0
    with torch.no_grad():
        logits = model(ids).logits                               # [B, T, V]
        pred = logits[:, :-1, :]                                 # predict token t+1 from position t
        tgt = ids[:, 1:]                                         # [B, T-1]
        tgt_logit = pred.gather(-1, tgt.unsqueeze(-1)).squeeze(-1)
        lse = torch.logsumexp(pred, dim=-1)                      # normalizer, no full softmax materialized
        logp = tgt_logit - lse                                   # [B, T-1] nats
        bits = (-(logp * mask[:, 1:]).sum(1) / LN2).tolist()
    return bits

out = {}; t1 = time.time(); B = 64
for k in range(0, len(subs), B):
    chunk = subs[k:k + B]
    for w, b in zip(chunk, score_batch(chunk)): out[w] = round(b, 4)
    if (k // B) % 50 == 0: print(f"  {k}/{len(subs)}  [{time.time()-t1:.0f}s]", flush=True)

path = os.path.join(D, f"llm_wordbits_{CORPUS}.json")
json.dump({"model": MODEL, "corpus": CORPUS, "n": N, "maxlen": MAXLEN, "bits": out}, open(path, "w"))
print(f"WROTE {path}  ({len(out)} words, {time.time()-t1:.0f}s)")