"""FLUENCY LOOP iteration 4 -- ZERO-BIT OOV: unknown word's class = deterministic function of its induced suffix
signature and the previous class (LOOP.md "ITERATION 4", committed before this run).

Usage:  python loop_it4_oov.py"""
import os, sys, random, time, math, collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.seqform import ClassBigram, SuffixTable, sentence_oov
from core.verdict import COMMIT, CONJECTURED
from core.registry import selfcheck
from core.form import sentences
from cogs_stage9 import chapters, shuffled
from loop_it1_size import load

T0 = time.time()


def say(s=""): print(s, flush=True)


def gains(m, held, table):
    u = sum(1 + m.unigram(s) for s in held)
    noconj = sum(m.sentence(s, conjecture=False)[0] for s in held)
    prev_only = sum(sentence_oov(m, s, None)[0] for s in held)
    suffix = sum(sentence_oov(m, s, table)[0] for s in held)
    known = [s for s in held if all(w in m.cls for w in s)]
    uk = sum(1 + m.unigram(s) for s in known); gk = sum(m.sentence(s)[0] for s in known)
    return dict(noconj=1 - noconj / u, prev=1 - prev_only / u, suffix=1 - suffix / u, known=1 - gk / uk,
                known_frac=len(known) / len(held))


if __name__ == "__main__":
    selfcheck(__file__)
    say("FLUENCY LOOP it.4 -- ZERO-BIT OOV: deterministic class for unknown words from induced suffix signature + previous class.\n")
    tr_all, held = load()
    ch = chapters()
    alice_tr = [s for c in ch[:9] for s in sentences(c)]; alice_hd = [s for c in ch[9:] for s in sentences(c)]
    rows = {}
    for name, tr, hd, budget in (("alice", alice_tr, alice_hd, 15), ("wikt-3000", tr_all[:3000], held, 25), ("wikt-30000", tr_all[:30000], held, 95)):
        m = ClassBigram(tr, 64)
        st = m.exchange(budget)
        tab = SuffixTable(m)
        g = gains(m, hd, tab)
        tabs = SuffixTable(m, shuffle=random.Random(4))
        gs = 1 - sum(sentence_oov(m, s, tabs)[0] for s in hd) / sum(1 + m.unigram(s) for s in hd)
        rows[name] = (g, gs, m, st)
        say(f"  {name:<11} K=64 V={m.V:<6} moves {st['moves']:<6} {'SPENT' if st['spent'] else 'conv '} {st['secs']:4.0f}s | gain vs unigram: no-conj {g['noconj']:+.4f}  "
            f"prev-only rule {g['prev']:+.4f}  SUFFIX rule {g['suffix']:+.4f}  (shuffled suffix table {gs:+.4f}) | KNOWN-ONLY {g['known']:+.4f} on {g['known_frac']:.3f} of sentences | "
            f"suffixes in table {len(tab.tab)}   [{time.time()-T0:.0f}s]")

    g30, gs30 = rows["wikt-30000"][0], rows["wikt-30000"][1]
    i4a = g30["suffix"] - g30["noconj"]
    say(f"\nI4-a  OOV EFFECT at 30000: suffix rule {g30['suffix']:+.4f} - no-conjecture {g30['noconj']:+.4f} = {i4a:+.4f}   [>= 0 -> {'PASS' if i4a >= 0 else 'FAIL (fourth OOV null)'}]")
    say(f"I4-b  F1 at 30000 K=64: {g30['suffix']:+.4f}   [>= +0.10 -> {'PASS' if g30['suffix'] >= 0.10 else 'FAIL'}]")
    say(f"I4-c  KNOWN-ONLY gain at 30000: {g30['known']:+.4f} on {g30['known_frac']:.3f} of held-out sentences")
    say(f"I4-d  SUFFIX ABLATION at 30000: real table {g30['suffix']:+.4f} vs shuffled {gs30:+.4f} vs prev-only {g30['prev']:+.4f}   "
        f"[shuffled must fall toward prev-only -> {'ablation bites' if gs30 < g30['suffix'] and abs(gs30 - g30['prev']) < abs(g30['suffix'] - g30['prev']) else 'ABLATION DOES NOT BITE'}]")
    k1 = random.Random(1)
    ms = ClassBigram(shuffled(tr_all[:3000], k1), 64); ms.exchange(20)
    hs = shuffled(held, k1)
    gk1 = 1 - sum(sentence_oov(ms, s, SuffixTable(ms))[0] for s in hs) / sum(1 + ms.unigram(s) for s in hs)
    say(f"I4-e  K1 SHUFFLED ORDER at 3000: suffix-rule gain {gk1:+.4f} vs real {rows['wikt-3000'][0]['suffix']:+.4f}")
    m = rows["wikt-30000"][2]
    tab = SuffixTable(m)
    say("\n  AUDIT -- 6 suffixes with the most word types and their top class's members:")
    for sfx, cnt in sorted(tab.tab.items(), key=lambda kv: -sum(kv[1].values()))[:6]:
        c = cnt.most_common(1)[0][0]
        ws = sorted(m.members[c], key=lambda w: -m.wc[w])[:8]
        say(f"     -{sfx:<4} {sum(cnt.values()):>5} types, top class {c} ({cnt[c]}/{sum(cnt.values())}): {' '.join(ws)}")
    say(f"\n[{time.time()-T0:.0f}s]")
    if g30["suffix"] >= 0.10: say(f"LOOP IT.4 ZERO-BIT OOV: F1 REACHED {g30['suffix']:+.4f}")
    elif i4a >= 0: say(f"LOOP IT.4 ZERO-BIT OOV: OOV EFFECT POSITIVE {i4a:+.4f}, F1 not reached ({g30['suffix']:+.4f}); known-only {g30['known']:+.4f}")
    else: say(f"LOOP IT.4 ZERO-BIT OOV: NULL -- OOV effect {i4a:+.4f}")
