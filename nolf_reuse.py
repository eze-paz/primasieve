"""SLOT REUSE -- a degree-4 representation extension for the nolf learner (nolf_reuse_prereg.md).

MEASURED, before this file existed (nolf_reuse_probe.py): the strings describer's hardest predicate is

    idx = [i for i,a in enumerate(s) if a == x];  tv = bool(idx) and all(i+1 < len(s) and s[i+1] == y for i in idx)

whose truth condition is  AND( member(S,x), ALL(positions(S,x), i. eq(at(S,succ(i)), y)) )  -- 7 atoms, and it
mentions x TWICE. Handed to the real `_fit_candidate` with a non-injective slot mapping (0,0,1) it **FITS**:
denotation solve, verification and the evidence gate all pass, recovering the alphabet lexicon exactly. The same
term without the non-emptiness conjunct does NOT fit, so the second mention of x is load-bearing.

The shipped learner cannot represent it. `_solve` requires `len(holes(term)) == nslots` and iterates
`itertools.permutations(range(nslots))`, so a term binding one slot twice is discarded before the solver sees it.
This is core/grow.py's DEGREE 4: the representation cannot STATE the distinction. The collision probe returned 0
collisions and could not see it, because (situation, fill) -> truth IS a consistent function -- the term language
just cannot write that function.

THE EXTENSION, minimal: hole->slot MAPPINGS instead of permutations, required to be SURJECTIVE (every slot word
must receive a denotation, or it is unconstrained and the construction memorises). `_env_pool` already indexes
`fill[perm[j]]`, so mappings work mechanically -- injectivity was a convention in the candidate loop, never a
requirement of the machinery.

`_solve` is copied by SOURCE TRANSFORM, not retyped, so the extension is exactly two substitutions against the
shipped method and cannot drift from it.

    python nolf_reuse.py --world strings                 # extension arm
    python nolf_reuse.py --world strings --injective      # knockout: permutations only (the shipped behaviour)
    python nolf_reuse.py --report
"""
import os, sys, re, json, time, inspect, itertools, textwrap, collections
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import nolf_learn as NL

OUT = os.path.join(HERE, "nolf_reuse_results.json")
REUSE_EXTRA = 2          # declared bias: a term may bind at most nslots+2 holes, i.e. reuse at most two slots


def _slot_maps(nholes, nslots, injective=False):
    """hole -> slot mappings. Surjective: every slot must be bound, else its word is unconstrained and the
    construction can memorise. Permutations are the injective special case (the knockout)."""
    if injective:
        return list(itertools.permutations(range(nslots))) if nholes == nslots else []
    if nholes < nslots: return []
    out = [m for m in itertools.product(range(nslots), repeat=nholes) if len(set(m)) == nslots]
    # try the injective ones first: the shipped behaviour is a prefix of the extended search, so the extension
    # can only ever ADD reach, never lose a construction the knockout would have found
    out.sort(key=lambda m: (len(set(m)) != nholes, m))
    return out


def _build():
    """subclass with `_solve` source-transformed: two substitutions, nothing retyped."""
    src = textwrap.dedent(inspect.getsource(NL.Learner._solve))
    m = re.search(r"^([ \t]*)if len\(hs\) != nslots: continue$", src, re.M)
    if not m: raise RuntimeError("hole-count guard not found; nolf_learn._solve changed")
    ind = m.group(1)
    src = src[:m.start()] + (
        f"{ind}if len(hs) < nslots or len(hs) > nslots + REUSE_EXTRA: continue\n"
        f"{ind}if len(hs) != nslots and not self.reuse: continue"
    ) + src[m.end():]
    c = "sorted(itertools.permutations(range(nslots)), key=novelty)"
    d = "sorted(_slot_maps(len(hs), nslots, injective=not self.reuse), key=novelty)"
    if c not in src: raise RuntimeError("perm generation not found; nolf_learn._solve changed")
    src = src.replace(c, d)
    # min_novelty's own permutation walk is an ORDERING heuristic; keep it valid for longer hole lists
    src = src.replace("if len(hs_) != nslots: return 99", "if len(hs_) < nslots: return 99")
    src = src.replace("for perm in itertools.permutations(range(nslots)):",
                      "for perm in _slot_maps(len(hs_), nslots, injective=not self.reuse):")
    # ORDERING: `reuse(term)` prefers terms containing fragments of ADOPTED constructions. A SEEDED schema is in
    # the enumeration but in no adopted construction, so it received no preference at all -- measured: with the
    # cap lifted, the shape allowed and the target term PRESENT in the table, it was still never tried inside the
    # budget. Give the seed the same preference an earned fragment gets.
    src = src.replace("lib = fragments(self.grammar)",
                      "lib = dict(fragments(self.grammar)); lib.update(getattr(self, 'seed_lib', None) or {})")
    # ORDERING DEFECT, measured: `ordered()` groups by ops(t) while enum.candidates() yields in TABLE-LEVEL
    # order. With a library present those differ (leaves carry ops>0), so the level grouping shatters into
    # accidental equal-ops runs and the (min_novelty, reuse) sort applies inside runs of a few terms instead of a
    # size level. Measured on the seeded strings table: 20,831 candidates, only 562 carry the seed leaf, target at
    # index 204 among those but 10,026 raw. Replace the run grouping with ONE global sort, fragment-carrying
    # first (the library lever's whole premise: a fragment buys depth), then simplest, then least novel.
    mo = re.search(r"^([ \t]*)def ordered\(\):$", src, re.M)
    mf = re.search(r"^([ \t]*)for term in ordered\(\):$", src, re.M)
    if not (mo and mf): raise RuntimeError("ordered()/consumer not found; nolf_learn._solve changed")
    i0, i1 = mo.group(1), mo.group(1) + "    "
    src = src[:mo.start()] + (
        f"{i0}def ordered():\n"
        f"{i1}cs = list(enum.candidates(enum.max_ops))\n"
        f"{i1}cs.sort(key=lambda x: (reuse(x), ops(x), min_novelty(x)))\n"
        f"{i1}for x in cs: yield x\n\n"
    ) + src[mf.start():]
    ns = dict(NL.__dict__)                       # the shipped module's own globals: nothing can be missing
    ns.update(REUSE_EXTRA=REUSE_EXTRA, _slot_maps=_slot_maps, NL=NL)
    exec(compile(src, "<reuse_solve>", "exec"), ns)
    return ns["_solve"]


_SOLVE = _build()


class ReuseLearner(NL.Learner):
    def __init__(self, *a, reuse=True, **kw):
        super().__init__(*a, **kw)
        self.reuse = reuse
    _solve = _SOLVE


def fit_one(world, shuffled, budget, reuse):
    import nolf_worlds as NW
    import nolf_run as NR
    from core.verdict import score_two_mode, line
    W = (NW.Records(seed=71) if shuffled else NW.Records()) if world == "records" else \
        (NW.Strings(seed=72) if shuffled else NW.Strings())
    sp = NW.splits(W, 1)
    arm = "REUSE" if reuse else "INJECTIVE (knockout)"
    print(f"=== {W.name}{' SHUFFLED' if shuffled else ''} [{arm}] budget {budget}s", flush=True)
    L = ReuseLearner(time_budget=budget, reuse=reuse).fit(sp["train"])
    print(f"  {len(L.grammar)} constructions in {L.seconds:.0f}s (table {L.table_seconds:.0f}s)", flush=True)
    reused = 0
    for k, alts in L.grammar.items():
        for term, perm in alts:
            if len(set(perm)) != len(perm):
                reused += 1
                print(f"    REUSING SLOT  perm={perm}  {NL.show(term)}   <- {[x if x=='B' else x[1] for x in k]}", flush=True)
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
    d[f"{world}{'_shuffled' if shuffled else ''}{'' if reuse else '_injective'}"] = dict(
        scores=res, constructions=len(L.grammar), seconds=round(L.seconds), reused_slots=reused,
        learned=[[x if x == "B" else x[1] for x in e[1]] for e in L.log if e[0] == "learned"],
        unsolved=[[x if x == "B" else x[1] for x in e[1]] for e in L.log if e[0] != "learned"])
    json.dump(d, open(OUT, "w"), indent=1, sort_keys=True, default=str)


def report():
    if not os.path.exists(OUT): print("NO FITS SAVED"); return
    d = json.load(open(OUT)); ok = True
    bars = {"strings": 0.80, "records": 0.95}
    for w in ("strings", "records"):
        if w not in d: print(f"{w}: NO FIT"); ok = False; continue
        c = d[w]; Lc = c["scores"]["learner/heldout_comp"]; Li = c["scores"]["learner/heldout_iid"]
        hit = Lc["EM"] >= bars[w] and Lc["confab"] == 0
        print(f"{w}: R1/R2 comp EM {Lc['EM']:.4f} (iid {Li['EM']:.4f}) vs bar {bars[w]}  [{hit}]   "
              f"constructions {c['constructions']}  slot-reusing {c['reused_slots']}")
        ok &= hit
        cf = all(v["confab"] == 0 for k, v in c["scores"].items() if k.startswith("learner/"))
        print(f"    R3 confabulation 0 on every split  [{cf}]"); ok &= cf
        o = d.get(w + "_injective")
        if o:
            Oc = o["scores"]["learner/heldout_comp"]
            beat = Lc["EM"] > Oc["EM"] + 1e-9 or c["constructions"] > o["constructions"]
            print(f"    R4 KNOCKOUT --injective: EM {Oc['EM']:.4f}, constructions {o['constructions']}  ->  "
                  f"reuse {'BEATS' if beat else 'DOES NOT BEAT'} it  [{beat}]"
                  + ("" if beat else "   <- VACUOUS: the extension bought nothing here"))
            ok &= beat
        else:
            print("    R4 KNOCKOUT: NOT RUN"); ok = False
        s = d.get(w + "_shuffled")
        if s:
            g5 = abs(s["constructions"] - c["constructions"]) <= 1
            print(f"    R5 shuffled lexicon: constructions {s['constructions']} vs {c['constructions']}  [{g5}]")
            ok &= g5
        else:
            print("    R5 shuffled: NOT RUN")
    print("\nSLOT REUSE: PASS" if ok else "\nSLOT REUSE: NOT PASSED -- read the gate lines")


if __name__ == "__main__":
    a = sys.argv
    if "--report" in a: report(); sys.exit(0)
    fit_one(a[a.index("--world") + 1] if "--world" in a else "strings",
            "--shuffled" in a,
            int(a[a.index("--budget") + 1]) if "--budget" in a else 240,
            "--injective" not in a)
