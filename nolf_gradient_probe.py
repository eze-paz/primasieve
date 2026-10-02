"""DIAGNOSTIC (read-only): does a REPAIR/DENOISING proposer have a slope to climb on an unsolved nolf skeleton?

WHY THIS QUESTION. E-5 measured that a task-level sound binary verdict is a flat landscape. But E9/E15 measured
the opposite INSIDE a task: a match-count gradient, pre-registered as deceptive, reached a verified target at
17.7-18.7x below blind -- "the frontier was deceptive, not the signal" -- for the residual-repair shape
(almost-right-primitive-plus-correction). Diffusion's transferable trick is exactly that shape: corrupt a
known-good object, learn the single-step repair, iterate. nolf's proposer uses none of it: blind size-ordered
enumeration.

THE SIGNAL IS ALREADY COMPUTED AND THROWN AWAY. `Learner._verify` returns the index of the FIRST FAILING ROW.
That is how far a candidate got before contradiction -- a graded, sound, per-candidate score the search computes
on every term and then discards, keeping only pass/fail.

This logs it and asks two things:
  1. DISTRIBUTION  is `reached` flat (every candidate dies at the same place -> nothing to climb) or spread?
  2. SLOPE         do candidates that are STRUCTURALLY NEARER an adopted construction reach further? That is the
                   denoiser's premise: proximity to something already verified predicts quality.

Honest confounder, stated up front: with a low true-fraction skeleton a constant-false term satisfies most rows,
so `reached` is inflated for degenerate candidates. Terms are therefore also scored on the TRUE rows alone.

Nothing here is a gate and nothing is claimed.

    python nolf_gradient_probe.py --world strings --skel "['gloop', 6, 5, 6]" --ref "[6, 5, 6]" --per 120
"""
import os, sys, time, collections
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import nolf_learn as NL
import nolf_fast as F

CUR = [None]
LOG = collections.defaultdict(int)          # term -> furthest row index reached by any verify
TRIED = set()


def instrument():
    real_compile = NL.compile_term
    def compile_spy(term):
        CUR[0] = term; TRIED.add(term); return real_compile(term)
    NL.compile_term = compile_spy

    real_verify = NL.Learner._verify
    def verify_spy(self, f, rows, hs, perm, doms):
        ok, unpinned, bad = real_verify(self, f, rows, hs, perm, doms)
        reached = len(rows) if ok else (bad or 0)
        t = CUR[0]
        if t is not None and reached > LOG[t]: LOG[t] = reached
        return ok, unpinned, bad
    NL.Learner._verify = verify_spy


def jaccard(a, b):
    sa, sb = set(NL.subterms(a)), set(NL.subterms(b))
    return len(sa & sb) / len(sa | sb) if (sa | sb) else 0.0


def main(world, skel, ref, per):
    W, train, L, probes, elems, rels, sels = F._setup(world)
    E = F.table(world, probes, elems, rels, sels, 4, 60000, None)
    g = F.groups_of(L, train)
    keys = {F.show_key(k): k for k in g}
    if skel not in keys or ref not in keys:
        print("skeleton not found; run nolf_fast.py --list"); return

    # 0. WARM-UP. Measured the hard way: a skeleton solved in ISOLATION mostly does not solve at all -- the
    # constraint problem is only tractable once earlier constructions have PINNED words in L.dom. That is what
    # the real loop's pinned_frac curriculum is for, and resetting dom per probe threw it away.
    L.grammar = {}; L.dom = {}; L.demoted = set()
    order = sorted(g, key=lambda k: -len(g[k]))
    for _ in range(2):
        for k in order:
            if k in L.grammar or len(g[k]) < NL.MIN_ROWS or k == keys[skel]: continue
            L.deadline = time.time() + 30
            f = L._solve(k, list(g[k]), E)
            if f:
                L._adopt(k, list(g[k]), f)
                print(f"  warm-up: {F.show_key(k)} -> {NL.show(f[0][0])}", flush=True)
    print(f"  warm-up done: {len(L.grammar)} constructions, {len(L.dom)} pinned (word,kind) denotations", flush=True)

    # 1. the REFERENCE: the adopted neighbour construction's real term
    if keys[ref] not in L.grammar:
        print(f"reference {ref} did not solve even after warm-up; cannot measure proximity"); return
    reference = L.grammar[keys[ref]][0][0]
    print(f"reference construction {ref}: {NL.show(reference)}", flush=True)

    # 2. the TARGET: run the real search, logging how far every candidate got
    rows = g[keys[skel]]
    pos = sum(1 for _, _, tv in rows if tv)
    print(f"target {skel}: {len(rows)} rows, {pos} true ({pos/len(rows):.3f}) -- a constant-FALSE term satisfies "
          f"{1-pos/len(rows):.3f} of them", flush=True)
    instrument()
    L.grammar = {}; L.dom = {}; L.demoted = set(); L.deadline = time.time() + per
    t0 = time.time()
    hit = L._solve(keys[skel], list(rows), E)
    print(f"search ran {time.time()-t0:.0f}s, compiled {len(TRIED)} candidates, "
          f"{len(LOG)} reached a verify   -> {'SOLVED' if hit else 'no term'}", flush=True)

    if not LOG:
        print("\nNO candidate ever reached verification: every term died in constraint propagation.\n"
              "-> there is no per-candidate gradient to expose here at all; a repair proposer has nothing to read.")
        return

    vals = sorted(LOG.values(), reverse=True)
    n = len(vals)
    print(f"\nreached-row distribution over {n} scored candidates:")
    print(f"  max {vals[0]}   p90 {vals[int(n*0.10)]}   median {vals[n//2]}   min {vals[-1]}")
    hist = collections.Counter(vals)
    top = hist.most_common(5)
    print(f"  most common values: {top}")
    flat = top[0][1] / n
    print(f"  {flat:.1%} of candidates share the single most common value"
          + ("   <-- FLAT: nothing to climb" if flat > 0.9 else "   <-- SPREAD: a gradient exists"))

    # 3. SLOPE: does structural proximity to the reference predict reaching further?
    pairs = [(jaccard(t, reference), v) for t, v in LOG.items()]
    pairs.sort(reverse=True)
    near = [v for j, v in pairs[:max(20, len(pairs)//10)]]
    far = [v for j, v in pairs[-max(20, len(pairs)//10):]]
    mn, mf = sum(near)/len(near), sum(far)/len(far)
    print(f"\nSLOPE (the denoiser's premise):")
    print(f"  nearest-10% to reference : mean reached {mn:.1f}  (max jaccard {pairs[0][0]:.3f})")
    print(f"  farthest-10%             : mean reached {mf:.1f}")
    print(f"  -> {'PROXIMITY PREDICTS QUALITY: repair has a slope' if mn > mf * 1.15 else 'NO SLOPE: proximity to a verified construction predicts nothing'}")
    print("\ntop candidates by reached rows:")
    for t, v in sorted(LOG.items(), key=lambda kv: -kv[1])[:8]:
        print(f"  {v:5d}  jac {jaccard(t, reference):.3f}  {NL.show(t)}")


if __name__ == "__main__":
    a = sys.argv
    main(a[a.index("--world") + 1] if "--world" in a else "strings",
         a[a.index("--skel") + 1] if "--skel" in a else "['gloop', 6, 5, 6]",
         a[a.index("--ref") + 1] if "--ref" in a else "[6, 5, 6]",
         int(a[a.index("--per") + 1]) if "--per" in a else 120)
