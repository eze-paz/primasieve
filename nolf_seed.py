"""SEEDED STRUCTURAL SCHEMAS + SLOT REUSE (nolf_reuse_prereg.md, arm 2). Owner approved hardcoded structure.

WHY BOTH ARE NEEDED, measured rather than argued:
  * nolf_reuse_probe.py: the target truth condition for 'every x followed y' is
        AND( member(S,x), ALL(positions(S,x), i. eq(at(S,succ(i)), y)) )
    which FITS the real solver -- but binds x TWICE, and the shipped `_solve` discards any term whose hole count
    differs from the slot count. -> slot reuse is NECESSARY.
  * that term is SEVEN atom applications. The enumerated table holds 20,159 BOOL terms at depth 4 and 193,217 at
    depth 5 (measured, 875 s); depth 7 extrapolates to ~2e7 and is not enumerable. -> reuse alone is INSUFFICIENT.

THE SEED, and what makes it not just handing over the answer: ONE generic sequence-navigation schema,

        eq( at(S, succ(x)), _e )        "the element after this position is _e"

is injected as an ops-0 leaf of the lambda table. It names no word, no alphabet symbol and no predicate of the
world; it is a fact about SEQUENCES, of the kind a learner has from tracking order before it has language. With
it the target sits at depth 4: member (1) + positions (1) + ALL (1) + AND (1) over the leaf. The quantifier, the
conjunction, the non-emptiness guard and every denotation are still INDUCED.

Deliberately NOT seeded: the 5-atom ALL(positions(...), ...) core, which would be the answer itself.

Verification is untouched -- the denotation solve, `_verify` and the evidence gate are the shipped ones, so a hit
is a real hit and a wrong seed can only waste time.

    python nolf_seed.py --world strings                    # seed + reuse
    python nolf_seed.py --world strings --no-reuse         # knockout A: seed only
    python nolf_seed.py --world strings --no-seed          # knockout B: reuse only
    python nolf_seed.py --world strings --shuffled
"""
import os, sys, re, json, time, inspect, itertools, textwrap, collections
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import nolf_learn as NL
import nolf_reuse as RU

OUT = os.path.join(HERE, "nolf_seed_results.json")


def atoms():
    A = {}
    for p in NL.P.pids():
        a, r = NL.P.signature(p)
        fn = NL.P._FN[p]
        try:
            if a == (NL.SEQ, NL.ELEM) and r == NL.SEQ: A["positions"] = p
            elif a == (NL.SEQ, NL.ELEM) and r == NL.BOOL: A["member"] = p
            elif a == (NL.INT,) and r == NL.INT and fn(3) == 4: A["succ"] = p
            elif a == (NL.SEQ, NL.INT) and r == NL.ELEM: A["at_elem"] = p
            elif a == (NL.ELEM, NL.ELEM) and r == NL.BOOL: A["eq_elem"] = p
            elif a == (NL.BOOL, NL.BOOL) and r == NL.BOOL and fn(True, False) is False: A["and"] = p
        except Exception:
            pass
    return A


def seed_library():
    """ONE schema: 'the element after this position is _e'. VAR-carrying, so it lands in the lambda table as a
    depth-0 BOOL leaf -- exactly where SELECT/ALL bodies are drawn from."""
    A = atoms()
    need = ["at_elem", "succ", "eq_elem"]
    if any(n not in A for n in need): raise RuntimeError(f"missing atoms: {[n for n in need if n not in A]}")
    frag = ("A", A["eq_elem"], ("A", A["at_elem"], ("SIT",), ("A", A["succ"], ("VAR",))), ("H", NL.HE))
    return {frag: (NL.BOOL, True)}


def _build_fit():
    """source-transform `fit` so the enumerator carries the seed library. Two substitutions, nothing retyped."""
    src = textwrap.dedent(inspect.getsource(NL.Learner.fit))
    m = re.search(r"^([ \t]*)enum = Enumerator\(probes, elems, rels, sels\)$", src, re.M)
    if not m: raise RuntimeError("enumerator construction not found; nolf_learn.fit changed")
    ind = m.group(1)
    src = src[:m.start()] + f"{ind}enum = Enumerator(probes, elems, rels, sels, library=self.seed_lib)" + src[m.end():]
    ns = dict(NL.__dict__)
    ns.update(NL=NL)
    exec(compile(src, "<seed_fit>", "exec"), ns)
    return ns["fit"]


_FIT = _build_fit()


class SeedLearner(RU.ReuseLearner):
    def __init__(self, *a, seed=True, fallback=True, **kw):
        super().__init__(*a, **kw)
        self.seed_lib = seed_library() if seed else None
        self.fallback = fallback
    fit = _FIT

    def __call__(self, x):
        """MEASURED: with the seed the learner adopts a 7th construction on the RAW key ['gloop', 6, 5, 6], and EM
        does not move at all -- abstain stays at 0.2517 to four decimals. The reason is that prediction reduces
        first: greedy `_reduce` swallows a sub-span of [every, x, followed, y] and hands lookup the key
        ['gloop', 'B'], which no construction covers, so the new construction never fires. `fit` already carries an
        unreduced fallback for exactly this ('the greedy reduction may have swallowed a non-constituent'); the
        prediction path does not.

        Added SOUNDLY, not opportunistically: both analyses are computed and a value is returned only when they do
        not disagree. Two analyses that disagree ABSTAIN, which is the standing verdict rule -- a fallback that
        simply preferred whichever analysis answered would be a confabulation channel."""
        sit, toks = x
        if any(w not in self.cls for w in toks): return None
        self.demoted = set()
        vals = []
        analyses = [self._reduce(toks)]
        if self.fallback:
            analyses.append([("c", self.cls[w], w) for w in toks])
        for items in analyses:
            key, fill = self._span_key(items)
            if key is None: continue
            outs = self._sub_values(("B", key, fill), sit)
            if len(outs) == 1: vals.append(next(iter(outs)))
        if not vals: return None
        return vals[0] if all(v is vals[0] for v in vals) else None


def fit_one(world, shuffled, budget, reuse, seed, cap=60000, fallback=True):
    # MEASURED: at the shipped BANK_CAP=6000 the target term is NOT in the seeded table; at 60000 it IS.
    # The cap, slot reuse and the seed are JOINTLY necessary -- lifting the cap alone (nolf_cap_probe) changed
    # nothing precisely because the other two were missing. Declared bias, reported, not tuned per world.
    NL.BANK_CAP = cap
    import nolf_worlds as NW
    import nolf_run as NR
    from core.verdict import score_two_mode, line
    W = (NW.Records(seed=71) if shuffled else NW.Records()) if world == "records" else \
        (NW.Strings(seed=72) if shuffled else NW.Strings())
    sp = NW.splits(W, 1)
    arm = f"{'SEED' if seed else 'no-seed'}+{'REUSE' if reuse else 'no-reuse'}+cap{cap}+{'fb' if fallback else 'NOfb'}"
    print(f"=== {W.name}{' SHUFFLED' if shuffled else ''} [{arm}] budget {budget}s", flush=True)
    L = SeedLearner(time_budget=budget, reuse=reuse, seed=seed, fallback=fallback).fit(sp["train"])
    print(f"  {len(L.grammar)} constructions in {L.seconds:.0f}s (table {L.table_seconds:.0f}s)", flush=True)
    reused = 0
    for k, alts in L.grammar.items():
        for term, perm in alts:
            if len(set(perm)) != len(perm):
                reused += 1
                print(f"    *** SLOT REUSE *** perm={perm}  {NL.show(term)}   <- {[x if x=='B' else x[1] for x in k]}", flush=True)
    for e in L.log:
        k = [x if x == "B" else x[1] for x in e[1]]
        print(f"    {'learned ' if e[0]=='learned' else 'UNSOLVED'} {e[2]:4d} rows  {e[3] if e[0]=='learned' else ''}  <- {k}", flush=True)
    res = {}
    for name, m in [("bag-of-words", NR.BagOfWords(sp["train"])), ("analogy", NR.Analogy(sp["train"])), ("learner", L)]:
        for split in ("heldout_iid", "heldout_comp"):
            r = score_two_mode(m, [((sit, toks), tv) for sit, toks, tv in sp[split]])
            res[f"{name}/{split}"] = {kk: vv for kk, vv in r.items() if kk != "per"}
            print(line(f"{name} / {split}", r, width=30), flush=True)
    d = json.load(open(OUT)) if os.path.exists(OUT) else {}
    tag = (f"{world}{'_shuffled' if shuffled else ''}"
           f"{'' if (reuse and seed) else ('_noreuse' if seed else '_noseed')}{'' if cap==60000 else f'_cap{cap}'}{'' if fallback else '_nofb'}")
    d[tag] = dict(scores=res, constructions=len(L.grammar), seconds=round(L.seconds), reused_slots=reused,
                  learned=[[x if x == "B" else x[1] for x in e[1]] for e in L.log if e[0] == "learned"],
                  unsolved=[[x if x == "B" else x[1] for x in e[1]] for e in L.log if e[0] != "learned"])
    json.dump(d, open(OUT, "w"), indent=1, sort_keys=True, default=str)


if __name__ == "__main__":
    a = sys.argv
    fit_one(a[a.index("--world") + 1] if "--world" in a else "strings",
            "--shuffled" in a,
            int(a[a.index("--budget") + 1]) if "--budget" in a else 300,
            "--no-reuse" not in a, "--no-seed" not in a,
            int(a[a.index("--cap") + 1]) if "--cap" in a else 60000,
            "--no-fallback" not in a)
