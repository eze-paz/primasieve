"""WordNet 3.1 grounding for the NL->equation experiment (zero-LLM, pure stdlib). Loads the committed WordNet
dict/ (SHA-pinned in the prereg), builds a lemma->synset and synset->(words,gloss,hypernym,derivational) graph,
and grounds an English word to executable primitives by BFS (depth<=3) over hypernyms (@), derivational links (+),
and gloss content-lemmas, until a synset whose word list contains a committed ANCHOR lemma is reached.

Anchors are the CANONICAL NAMES of the four grounded primitives (operator.add/sub/mul/truediv) -- the definitional
names of the operations, committed BEFORE any prompt is seen; the shuffle-dictionary control proves the CHAINS,
not the anchor list, carry the load. All reachable primitives are licensed (ambiguity preserved); chain depth is
energy, never a selector."""
import os, re, sys

_WORD = re.compile(r"[a-z]+")
ANCHORS = {                                   # primitive -> committed canonical operation-name lemmas
    "+": {"addition", "add", "sum", "plus"},
    "-": {"subtraction", "subtract", "minus", "difference"},
    "*": {"multiplication", "multiply", "product"},
    "/": {"division", "divide", "quotient"},
}
LEMMA2PRIM = {l: p for p, ls in ANCHORS.items() for l in ls}

def _datadir():
    d = os.path.join(os.path.dirname(__file__), "_nldata", "dict")
    if not os.path.isdir(d):
        sys.exit(f"WordNet dict/ not found at {d} (run the download step; SHA-pinned in prereg)")
    return d

class WN:
    def __init__(self, use_gloss=True, shuffle_seed=None):
        self.words = {}       # (pos,off) -> [lemmas]
        self.gloss = {}       # (pos,off) -> [content lemmas in gloss]
        self.hyper = {}       # (pos,off) -> [(pos,off)]   (@ hypernym)
        self.deriv = {}       # (pos,off) -> [(pos,off)]   (+ derivational)
        self.index = {}       # lemma -> [(pos,off)]
        self.use_gloss = use_gloss
        for pos, fn in (("n", "data.noun"), ("v", "data.verb"), ("a", "data.adj"), ("r", "data.adv")):
            self._load(pos, fn)
        if shuffle_seed is not None:          # SHUFFLE control: permute glosses among synsets (same stats, wrong content)
            import random
            keys = list(self.gloss.keys()); vals = [self.gloss[k] for k in keys]
            random.Random(shuffle_seed).shuffle(vals)
            self.gloss = dict(zip(keys, vals))

    def _load(self, pos, fn):
        path = os.path.join(_datadir(), fn)
        with open(path, encoding="latin-1") as f:
            for line in f:
                if line.startswith("  "):     # license/header lines
                    continue
                head, _, gl = line.partition("|")
                t = head.split()
                if len(t) < 4:
                    continue
                try:
                    off = t[0]; wcnt = int(t[3], 16)
                except ValueError:
                    continue
                key = (pos, off)
                ws = []
                i = 4
                for _w in range(wcnt):
                    ws.append(t[i].lower()); i += 2
                self.words[key] = ws
                for w in ws:
                    self.index.setdefault(w, []).append(key)
                pcnt = int(t[i]); i += 1
                hy, de = [], []
                for _p in range(pcnt):
                    sym, toff, tpos = t[i], t[i + 1], t[i + 2]; i += 4
                    if sym.startswith("@"): hy.append((tpos, toff))
                    elif sym == "+": de.append((tpos, toff))
                self.hyper[key] = hy; self.deriv[key] = de
                self.gloss[key] = [w for w in _WORD.findall(gl.lower()) if len(w) > 2]

    def ground(self, word, maxdepth=3):
        """Return the set of primitives licensed for `word` via BFS over hyper/deriv/gloss, depth<=maxdepth."""
        word = word.lower()
        if word in LEMMA2PRIM:                # the word IS an operation name
            return {LEMMA2PRIM[word]}
        seen = set(); frontier = list(self.index.get(word, [])); lic = set()
        for key in frontier: seen.add(key)
        for _d in range(maxdepth):
            nxt = []
            for key in frontier:
                for w in self.words.get(key, []):
                    if w in LEMMA2PRIM: lic.add(LEMMA2PRIM[w])
                for tgt in self.hyper.get(key, []) + self.deriv.get(key, []):
                    if tgt not in seen: seen.add(tgt); nxt.append(tgt)
                if self.use_gloss:
                    for gw in self.gloss.get(key, []):
                        for tgt in self.index.get(gw, [])[:3]:      # cap gloss-lemma fan-out
                            if tgt not in seen: seen.add(tgt); nxt.append(tgt)
            frontier = nxt[:400]              # cap frontier per depth
        return lic

if __name__ == "__main__":
    wn = WN(use_gloss=True)
    print(f"loaded synsets={len(wn.words)} lemmas={len(wn.index)}\n")
    probe = ["total", "sum", "altogether", "combined", "gained", "more",
             "left", "remain", "fewer", "spent", "gave", "difference",
             "each", "times", "per", "twice", "product",
             "share", "split", "divide", "quotient", "ratio", "average",
             "apple", "dog", "run"]   # last 3 = should ground to nothing (controls)
    for w in probe:
        print(f"  {w:12s} -> {sorted(wn.ground(w)) or '(none)'}")