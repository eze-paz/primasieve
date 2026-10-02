"""NEAR-MISS FRAGMENTS -- a target-aware, lexicon-blind selector for library growth (nolf_select_prereg.md).
Imports core/ only besides nolf_learn (the learner) and nolf_worlds (the sealed worlds, for the fit and the score).

At a STALL (every reachable skeleton tried since the last pin, unsolved skeletons left) the learner probes the
enumerator's candidates against each unsolved skeleton's own rows, scores each by rows individually satisfiable, and
promotes the sub-terms of the closest misses as leaves (Enumerator.extend), then retries. Knockouts promote the same
NUMBER of sub-terms chosen at random (target-blind) or by recurrence (the closure prereg's selector).

    python nolf_select.py --world strings --arm near|random|recur|once [--shuffled] [--budget 300]
    python nolf_select.py --report          # the gates over nolf_select_results.json"""
import os, sys, time, json, random, itertools, collections

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import nolf_learn as NL
from nolf_learn import Learner, Enumerator, fragments, subterms, ops, result_type, has_var, holes, show, MIN_ROWS, HB
from core.verdict import score_two_mode
from core.registry import selfcheck

PROBE_S, SCORE_ROWS, TOP_N, MAX_ROUNDS = 25, 40, 6, 3          # declared budget devices (prereg section 2)
OUT = os.path.join(HERE, "nolf_select_results.json")


def say(s=""): print(str(s).encode("ascii", "replace").decode(), flush=True)


class SelectLearner(Learner):
    def __init__(self, arm="near", **kw):
        super().__init__(**kw)
        self.arm = arm; self.rounds = []; self.promoted = {}; self.landscapes = []; self.halt = None

    # ---- the signal: rows individually satisfiable --------------------------------------------------------------------
    MAX_ASSIGN = 400

    def _rows_ok(self, f, rows, hs, perm, doms, limit, floor=0):
        """-> the largest number of the first `limit` rows that ONE denotation assignment (one value per (word, kind) from
        the words' current domains) gets right. Measured first with a per-row count -- some assignment per row -- and the
        landscape was flat at the top: 72 % of candidates scored every row, because an unpinned relation word can be
        re-chosen per row. The signal has to be global, as the solver's own fit is: it is max-SAT over the assignment
        product, bounded by MAX_ASSIGN (a candidate whose product is larger is not scored), abandoned when it cannot
        reach `floor` (the current N-th best)."""
        keys = []
        for j, h in enumerate(hs):
            it = rows[0][1][perm[j]]
            if not isinstance(it, str): return -1
            keys.append((it, h))
        uniq = list(dict.fromkeys(keys))
        pools = [sorted(doms[k], key=repr) for k in uniq]
        size = 1
        for p in pools: size *= len(p)
        if size > self.MAX_ASSIGN or size == 0: return -1
        use = rows[:limit]; best = 0
        for vals in itertools.product(*pools):
            val = dict(zip(uniq, vals)); env = tuple(val[k] for k in keys); n = 0
            for i, (sit, fill, tv) in enumerate(use):
                if n + (len(use) - i) <= max(best, floor - 1): break
                if self._top(f, sit, env) is tv: n += 1
            best = max(best, n)
            if best == len(use) or time.time() > self.deadline: break
        return best

    def _probe(self, key, rows, enum, seconds):
        """iterate the search's own candidate order for `seconds`; -> {term: best score}, and the list of all terms seen.
        `rows` are RAW rows (every slot a word): a skeleton whose reduced form holds a sub-sentence the grammar cannot
        evaluate (the unsolved construction itself, reduced by a same-shaped learned one) scores nothing on its reduced
        rows -- measured in the first run: every candidate at 0 -- so the stall probes the unreduced skeleton, as the
        learner's own unreduced fallback does."""
        nslots = len(rows[0][1]); scores = {}; seen = []; top = []
        # scored rows are BALANCED by truth value: the target is true on ~5 % of its rows, and on the first 40 rows a
        # mostly-false term scored 38 of 40 (90 % of candidates at the mode) -- the constant-false confounder
        # nolf_gradient_probe named. Half true, half false removes the degenerate advantage.
        half = SCORE_ROWS // 2
        bal = [r for r in rows if r[2]][:half] + [r for r in rows if not r[2]][:half]
        self.deadline = time.time() + seconds
        for term in enum.candidates(enum.max_ops):
            if time.time() > self.deadline: break
            hs = holes(term)
            if len(hs) != nslots: continue
            if not NL.uses_sit(term) and HB not in hs: continue
            seen.append(term)
            f = NL.compile_term(term); best = -1
            floor = top[-1] if len(top) >= TOP_N else 0
            for perm in itertools.permutations(range(nslots)):
                doms = self._initial_domains(rows, hs, perm)
                if doms is None: continue
                s = self._rows_ok(f, bal, hs, perm, doms, len(bal), floor)
                best = max(best, s)
                if time.time() > self.deadline: break
            if best >= 0:
                scores[term] = best; top = sorted(top + [best], reverse=True)[:TOP_N]
        return scores, seen

    @staticmethod
    def _harvest(terms, enum):
        out = {}
        for t in terms:
            for sub in subterms(t):
                if ops(sub) >= 1 and result_type(sub) is not None and len(holes(sub)) <= NL.MAX_HOLES and sub not in enum.library:
                    out[sub] = (result_type(sub), has_var(sub))
        return out

    def _select(self, unsolved, enum):
        """-> promoted {fragment: (type, has_var)} for this arm, and the landscape record"""
        land = []; near_terms = []; pool_terms = []
        for key, rows in unsolved:
            # the probe runs over the PLAIN depth-4 table (self.enum): a near-miss of a deep construction is a deep term,
            # and the two-application library table cannot hold it (measured: probing the library table surfaced
            # count-comparison terms at 39/40 rows whose sub-terms unlocked nothing). Promotion goes into the library
            # table `enum`, where the deep term's pieces become leaves. Amendment to the prereg's section 2, recorded.
            scores, seen = self._probe(key, rows, self.enum, PROBE_S / max(1, len(unsolved)))
            pool_terms += seen
            if not scores: land.append(dict(key=show_key(key), probed=len(seen), scored=0)); continue
            vals = sorted(scores.values(), reverse=True); n = len(vals); mode = collections.Counter(vals).most_common(1)[0]
            land.append(dict(key=show_key(key), probed=len(seen), scored=n, rows=min(SCORE_ROWS, len(rows)), max=vals[0],
                             p90=vals[int(n * 0.1)], median=vals[n // 2], mode=mode[0], mode_share=round(mode[1] / n, 3)))
            top = [t for t, _ in sorted(scores.items(), key=lambda kv: -kv[1])[:TOP_N]]
            near_terms += top
            land[-1]["top"] = [(scores[t], show(t)) for t in top[:3]]
        self.landscapes.append(land)
        if self.arm == "near":
            return self._harvest(near_terms, enum)
        want = len(self._harvest(near_terms, enum))                       # the knockouts promote the SAME number
        if self.arm == "random":
            rng = random.Random(len(self.rounds)); cand = {}
            pool = list(pool_terms); rng.shuffle(pool)
            for t in pool:
                cand.update(self._harvest([t], enum))
                if len(cand) >= want: break
            return dict(list(cand.items())[:want])
        if self.arm == "recur":
            recur = collections.Counter()
            for lam in (False, True):
                T = enum.tables.get(lam)
                if not T: continue
                for k in T:
                    for ty in T[k]:
                        for term in T[k][ty]:
                            for sub in set(subterms(term)):
                                if ops(sub) >= 1 and result_type(sub) is not None and len(holes(sub)) <= NL.MAX_HOLES and sub not in enum.library:
                                    recur[sub] += 1
            return {sub: (result_type(sub), has_var(sub)) for sub, _ in recur.most_common(want)}
        return {}

    # ---- fit: nolf_learn.fit with the stall round -----------------------------------------------------------------------
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
        rels = [p for p in NL.P.pids() if NL.P.signature(p) == ((NL.INT, NL.INT), NL.BOOL)]
        sels = [("all",), ("any",)] + [("idx", k) for k in range(-1, 4)]
        self.universe = {NL.HI: sorted(ints), NL.HE: sorted(elems, key=repr), NL.HR: rels, NL.HS: sels}
        by_size = {}
        for sit, _, _ in train: by_size.setdefault(len(sit), []).append(sit)
        probes = [x for k in sorted(by_size) for x in by_size[k][:3]][:8]
        if len(probes) < 8: probes += [sit for sit, _, _ in train[:8 - len(probes)]]
        enum = Enumerator(probes, elems, rels, sels)
        enum.table(False); self.table_seconds = time.time() - t0; self.t0 = t0; self.enum = enum
        self.demoted = set(); self.log = []
        final = t0 + self.budget
        tried = {}; library_pass = False; stalls = 0
        while time.time() < final:
            groups = collections.defaultdict(list); raw = collections.defaultdict(list)
            for sit, toks, tv in train:
                items = self._reduce(toks); key, fill = self._key(items)
                groups[key].append((sit, fill, tv))
                rkey, rfill = self._key([("c", self.cls[w], w) for w in toks]); raw[key].append((rkey, (sit, rfill, tv)))
            npins = len(self.dom); pinned_words = {k[0] for k in self.dom}
            def pinned_frac(key, rows):
                slots = {w for _, fill, _ in rows for w in fill if isinstance(w, str)}
                return sum(1 for w in slots if w in pinned_words) / len(slots) if slots else 1.0
            def unknown_classes(key):
                return sum(1 for k in key if k != "B" and k[0] == "C" and not any(self.cls.get(w) == k[1] for (w, _) in self.dom))
            pending = [(k, r) for k, r in groups.items() if k not in self.grammar and len(r) >= MIN_ROWS
                       and any(x != "B" and x[0] == "C" or x == "B" for x in k)]
            failed = [k for k in tried if k not in self.grammar and "B" not in k]
            def contains_failed(key):
                return any(len(u) < len(key) and any(key[i:i + len(u)] == u for i in range(len(key) - len(u) + 1)) for u in failed)
            todo = [(k, r) for k, r in pending if tried.get(k, -1) < npins and not contains_failed(k)]
            plain_done = pending and all(k in tried for k, _ in pending)
            late = failed and (final - time.time()) < 0.45 * self.budget
            if pending and not library_pass and (plain_done or late) and fragments(self.grammar) and final - time.time() > 45:
                todo = []
            if not todo:
                if not library_pass and fragments(self.grammar):
                    library_pass = True                                   # nolf_learn's library pass, through extend()
                    enum = Enumerator(probes, elems, rels, sels, max_ops=2); enum.table(False); enum.extend(fragments(self.grammar))
                    self.library_seconds = time.time() - t0; tried = {}; continue
                # ---- STALL ROUND (the mechanism) ----------------------------------------------------------------
                # targets are UNREDUCED skeletons: a pending key holding a sub-sentence is replaced by the raw keys of its
                # rows that the grammar has not learned (three pending keys of the first run were one construction,
                # 'every x followed y', reduced by the same-shaped 'x before y' into a sub-sentence with no value)
                targets = {}
                for k, r in pending:
                    if k in self.grammar: continue
                    if "B" in k:
                        for rkey, row in raw[k]:
                            if rkey not in self.grammar and "B" not in rkey: targets.setdefault(rkey, []).append(row)
                    else: targets.setdefault(k, []).extend(r)
                unsolved = [(k, r) for k, r in targets.items() if len(r) >= MIN_ROWS]
                if self.arm == "once" or not unsolved or stalls >= MAX_ROUNDS or final - time.time() < PROBE_S + 30:
                    self.halt = ("once" if self.arm == "once" else "no unsolved skeleton" if not unsolved else
                                 f"{stalls} stall rounds" if stalls >= MAX_ROUNDS else "BUDGET-BOUND (not a halt)"); break
                if not library_pass:
                    library_pass = True; enum = Enumerator(probes, elems, rels, sels, max_ops=2); enum.table(False)
                r_t = time.time()
                promoted = self._select(unsolved, enum)
                if not promoted:
                    self.halt = "HALT: the stall promoted nothing new"; break
                self.promoted.update(promoted); rep = enum.extend(promoted); stalls += 1
                self.rounds.append(dict(stall=stalls, unsolved=[show_key(k) for k, _ in unsolved], promoted=len(promoted),
                                        delta=rep, seconds=round(time.time() - r_t, 1)))
                tried = {}; continue
            key, rows = max(todo, key=lambda kr: (pinned_frac(*kr), -unknown_classes(kr[0]), len(kr[1])))
            tried[key] = npins
            left = final - time.time()
            cap = 120 if npins == 0 else (90 if library_pass else 60)
            self.deadline = min(final, time.time() + min(cap, left))
            self._learn_key(key, rows, enum)
            if key not in self.grammar and any(k == "B" for k in key):
                by_raw = collections.defaultdict(list)
                for rkey, row in raw[key]: by_raw[rkey].append(row)
                for rkey, rrows in by_raw.items():
                    if rkey not in self.grammar and len(rrows) >= MIN_ROWS and time.time() < final:
                        self.deadline = min(final, time.time() + 30); self._learn_key(rkey, rrows, enum)
        if self.halt is None: self.halt = "BUDGET-BOUND: still working when the budget ran out (not a halt)"
        self.deadline = final
        self.log = [e for i, e in enumerate(self.log) if not (e[0] == "unsolved" and any(
            f[0] == "learned" and f[1] == e[1] for f in self.log[i + 1:]))]
        self.seconds = time.time() - t0
        return self


def show_key(key): return repr([x if x == "B" else x[1] for x in key])


def fit_one(world, arm, shuffled, budget):
    import nolf_worlds as NW
    W = (NW.Records(seed=71) if shuffled else NW.Records()) if world == "records" else (NW.Strings(seed=72) if shuffled else NW.Strings())
    sp = NW.splits(W, 1)
    say(f"=== {W.name}{' SHUFFLED' if shuffled else ''} arm {arm} budget {budget} s")
    L = SelectLearner(arm=arm, time_budget=budget).fit(sp["train"])
    say(f"  {len(L.grammar)} constructions in {L.seconds:.0f} s (table {L.table_seconds:.0f} s); halt: {L.halt}")
    for e in L.log:
        k = [x if x == "B" else x[1] for x in e[1]]
        say(f"    {'learned ' if e[0] == 'learned' else 'UNSOLVED'} {e[2]:4d} rows  {e[3] if e[0] == 'learned' else ''}  <- {k}")
    for r in L.rounds: say(f"  stall {r['stall']}: unsolved {r['unsolved']} -> promoted {r['promoted']} leaves, delta {r['delta']}, {r['seconds']} s")
    for land in L.landscapes:
        for l in land:
            if l.get("scored"):
                say(f"  landscape {l['key']}: probed {l['probed']} scored {l['scored']} of {l['rows']} rows -> max {l['max']} p90 {l['p90']} median {l['median']} "
                    f"mode {l['mode']} ({l['mode_share']:.0%})   top {l['top']}")
            else: say(f"  landscape {l['key']}: probed {l['probed']}, nothing scored")
    res = {}
    for split in ("heldout_iid", "heldout_comp"):
        r = score_two_mode(L, [((sit, toks), tv) for sit, toks, tv in sp[split]])
        res[split] = {k: v for k, v in r.items() if k != "per"}
        say(f"  {split:13s} EM {r['EM']:.4f} confab {r['confab']:.4f}")
    # N6: the construction holding the hidden 'followed' word, and whether its term stands on a promoted leaf
    hidden = {f: c for c, f in W.lex.c2f.items()}
    mech = None
    for key, alts in L.grammar.items():
        words = [hidden.get(x[1], x[1]) for x in key if x != "B" and x[0] == "W"]
        rows = L.rows_of.get(key, [])
        slot_words = {hidden.get(w, w) for _, fill, _ in rows[:50] for w in fill if isinstance(w, str)}
        if "followed" in words or "followed" in slot_words or "every" in words or "every" in slot_words:
            term = alts[0][0]
            on_promoted = any(sub in L.promoted for sub in subterms(term))
            mech = dict(key=show_key(key), term=show(term), on_promoted_leaf=on_promoted)
    say(f"  N6 every/followed construction: {mech}")
    d = json.load(open(OUT)) if os.path.exists(OUT) else {}
    d[f"{world}{'_shuffled' if shuffled else ''}/{arm}"] = dict(scores=res, constructions=len(L.grammar), seconds=round(L.seconds), halt=L.halt,
                                                              rounds=L.rounds, landscapes=L.landscapes, mech=mech, promoted=len(L.promoted),
                                                              learned=[show_key(e[1]) for e in L.log if e[0] == "learned"])
    json.dump(d, open(OUT, "w"), indent=1, default=str)


def report():
    d = json.load(open(OUT))
    def g(k): return d.get(k)
    near, rnd, rec, once = g("strings/near"), g("strings/random"), g("strings/recur"), g("strings/once")
    recs, shuf = g("records/near"), g("strings_shuffled/near")
    em = lambda r: r["scores"]["heldout_comp"]["EM"] if r else None
    cf = lambda r: max(r["scores"][s]["confab"] for s in r["scores"]) if r else None
    say("NEAR-MISS FRAGMENTS -- gates (nolf_select_prereg.md)")
    n1 = near and em(near) >= 0.80 and cf(near) == 0
    say(f"  N1 strings near: comp EM {em(near)} (iid {near['scores']['heldout_iid']['EM'] if near else None}) at confab {cf(near)}, {near['constructions'] if near else '?'} constructions   [>= 0.80, 0 -> {'PASS' if n1 else 'FAIL'}]")
    n2 = recs and em(recs) >= 0.95 and cf(recs) == 0
    say(f"  N2 records near: comp EM {em(recs)} confab {cf(recs)}   [>= 0.95 -> {'PASS' if n2 else 'FAIL'}]")
    arms = [r for r in (near, rnd, rec, once, recs, shuf) if r]
    n3 = all(cf(r) == 0 for r in arms)
    say(f"  N3 confab 0 on every split of every arm: {[cf(r) for r in arms]}   [{'PASS' if n3 else 'FAIL'}]")
    n4 = rnd is not None and not (em(rnd) >= 0.80 and cf(rnd) == 0)
    say(f"  N4 knockout random: comp EM {em(rnd)} ({rnd['constructions'] if rnd else '?'} constructions)   [must not reach N1 -> {'PASS' if n4 else ('FAIL' if rnd else 'NOT RUN')}]")
    n5 = rec is not None and not (em(rec) >= 0.80 and cf(rec) == 0)
    say(f"  N5 knockout recurrence: comp EM {em(rec)} ({rec['constructions'] if rec else '?'} constructions)   [must not reach N1 -> {'PASS' if n5 else ('FAIL' if rec else 'NOT RUN')}]")
    say(f"      baseline once: comp EM {em(once)} ({once['constructions'] if once else '?'} constructions)")
    m = near and near.get("mech")
    n6 = bool(m) and m.get("on_promoted_leaf")
    say(f"  N6 mechanism: {m}   [adopted on a promoted leaf -> {'PASS' if n6 else 'FAIL'}]")
    n7 = near and shuf and abs(near["constructions"] - shuf["constructions"]) <= 1
    say(f"  N7 shuffled lexicon: {shuf['constructions'] if shuf else '?'} vs {near['constructions'] if near else '?'} constructions   [within 1 -> {'PASS' if n7 else 'FAIL'}]")
    for k, r in d.items():
        for land in r.get("landscapes", []):
            for l in land:
                if l.get("scored"): say(f"  N8 landscape [{k}] {l['key']}: max {l['max']}/{l['rows']} median {l['median']} mode share {l['mode_share']}")
    say(f"  N9 runtime: {[(k, r['seconds']) for k, r in d.items()]}")
    ok = all([n1, n2, n3, n4, n5, n6, n7])
    say(f"\nNEAR-MISS SELECTOR: {'PASS' if ok else 'NOT PASSED'} -- strings near {em(near)} / random {em(rnd)} / recur {em(rec)} / once {em(once)}; records {em(recs)}; confab {'0' if n3 else 'NONZERO'}")


if __name__ == "__main__":
    selfcheck(__file__)
    a = sys.argv
    if "--report" in a: report(); sys.exit(0)
    world = a[a.index("--world") + 1] if "--world" in a else "strings"
    arm = a[a.index("--arm") + 1] if "--arm" in a else "near"
    budget = int(a[a.index("--budget") + 1]) if "--budget" in a else 300
    t = time.time(); fit_one(world, arm, "--shuffled" in a, budget); say(f"({time.time() - t:.0f} s)")
