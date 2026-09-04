"""IDEA-1 solver (pure-Python, the SOUND verifier). Consumes llm_feats_<corpus>.json (LLM boundary proposals from
llm_featurize.py) and runs the SAME verified Zhikov MDL search seeded three ways -- n-gram branching entropy
(baseline), the LLM's next-token entropy / tokenization (the proposal under test), shuffle control -- so ONLY the
proposal source differs. The LLM only PROPOSES; the sound MDL DECIDES and is scored against gold. If LLM-seeded
verified token-F beats n-gram-seeded, the LLM's knowledge helped (Idea 1 works). Apples-to-apples: all arms use
zhikov_segment(scores=None) (same MDLZ + Alg-2 + attested Alg-3), differing only in seeds. Gold built from the words
saved in the feats file (corpus-agnostic). Usage: python llm_seg.py [brp|alice]."""
import os, sys, json, random
sys.path.insert(0, os.path.dirname(__file__))
import seg_zhikov as Z

D = os.path.join(os.path.dirname(__file__), "_nldata")
CORPUS = sys.argv[1] if len(sys.argv) > 1 else "brp"
feats = json.load(open(os.path.join(D, f"llm_feats_{CORPUS}.json")))
N = feats["n"]; U = feats["utts"]

gold = Z.gold_spans([u["words"] for u in U]); streams = [s for s, _ in gold]
assert all(streams[i] == U[i]["s"] for i in range(N)), "stream/feature misalignment!"
print(f"IDEA-1 | LLM={feats['model']} | corpus={CORPUS} | {N} utts, {sum(len(u['words']) for u in U)} tokens")
gg = Z.token_f(gold, [set(a for (a, b) in gb if a > 0) for _, gb in gold])[0]
print(f"scorer-drift: gold-vs-gold={gg:.3f} (must=1.000)\n")

ng_rises = Z.entropy_rise(streams, k=4)
ng_seed = [set(g for g in range(1, len(s)) if ng_rises[u][g] > 0.0) for u, s in enumerate(streams)]

ents = [list(U[i]["gaps"].values()) for i in range(N)]
allent = [e for es in ents for e in es]; med = sorted(allent)[len(allent)//2] if allent else 0.0
llm_seed_tok = [set(int(k) for k in U[i]["gaps"]) for i in range(N)]
llm_seed_hi = [set(int(k) for k, h in U[i]["gaps"].items() if h >= med) for i in range(N)]

def raw_f(seeds): return Z.token_f(gold, [set(b) for b in seeds])[0]
def dens(seeds): return sum(len(b) for b in seeds) / max(1, sum(len(s)-1 for s in streams))
print("RAW SEED quality (pre-MDL token-F | density):")
for tag, sd in [("n-gram entropy", ng_seed), ("LLM tokenization", llm_seed_tok),
                (f"LLM hi-entropy(>med {med:.1f})", llm_seed_hi)]:
    print(f"  {tag:26s} F={raw_f(sd):.3f}  density={dens(sd):.2f}")

def mdl(seeds, st=None, sg=None):
    pred, _ = Z.zhikov_segment(st if st is not None else streams, kappa=1.5, rounds=8, sweeps=6,
                               seeds=[set(b) for b in seeds], scores=None)
    return Z.token_f(sg if sg is not None else gold, pred)[0]

print("\nSAME MDL SEARCH from each seed (verified token-F):")
f_ng = mdl(ng_seed);      print(f"  n-gram-seeded  F={f_ng:.3f}")
f_lt = mdl(llm_seed_tok); print(f"  LLM-tok-seeded F={f_lt:.3f}   delta {f_lt-f_ng:+.3f}")
f_lh = mdl(llm_seed_hi);  print(f"  LLM-hi-seeded  F={f_lh:.3f}   delta {f_lh-f_ng:+.3f}")
allc = list("".join(streams)); random.Random(1).shuffle(allc); i = 0; shuf = []
for s in streams: shuf.append("".join(allc[i:i+len(s)])); i += len(s)
sh_gold = [(ss, gb) for ss, (_, gb) in zip(shuf, gold)]
sh_rises = Z.entropy_rise(shuf, 4); sh_seed = [set(g for g in range(1, len(s)) if sh_rises[u][g] > 0) for u, s in enumerate(shuf)]
print(f"  SHUFFLE-chars  F={mdl(sh_seed, shuf, sh_gold):.3f}   (must collapse)")

best_llm = max(f_lt, f_lh)
print(f"\nVERDICT ({CORPUS}): LLM-seeded best {best_llm:.3f} vs n-gram-seeded {f_ng:.3f} = {best_llm-f_ng:+.3f} "
      f"({'LLM HELPS' if best_llm-f_ng>0.01 else 'no gain'}).")
if CORPUS == "brp":
    print("  (br-phono = phonemic, LLM never trained on it -> tests sequence-model only, not lexical knowledge.)")
else:
    print("  (alice = orthographic English, LLM knowledge APPLIES -> the real Idea-1 test.)")