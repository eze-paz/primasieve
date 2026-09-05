"""TEST 1 -- coarse cross-model forms as SOUND primasieve grounding. Build one 'form' per human category (the
centroid of its words) in EACH model. Label a held-out word by nearest form; COMMIT the label only if LFM and Qwen
AGREE, else ABSTAIN (cross-model agreement = the rejection oracle, primasieve-style). Leave-one-out over 144 words.
Question: does requiring two independent models to agree buy SOUNDNESS (higher committed accuracy + honest abstention
on genuinely ambiguous words) over either model alone? Knockout: shuffle word<->category -> must collapse."""
import numpy as np, os
from platonic_concepts import CATS, WORDS, LAB, RL, RQ, N
cats = list(CATS.keys())


def norm(X): return X / (np.linalg.norm(X, axis=1, keepdims=True) + 1e-9)
NL, NQ = norm(RL), norm(RQ)


def predict(NX, labels, i):
    """category whose centroid (excluding word i) is nearest to word i, in one model's space."""
    best, bc = -9, None
    for c in cats:
        idx = [j for j in range(N) if labels[j] == c and j != i]
        if not idx: continue
        cen = NX[idx].mean(0); cen /= (np.linalg.norm(cen) + 1e-9)
        s = float(NX[i] @ cen)
        if s > best: best, bc = s, c
    return bc


def run(labels):
    single_L = single_Q = 0
    commit = correct = 0
    for i in range(N):
        pl = predict(NL, labels, i); pq = predict(NQ, labels, i)
        single_L += (pl == labels[i]); single_Q += (pq == labels[i])
        if pl == pq:                                  # both models agree -> COMMIT
            commit += 1; correct += (pl == labels[i])
    return dict(accL=single_L / N, accQ=single_Q / N,
                coverage=commit / N, committed_acc=(correct / commit if commit else 0.0))


real = run(LAB)
rng = np.random.default_rng(0)
shuf = list(LAB); rng.shuffle(shuf)
ko = run(shuf)

print("TEST 1 -- cross-model-agreement grounding (leave-one-out over 144 concept words, 12 forms)\n")
print(f"  single-model accuracy:     LFM {real['accL']:.2f}   Qwen {real['accQ']:.2f}")
print(f"  COMMIT (both models agree): coverage {real['coverage']:.2f}   committed accuracy {real['committed_acc']:.2f}")
print(f"    -> agreement filter {'RAISES' if real['committed_acc']>max(real['accL'],real['accQ']) else 'does not raise'}"
      f" precision over either model, abstaining on {1-real['coverage']:.0%} (the ambiguous words).")
print(f"\n  KNOCKOUT (shuffled word<->category): committed acc {ko['committed_acc']:.2f} "
      f"coverage {ko['coverage']:.2f}  (chance {1/len(cats):.2f})")
print(f"\n  VERDICT: forms are {'SOUND grounding' if real['committed_acc']>0.9 and ko['committed_acc']<0.3 else 'partial'}"
      f" -- committed {real['committed_acc']:.2f} vs knockout {ko['committed_acc']:.2f}.")
