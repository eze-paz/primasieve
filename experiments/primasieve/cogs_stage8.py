"""STAGE 8 RUN -- meaning-first fluent realization with RNG over meaning-preserving choices, gated on the
round-trip soundness invariant. Pre-registered gates:

  G8a  SOUNDNESS (the cardinal one): every RNG realization of a meaning PARSES BACK to the SAME meaning
       (voice-neutral role set). Zero meaning-confabulation -- a synonym or voice choice never alters meaning.
  G8b  FLUENCY: every realization is a complete, grammatical sentence the engine commits to (parses, no
       abstention on its own output).
  G8c  VARIETY: one meaning yields MANY distinct fluent surface forms (synonyms x voice) -- the RNG buys
       fluency and variation without touching soundness.
  G8d  the SIGNAL that keeps it honest: a corrupted realization (a wrong synonym that denotes a DIFFERENT
       concept) is CAUGHT by the round-trip -- the invariant can fail, so passing it means something.

Usage:  python cogs_stage8.py"""
import os, sys, random, collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cogs_fluent import meaning, realize_variants, build_train, role_set, SYN, CONCEPTS_N
from cogs_gram import induce, generate
from core.registry import selfcheck


def target_roleset(m):
    return frozenset({(m["event"], "agent", m["agent"]), (m["event"], "theme", m["theme"])})


if __name__ == "__main__":
    selfcheck(__file__)
    rng = random.Random(8)
    print("STAGE 8 -- MEANING FIRST, then fluent realization; RNG only over meaning-preserving choices.")
    print("Soundness invariant: every realization must parse back to the SAME meaning (round trip).\n")

    tr = build_train(rng, n=2500)
    m = induce(tr)
    print(f"  grammar induced from {len(tr)} fluent pairs (both voices, every synonym)\n")

    # generate meanings, realize each many times with RNG, round-trip each
    N = 300
    round_ok = confab = fluent = 0
    variety = []
    for _ in range(N):
        M = meaning(rng)
        want = target_roleset(M)
        surf_seen = set()
        for s, lf, voice in realize_variants(M, rng, n_samples=6):
            surf_seen.add(s)
            back = generate(m, s)                         # parse the realized sentence back to a logical form
            if back is None:
                continue                                  # not fluent/committed (counted below)
            fluent += 1
            got = role_set(back)
            if got == want:
                round_ok += 1
            else:
                confab += 1
        variety.append(len(surf_seen))
    total = round_ok + confab
    print(f"G8a  SOUNDNESS: round-trip preserved the meaning {round_ok}/{total} = {round_ok/max(total,1):.4f}   "
          f"CONFABULATION {confab}/{total} = {confab/max(total,1):.4f}   "
          f"[gate round-trip 1.000, CONFAB 0 -> {'PASS' if confab == 0 and total > 0 else 'FAIL'}]")

    # fluency: fraction of realizations the engine commits to
    tried = N * 6
    print(f"G8b  FLUENCY: {fluent}/{tried} = {fluent/tried:.4f} realizations are complete committed sentences   "
          f"[gate >= 0.99 -> {'PASS' if fluent/tried >= 0.99 else 'FAIL'}]")

    meanv = sum(variety) / len(variety)
    print(f"G8c  VARIETY: mean distinct surface forms per meaning {meanv:.2f} (synonyms x voice)   "
          f"[gate > 1.5 -> {'PASS' if meanv > 1.5 else 'FAIL'}]")

    # G8d -- the invariant can FAIL: corrupt a realization by swapping a content word for a DIFFERENT concept's
    # synonym and confirm the round trip catches the meaning change.
    caught = 0
    trials = 100
    for _ in range(trials):
        M = meaning(rng)
        s, lf, voice = realize_variants(M, rng, n_samples=1)[0]
        toks = s.split()
        # replace the agent surface ACTUALLY present with a synonym of a DIFFERENT concept -> meaning changes
        present = [i for i, t in enumerate(toks) if t in SYN[M["agent"]]]
        if not present:
            trials -= 1                                   # this realization didn't surface the agent word
            continue
        other = rng.choice([c for c in CONCEPTS_N if c != M["agent"]])
        toks[present[0]] = rng.choice(SYN[other])
        back = generate(m, " ".join(toks))
        if back is None or role_set(back) != target_roleset(M):
            caught += 1                                   # the corruption was caught (parse changed or failed)
    g8d = caught >= 0.95 * trials
    print(f"\nG8d  the invariant CAN fail: a wrong-concept synonym is caught by the round trip {caught}/{trials} "
          f"= {caught/trials:.3f}   [gate >= 0.95 -> {'PASS' if g8d else 'FAIL'}]")
    print("     -> soundness is real, not vacuous: change the MEANING and the round trip flags it; the RNG is")
    print("        safe precisely because it never changes the meaning, only the meaning-preserving surface.")

    allpass = confab == 0 and total > 0 and fluent / tried >= 0.99 and meanv > 1.5 and g8d
    print(f"\nSTAGE 8 MEANING-FIRST FLUENT REALIZATION: {'PASS' if allpass else 'FAIL'}")
    print("  Fluency and variety from RNG over synonyms + voice, with ZERO meaning-confabulation, gated by the")
    print("  round-trip invariant. NEXT: passively learn the realization grammar + synonym classes from raw")
    print("  text (alice.txt, WordNet) under the MDL oracle, replacing the paired supervision used here.")
