"""L1_prereg.md: the training corpus (Gutenberg training books, never the 41 held-out ones) and a byte-pair encoding
learned from it. Run: python learned/data.py  -> learned/cache/{bpe.json, train.bin, held.bin}"""
import os, re, sys, json, hashlib, collections, array, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
GUT = os.path.join(ROOT, "_nldata", "gutenberg")
CACHE = os.path.join(HERE, "cache")
PIECE = re.compile(r" ?[A-Za-z]+| ?[0-9]| ?[^\sA-Za-z0-9]|\n")


def held_book(bid):                       # the same split as book_battery.held_book
    return int(hashlib.sha256(f"book:{bid}".encode()).hexdigest(), 16) % 10 == 0


def books():
    ids = sorted(f[:-4] for f in os.listdir(GUT) if f.endswith(".txt"))
    return [b for b in ids if not held_book(b)], [b for b in ids if held_book(b)]


def clean(text):
    """the book between the Gutenberg START/END lines; paragraphs kept as one newline, lines inside them joined"""
    text = text.replace("\r", "")
    s = re.search(r"\*\*\* ?START OF.*?\*\*\*", text)
    if s: text = text[s.end():]
    e = re.search(r"\*\*\* ?END OF", text)
    if e: text = text[:e.start()]
    paras = [" ".join(p.split()) for p in re.split(r"\n\s*\n", text)]
    return "\n".join(p for p in paras if p) + "\n"


def read(bid):
    return clean(open(os.path.join(GUT, bid + ".txt"), encoding="utf-8", errors="replace", newline="").read())   # raw: Gutenberg lines end in CR CR LF


def learn_bpe(counts, n_symbols=4096):
    """merges learned from piece counts: start from characters, repeatedly join the most frequent adjacent pair"""
    words = {tuple(w): c for w, c in counts.items()}
    chars = collections.Counter()
    for w, c in words.items():
        for ch in w: chars[ch] += c
    vocab = [ch for ch, _ in chars.most_common()]
    pairs = collections.Counter(); where = collections.defaultdict(set)
    for w, c in words.items():
        for a, b in zip(w, w[1:]): pairs[(a, b)] += c; where[(a, b)].add(w)
    merges = []
    while len(vocab) < n_symbols and pairs:
        (a, b), n = pairs.most_common(1)[0]
        if n < 2: break
        merges.append((a, b)); new = a + b; vocab.append(new)
        for w in list(where.pop((a, b), ())):
            if w not in words: continue
            c = words.pop(w)
            for x, y in zip(w, w[1:]):
                pairs[(x, y)] -= c
                if pairs[(x, y)] <= 0: del pairs[(x, y)]
                where[(x, y)].discard(w)
            out = []; i = 0
            while i < len(w):
                if i + 1 < len(w) and w[i] == a and w[i + 1] == b: out.append(new); i += 2
                else: out.append(w[i]); i += 1
            w2 = tuple(out); words[w2] = words.get(w2, 0) + c
            for x, y in zip(w2, w2[1:]): pairs[(x, y)] += c; where[(x, y)].add(w2)
        if len(merges) % 500 == 0: print(f"  bpe: {len(vocab)} symbols", flush=True)
    return vocab, merges


class BPE:
    def __init__(self, vocab, merges):
        self.vocab = vocab; self.id = {s: i for i, s in enumerate(vocab)}
        self.rank = {tuple(m): i for i, m in enumerate(merges)}; self.memo = {}
        self.unk = len(vocab)                                      # one id for unseen characters

    def piece(self, p):
        if p in self.memo: return self.memo[p]
        w = list(p)
        while len(w) > 1:
            best = min(((self.rank.get((w[i], w[i + 1]), 1 << 30), i) for i in range(len(w) - 1)))
            if best[0] == 1 << 30: break
            i = best[1]; w[i:i + 2] = [w[i] + w[i + 1]]
        ids = [self.id.get(s, self.unk) for s in w]
        if len(self.memo) < 2_000_000: self.memo[p] = ids
        return ids

    def encode(self, text):
        out = []
        for p in PIECE.findall(text): out.extend(self.piece(p))
        return out

    def decode(self, ids):
        return "".join(self.vocab[i] if i < len(self.vocab) else "?" for i in ids)

    @property
    def size(self): return len(self.vocab) + 1

    @staticmethod
    def load(path=os.path.join(CACHE, "bpe.json")):
        d = json.load(open(path, encoding="utf-8")); return BPE(d["vocab"], d["merges"])


def main():
    os.makedirs(CACHE, exist_ok=True); T0 = time.time()
    train, held = books()
    print(f"{len(train)} training books, {len(held)} held-out", flush=True)
    counts = collections.Counter(); texts = {}
    for b in train:
        t = read(b); texts[b] = t; counts.update(PIECE.findall(t))
    print(f"read {sum(map(len, texts.values())) / 1e6:.0f} M characters, {len(counts)} distinct pieces ({time.time() - T0:.0f} s)", flush=True)
    vocab, merges = learn_bpe(counts, 4096)
    json.dump(dict(vocab=vocab, merges=merges), open(os.path.join(CACHE, "bpe.json"), "w", encoding="utf-8"))
    tok = BPE(vocab, merges); print(f"bpe learned: {len(vocab)} symbols ({time.time() - T0:.0f} s)", flush=True)
    for name, ids_ in (("train", train), ("held", held)):
        arr = array.array("H"); nch = 0
        for b in ids_:
            t = texts.get(b) or read(b); nch += len(t); arr.extend(tok.encode(t))
        arr.tofile(open(os.path.join(CACHE, name + ".bin"), "wb"))
        print(f"{name}: {len(arr) / 1e6:.1f} M tokens from {nch / 1e6:.0f} M characters ({nch / len(arr):.2f} chars/token)  ({time.time() - T0:.0f} s)", flush=True)
    json.dump(dict(train=train, held=held), open(os.path.join(CACHE, "split.json"), "w"))


if __name__ == "__main__":
    main()
