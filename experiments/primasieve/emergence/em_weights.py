"""EMERGENCE E-11 -- POINT THE ENGINE AT LLM WEIGHTS: is there exact, verifiable structure in a model's embedding table?

Owner's ask (2026-09-07): point the system at LLM weights and see whether it extracts a high-dimensional pattern.
The engine's way of doing that: the weights are a WORLD (a table of vectors), the engine's SOUND knowledge (the
morphology table it already treats as an oracle, WordNet synsets, the numerals) supplies HYPOTHESES about which
vectors should stand in which relation, and every claim carries a SHUFFLED knockout that must fail. This is a
structure probe with knockouts, not a soundness claim: nearest-neighbour decoding in the model's own geometry is
the model's own account of itself, not an oracle over the world. Predictions, committed before running:

  H1 MORPHOLOGY IS A TRANSLATION  E(plural) - E(singular) ~ one constant vector d. Leave-one-out: predict E(s)+d,
     nearest neighbour among whole-word tokens. PREDICTED: accuracy well above the shuffled-pair knockout (which
     must sit near 0); past tense weaker than plural. If the knockout is not near 0, the geometry is decorative.
  H2 SYNONYMY IS PROXIMITY  WordNet same-synset pairs have higher cosine than random pairs and the synonym sits in
     the top-10 neighbours far more often than chance. PREDICTED: yes, with a long tail of misses (polysemy).
  H3 NUMERALS ARE A LINE  E(' 0')...E(' 9') and ' one'...' nine' lie near a 1-D line ordered by value: the
     residual of a best-fit line through them is smaller than for any shuffled ordering. PREDICTED: partially --
     digits yes, number words weaker.
  H4 THE TOLERANCE SET  (Phase 6) the fraction of morphology pairs whose offset lies within eps of d, as eps
     grows, against random pairs: a SEPARATION says the relation is exact-up-to-eps for a measurable core, not a
     statistical tendency. PREDICTED: a core of >= 30% of pairs separates from random at an eps where random is < 5%.

Runs in the throwaway numpy environment (the engine itself is stdlib-only by design and this probe stays outside
core/). Nothing here is trained; nothing is tuned to the outcome; the knockouts are printed beside every number."""
import os, sys, json, re, random, collections
import numpy as np
from safetensors import safe_open
from tokenizers import Tokenizer

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT); sys.path.insert(0, HERE)
import wn_acquire as ACQ
SNAP = sys.argv[sys.argv.index("--snapshot") + 1] if "--snapshot" in sys.argv else \
    r"C:/Users/aezequiel/.cache/huggingface/hub/models--Qwen--Qwen2.5-0.5B/snapshots/060db6499f32faf8b98477b0a26969ef7d8b9987"
UNIMORPH = sys.argv[sys.argv.index("--unimorph") + 1] if "--unimorph" in sys.argv else os.path.join(ROOT, "_nldata", "unimorph_eng.tsv")
rng = random.Random(1)


def load():
    tok = Tokenizer.from_file(os.path.join(SNAP, "tokenizer.json"))
    f = safe_open(os.path.join(SNAP, "model.safetensors"), "pt")          # bfloat16: read through torch
    key = next(k for k in f.keys() if "embed_tokens" in k)
    E = f.get_tensor(key).float().numpy()
    vocab = tok.get_vocab()
    # whole lowercase words as single tokens with a leading space (GPT-2 style 'Ġ')
    words = {}
    for t, i in vocab.items():
        if t.startswith("Ġ") and t[1:].isalpha() and t[1:].islower(): words[t[1:]] = i
    return E, words


def unit(v): return v / (np.linalg.norm(v, axis=-1, keepdims=True) + 1e-9)


def nn_rank(E_unit, ids, q, target):
    """rank of `target` among `ids` by cosine to q (0 = nearest)."""
    sims = E_unit[ids] @ unit(q)
    order = np.argsort(-sims)
    pos = {ids[j]: r for r, j in enumerate(order[:200])}
    return pos.get(target, 999)


def morphology_pairs(words, feature):
    """(lemma, form) pairs from the unimorph table for one feature string, both single whole-word tokens."""
    pairs = []
    if not os.path.exists(UNIMORPH): return pairs
    for line in open(UNIMORPH, encoding="utf-8"):
        p = line.rstrip("\n").split("\t")
        if len(p) < 3: continue
        lemma, form, feats = p[0], p[1], p[2]
        if feats == feature and lemma in words and form in words and lemma != form: pairs.append((lemma, form))
    return sorted(set(pairs))


def h1_translation(E, U, words, pairs, label, ids_all):
    if len(pairs) < 20: print(f"  {label}: only {len(pairs)} pairs, skipped"); return None
    pairs = pairs[:400]
    def run(pairs_):
        offs = np.stack([E[words[f]] - E[words[l]] for l, f in pairs_])
        hits = 0
        for k, (l, f) in enumerate(pairs_):
            d = (offs.sum(0) - offs[k]) / (len(pairs_) - 1)          # leave-one-out mean offset
            q = E[words[l]] + d
            cand = [i for i in ids_all if i != words[l]]
            hits += nn_rank(U, cand, q, words[f]) == 0
        return hits / len(pairs_), offs
    acc, offs = run(pairs)
    shuffled = [(l, pairs[(k + 7) % len(pairs)][1]) for k, (l, _) in enumerate(pairs)]   # every lemma with another's form
    acc_sh, _ = run(shuffled)
    # H4 tolerance set: offsets within eps of the mean vs random pairs' offsets
    d = offs.mean(0); dist = np.linalg.norm(offs - d, axis=1)
    rand_pairs = [(rng.choice(list(words)), rng.choice(list(words))) for _ in range(len(pairs))]
    roffs = np.stack([E[words[b]] - E[words[a]] for a, b in rand_pairs]); rdist = np.linalg.norm(roffs - d, axis=1)
    eps = np.percentile(rdist, 5)
    core = float((dist <= eps).mean())
    print(f"  {label}: {len(pairs)} pairs  nearest-neighbour accuracy {acc:.3f}   shuffled-pair knockout {acc_sh:.3f}   "
          f"[H4] core within eps (5% of random) {core:.3f}")
    return acc, acc_sh, core


def h2_synonymy(E, U, words, ids_all):
    idx = ACQ._index("noun"); dat = ACQ._data("noun")
    pairs = set()
    for w, offs in idx.items():
        if w not in words: continue
        for o in offs[:1]:
            lem = [l for l in dat.get(o, ([], []))[0] if l in words and l != w]
            for l in lem[:1]: pairs.add(tuple(sorted((w, l))))
    pairs = sorted(pairs)[:600]
    if len(pairs) < 50: print(f"  synonymy: only {len(pairs)} pairs, skipped"); return None
    cos = np.array([float(U[words[a]] @ U[words[b]]) for a, b in pairs])
    rnd = np.array([float(U[words[a]] @ U[words[rng.choice(list(words))]]) for a, _ in pairs])
    top10 = np.mean([nn_rank(U, [i for i in ids_all if i != words[a]], E[words[a]], words[b]) < 10 for a, b in pairs])
    top10_r = np.mean([nn_rank(U, [i for i in ids_all if i != words[a]], E[words[a]], words[rng.choice(list(words))]) < 10 for a, _ in pairs])
    print(f"  synonymy (WordNet noun, first synset): {len(pairs)} pairs  mean cosine {cos.mean():.3f} vs random {rnd.mean():.3f}   "
          f"synonym in top-10 neighbours {top10:.3f} vs random word {top10_r:.3f}")
    return float(cos.mean()), float(rnd.mean()), float(top10), float(top10_r)


def h3_numerals(E, words, tok_vocab_ids):
    def line_resid(vecs):
        X = np.stack(vecs); n = len(X); t = np.arange(n, dtype=np.float32); t = (t - t.mean())
        mu = X.mean(0); slope = (t[:, None] * (X - mu)).sum(0) / (t ** 2).sum()
        fit = mu + t[:, None] * slope
        return float(np.linalg.norm(X - fit) / np.linalg.norm(X - mu))
    out = {}
    for label, toks in (("digits", [str(i) for i in range(10)]), ("number words", ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"])):
        ids = [tok_vocab_ids.get("Ġ" + t) for t in toks]
        if any(i is None for i in ids): print(f"  {label}: missing tokens, skipped"); continue
        vecs = [E[i] for i in ids]
        r = line_resid(vecs)
        shuf = []
        for _ in range(200):
            p = list(range(10)); rng.shuffle(p); shuf.append(line_resid([vecs[i] for i in p]))
        better = float(np.mean([s > r for s in shuf]))
        print(f"  {label}: line residual (fraction of variance off the line) {r:.3f}; shuffled orderings worse than the true order {better:.3f} of the time (chance 0.5)")
        out[label] = (r, better)
    return out


if __name__ == "__main__":
    print("EMERGENCE E-11 -- the embedding table as a world; hypotheses from what the engine knows soundly; knockouts beside every number\n")
    E, words = load()
    tok = Tokenizer.from_file(os.path.join(SNAP, "tokenizer.json")); vocab = tok.get_vocab()
    U = unit(E)
    ids_all = sorted(words.values())
    print(f"embedding table {E.shape}; whole-word lowercase tokens {len(words)}\n")
    print("H1/H4 morphology as translation (unimorph pairs; leave-one-out mean offset; shuffled-pair knockout):")
    res = {}
    for feat, label in (("N;PL", "plural"), ("V;PST", "past tense"), ("V;V.PTCP;PRS", "present participle"), ("V;PRS;3;SG", "3rd person singular")):
        res[label] = h1_translation(E, U, words, morphology_pairs(words, feat), label, ids_all)
    print("\nH2 synonymy as proximity:")
    res["synonymy"] = h2_synonymy(E, U, words, ids_all)
    print("\nH3 numerals as a line:")
    res["numerals"] = h3_numerals(E, words, vocab)
    ok = res.get("plural") and res["plural"][0] > 0.3 and res["plural"][1] < 0.05
    print("\nE11 WEIGHT PROBE: " + ("STRUCTURE -- morphology is a translation the engine can verify by nearest neighbour, and the shuffled knockout fails"
                                  if ok else "NO EXACT STRUCTURE FOUND at the bar (plural accuracy > 0.30 with knockout < 0.05)"))
    json.dump({k: v for k, v in res.items()}, open(os.path.join(HERE, "em_weights_result.json"), "w"), indent=1, default=str)
