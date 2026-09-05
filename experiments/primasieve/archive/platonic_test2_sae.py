"""TEST 2 -- SAE atomic forms. Raw PCA/CCA axes are superposed (Test-of-concepts purity ~0.31). A sparse autoencoder
forces MONOSEMANTIC dictionary features. Train an over-complete SAE (ReLU + L1) on each model's word reps separately,
name each feature by its top-activating words, and check (a) monosemanticity = are a feature's top words one human
category? and (b) UNIVERSALITY = does a matching feature (same top-word set) exist in the OTHER model? A form is REAL
only if it is monosemantic AND appears in both models. Compare feature purity to the CCA-axis purity (0.31)."""
import numpy as np, os, torch, torch.nn as nn
from collections import Counter
from platonic_concepts import CATS, WORDS, LAB, RL, RQ, N
torch.manual_seed(0); np.random.seed(0)
cats = list(CATS.keys())


class SAE(nn.Module):
    def __init__(self, d, m):
        super().__init__()
        self.enc = nn.Linear(d, m); self.dec = nn.Linear(m, d, bias=False)
        with torch.no_grad():                                 # tied-ish init, unit-norm dict
            self.dec.weight.copy_(torch.randn(d, m)); self.dec.weight /= self.dec.weight.norm(dim=0, keepdim=True)

    def forward(self, x):
        h = torch.relu(self.enc(x - self.b) if hasattr(self, "b") else self.enc(x))
        return h, self.dec(h)


def train_sae(X, m=64, l1=4e-3, epochs=4000, lr=2e-3):
    d = X.shape[1]
    Xc = X - X.mean(0, keepdims=True)
    Xt = torch.tensor(Xc, dtype=torch.float32)
    sae = SAE(d, m); opt = torch.optim.Adam(sae.parameters(), lr=lr)
    for e in range(epochs):
        h, xr = sae(Xt)
        loss = ((xr - Xt) ** 2).sum(1).mean() + l1 * h.abs().sum(1).mean()
        opt.zero_grad(); loss.backward()
        with torch.no_grad():                                 # keep decoder columns unit-norm
            sae.dec.weight /= sae.dec.weight.norm(dim=0, keepdim=True).clamp_min(1e-6)
        opt.step()
    with torch.no_grad():
        H = torch.relu(sae.enc(Xt)).numpy()
    return H                                                  # (N, m) feature activations


def feature_words(H, k=5):
    """for each feature, its top-k activating words + their dominant category and purity."""
    feats = []
    for j in range(H.shape[1]):
        a = H[:, j]
        if (a > 1e-4).sum() < 2:                              # dead feature
            feats.append(None); continue
        top = np.argsort(a)[::-1][:k]
        labs = [LAB[i] for i in top]; words = [WORDS[i] for i in top]
        dom, cnt = Counter(labs).most_common(1)[0]
        feats.append((dom, cnt / k, words))
    return feats


def match_universal(fa, fb):
    """count features in A that have a B-feature sharing >=3/5 top words (universal forms)."""
    setsB = [set(f[2]) for f in fb if f]
    uni = 0; pairs = []
    for f in fa:
        if not f: continue
        best = max((len(set(f[2]) & sb) for sb in setsB), default=0)
        if best >= 3:
            uni += 1; pairs.append(f)
    return uni, pairs


if __name__ == "__main__":
    print("TEST 2 -- SAE atomic forms (over-complete sparse autoencoder per model, 64 features)\n")
    HL = train_sae(RL, m=64); HQ = train_sae(RQ, m=64)
    fL = feature_words(HL); fQ = feature_words(HQ)
    aliveL = [f for f in fL if f]; aliveQ = [f for f in fQ if f]
    purL = np.mean([f[1] for f in aliveL]); purQ = np.mean([f[1] for f in aliveQ])
    monoL = sum(f[1] >= 0.8 for f in aliveL); monoQ = sum(f[1] >= 0.8 for f in aliveQ)
    print(f"  live features: LFM {len(aliveL)}/64  Qwen {len(aliveQ)}/64")
    print(f"  feature purity (top-5 words one category):  LFM {purL:.2f}  Qwen {purQ:.2f}   (CCA-axis purity was 0.31)")
    print(f"  MONOSEMANTIC features (purity>=0.8):         LFM {monoL}  Qwen {monoQ}")
    uni, pairs = match_universal(fL, fQ)
    print(f"  UNIVERSAL features (a matching feature in BOTH models, >=3/5 shared top words): {uni}")
    # knockout: shuffle word<->rep pairing for Qwen -> universality must collapse
    rng = np.random.default_rng(1); perm = rng.permutation(N)
    HQk = HQ[perm]; fQk = feature_words(HQk)
    unik, _ = match_universal(fL, fQk)
    print(f"    knockout (shuffled Qwen words): universal {unik}\n")
    print("  named atomic forms (monosemantic, cross-model, sorted by category):")
    seen = set()
    for dom, pur, words in sorted([f for f in pairs if f[1] >= 0.8], key=lambda x: x[0]):
        key = (dom, tuple(sorted(words)))
        if key in seen: continue
        seen.add(key)
        print(f"    [{dom:>9}] {' '.join(words)}")
