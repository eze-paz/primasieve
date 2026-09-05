"""OOD calibration: does the controller GENERALIZE to task structures NOT in the
training templates, or did it just memorize the 6 templates? Same action vocab,
novel compositions/phrasings. This is the knockout that says whether 1.0 was real."""
import torch, torch.nn as nn, time
from transformers import AutoModelForCausalLM, AutoTokenizer

torch.set_num_threads(10)
ckpt = torch.load("controller_head.pt")
LABELS = ckpt["labels"]; L2I = {l: i for i, l in enumerate(LABELS)}
mu, sd = ckpt["mu"], ckpt["sd"]
head = nn.Sequential(nn.Linear(len(mu), 256), nn.GELU(), nn.Dropout(0.1), nn.Linear(256, len(LABELS)))
head.load_state_dict(ckpt["head"]); head.eval()

MODEL = "Qwen/Qwen2.5-0.5B-Instruct"
tok = AutoTokenizer.from_pretrained(MODEL)
enc = AutoModelForCausalLM.from_pretrained(MODEL, dtype=torch.float32, output_hidden_states=True).eval()

@torch.no_grad()
def embed(texts):
    ids = tok(texts, return_tensors="pt", padding=True, truncation=True, max_length=192)
    h = enc(**ids).hidden_states[-1]; m = ids.attention_mask.unsqueeze(-1).float()
    return (h * m).sum(1) / m.sum(1).clamp(min=1)

def S(goal, sofar): return f"GOAL: {goal}\nSTEPS SO FAR:\n" + ("\n".join(sofar) if sofar else "(none)")

# NOVEL structures (not in the 6 training templates), hand-labeled gold next-action:
CASES = [
    # sum of TWO independent lookups (training only had capital-of CHAINS + single divide)
    (S("What is the population of Paris plus the population of Tokyo?", []), "SEARCH"),
    (S("What is the population of Paris plus the population of Tokyo?",
       ["- did SEARCH population of Paris -> found: Paris population is 2000000"]), "SEARCH"),
    (S("What is the population of Paris plus the population of Tokyo?",
       ["- did SEARCH population of Paris -> found: 2000000",
        "- did SEARCH population of Tokyo -> found: 14000000"]), "CALC"),
    (S("What is the population of Paris plus the population of Tokyo?",
       ["- did SEARCH population of Paris -> found: 2000000",
        "- did SEARCH population of Tokyo -> found: 14000000",
        "- did CALC 2000000 + 14000000 -> 16000000"]), "ANSWER"),
    # imperative phrasing (training was all questions)
    (S("Tell me the area of Brazil.", []), "SEARCH"),
    (S("Tell me the area of Brazil.", ["- did SEARCH area of Brazil -> found: 8.5 million km2"]), "ANSWER"),
    # novel creative phrasings
    (S("Draft a slogan for a coffee shop.", []), "REASON"),
    (S("Brainstorm three names for a puppy.", []), "REASON"),
    # novel unanswerable phrasing
    (S("What is the GDP of Atlantis?", []), "SEARCH"),
    (S("What is the GDP of Atlantis?", ["- did SEARCH GDP of Atlantis -> found: (nothing found)"]), "DEFER"),
    # three-step chain (deeper than 2-hop training)
    (S("What is the elevation of the capital of Norway, times 3?", []), "SEARCH"),
    (S("What is the elevation of the capital of Norway, times 3?",
       ["- did SEARCH capital of Norway -> found: Oslo"]), "SEARCH"),
    (S("What is the elevation of the capital of Norway, times 3?",
       ["- did SEARCH capital of Norway -> found: Oslo",
        "- did SEARCH elevation of Oslo -> found: 23 meters"]), "CALC"),
    (S("What is the elevation of the capital of Norway, times 3?",
       ["- did SEARCH capital of Norway -> found: Oslo",
        "- did SEARCH elevation of Oslo -> found: 23 meters",
        "- did CALC 23 * 3 -> 69"]), "ANSWER"),
]
t0 = time.time()
X = embed([c[0] for c in CASES]); Xn = (X - mu) / sd
with torch.no_grad(): pred = head(Xn).argmax(-1)
correct = 0
print("=" * 70); print("OOD generalization (novel task structures, hand-labeled):"); print("=" * 70)
for (state, gold), p in zip(CASES, pred):
    pl = LABELS[p]; ok = pl == gold; correct += ok
    goal = state.split("\n")[0][6:50]; nsteps = state.count("- did")
    print(f"  [{'OK ' if ok else 'XX '}] {goal:46} step{nsteps}: gold={gold:7} pred={pl}")
print("=" * 70)
print(f"OOD accuracy: {correct}/{len(CASES)} = {correct/len(CASES):.2f}  ({time.time()-t0:.0f}s)")
