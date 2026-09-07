"""EMERGENCE E-11b -- (A) meaning in the raw weights, unsupervised: the principal directions of the word subspace,
decoded by the words at their ends. (B) the CAUSAL test: the plural operator extracted from the embedding table,
injected into the residual stream while the model predicts -- does the model's next word become plural?
Knockouts: a random direction of the same norm (must do nothing) and the negated operator (should push singular).
The model is the oracle here: behaviour, not geometry."""
import os, sys, json, random, collections
import numpy as np, torch
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from qwen_fwd import Qwen
from em_weights import morphology_pairs, UNIMORPH

SNAP = r"C:/Users/aezequiel/.cache/huggingface/hub/models--Qwen--Qwen2.5-0.5B/snapshots/060db6499f32faf8b98477b0a26969ef7d8b9987"
rng = random.Random(3); torch.manual_seed(3)

m = Qwen(SNAP)
E = m.w["model.embed_tokens.weight"].numpy()
vocab = m.tok.get_vocab()
words = {t[1:]: i for t, i in vocab.items() if t.startswith("Ġ") and t[1:].isalpha() and t[1:].islower()}
inv = {i: w for w, i in words.items()}
ids = np.array(sorted(words.values()))

# ---------------------------------------------------------------- (A) unsupervised: principal directions, decoded
print("(A) MEANING IN THE RAW WEIGHTS, no hypothesis: principal directions of the whole-word subspace, read by the words at each end\n")
X = E[ids]; mu = X.mean(0); Xc = X - mu
U_, S, Vt = np.linalg.svd(Xc[rng.sample(range(len(Xc)), 8000)], full_matrices=False)
for c in range(8):
    proj = Xc @ Vt[c]
    lo = [inv[ids[j]] for j in np.argsort(proj)[:9]]; hi = [inv[ids[j]] for j in np.argsort(-proj)[:9]]
    print(f"  PC{c+1} ({100*S[c]**2/(S**2).sum():4.1f}% var)   -:{' '.join(lo)}\n{'':30s}+:{' '.join(hi)}")

# plural table: which whole words are plural forms (N;PL) and their singulars
plural_of = {}
for l, f in morphology_pairs(words, "N;PL"): plural_of[l] = f
sing_of = {f: l for l, f in plural_of.items()}
pairs = sorted(plural_of.items())
d_emb = np.stack([E[words[f]] - E[words[l]] for l, f in pairs]).mean(0)
print(f"\nplural operator d from {len(pairs)} embedding pairs, |d| = {np.linalg.norm(d_emb):.3f}")

# ---------------------------------------------------------------- (B) causal: inject d, watch the next word
prompts = ["I looked at the", "She picked up the", "He pointed at the", "We talked about the", "They found the",
           "There was a problem with the", "I need to buy a new", "Please pass me the", "The child drew a",
           "Yesterday I saw a", "He wrote about his", "She thanked her", "We visited the old", "Tell me about your",
           "The museum displayed a", "I forgot my", "He lost his", "The teacher praised the", "My neighbour owns a",
           "In the garden there is a"]


def plural_score(ids_prompt, inject):
    """log-odds of plural over singular among the top nouns the model proposes: sum over the top-30 tokens of
    P(plural forms) vs P(singular forms) as classified by the morphology table."""
    lg = m.logits(ids_prompt, inject); p = torch.softmax(lg, -1)
    top = torch.topk(p, 40).indices.tolist()
    pl = sum(float(p[t]) for t in top if inv.get(t) in sing_of)
    sg = sum(float(p[t]) for t in top if inv.get(t) in plural_of)
    return pl, sg, [m.decode([t]) for t in top[:4]]


print("\n(B) CAUSAL TEST: add the operator to the residual stream at the last position after layer L; next-word plural mass vs singular mass\n")
rand = np.random.RandomState(3).randn(*d_emb.shape).astype(np.float32); rand *= np.linalg.norm(d_emb) / np.linalg.norm(rand)
results = {}
for L in (0, 3, 6, 10, 14):
    for alpha in (4.0, 8.0, 16.0):
        row = {}
        for name, vec in (("plural d", d_emb), ("random", rand), ("-d", -d_emb)):
            flips = 0; dpl = 0.0; n = 0
            for pr in prompts:
                ids_p = m.encode(pr)
                pl0, sg0, top0 = plural_score(ids_p, None)
                pl1, sg1, top1 = plural_score(ids_p, (L, torch.tensor(vec * alpha), len(ids_p) - 1))
                dpl += (pl1 - sg1) - (pl0 - sg0); n += 1
                flips += (top1[0] != top0[0]) and (inv.get(m.encode(top1[0])[-1]) in sing_of)
            row[name] = (dpl / n, flips)
        results[(L, alpha)] = row
        print(f"  layer {L:2d} x{alpha:4.0f}:  plural d: mass shift {row['plural d'][0]:+.3f}, top-1 became a plural in {row['plural d'][1]:2d}/{len(prompts)}   "
              f"| random: {row['random'][0]:+.3f}, {row['random'][1]:2d}   | -d: {row['-d'][0]:+.3f}, {row['-d'][1]:2d}")

best = max(results.items(), key=lambda kv: kv[1]["plural d"][1] - kv[1]["random"][1])
(L, a), row = best
print(f"\nbest setting layer {L} x{a:.0f}: plural d flips {row['plural d'][1]}/{len(prompts)} vs random {row['random'][1]}/{len(prompts)}; examples:")
for pr in prompts[:6]:
    ids_p = m.encode(pr)
    print(f"    {pr!r:34s} {plural_score(ids_p, None)[2]}  ->  {plural_score(ids_p, (L, torch.tensor(d_emb * a), len(ids_p) - 1))[2]}")
verdict = row["plural d"][1] >= 0.5 * len(prompts) and row["random"][1] <= 0.1 * len(prompts)
print("\nE11b CAUSAL: " + ("the operator read off the weights CHANGES THE MODEL'S BEHAVIOUR as predicted and a random direction does not"
                        if verdict else "the operator does not steer behaviour at the bar (>= 50% flips, random <= 10%)"))
