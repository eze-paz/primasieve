"""R25-c: the learner refines its own word groups by its own prediction score on real book text (R25_prereg.md).
Groups persist in r25_classes.json and are refined further at every run, never rebuilt. Starting point on the first
run: the induced k-means classes (r24_classes via r24_events.induce_verbish). Each pass moves every frequent word to
the group under which a class-bigram model of the training books has the highest likelihood (exchange clustering).
Score: bits per token of the class-bigram model on held-out books (books the counts never saw). Kept only if it falls.
Run: python learned/base/r25_classes.py [--passes N] [--vocab N]"""
import os, sys, json, math, collections, time
import numpy as np
ARGV = list(sys.argv)
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE)); os.chdir(HERE); sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(ROOT, "learned"))
import r24_tlm as T, r24_events as E, r24_books as B, data as D0

STORE = os.path.join(HERE, "r25_classes.json")


def sents_of(paras):
    for p in paras:
        for s in T.SENT.split(p["text"]):
            w = [x.lower() for x in T.TOK.findall(s) if x.isalpha()]
            if len(w) >= 2: yield w


def f(x): return np.where(x > 0, x * np.log(np.maximum(x, 1e-12)), 0.0)


def main():
    t0 = time.time(); passes = int(ARGV[ARGV.index("--passes") + 1]) if "--passes" in ARGV else 4
    vmax = int(ARGV[ARGV.index("--vocab") + 1]) if "--vocab" in ARGV else 8000
    train_b, test_b = D0.books()
    train_p = B.paragraphs(train_b, 150000); test_p = B.paragraphs(test_b, 20000)
    E.induce_verbish([p["text"] for p in train_p], k=200)
    uni = collections.Counter(); L = collections.defaultdict(collections.Counter); Rn = collections.defaultdict(collections.Counter)
    for w in sents_of(train_p):
        for i, x in enumerate(w):
            uni[x] += 1
            if i: L[x][w[i - 1]] += 1; Rn[w[i - 1]][x] += 1
    vocab = [w for w, c in uni.most_common() if c >= 5]
    if os.path.exists(STORE):
        cls = json.load(open(STORE, encoding="utf-8")); src = "the learner's own saved groups"
    else:
        cls = {w: E.CLASS[w] for w in vocab if w in E.CLASS}; src = "the induced k-means classes"
    C = max(cls.values()) + 2; REST = C - 1                                               # one extra group for words with no group yet
    cls = {w: cls.get(w, REST) for w in vocab}
    print(f"R25-c start from {src}: {len(vocab)} words, {C} groups, training tokens {sum(uni.values())} ({time.time() - t0:.0f} s)", flush=True)

    def heldout_bits(cl):
        C = max(cl.values()) + 2
        N = np.zeros((C + 1, C + 1)); n = np.zeros(C + 1); UNK = C
        cof = lambda x: cl.get(x, UNK)
        for w in sents_of(train_p):
            for i, x in enumerate(w):
                n[cof(x)] += 1
                if i: N[cof(w[i - 1]), cof(x)] += 1
        rows = N.sum(1); bits = 0.0; tok = 0; a = 0.1
        for w in sents_of(test_p):
            for i in range(1, len(w)):
                c0, c1 = cof(w[i - 1]), cof(w[i])
                pc = (N[c0, c1] + a) / (rows[c0] + a * (C + 1))
                pw = (uni[w[i]] / n[c1]) if (w[i] in cl and n[c1] > 0) else (1.0 / (sum(uni.values())))
                bits -= math.log2(pc * pw); tok += 1
        return bits / tok

    b0 = heldout_bits(cls); print(f"R25-c held-out bits/token at start: {b0:.4f}", flush=True)
    for ps in range(passes):
        N = np.zeros((C, C)); n = np.zeros(C)
        for w, c in uni.items():
            if w in cls: n[cls[w]] += c
        for x, ps_ in L.items():
            if x not in cls: continue
            for p, k in ps_.items():
                if p in cls: N[cls[p], cls[x]] += k
        moves = 0
        for w in vocab[:vmax]:
            a = cls[w]; cnt = uni[w]
            lw = np.zeros(C); rw = np.zeros(C)
            for p, k in L[w].items():
                if p in cls and p != w: lw[cls[p]] += k
            for x, k in Rn[w].items():
                if x in cls and x != w: rw[cls[x]] += k
            N[:, a] -= lw; N[a, :] -= rw; n[a] -= cnt
            gain = (f(N + rw[None, :]) - f(N)).sum(1) + (f(N + lw[:, None]) - f(N)).sum(0) - 2 * (f(n + cnt) - f(n))
            k = int(np.argmax(gain))
            N[:, k] += lw; N[k, :] += rw; n[k] += cnt
            if k != a: cls[w] = k; moves += 1
        b1 = heldout_bits(cls)
        print(f"R25-c pass {ps + 1}: {moves} words moved; held-out bits/token {b1:.4f} ({time.time() - t0:.0f} s)", flush=True)
        if b1 < b0: json.dump(cls, open(STORE, "w", encoding="utf-8")); b0 = b1
        else:
            print("R25-c held-out score did not improve; groups from the previous pass kept", flush=True)
            if os.path.exists(STORE): cls = {w: c for w, c in json.load(open(STORE, encoding="utf-8")).items()}   # R25-c3: really go back to the saved groups
            break
    if "--split" in ARGV:                                                                 # R25-c3: the learner may split a group in two when that predicts held-out books better
        z = np.load(os.path.join(HERE, "r25_vectors.npz")); VEC = {w: v for w, v in zip(z["vocab"].tolist(), z["vecs"])}
        tries = int(ARGV[ARGV.index("--split") + 1]) if ARGV.index("--split") + 1 < len(ARGV) and ARGV[ARGV.index("--split") + 1].isdigit() else 30
        size = collections.Counter()
        for w, c in cls.items(): size[c] += uni[w]
        kept = 0
        for g, _ in size.most_common(tries):
            ws = [w for w in cls if cls[w] == g and w in VEC]
            if len(ws) < 8: continue
            X = np.stack([VEC[w] for w in ws]); rng = np.random.default_rng(0); cent = X[rng.choice(len(ws), 2, replace=False)]
            for _ in range(10):
                lab = (X @ cent.T).argmax(1)
                for j in range(2):
                    if (lab == j).any(): cent[j] = X[lab == j].mean(0); cent[j] /= (np.linalg.norm(cent[j]) + 1e-9)
            if lab.min() == lab.max(): continue
            new_id = max(cls.values()) + 1; trial = dict(cls)
            for w, l in zip(ws, lab):
                if l == 1: trial[w] = new_id
            b1 = heldout_bits(trial)
            if b1 < b0:
                cls = trial; b0 = b1; kept += 1; json.dump(cls, open(STORE, "w", encoding="utf-8"))
                print(f"R25-c3 split kept: group {g} -> {new_id} ({sum(1 for l in lab if l == 1)} words moved) held-out {b1:.4f} | e.g. {[w for w, l in zip(ws, lab) if l == 0][:5]} / {[w for w, l in zip(ws, lab) if l == 1][:5]}", flush=True)
        print(f"R25-c3 splits kept {kept} of {tries} tried; groups now {len(set(cls.values()))}; held-out bits/token {b0:.4f}", flush=True)
    groups = collections.defaultdict(list)
    for w in vocab[:3000]: groups[cls[w]].append(w)
    for probe in ("doctor", "mole", "dusk", "lend", "parcel", "nephew", "eleven", "spin"):
        if probe in cls: print(f"  group of {probe!r}:", [x for x in vocab if cls.get(x) == cls[probe]][:14], flush=True)
    json.dump(dict(final_bits=b0), open("r25_classes_results.json", "w"))


if __name__ == "__main__":
    main()
