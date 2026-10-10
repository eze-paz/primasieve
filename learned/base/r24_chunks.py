"""R24 run 2c: the template inventory as CHUNKS (constructions) over classes / frozen words / slots. A sentence is a
segmentation into chunks of 2-6 symbols; the inventory is learned by counting symbol n-grams, pruned to --max chunks by
description-length gain, then re-estimated from the best segmentations for a few rounds. No n-gram backoff: a symbol
no chunk covers is paid at the floor. Slots (PERSON / ENT / PRON) and class positions are filled as in r24_tlm.
Run: python learned/base/r24_chunks.py [--train 150000] [--held 5000] [--k 200] [--freeze 100] [--max 5000]"""
import os, sys, json, math, random, collections, time
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE)); os.chdir(HERE)
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(ROOT, "learned"))
import r24_tlm as T, r24_books as B, r24_classes as C

MAXLEN = 6; ROUNDS = 3


def arg(name, default):
    return type(default)(sys.argv[sys.argv.index(name) + 1]) if name in sys.argv else default


class ChunkLM(C.ClassTLM):
    def __init__(self, classes, frozen, max_chunks):
        super().__init__(classes, frozen, 2); self.max = max_chunks; self.chunks = collections.Counter(); self.single = collections.Counter(); self.in_chunks = 0; self.n_syms = 0

    def seqs(self, stories, names):
        out = []
        for text in stories:
            for s in T.SENT.split(text):
                toks = T.TOK.findall(s)
                if toks: out.append([sym for sym, _ in self.symbols(T.slotify(toks, names))])
        return out

    def segment(self, syms):
        """best segmentation: maximise sum of log P(chunk); singletons allowed at the floor cost"""
        n = len(syms); best = [0.0] + [-1e18] * n; back = [0] * (n + 1)
        for j in range(1, n + 1):
            for L in range(1, min(MAXLEN, j) + 1):
                ch = tuple(syms[j - L:j])
                lp = self.lp_chunk(ch)
                if lp is None: continue
                v = best[j - L] + lp
                if v > best[j]: best[j] = v; back[j] = L
        out = []; j = n
        while j > 0: out.append(tuple(syms[j - back[j]:j])); j -= back[j]
        return out[::-1], best[n]

    def lp_chunk(self, ch):
        if len(ch) == 1: return math.log(self.p_single(ch[0]))
        c = self.chunks.get(ch)
        return math.log((1 - self.PS) * c / self.Z) if c else None

    def p_single(self, sym):
        return self.PS * (self.single[sym] + 0.5) / (sum(self.single.values()) + 0.5 * (len(self.single) + 1))

    def fit(self, seqs):
        # round 0: every n-gram of length 2..MAXLEN with count >= 5; prune to the top self.max by (count * (len - 1))
        cnt = collections.Counter()
        for s in seqs:
            for i in range(len(s)):
                for L in range(2, MAXLEN + 1):
                    if i + L <= len(s): cnt[tuple(s[i:i + L])] += 1
        cand = {ch: c for ch, c in cnt.items() if c >= 5}
        keep = sorted(cand, key=lambda ch: -(cand[ch] * (len(ch) - 1) - 3 * len(ch)))[:self.max]      # description-length gain: saved symbols minus the chunk's own cost
        self.chunks = collections.Counter({ch: cand[ch] for ch in keep}); self.single = collections.Counter(x for s in seqs for x in s)
        self.PS = 0.3; self.Z = sum(self.chunks.values())
        for r in range(ROUNDS):
            ch_c = collections.Counter(); sg = collections.Counter(); n_single = n_all = 0
            for s in seqs:
                seg, _ = self.segment(s)
                for ch in seg:
                    n_all += 1
                    if len(ch) == 1: sg[ch[0]] += 1; n_single += 1
                    else: ch_c[tuple(ch)] += 1
            self.chunks = ch_c; self.single = sg + collections.Counter(); self.PS = max(0.02, n_single / max(1, n_all)); self.Z = sum(ch_c.values())
            print(f"   round {r + 1}: {len(ch_c)} chunks in use, singleton share {self.PS:.2f}", flush=True)

    def score(self, toks, names, st):
        """bits of the sentence: chunk structure from the best segmentation + fillers at slots and class positions"""
        items = self.symbols(T.slotify(toks, names)); syms = [sym for sym, _ in items]
        seg, lp = self.segment(syms); bits = -lp / math.log(2); full = all(len(ch) >= 2 for ch in seg); self.in_chunks += sum(len(ch) for ch in seg if len(ch) >= 2); self.n_syms += len(syms)
        for k, (sym, filler) in enumerate(items):
            pos = "first" if k == 0 else "later"
            if sym in ("PERSON", "ENT", "PRON") or sym.startswith("C"):
                pf = self.p_filler(sym, filler, st, pos); pfl = 1.0
                for w in filler: pfl *= self.p_floor(w)
                bits += -math.log2((1 - T.FLOOR) * pf + T.FLOOR * pfl)
            if sym in ("PERSON", "ENT"): st.mention(sym, filler, first=(k == 0))
        return bits, len(toks), full


def main():
    import data as D
    train_b, held_b = D.books(); random.Random(2).shuffle(held_b)
    train = B.paragraphs(train_b, arg("--train", 150000)); held = B.paragraphs(held_b, arg("--held", 5000)); T0 = time.time()
    classes, uni = C.induce_classes([s["text"] for s in train], k=arg("--k", 200)); frozen = {w for w, _ in uni.most_common(arg("--freeze", 100))}
    names = T.mid_caps([s["text"] for s in train])
    M = ChunkLM(classes, frozen, arg("--max", 5000)); M.learn([s["text"] for s in train], names)        # slot / class / floor statistics
    seqs = M.seqs([s["text"] for s in train], names); M.fit(seqs); print(f"fitted in {(time.time() - T0) / 60:.1f} min", flush=True)
    bits = n = full = ns = 0
    for s in held:
        st = T.State()
        for sent in T.SENT.split(s["text"]):
            toks = T.TOK.findall(sent)
            if not toks: continue
            b, k, f = M.score(toks, names, st); bits += b; n += k; full += f; ns += 1
    tlm = bits / n; bi = T.ngram_bits([s["text"] for s in train], [s["text"] for s in held], 2)
    print(f"held-out {ns} sentences, {n} tokens; bits/token: chunk learner {tlm:.2f} | interpolated bigram {bi:.2f} (R24-a2: <= bigram + 0.5 -> {'PASS' if tlm <= bi + 0.5 else 'MISS'})")
    print(f"sentences fully explained by chunks of length >= 2: {full}/{ns} = {full / ns:.3f} (bar >= 0.30 -> {'PASS' if full / ns >= 0.3 else 'MISS'}); tokens inside multi-symbol chunks {M.in_chunks / max(1, M.n_syms):.2f}")
    inv = collections.defaultdict(list)
    for w, c in classes.items(): inv[c].append(w)
    def show(ch): return " ".join(f"[{'/'.join(sorted(inv[int(x[1:])], key=lambda w: -uni[w])[:3])}]" if x.startswith("C") else x for x in ch)
    for ch, c in M.chunks.most_common(12): print("   ", c, show(ch))
    json.dump(dict(bits=tlm, bigram=bi, full=(full, ns), chunks=len(M.chunks)), open("r24_chunks_results.json", "w"))


if __name__ == "__main__":
    main()
