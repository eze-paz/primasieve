"""TEST 2 (scaled) -- SAE atomic forms on 1000 words, cross-model UNIVERSALITY (no category labels needed).
Train an over-complete SAE per model on the 1000-word reps, name each feature by top-activating words, and count
UNIVERSAL features: a feature whose top-word set also appears (>=3/5 overlap) as some feature in the OTHER model.
Knockout: shuffle the word<->word correspondence -> universality must collapse to chance. This is the atomic-form
version of the platonic claim: do two independently-trained models learn the SAME sparse features?"""
import numpy as np, os, torch
from platonic_test2_sae import train_sae
here = os.path.dirname(__file__)


def load_words(n):
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained("Qwen/Qwen2.5-1.5B")
    words, seen = [], set()
    for i in range(tok.vocab_size):
        s = tok.convert_ids_to_tokens(i)
        if s and s.startswith("Ġ"):
            w = s[1:]
            if w.isalpha() and w.islower() and 3 <= len(w) <= 12 and w not in seen:
                seen.add(w); words.append(w)
        if len(words) >= n: break
    return words


def top_word_sets(H, words, k=5):
    out = []
    for j in range(H.shape[1]):
        a = H[:, j]
        if (a > 1e-4).sum() < 2: out.append(None); continue
        top = np.argsort(a)[::-1][:k]
        out.append([words[i] for i in top])
    return out


def universal(fa, fb, thr=3):
    setsB = [set(f) for f in fb if f]
    hits = [f for f in fa if f and max((len(set(f) & sb) for sb in setsB), default=0) >= thr]
    return hits


if __name__ == "__main__":
    z = np.load(os.path.join(here, "reps_big.npz"))
    RL, RQ = z["RL"], z["RQ"]
    words = load_words(RL.shape[1])
    li, qi = int(RL.shape[0] * 0.75), int(RQ.shape[0] * 0.75)     # mid-late layer (near peak alignment)
    print(f"TEST 2 scaled -- SAE on {len(words)} words, LFM L{li} / Qwen L{qi}, 128 features each\n")
    HL = train_sae(RL[li], m=128, epochs=3000); HQ = train_sae(RQ[qi], m=128, epochs=3000)
    fL = top_word_sets(HL, words); fQ = top_word_sets(HQ, words)
    aliveL = sum(f is not None for f in fL); aliveQ = sum(f is not None for f in fQ)
    uni = universal(fL, fQ)
    rng = np.random.default_rng(1); perm = rng.permutation(len(words))
    fQk = top_word_sets(HQ[perm], words)
    unik = universal(fL, fQk)
    print(f"  live features: LFM {aliveL}/128  Qwen {aliveQ}/128")
    print(f"  UNIVERSAL features (>=3/5 shared top words in BOTH models): {len(uni)}")
    print(f"    knockout (shuffled correspondence): {len(unik)}  (chance)\n")
    print(f"  example universal atomic forms (top words shared across both independently-trained models):")
    seen = set()
    for f in uni:
        key = tuple(sorted(f))
        if key in seen: continue
        seen.add(key)
        print(f"    {' '.join(f)}")
        if len(seen) >= 20: break
