# Coax the SAME named crystals from different models and compare their geometry.
# A crystal = a named concept direction, extracted by contrastive mean-pooling:
#   crystal_c = mean(pooled activations over concept-c sentences) - global mean.
# Extract the same concept set from LFM2.5-350M and Qwen2.5-1.5B (different dims),
# then ask: do the two models ARRANGE the concepts the same way?
#   (a) relational: correlate the 32x32 concept-similarity matrices (dim-agnostic)
#   (b) family block structure: same-family sim vs cross-family, per model
#   (c) cross-model alignment: Procrustes map fit on TRAIN concepts, retrieval on held-out
import torch, math, torch.nn.functional as F
from transformers import AutoTokenizer, AutoModelForCausalLM
torch.set_num_threads(10); torch.manual_seed(0)

FAMILIES = {
 "country": ["France","Japan","Egypt","Brazil"],
 "emotion": ["anger","joy","grief","fear"],
 "animal":  ["elephant","eagle","shark","wolf"],
 "science": ["physics","biology","chemistry","mathematics"],
 "food":    ["bread","coffee","cheese","chocolate"],
 "music":   ["jazz","piano","orchestra","rhythm"],
 "nature":  ["mountain","ocean","forest","desert"],
 "abstract":["justice","freedom","war","money"],
}
CONCEPTS = [(fam, w) for fam, ws in FAMILIES.items() for w in ws]

# a few templates so the crystal reflects the concept, not one sentence's syntax
TEMPLATES = [
 "The {} was central to everything that happened next.",
 "People have always been fascinated by {}.",
 "Nothing compares to the feeling of {}.",
 "Scholars wrote many books about {}.",
 "She thought deeply about {} that evening.",
 "In the end, it all came down to {}.",
]

def extract(model_id):
    tok = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)
    m = AutoModelForCausalLM.from_pretrained(model_id, dtype=torch.float32,
        output_hidden_states=True, trust_remote_code=True).eval()
    L = m.config.num_hidden_layers // 2
    dim = m.config.hidden_size
    vecs = []
    with torch.no_grad():
        for fam, w in CONCEPTS:
            pooled = []
            for t in TEMPLATES:
                ids = tok(t.format(w), return_tensors="pt")
                h = m(**ids).hidden_states[L][0]          # (seq, dim)
                pooled.append(h.mean(0))                  # mean-pool the sentence
            vecs.append(torch.stack(pooled).mean(0))      # concept crystal (pre-centering)
    V = torch.stack(vecs)                                 # (C, dim)
    V = V - V.mean(0)                                     # contrast against global mean
    del m
    print(f"{model_id}: layer {L} dim {dim}", flush=True)
    return F.normalize(V, dim=1)

Va = extract("LiquidAI/LFM2.5-350M")
Vb = extract("Qwen/Qwen2.5-1.5B-Instruct")

def simmat(V): return V @ V.T
Sa, Sb = simmat(Va), simmat(Vb)
C = len(CONCEPTS); iu = torch.triu_indices(C, C, 1)
a, b = Sa[iu[0], iu[1]], Sb[iu[0], iu[1]]
pear = ((a - a.mean()) * (b - b.mean())).mean() / (a.std() * b.std())
# spearman
ra = a.argsort().argsort().float(); rb = b.argsort().argsort().float()
spear = ((ra - ra.mean()) * (rb - rb.mean())).mean() / (ra.std() * rb.std())
print(f"\nRelational agreement between models (32x32 concept-sim matrices):")
print(f"  Pearson r = {pear:.3f}   Spearman = {spear:.3f}   (0=unrelated, 1=identical geometry)")

fams = [f for f, _ in CONCEPTS]
def block_ratio(S):
    same = []; diff = []
    for i in range(C):
        for j in range(i + 1, C):
            (same if fams[i] == fams[j] else diff).append(S[i, j].item())
    return sum(same) / len(same), sum(diff) / len(diff)
for tag, S in (("LFM", Sa), ("Qwen", Sb)):
    s, d = block_ratio(S)
    print(f"  {tag}: same-family sim={s:.3f}  cross-family sim={d:.3f}  separation={s-d:.3f}")

# cross-model Procrustes: fit map on train concepts, retrieval accuracy on held-out
torch.manual_seed(1)
perm = torch.randperm(C); tr, te = perm[:24], perm[24:]
W = torch.linalg.lstsq(Va[tr], Vb[tr]).solution          # Va@W ~ Vb  (dimA->dimB)
pred = F.normalize(Va[te] @ W, dim=1)
sims = pred @ F.normalize(Vb[te], dim=1).T               # (nte, nte)
rank1 = (sims.argmax(1) == torch.arange(len(te))).float().mean()
print(f"\nCross-model alignment (Procrustes, {len(te)} held-out concepts):")
print(f"  held-out match retrieval @1 = {rank1:.2f}  (chance = {1/len(te):.2f})")
for k, idx in enumerate(te):
    j = sims[k].argmax().item()
    hit = "OK" if te[j] == idx else f"-> {CONCEPTS[te[j]][1]}"
    print(f"    {CONCEPTS[idx][1]:12s} {hit}")
