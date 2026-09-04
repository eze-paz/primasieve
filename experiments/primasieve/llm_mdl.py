"""IDEA-1b solver (pure-Python, sound). The TIGHT coupling: LLM word-probability INSIDE the MDL objective. Same
Zhikov search (Alg-2 greedy + Alg-3 batch merge/split), same n-gram-entropy seed, same scores -- the ONLY thing
swapped is the LEXICON spelling cost: char-model codebook (MDLZ = baseline) vs -log2 P_LLM(word) (MDLL = the test)
vs SHUFFLED LLM bits (control: does the LLM's SPECIFIC word knowledge matter, or would any word-cost do?). Reported
across a small kappa band (not tuned to F). If LLM-lex beats char-lex AND beats shuffled-LLM, the LLM's lexical
knowledge, injected into the objective (not the seed), helps -- the thing seeding could not do."""
import os, sys, json, math, random
sys.path.insert(0, os.path.dirname(__file__))
import seg_zhikov as Z
LOG2 = math.log2

D = os.path.join(os.path.dirname(__file__), "_nldata")
CORPUS = sys.argv[1] if len(sys.argv) > 1 else "alice"
WB = json.load(open(os.path.join(D, f"llm_wordbits_{CORPUS}.json")))
wordbits = WB["bits"]; N = WB["n"]

def load_brp(): return [l.split() for l in open(os.path.join(D, "brent_phono.txt"), encoding="utf-8") if l.strip()]
def load_alice():
    import re
    raw = open(os.path.join(D, "alice.txt"), encoding="utf-8", errors="ignore").read()
    m = re.search(r"\*\*\* START OF.*?\*\*\*(.*?)\*\*\* END OF", raw, re.S); body = m.group(1) if m else raw
    out = []
    for s in re.split(r"[.!?]+", body):
        w = re.findall(r"[a-z]+", s.lower())
        if 2 <= len(w) <= 40: out.append(w)
    return out

utts = (load_brp() if CORPUS == "brp" else load_alice()); random.Random(2024).shuffle(utts); utts = utts[:N]
gold = Z.gold_spans(utts); streams = [s for s, _ in gold]
print(f"IDEA-1b | LLM lexicon cost | corpus={CORPUS} {len(utts)} utts, {sum(len(w) for w in utts)} tokens")
gg = Z.token_f(gold, [set(a for (a, b) in gb if a > 0) for _, gb in gold])[0]
print(f"scorer-drift gold-vs-gold={gg:.3f} | wordbits {len(wordbits)} entries\n")

class MDLL:
    """corpus MLE code + lexicon spelling cost from a word->bits table + Zhikov parametric term."""
    def __init__(self, streams, wb, kappa=1.5):
        self.wb = wb; self.A = len(set("".join(streams))) + 1
        self.parm = 0.5 * LOG2(sum(len(s) for s in streams)); self.kappa = kappa
        self.cnt = __import__("collections").Counter(); self.N = 0; self.Sc = 0.0; self.M = 0; self.lex = 0.0
    def wcost(self, w):
        b = self.wb.get(w); return b if b is not None else len(w) * LOG2(self.A) + 4.0
    def change(self, w, delta):
        old = self.cnt[w]; new = old + delta
        if old > 0: self.Sc -= old * LOG2(old)
        if new > 0: self.Sc += new * LOG2(new)
        if old == 0 and new > 0: self.M += 1; self.lex += self.wcost(w)
        elif old > 0 and new == 0: self.M -= 1; self.lex -= self.wcost(w)
        self.cnt[w] = new; self.N += delta
    def dl(self):
        corpus = (self.N * LOG2(self.N) - self.Sc) if self.N > 0 else 0.0
        return corpus + self.lex + self.kappa * max(0, self.M - 1) * self.parm

# shared seed + scores (identical across arms)
rises = Z.entropy_rise(streams, k=4); scores = Z.entropy_abs(streams, k=4)
seed = Z.entropy_seed(streams, 4, 0.0, rises)
low = Z.percentile([scores[u][g] for u in range(len(streams)) for g in range(1, len(streams[u]))], 35)

def search(mdl):
    B = [sorted(b) for b in seed]; Z._init_counts(mdl, streams, B); Z.greedy_sweep(mdl, streams, B, 6)
    prev = None
    for r in range(8):
        Z.pair_merge_cleanup(mdl, streams, B, scores=scores, low_thresh=low)
        Z.type_split_cleanup(mdl, streams, B); Z.greedy_sweep(mdl, streams, B, 6)
        dl = mdl.dl()
        if prev is not None and abs(prev - dl) < 1.0: break
        prev = dl
    return Z.token_f(gold, [set(b) for b in B])[0]

# shuffled-LLM control: permute bits across words (keep the value distribution, destroy word-specific signal)
keys = list(wordbits); vals = [wordbits[k] for k in keys]; random.Random(0).shuffle(vals)
wb_shuf = dict(zip(keys, vals))

print(f"  {'kappa':>6} | {'CHAR-lex(Zhikov)':>16} | {'LLM-lex':>9} | {'LLM-shuffled':>12}")
best = {"char": 0, "llm": 0, "shuf": 0}
for kappa in [0.75, 1.5, 2.5]:
    fc, _ = Z.zhikov_segment(streams, kappa=kappa, rounds=8, sweeps=6, seeds=[set(b) for b in seed],
                             scores=scores, low_thresh=low)
    fc = Z.token_f(gold, fc)[0]
    fl = search(MDLL(streams, wordbits, kappa))
    fs = search(MDLL(streams, wb_shuf, kappa))
    for k, v in [("char", fc), ("llm", fl), ("shuf", fs)]: best[k] = max(best[k], v)
    print(f"  {kappa:>6.2f} | {fc:>16.3f} | {fl:>9.3f} | {fs:>12.3f}")

print(f"\n  best-over-kappa: CHAR {best['char']:.3f} | LLM {best['llm']:.3f} | LLM-shuffled {best['shuf']:.3f}")
print(f"  LLM - CHAR        = {best['llm']-best['char']:+.3f}  (does LLM lexical knowledge in the OBJECTIVE beat char model?)")
print(f"  LLM - LLM-shuffled= {best['llm']-best['shuf']:+.3f}  (is it the SPECIFIC word knowledge, not just any cost?)")
verdict = "LLM HELPS" if (best['llm']-best['char'] > 0.01 and best['llm']-best['shuf'] > 0.01) else "no gain"
print(f"  VERDICT: {verdict}. (Alice orthographic; kappa reported as a band, not tuned to F.)")