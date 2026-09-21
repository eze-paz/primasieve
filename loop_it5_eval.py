"""FLUENCY LOOP it.5 -- EVALUATE the converged class map (LOOP.md "ITERATION 5"). Gates I5-a..e. Under the cap.

Usage:  python loop_it5_eval.py"""
import os, sys, time, json, random, collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.seqform import ClassBigram, SuffixTable, sentence_oov, load_classes
from core.registry import selfcheck
from cogs_stage9 import wordnet_pos
from loop_it1_size import load
from loop_it5_build import PATH, META, K, N

T0 = time.time()


def say(s=""): print(s.encode("ascii", "replace").decode(), flush=True)


if __name__ == "__main__":
    selfcheck(__file__)
    say("FLUENCY LOOP it.5 -- CONVERGENCE: evaluate the converged K=128 class map on 30k Wiktionary sentences.\n")
    tr, held = load()
    m = ClassBigram(tr[:N], K)
    ok = load_classes(m, PATH)
    meta = json.load(open(META)) if os.path.exists(META) else {}
    say(f"I5-a  class map loaded={ok}; passes {meta.get('passes')}, moves per pass {meta.get('moves')}, build {meta.get('secs', 0):.0f}s, "
        f"converged={meta.get('converged')}, rare assigned {meta.get('rare_assigned')}   [{'CONVERGED' if meta.get('converged') else 'UNCONVERGED -- used as-is'}]")

    u = sum(1 + m.unigram(s) for s in held)
    known = [s for s in held if all(w in m.cls for w in s)]
    uk = sum(1 + m.unigram(s) for s in known); gk = sum(m.sentence(s)[0] for s in known)
    g_known = 1 - gk / uk
    say(f"I5-b  KNOWN-ONLY gain vs unigram: {g_known:+.4f} on {len(known)}/{len(held)} sentences   [>= +0.08 -> {'PASS' if g_known >= 0.08 else 'FAIL'}]")

    noconj = 1 - sum(m.sentence(s, conjecture=False)[0] for s in held) / u
    prev = 1 - sum(sentence_oov(m, s, None)[0] for s in held) / u
    tab = SuffixTable(m)
    suf = 1 - sum(sentence_oov(m, s, tab)[0] for s in held) / u
    shuf = 1 - sum(sentence_oov(m, s, SuffixTable(m, shuffle=random.Random(5)))[0] for s in held) / u
    say(f"I5-c  OOV: no-conjecture {noconj:+.4f} | prev-only rule {prev:+.4f} (effect {prev-noconj:+.4f}) | suffix rule {suf:+.4f} | shuffled suffix table {shuf:+.4f}   "
        f"[effect >= 0 -> {'PASS' if prev - noconj >= 0 else 'FAIL'}; ablation bites (real - shuffled >= 0.005) -> {'yes' if suf - shuf >= 0.005 else 'NO'}]")
    best = max(noconj, prev, suf)
    say(f"I5-d  F1 total gain vs unigram (best rule): {best:+.4f}   [>= +0.10 -> {'PASS' if best >= 0.10 else 'FAIL'}]")

    pos = wordnet_pos(); tot = pure = 0
    for c, ws in m.members.items():
        tagged = [w for w in ws if w in pos]
        if len(tagged) < 2: continue
        b = max("nvar", key=lambda p: sum(1 for w in tagged if p in pos[w]))
        pure += sum(1 for w in tagged if b in pos[w]); tot += len(tagged)
    say(f"I5-e  POS purity vs WordNet: {pure/max(tot,1):.3f}")

    say("\n  AUDIT -- 10 classes by token mass, 10 most frequent members each:")
    for c in sorted(m.members, key=lambda c: -m.cn[c])[:10]:
        ws = sorted(m.members[c], key=lambda w: -m.wc[w])[:10]
        say(f"     class {c:<4} ({len(m.members[c]):>5} words): {' '.join(ws)}")
    say("  suffix table -- 5 suffixes with most types, top class share:")
    for sfx, cnt in sorted(tab.tab.items(), key=lambda kv: -sum(kv[1].values()))[:5]:
        c, n = cnt.most_common(1)[0]
        say(f"     -{sfx:<4} {sum(cnt.values()):>5} types, top class {c} share {n/sum(cnt.values()):.2f}")

    say(f"\n[{time.time()-T0:.0f}s]")
    tag = "CONVERGED" if meta.get("converged") else "UNCONVERGED"
    if best >= 0.10: say(f"LOOP IT.5 CONVERGENCE ({tag}): F1 REACHED {best:+.4f}; known-only {g_known:+.4f}")
    else: say(f"LOOP IT.5 CONVERGENCE ({tag}): F1 not reached, best {best:+.4f}; known-only {g_known:+.4f}; OOV effect {prev-noconj:+.4f}")
