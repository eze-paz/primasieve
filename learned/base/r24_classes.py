"""R24 run 2b: word classes induced from the books by distribution (no labels, no gradients): each frequent word is a
vector of its left/right neighbour counts over the 300 most frequent words; k-means on the normalised vectors gives K
classes. Templates then range over classes (a template symbol is a class id, a slot kind, or a frozen frequent word),
and the next word at a class position costs P(class position | template) * P(word | class). Still no n-gram memory.
Run: python learned/base/r24_classes.py [--train 150000] [--held 5000] [--k 200] [--freeze 100]"""
import os, sys, re, json, math, random, collections, time
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE)); os.chdir(HERE)
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(ROOT, "learned"))
import r24_tlm as T, r24_books as B


def arg(name, default):
    return type(default)(sys.argv[sys.argv.index(name) + 1]) if name in sys.argv else default


def induce_classes(stories, k=200, n_feat=300, min_count=10, iters=15, seed=0):
    """word -> class id for words with >= min_count occurrences; the rest get no class"""
    uni = collections.Counter(); left = collections.defaultdict(collections.Counter); right = collections.defaultdict(collections.Counter)
    for text in stories:
        for s in T.SENT.split(text):
            w = [x.lower() for x in T.TOK.findall(s)]
            for i, x in enumerate(w):
                uni[x] += 1
                if i: left[x][w[i - 1]] += 1; right[w[i - 1]][x] += 1
    feats = [w for w, _ in uni.most_common(n_feat)]; fi = {w: i for i, w in enumerate(feats)}
    words = [w for w, c in uni.items() if c >= min_count]
    X = np.zeros((len(words), 2 * n_feat), dtype=np.float32)
    for r, w in enumerate(words):
        for c, n in left[w].items():
            if c in fi: X[r, fi[c]] = n
        for c, n in right[w].items():
            if c in fi: X[r, n_feat + fi[c]] = n
    X = np.log1p(X); X /= (np.linalg.norm(X, axis=1, keepdims=True) + 1e-6)
    rng = np.random.default_rng(seed); C = X[rng.choice(len(words), k, replace=False)].copy()
    for _ in range(iters):
        a = (X @ C.T).argmax(1)
        for j in range(k):
            m = a == j
            if m.any(): C[j] = X[m].mean(0); C[j] /= (np.linalg.norm(C[j]) + 1e-6)
    a = (X @ C.T).argmax(1)
    return {w: int(a[r]) for r, w in enumerate(words)}, uni


class ClassTLM(T.TLM):
    """templates over classes: a literal word is replaced by its class symbol unless it is one of the --freeze most
    frequent words (function words stay literal); P(word | class) is a learned unigram within the class"""
    def __init__(self, classes, frozen, min_count=2):
        super().__init__(min_count); self.classes = classes; self.frozen = frozen; self.cw = collections.defaultdict(collections.Counter)

    def symbols(self, items):
        out = []
        for sym, filler in items:
            if sym in ("PERSON", "PRON", "ENT") or sym in self.frozen or sym not in self.classes: out.append((sym, filler))
            else: out.append((f"C{self.classes[sym]}", filler))
        return out

    def learn(self, stories, names):
        for text in stories:
            for s in T.SENT.split(text):
                for sym, filler in T.slotify(T.TOK.findall(s), names):
                    if sym in self.classes and sym not in self.frozen and sym not in ("PERSON", "PRON", "ENT"): self.cw[self.classes[sym]][sym] += 1
        self._slotify = T.slotify
        T.slotify = lambda toks, names: self.symbols(self._slotify(toks, names))      # the base learner now sees class symbols
        try: super().learn(stories, names)
        finally: T.slotify = self._slotify

    def p_filler(self, sym, filler, st, pos):
        if sym.startswith("C"):
            c = self.cw[int(sym[1:])]; n = sum(c.values()); return (c[filler[0]] + 0.5) / (n + 0.5 * (len(c) + 1))
        return super().p_filler(sym, filler, st, pos)

    def score_sentence(self, toks, names, st):
        self._slotify = T.slotify; T.slotify = lambda t, nm: self.symbols(self._slotify(t, nm))
        try:
            items = T.slotify(toks, names); syms = tuple(sym for sym, _ in items)
            n = len(toks); bits = 0.0; covered = syms in self.templates
            alive = {t: c for t, c in self.templates.items() if len(t) == len(syms)}
            for k, (sym, filler) in enumerate(items):
                pos = "first" if k == 0 else "later"; p_struct = 0.0; w_alive = sum(alive.values())
                if w_alive:
                    match = {t: c for t, c in alive.items() if t[k] == sym}
                    if match:
                        pi = self.p_filler(sym, filler, st, pos) if (sym in ("PERSON", "ENT", "PRON") or sym.startswith("C")) else 1.0
                        p_struct = (sum(match.values()) / w_alive) * pi; alive = match
                    else: alive = {}
                p_floor = 1.0
                for w in filler: p_floor *= self.p_floor(w)
                bits += -math.log2((1 - T.FLOOR) * p_struct + T.FLOOR * p_floor)
                if sym in ("PERSON", "ENT"): st.mention(sym, filler, first=(k == 0))
            return bits, n, covered, items
        finally: T.slotify = self._slotify


def main():
    import data as D
    train_b, held_b = D.books(); random.Random(2).shuffle(held_b)
    train = B.paragraphs(train_b, arg("--train", 150000)); held = B.paragraphs(held_b, arg("--held", 5000)); T0 = time.time()
    classes, uni = induce_classes([s["text"] for s in train], k=arg("--k", 200)); print(f"{len(classes)} words in {arg('--k', 200)} classes [{(time.time() - T0) / 60:.1f} min]", flush=True)
    frozen = {w for w, _ in uni.most_common(arg("--freeze", 100))}
    inv = collections.defaultdict(list)
    for w, c in classes.items(): inv[c].append(w)
    for c in sorted(inv, key=lambda c: -len(inv[c]))[:6]: print("   class", c, sorted(inv[c], key=lambda w: -uni[w])[:12])
    names = T.mid_caps([s["text"] for s in train])
    M = ClassTLM(classes, frozen, arg("--min-count", 2)); M.learn([s["text"] for s in train], names); print(f"learned {len(M.templates)} class templates [{(time.time() - T0) / 60:.1f} min]", flush=True)
    bits = n = cov = ns = 0
    for s in held:
        st = T.State()
        for sent in T.SENT.split(s["text"]):
            toks = T.TOK.findall(sent)
            if not toks: continue
            b, k, c, _ = M.score_sentence(toks, names, st); bits += b; n += k; cov += c; ns += 1
    tlm = bits / n; bi = T.ngram_bits([s["text"] for s in train], [s["text"] for s in held], 2)
    print(f"held-out {ns} sentences, {n} tokens; bits/token: class-template learner {tlm:.2f} | bigram {bi:.2f} (R24-a2: <= bigram + 0.5 -> {'PASS' if tlm <= bi + 0.5 else 'MISS'})")
    print(f"class-template coverage of held-out sentences: {cov}/{ns} = {cov / ns:.3f} (bar >= 0.30 -> {'PASS' if cov / ns >= 0.3 else 'MISS'})")
    for t, c in M.templates.most_common(8): print("   ", c, " ".join(t))
    json.dump(dict(bits=tlm, bigram=bi, coverage=(cov, ns), templates=len(M.templates), k=arg("--k", 200)), open("r24_classes_results.json", "w"))


if __name__ == "__main__":
    main()
