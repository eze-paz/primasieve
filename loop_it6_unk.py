"""FLUENCY LOOP it.6 -- ESTIMATION: learned UNK symbol + Witten-Bell transitions (LOOP.md "ITERATION 6").
Build (resumable, background) and evaluation in one file:
    python loop_it6_unk.py build [slice_seconds]     -> settles the class map on the UNK-ified 30k train
    python loop_it6_unk.py eval                      -> gates I6-a..e under the cap"""
import os, sys, time, json, math, random, collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.seqform import ClassBigram, ClassBigramWB, unkify, apply_unk, UNK, save_classes, load_classes
from core.verdict import COMMIT, CONJECTURED
from core.registry import selfcheck
from cogs_stage9 import wordnet_pos
from loop_it1_size import load

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(HERE, "_nldata", "classes_wikt30k_K128_unk.json")
META = PATH + ".meta.json"
K, N = 128, 30000
T0 = time.time()


def say(s=""): print(s.encode("ascii", "replace").decode(), flush=True)


def data():
    tr, held = load()
    train, keep, n_rare = unkify(tr[:N])
    return train, apply_unk(held, keep), keep, n_rare


def settle(m, slice_s, meta):
    t0 = time.time()
    words = [w for w in m.vocab if m.wc[w] >= 2]; rare = [w for w in m.vocab if m.wc[w] < 2]
    while time.time() - t0 < slice_s:
        tp = time.time(); moves = 0
        for w in words:
            a = m.cls[w]; best = (1e-9, a)
            for b in range(m.K):
                if b != a:
                    d = m._delta(w, a, b)
                    if d > best[0]: best = (d, b)
            if best[1] != a: m._move(w, a, best[1]); moves += 1
        meta["passes"] += 1; meta["secs"] += time.time() - tp; meta["moves"].append(moves)
        save_classes(m, PATH); json.dump(meta, open(META, "w"))
        print(f"  pass {meta['passes']}: {moves} moves of {len(words)} words ({time.time()-tp:.0f}s)", flush=True)
        if moves <= 0.01 * len(words):
            meta["converged"] = True; json.dump(meta, open(META, "w"))
            print(f"CONVERGED (settled) after {meta['passes']} passes, {meta['secs']:.0f}s; rare words in vocab: {len(rare)}")
            return True
    print(f"slice over after {meta['passes']} passes ({meta['secs']:.0f}s); re-invoke")
    return False


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "eval"
    train, held, keep, n_rare = data()
    ident = math.log2(n_rare + 1)
    if mode == "build":
        slice_s = int(sys.argv[2]) if len(sys.argv) > 2 else 480
        m = ClassBigramWB(train, K, ident)
        meta = json.load(open(META)) if os.path.exists(META) else {"passes": 0, "secs": 0.0, "converged": False, "moves": []}
        load_classes(m, PATH)
        print(f"build: V={m.V} (rare types collapsed {n_rare}, UNK tokens {m.wc[UNK]}) K={K} passes so far {meta['passes']}", flush=True)
        if not meta["converged"]: settle(m, slice_s, meta)
        sys.exit(0)

    selfcheck(__file__)
    say("FLUENCY LOOP it.6 -- ESTIMATION: learned UNK symbol + Witten-Bell transitions on the class bigram (K=128, 30k).\n")
    meta = json.load(open(META)) if os.path.exists(META) else {}
    m = ClassBigramWB(train, K, ident); ok = load_classes(m, PATH)
    say(f"  map loaded={ok} converged={meta.get('converged')} passes={meta.get('passes')} build {meta.get('secs', 0):.0f}s; V={m.V}, rare types collapsed {n_rare} "
        f"(identity {ident:.2f} bits per UNK token, paid by both models); UNK tokens train {m.wc[UNK]}, class of UNK = {m.cls[UNK]}")
    m_add = ClassBigram(train, K); m_add.cls = dict(m.cls); m_add._rebuild()      # ablation (i): UNK without Witten-Bell
    m_add_unigram = m_add.unigram
    known = [s for s in held if UNK not in s]; unkS = [s for s in held if UNK in s]
    say(f"  held-out: {len(known)} sentences fully known, {len(unkS)} with an unseen word")

    def gain(model, sents, ident_extra=0.0):
        g = sum(model.sentence(s)[0] for s in sents); u = sum(1 + model.unigram(s) for s in sents)
        return 1 - g / u

    gk = gain(m, known); gu = gain(m, unkS); gt = gain(m, held)
    say(f"\nI6-a  KNOWN-ONLY gain vs unigram: {gk:+.4f} (n={len(known)})   [>= +0.06 -> {'PASS' if gk >= 0.06 else 'FAIL'}]")
    say(f"I6-b  OOV EFFECT: gain on UNK-bearing sentences vs unigram on the same sentences: {gu:+.4f} (n={len(unkS)})   [>= 0 -> {'PASS' if gu >= 0 else 'FAIL (fifth OOV null)'}]")
    say(f"I6-c  F1 total gain vs unigram: {gt:+.4f}   [>= +0.10 -> {'PASS' if gt >= 0.10 else 'FAIL'}]")
    # ablations: (i) UNK without WB = add-one class bigram on the same map; identity bits cancel in the ratio only if added to both -> add to both
    def gain_add(sents):
        g = sum(m_add.sentence(s)[0] + sum(1 for w in s if w == UNK) * ident for s in sents)
        u = sum(1 + m_add.unigram(s) + sum(1 for w in s if w == UNK) * ident for s in sents)
        return 1 - g / u
    ga = gain_add(held)
    # (ii) WB without UNK: the it.5 map with WB transitions (identity bits as before: unigram-unknown cost inside sentence())
    from loop_it5_build import PATH as P5
    tr_raw, held_raw = load()
    m5 = ClassBigramWB(tr_raw[:N], K, 0.0); ok5 = load_classes(m5, P5)
    g5 = 1 - sum(m5.sentence(s, conjecture=False)[0] for s in held_raw) / sum(1 + m5.unigram(s) for s in held_raw) if ok5 else float("nan")
    say(f"I6-d  ABLATIONS: UNK without Witten-Bell {ga:+.4f}; Witten-Bell on the it.5 map without UNK (no-conjecture path) {g5:+.4f}; both {gt:+.4f}; it.5 reference +0.0098")
    pos = wordnet_pos(); tot = pure = 0
    for c, ws in m.members.items():
        tagged = [w for w in ws if w in pos]
        if len(tagged) < 2: continue
        b = max("nvar", key=lambda p: sum(1 for w in tagged if p in pos[w]))
        pure += sum(1 for w in tagged if b in pos[w]); tot += len(tagged)
    say(f"I6-e  POS purity vs WordNet (frequent words only now): {pure/max(tot,1):.3f}")
    say("\n  AUDIT -- class of UNK and its 12 most frequent members; 6 other classes by mass:")
    cu = m.cls[UNK]
    say(f"     UNK class {cu} ({len(m.members[cu])} words): " + " ".join(w if w != UNK else "<UNK>" for w in sorted(m.members[cu], key=lambda w: -m.wc[w])[:12]))
    for c in sorted(m.members, key=lambda c: -m.cn[c])[:6]:
        ws = sorted(m.members[c], key=lambda w: -m.wc[w])[:10]; say(f"     class {c:<4} ({len(m.members[c]):>5} words): {' '.join(w if w != UNK else '<UNK>' for w in ws)}")
    say(f"\n[{time.time()-T0:.0f}s]")
    if gt >= 0.10: say(f"LOOP IT.6 ESTIMATION: F1 REACHED {gt:+.4f} (known-only {gk:+.4f}, OOV {gu:+.4f})")
    else: say(f"LOOP IT.6 ESTIMATION: F1 not reached {gt:+.4f}; known-only {gk:+.4f}; OOV effect {gu:+.4f}")
