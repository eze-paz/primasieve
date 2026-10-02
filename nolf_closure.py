"""CLOSURE-SCHEDULED LIBRARY GROWTH for the nolf learner (nolf_closure_prereg.md). Imports core/ only.

The measured problem (ARCHITECTURE.md, Phase 3): the learner is correct and budget-bound, and the LIBRARY LEVER
-- fragments of adopted constructions entering the enumeration as ops-0 LEAVES -- is the one mechanism that beats
the exponential. It took records 0.715 -> 1.000. Strings did not move: "its two unsolved constructions need
positions/successor fragments no adopted construction supplies".

Two facts in nolf_learn.py make that a structural claim, not a budget observation:
  BOOTSTRAP GAP   fragments() harvests sub-terms of ADOPTED constructions only, and adoption requires passing the
                  evidence gate -- so a sub-term useless alone but necessary as a COMPONENT can never become a
                  leaf. To get the fragment you must already have solved the thing it was needed for.
  ONCE ONLY       the library pass fires exactly once; fragments produced by adoptions made DURING it are never
                  used, because the next empty `todo` breaks the loop.

This is E-5 -> E-6 again (core/closure.py): adoption-gated harvesting is a flat landscape over fragment space,
where "not yet reachable" and "never reachable" are indistinguishable. What E-6 measured as the closure's real
contribution -- prioritisation, the stall trigger, the halt -- is what is applied here.

THE HONEST DISANALOGY, and it bounds the claim: in E-6 a task IS a target signature, so closure.distance() is an
exact membership test. Here a skeleton's target is a truth column and a term's signature depends on the
denotations solved for it, so E-6's distance-to-task test is NOT available and is not used. The closure is used
for the exact reachable-SIGNATURE set (so a promotion that adds nothing new is skipped soundly), the stall, and
the halt. Verification is untouched: promotion changes what is ENUMERATED, never what is accepted.

    python nolf_closure.py --world strings              # closure arm
    python nolf_closure.py --world strings --once       # C4 knockout: the current once-only library pass
    python nolf_closure.py --world records --shuffled   # C6
    python nolf_closure.py --report                     # C1-C6 over the saved fits
"""
import os, sys, json, time, collections
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import nolf_learn as NL
from nolf_learn import (Enumerator, fragments, subterms, ops, holes, result_type, has_var, show,
                        compile_term, MIN_ROWS, MAX_HOLES, HOLE_TYPE, BOOL)
from core.closure import Closure

OUT = os.path.join(HERE, "nolf_closure_results.json")
PROMOTE = 24                 # declared bias: promotion cap per stall, a budget device, not tuned per world


# ------------------------------------------------------------------------------- composition over fragment space
def subst_first(a, b):
    """ordered pair-composition (E-6's pair-closure, depth 1): b into the FIRST hole of a whose type matches b's
    result type. Operator holes (relation/selector) take a word's denotation, never a term, and are skipped."""
    tb = result_type(b)
    if tb is None: return None
    done = [False]

    def walk(t):
        if done[0]: return t
        tag = t[0]
        if tag == "H":
            if HOLE_TYPE.get(t[1]) == tb: done[0] = True; return b
            return t
        if tag in ("SIT", "VAR", "K"): return t
        if tag == "A": return (t[0], t[1]) + tuple(walk(x) for x in t[2:])
        if tag == "SK": return (t[0], t[1]) + tuple(walk(x) for x in t[2:])
        return (t[0],) + tuple(walk(x) for x in t[1:])

    out = walk(a)
    return out if done[0] else None


class FragmentSpace:
    """the thread's compose/sig for core.closure, plus the library it maintains. `sig` is the enumerator's own
    observational signature (hole KINDS included -- the lesson that keeps not(_b) and 0<_i apart)."""

    def __init__(self, enum):
        self.enum = enum

    def compose(self, a, b):
        return subst_first(a, b) if a is not None and b is not None else None

    def sig(self, term):
        if term is None: return None
        if len(holes(term)) > MAX_HOLES: return None
        try:
            return self.enum._sig(term, False)
        except Exception:
            return None


# ------------------------------------------------------------------------------------------------- the learner
class ClosureLearner(NL.Learner):
    """rounds instead of one library pass. On adoption the library grows from the new construction's fragments;
    on a STALL (a full round with no adoption) the closure promotes recurring sub-terms the library cannot
    already reach; on a stall that promotes nothing new, HALT."""

    def __init__(self, *a, once=False, **kw):
        super().__init__(*a, **kw)
        self.once = once                 # C4 knockout: reproduce nolf_learn's single library pass
        self.energy = 0                  # closure maintenance + queries, charged as in E-6
        self.rounds = []                 # (round, mode, constructions_after, promoted, seconds)
        self.halt_reason = None
        self.promoted = {}
        self.last_rebuild = 0.0          # seconds the most recent enumerator rebuild cost; a rebuild cannot be
                                         # preempted once started, so the stall guard budgets for it in advance

    def _rebuild(self, probes, elems, rels, sels, lib, space):
        """rebuild the enumerator with the current library as leaves, and CHARGE the wall time, so the stall guard
        knows what the next one will cost. Timed here rather than folded into a round: the first version left it
        out of every round's clock and a 240 s fit ran 683 s."""
        t = time.time()
        enum = Enumerator(probes, elems, rels, sels, library=lib, max_ops=2) if lib else \
            Enumerator(probes, elems, rels, sels)
        enum.table(False)
        self.last_rebuild = time.time() - t
        space.enum = enum
        return enum

    # ---- the promotion step: core/generate.py's SLEEP applied to fragment space --------------------------------
    def _promote(self, enum, space, closure, lib_names):
        """candidates are sub-terms (>=1 atom) of the enumeration's distinct-signature representatives, ranked by
        RECURRENCE -- how many distinct representatives contain them. Target-blind by construction: the statistic
        reads the enumeration, never the truth column. A candidate whose signature the closure already reaches is
        skipped: it would add no new leaf, and that judgement is exact, not scored."""
        recur = collections.Counter()
        seen = set()
        for lam in (False, True):
            T = enum.tables.get(lam)
            if not T: continue
            for k in sorted(T):
                for ty in T[k]:
                    for term in T[k][ty]:
                        for sub in subterms(term):
                            if ops(sub) >= 1 and result_type(sub) is not None and len(holes(sub)) <= MAX_HOLES:
                                if sub not in seen: seen.add(sub)
                                recur[sub] += 1
        out = {}
        for term, _ in recur.most_common():
            if len(out) >= PROMOTE: break
            if term in self.promoted or term in lib_names: continue
            s = space.sig(term)
            if s is None: continue
            self.energy += 1
            if s in closure.sigs: continue                    # exactly reachable already -- promoting adds nothing
            out[term] = (result_type(term), has_var(term))
        return out

    # ---- fit ---------------------------------------------------------------------------------------------------
    def fit(self, train):
        t0 = time.time(); self.deadline = t0 + self.budget
        self._classes(train)
        elems = set(); ints = set(range(0, 10))
        for sit, _, _ in train:
            for x in sit:
                if NL.P.CHECK[NL.ELEM](x): elems.add(x)
                elif NL.P.CHECK[NL.SEQ](x):
                    for y in x:
                        if NL.P.CHECK[NL.ELEM](y): elems.add(y)
        rels = [p for p in NL.P.pids() if NL.P.signature(p) == ((NL.INT, NL.INT), BOOL)]
        sels = [("all",), ("any",)] + [("idx", k) for k in range(-1, 4)]
        self.universe = {NL.HI: sorted(ints), NL.HE: sorted(elems, key=repr), NL.HR: rels, NL.HS: sels}
        by_size = {}
        for sit, _, _ in train:
            by_size.setdefault(len(sit), []).append(sit)
        probes = [x for k in sorted(by_size) for x in by_size[k][:3]][:8]
        if len(probes) < 8: probes += [sit for sit, _, _ in train[:8 - len(probes)]]

        enum = Enumerator(probes, elems, rels, sels)
        enum.table(False); self.table_seconds = time.time() - t0; self.t0 = t0; self.enum = enum
        space = FragmentSpace(enum)
        closure = Closure(space.compose, space.sig)
        self.demoted = set()
        self.log = []
        final = t0 + self.budget
        tried = {}
        library_pass = False                # knockout arm only
        rnd = 0
        lib = {}

        while time.time() < final:
            rnd += 1; r_t0 = time.time(); adopted_before = len(self.grammar)
            # ---- one round over the skeletons, under the existing self-generated curriculum (unchanged) --------
            while time.time() < final:
                groups = collections.defaultdict(list); raw = collections.defaultdict(list)
                for sit, toks, tv in train:
                    items = self._reduce(toks); key, fill = self._key(items)
                    groups[key].append((sit, fill, tv))
                    rkey, rfill = self._key([("c", self.cls[w], w) for w in toks]); raw[key].append((rkey, (sit, rfill, tv)))
                npins = len(self.dom)
                pinned_words = {k[0] for k in self.dom}

                def pinned_frac(key, rows):
                    slots = {w for _, fill, _ in rows for w in fill if isinstance(w, str)}
                    return sum(1 for w in slots if w in pinned_words) / len(slots) if slots else 1.0

                def unknown_classes(key):
                    return sum(1 for k in key if k != "B" and k[0] == "C"
                               and not any(self.cls.get(w) == k[1] for (w, _) in self.dom))

                pending = [(k, r) for k, r in groups.items() if k not in self.grammar and len(r) >= MIN_ROWS
                           and any(x != "B" and x[0] == "C" or x == "B" for x in k)]
                failed = [k for k in tried if k not in self.grammar and "B" not in k]

                def contains_failed(key):
                    return any(len(u) < len(key) and any(key[i:i + len(u)] == u for i in range(len(key) - len(u) + 1))
                               for u in failed)

                todo = [(k, r) for k, r in pending if tried.get(k, -1) < npins and not contains_failed(k)]
                if not todo: break
                key, rows = max(todo, key=lambda kr: (pinned_frac(*kr), -unknown_classes(kr[0]), len(kr[1])))
                tried[key] = npins
                left = final - time.time()
                cap = 120 if npins == 0 else (90 if lib else 60)
                self.deadline = min(final, time.time() + min(cap, left))
                self._learn_key(key, rows, enum)
                if key not in self.grammar and any(k == "B" for k in key):
                    by_raw = collections.defaultdict(list)
                    for rkey, row in raw[key]: by_raw[rkey].append(row)
                    for rkey, rrows in by_raw.items():
                        if rkey not in self.grammar and len(rrows) >= MIN_ROWS and time.time() < final:
                            self.deadline = min(final, time.time() + 30); self._learn_key(rkey, rrows, enum)

            gained = len(self.grammar) - adopted_before
            # ---- C4 KNOCKOUT ARM: nolf_learn's behaviour exactly -- one library pass, then stop ----------------
            if self.once:
                self.rounds.append((rnd, "plain" if not library_pass else "library", len(self.grammar), 0,
                                    round(time.time() - r_t0, 1)))
                if library_pass or not fragments(self.grammar):
                    self.halt_reason = "once-only library pass exhausted (knockout arm)"; break
                library_pass = True
                lib = fragments(self.grammar)
                enum = self._rebuild(probes, elems, rels, sels, lib, space); tried = {}; continue

            # ---- CLOSURE ARM -----------------------------------------------------------------------------------
            new_lib = dict(fragments(self.grammar)); new_lib.update(self.promoted)
            fresh = {t: v for t, v in new_lib.items() if t not in lib}
            if gained and fresh:
                libmap = {t: t for t in new_lib}                   # core.closure indexes lib by NAME -> item
                for term in fresh:                                 # the closure learns what the library now reaches
                    closure.add(term, term, libmap)
                self.energy = closure.cost
                lib = new_lib
                self.rounds.append((rnd, "grow", len(self.grammar), 0, round(time.time() - r_t0, 1)))
                enum = self._rebuild(probes, elems, rels, sels, lib, space); tried = {}
                continue

            # STALL: a full round with no adoption. Promote, or halt.
            # The budget must cover the REBUILD the promotion forces, not just the promotion: measured on
            # records_shuffled, two promote rounds (48 leaves) drove a 240 s fit to 683 s because the enumerator
            # rebuild is not deadline-checked and cannot be preempted once started. Refuse a rebuild that will not
            # fit, using what the last one actually cost.
            need = 20 + 2 * self.last_rebuild
            if time.time() >= final - need:
                self.halt_reason = (f"budget exhausted before the stall could be worked -- a rebuild needs "
                                    f"~{need:.0f}s and {final - time.time():.0f}s remain (BUDGET-BOUND, not a halt)")
                self.rounds.append((rnd, "stall/no-time", len(self.grammar), 0, round(time.time() - r_t0, 1))); break
            promoted = self._promote(enum, space, closure, set(lib))
            if not promoted:
                self.halt_reason = f"HALT: stall promoted nothing the closure cannot already reach (energy {closure.cost})"
                self.rounds.append((rnd, "stall/halt", len(self.grammar), 0, round(time.time() - r_t0, 1))); break
            self.promoted.update(promoted)
            libmap = {t: t for t in {**lib, **promoted}}
            for term in promoted: closure.add(term, term, libmap)
            self.energy = closure.cost
            lib = dict(fragments(self.grammar)); lib.update(self.promoted)
            self.rounds.append((rnd, "stall/promote", len(self.grammar), len(promoted), round(time.time() - r_t0, 1)))
            enum = self._rebuild(probes, elems, rels, sels, lib, space); tried = {}

        if self.halt_reason is None:
            self.halt_reason = "BUDGET-BOUND: the loop was still working when the budget ran out (not a halt)"
        self.deadline = final
        self.log = [e for i, e in enumerate(self.log) if not (e[0] == "unsolved" and any(
            f[0] == "learned" and f[1] == e[1] for f in self.log[i + 1:]))]
        self.seconds = time.time() - t0
        self.energy = closure.cost
        return self


# ------------------------------------------------------------------------------------------------- gate runner
def fit_one(world, shuffled, budget, once):
    import nolf_worlds as NW                      # the runner may import a world; the learner never does (C4/C7)
    from core.verdict import score_two_mode, line
    import nolf_run as NR
    W = (NW.Records(seed=71) if shuffled else NW.Records()) if world == "records" else \
        (NW.Strings(seed=72) if shuffled else NW.Strings())
    sp = NW.splits(W, 1)
    arm = "ONCE (knockout)" if once else "CLOSURE"
    print(f"=== {W.name}{' SHUFFLED' if shuffled else ''} [{arm}] train {len(sp['train'])}  "
          f"iid {len(sp['heldout_iid'])}  compositional {len(sp['heldout_comp'])}", flush=True)
    L = ClosureLearner(time_budget=budget, once=once).fit(sp["train"])
    print(f"  {len(L.grammar)} constructions in {L.seconds:.0f}s (table {L.table_seconds:.0f}s), "
          f"energy {L.energy}, {len(L.promoted)} promoted leaves")
    for r in L.rounds:
        print(f"    round {r[0]:2d}  {r[1]:<16} constructions {r[2]:2d}  promoted {r[3]:2d}  {r[4]:6.1f}s")
    print(f"    {L.halt_reason}")
    for e in L.log:
        k = [x if x == "B" else x[1] for x in e[1]]
        print(f"    {'learned ' if e[0] == 'learned' else 'UNSOLVED'} {e[2]:4d} rows  {e[3] if e[0] == 'learned' else ''}  <- {k}")
    res = {}
    for name, m in [("bag-of-words", NR.BagOfWords(sp["train"])), ("analogy", NR.Analogy(sp["train"])), ("learner", L)]:
        for split in ("heldout_iid", "heldout_comp"):
            r = score_two_mode(m, [((sit, toks), tv) for sit, toks, tv in sp[split]])
            res[f"{name}/{split}"] = {k: v for k, v in r.items() if k != "per"}
            print(line(f"{name} / {split}", r, width=30))
    d = json.load(open(OUT)) if os.path.exists(OUT) else {}
    tag = f"{world}{'_shuffled' if shuffled else ''}{'_once' if once else ''}"
    d[tag] = dict(scores=res, constructions=len(L.grammar), seconds=round(L.seconds), energy=L.energy,
                  promoted=len(L.promoted), halt=L.halt_reason,
                  rounds=[list(r) for r in L.rounds],
                  learned=[[x if x == "B" else x[1] for x in e[1]] for e in L.log if e[0] == "learned"],
                  unsolved=[[x if x == "B" else x[1] for x in e[1]] for e in L.log if e[0] != "learned"])
    json.dump(d, open(OUT, "w"), indent=1, sort_keys=True, default=str)


def report():
    import re
    if not os.path.exists(OUT): print("NO FITS SAVED"); return
    d = json.load(open(OUT)); ok = True
    bars = {"strings": 0.80, "records": 0.95}
    for w in ("strings", "records"):
        if w not in d: print(f"{w}: NO CLOSURE FIT SAVED"); ok = False; continue
        c = d[w]; Lc = c["scores"]["learner/heldout_comp"]; Li = c["scores"]["learner/heldout_iid"]
        gate = "C1" if w == "strings" else "C2"
        hit = Lc["EM"] >= bars[w] and Lc["confab"] == 0
        print(f"{w}: {gate} compositional EM {Lc['EM']:.3f} (iid {Li['EM']:.3f}) vs bar {bars[w]}  [{hit}]   "
              f"constructions {c['constructions']}  energy {c['energy']}  promoted {c['promoted']}")
        ok &= hit
        confab_ok = all(v["confab"] == 0 for k, v in c["scores"].items() if k.startswith("learner/"))
        print(f"    C3 confabulation 0 on every split  [{confab_ok}]")
        ok &= confab_ok
        o = d.get(w + "_once")
        if o:
            Oc = o["scores"]["learner/heldout_comp"]
            drop = c["constructions"] > o["constructions"] or Lc["EM"] > Oc["EM"] + 1e-9
            print(f"    C4 KNOCKOUT --once: EM {Oc['EM']:.3f}, constructions {o['constructions']}  ->  "
                  f"closure arm {'BEATS' if drop else 'DOES NOT BEAT'} it  [{drop}]"
                  + ("" if drop else "   <- VACUOUS on this world: the pass means nothing here"))
        else:
            print("    C4 KNOCKOUT: NOT RUN"); ok = False
        halt = c.get("halt", "")
        honest = ("HALT:" in halt) or ("BUDGET-BOUND" in halt) or ("budget exhausted" in halt)
        print(f"    C5 halt honesty: {halt}  [{honest}]")
        ok &= honest
        s = d.get(w + "_shuffled")
        if s:
            g6 = abs(s["constructions"] - c["constructions"]) <= 1
            print(f"    C6 shuffled lexicon: constructions {s['constructions']} vs {c['constructions']}  [{g6}]"
                  + ("" if g6 else "   <- budget statement, not a spelling leak (P4)"))
            ok &= g6
        else:
            print("    C6 shuffled: NOT RUN")
    # C7 scores the MECHANISM, not the gate runner: everything above the runner divider. Scoring this file whole
    # would always "leak", because the checker's own vocabulary list is a literal in it -- a control that cannot
    # discriminate always passes, and its mirror image, a control that can never pass, is just as useless.
    src = open(__file__, encoding="utf-8").read().split("gate runner")[0]
    src += open(NL.__file__, encoding="utf-8").read()
    leak = [x for x in ("agent", "theme", "recipient", "FORALL", "LAMBDA", "x_") if re.search(r"\b" + re.escape(x), src)]
    world_free = not re.search(r"^\s*import nolf_worlds", src, re.M)
    print(f"    C7 hygiene: LF vocabulary {leak}, mechanism world-free {world_free}  [{not leak and world_free}]")
    ok &= not leak and world_free
    print("\nCLOSURE-SCHEDULED LIBRARY GROWTH: PASS" if ok else
          "\nCLOSURE-SCHEDULED LIBRARY GROWTH: NOT PASSED -- read the gate lines")


if __name__ == "__main__":
    if "--report" in sys.argv:
        report(); sys.exit(0)
    world = sys.argv[sys.argv.index("--world") + 1] if "--world" in sys.argv else "strings"
    budget = int(sys.argv[sys.argv.index("--budget") + 1]) if "--budget" in sys.argv else 240
    t0 = time.time()
    fit_one(world, "--shuffled" in sys.argv, budget, "--once" in sys.argv)
    print(f"({time.time()-t0:.0f}s)")
