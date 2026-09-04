"""IDEA-1 featurizer (runs under Python 3.12 + torch; the external 'SOURCE' step, NOT the solver). For each utterance's
space-stripped CHARACTER string, one teacher-forced forward pass through a small LLM (Qwen2.5-0.5B); read the entropy
of the next-token distribution at each position and map it (offset_mapping) to the CHARACTER-GAP where that token
ends. High next-token entropy at a gap = LLM uncertain what comes next = a boundary proposal (the LLM analog of
n-gram branching entropy). Output per-utterance {words, s, gaps} to _nldata/llm_feats_<corpus>.json; the pure-Python
sound MDL solver (llm_seg.py) consumes it and VERIFIES -- the LLM only PROPOSES, never sees gold, never decides.

--corpus=brp   : real br-phono (phonemic ASCII the LLM never trained on -> tests LLM as a general SEQUENCE model).
--corpus=alice : orthographic English (LLM's lexical knowledge APPLIES -> the real Idea-1 test)."""
import os, sys, re, json, math, random, time
import torch, torch.nn.functional as F
from transformers import AutoTokenizer, AutoModelForCausalLM

D = os.path.join(os.path.dirname(__file__), "_nldata")
MODEL = "Qwen/Qwen2.5-0.5B"
N = int(next((a.split("=")[1] for a in sys.argv if a.startswith("--n=")), 1500))
CORPUS = next((a.split("=")[1] for a in sys.argv if a.startswith("--corpus=")), "brp")

def load_brp():
    return [l.split() for l in open(os.path.join(D, "brent_phono.txt"), encoding="utf-8") if l.strip()]
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

t0 = time.time()
tok = AutoTokenizer.from_pretrained(MODEL)
model = AutoModelForCausalLM.from_pretrained(MODEL, dtype=torch.float32); model.eval()
print(f"loaded {MODEL} in {time.time()-t0:.0f}s; corpus={CORPUS} featurizing {len(streams)} utts", flush=True)

out = []; t1 = time.time()
with torch.no_grad():
    for k, (s, w) in enumerate(zip(streams, utts)):
        enc = tok(s, return_offsets_mapping=True, return_tensors="pt")
        ids = enc["input_ids"]; offs = enc["offset_mapping"][0].tolist()
        logits = model(ids).logits[0]
        gaps = {}
        for i in range(logits.shape[0] - 1):
            p = F.softmax(logits[i], dim=-1)
            H = float(-(p * torch.log2(p + 1e-12)).sum())
            g = offs[i][1]
            if 0 < g < len(s): gaps[g] = max(gaps.get(g, 0.0), H)
        out.append({"words": w, "s": s, "gaps": gaps})
        if (k + 1) % 200 == 0: print(f"  {k+1}/{len(streams)}  [{time.time()-t1:.0f}s]", flush=True)

path = os.path.join(D, f"llm_feats_{CORPUS}.json")
json.dump({"model": MODEL, "corpus": CORPUS, "n": len(out), "utts": out}, open(path, "w"))
print(f"WROTE {path}  ({len(out)} utts, {time.time()-t1:.0f}s)")