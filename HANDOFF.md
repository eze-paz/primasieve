# Reasoning-Library — Handoff

**One line:** a zero-LLM, verifier-gated bug-fix/feature reasoning engine — *reasoning lives in the search*, the LLM is demoted to a narrow, checkable slot-filler at the edges (language→spec) or removed entirely.

This doc lets a new session/engineer continue without re-deriving anything. All work is in
`experiments/primasieve/`. Everything is committed + pushed. CPU-only, ≤16 GB RAM.

---

## The thesis (why this exists)

The user's driving objection, in order, and what each drove:
1. *"If the LLM solves it, the reasoner does nothing — it should DECOMPOSE not PROPOSE."* → reasoning belongs in the **search**, not a monolithic LLM proposal.
2. *"The search space isn't infinite — syntax + finite tokens + smallest-necessary-change bound it."* → a **stratified move grammar**, not free generation.
3. *"If the proposer is an LLM, the system is dead. Make the proposal mechanism the reasoner."* → **proposer-free** repair (execute + belief + enumerate).
4. *"Neither LLM (memory) nor enumeration (monkeys) reasons — a human finds the divergence, fetches the closest analogue, and interpolates."* → **analogical projection + interpolation**.
5. *"Make it coding-agnostic; make emergent behaviour appear."* → **domain-agnostic core + library-learning**.
6. *"How do we unlock synthesis / structural rewrites without an LLM?"* → **angelic point-spec synthesis** + the (still-open) **guidance** problem.

**Architecture verdict reached:** *neural for meaning (intent→spec), deterministic for truth
(spec→fix), epistemic acquire for gaps.* The only irreducible LLM role is language→spec (and
confirming intent for brand-new features). Everything downstream is LLM-free and verified.

---

## What's built (files, newest capability last)

| file | what it does | key commit |
|---|---|---|
| `reasoner_core.py` | domain-agnostic loop: expect→simulate→diff→reconcile→**acquire** (~40 lines) | 7df4582 |
| `reasoner_code.py` | code domain: exec-trace (step+**value-size**-capped), Ochiai belief, **stratified** AST-mutation grammar (strata 0–2), solve-first steepest scan, reset-on-escalation, anti-cheat (confusion-pair builtins, program-only donors) | c4f76a2 |
| `reasoner_analog.py` | **analogical** repair: energy-budget stall → fetch closest analog → structure-map relational delta → verify | b94cad6 |
| `reasoner_interp.py` | **anti-unification interpolation**: extract the analog's *relational frame* (`HOLE op REC`), fill the hole with the *target's own* material → crosses surface gaps (real stdlib `get_class_members` repairs `powerset`) | cb0ac4d |
| `projection_core.py` + `demo_domains.py` | **domain-agnostic** projection engine; same core runs code **and** arithmetic (no code concepts in the core) | 9a20aaa |
| `synth.py` | **angelic point-spec synthesis**: bottom-up enumerative, **observational-equivalence** pruned; builds novel multi-op expressions from a value-spec | 46016ea |
| `emergence.py` | **library-learning** (wake/sleep): compress recurring solution-fragments into a new operator; `a^4−b^4` becomes solvable *only after* learning `sq` from its own solutions | 6c66345 |
| `unified_loop.py` | **one FSM** for bug-fix AND feature-add: `locate→miss?→retrieve→project→verify`; only the analogue source + a human-confirm-spec step differ | 0eb0b59 |
| `swe_run.py` | **real SWE-bench harness**: persistent Docker container, mutate real repo file, verify via **real tests** (fast oracle); traceback localization; NameError edit-distance prior; **anti-cheat F2P+P2P** oracle | 9221516 |
| `batch_sympy.py` | measured-score batch over the sympy reachable subset (build image → search → **official** verify → tally) | 89cf1f5 |
| census: `swebench_census.py`, `swebench_reach.py`, `swebench_express.py`, `swebench_families.py`, `swebench_synth_census.py` | static (no Docker) measurements of what fraction of SWE-bench each mechanism can reach | 0363ce9, f794533, cd5eba9 |
| `quixbugs_bench.py` | LLM-arm baseline (one-shot / best-of-N / reasoner) with Qwen2.5-1.5B | ea6244a |
| `kuhn_cfr.py` | belief-state reasoner (CFR→exact Nash) — the "beliefs as inputs" strand | (in log) |

---

## Key results (all verified, honest)

- **QuixBugs: 26/26** (25 by stratified grammar in 81 s, `c4f76a2`; the last, `powerset`, by
  analogical interpolation, `b94cad6`). All genuine fixes; cheats removed. **Zero LLM.**
  - Beats the 1.5B-LLM arms (~1/3 solved, ~2 min/attempt) at ~100× less wall-time.
- **First REAL verified SWE-bench solve, zero LLM** (`9221516`): `sympy__sympy-13480`, confirmed
  by the **official `run_evaluation`** harness (patch byte-identical to gold). Fix = `cotm→cothm`,
  found in 3 candidates / 41 s via traceback-localize + NameError edit-distance prior.
- **The ceiling, measured statically** (no Docker): grammar-accurate reachability on SWE-bench
  Lite = **~3.3% confident, ≤8% absolute** (`0363ce9`). Fix-family breakdown (`f794533`):
  large-rewrite 33% + small-mixed 20% = **~53% structural** (needs guided construction);
  add-def/class/import ~13% (generative); token/expr ~14% + simple inserts ~11% (reachable).
  **Realistic non-generative ceiling ≈ 20–25%.**
- **QuixBugs 96% vs SWE-bench ~3% is not a weakness** — QuixBugs bugs *are* seeded single-site
  mutations, so a single-edit grammar was implicitly built for them; real bugs are 85% structural.

---

## Hard-won lessons (don't re-learn these)

- **Anti-cheat is mandatory.** Verify **F2P *and* all P2P** (previously-passing tests). A F2P-only
  oracle produced a false positive on seaborn (`LtE→Gt` emptied both sides → F2P passed, P2P broke).
- **DoF must be a-priori defect classes, not answer-derived.** A prior session "poisoned"
  `reasoner_code.py` with move-kinds named after the target programs — reverted. Same discipline
  for specs: **behavior not structure** (see "spec" below).
- **Armor the simulator on every axis.** Line-step caps don't bound time/memory: `n**=n-1` and
  `n*=n-1` blow up inside one bytecode op → also cap integer bit-length and container size.
- **Greedy first-improvement strands the search** (a cheap partial fix blocks the true deeper fix).
  Use **solve-first steepest scan + reset-to-pristine on stratum escalation**.
- **Corpus must match the bug's pattern distribution.** Python stdlib (6794 fns) has **zero**
  instances of the recursive-union idiom `powerset` needs → retrieval works, coverage fails
  (`a851640`). Algorithm corpora cover it but are *leakage* for QuixBugs benchmarking.
- **WSL gotchas:** `nohup` background procs die when the `wsl.exe` call returns (use the harness's
  `run_in_background`); Windows-Python `open("/tmp/…")` writes Windows `/tmp`, **not** WSL `/tmp`
  (this bug makes `batch_sympy.py`'s official-verify report False — see Open threads).
- **Per-repo test harnesses differ:** sympy uses `bin/test` (no pytest; editable install so
  `docker cp` of a mutated file takes effect); django uses `tests/runtests.py`; pytest dogfoods pytest.

---

## The spec discipline (the language→spec contract)

A spec is **executable code** (I/O examples + properties + optional oracle), never prose, and must
pin **behavior not structure**. Integrity gate (buildable, not yet built): a spec is structure-free
iff **≥2 structurally-different reference impls both pass it** (diverse-witness test). The *same*
committee doubles as an **incompleteness detector**: if the witnesses *disagree* on some input,
that input is the missing decision → query the human (query-by-committee active learning).

**Estimated model size for language→spec:** ~7B fine-tuned for messy real issues; **tiny
(tens of M, plausibly ~1.6M for a stereotyped head)** if you (a) extract most of the spec *from
the code* (code = spec-minus-bug), (b) run a deterministic diagnostic FSM, (c) query the user on
ambiguity. 100%-LLM-free is blocked by the **spec wall** (forming the goal from NL needs language
understanding under the hidden-tests protocol), *not* by construction.

---

## How to run

**QuixBugs (no Docker):**
```
python reasoner_code.py                 # full stratified sweep (25/26)
python reasoner_analog.py               # analogical repair (powerset → 26/26) + transfer probe
python reasoner_interp.py               # stdlib get_class_members interpolates powerset
python demo_domains.py                  # SAME core: code + arithmetic
python synth.py ; python emergence.py ; python unified_loop.py
```

**Real SWE-bench (WSL Docker; `swebench<4`, i.e. 3.0.17, in `~/swebench-env`):**
```
# 1) build+cache an instance image (also confirms gold resolves):
python -m swebench.harness.run_evaluation --dataset_name princeton-nlp/SWE-bench_Lite \
  --predictions_path /tmp/<iid>.gold.jsonl --instance_ids <iid> --run_id gold_<iid> \
  --max_workers 1 --cache_level instance --clean False
# 2) container + test patch (test patch ADDS the F2P test):
docker run -d --name wk <image> tail -f /dev/null
docker cp <iid>.testpatch wk:/tmp/tp.patch && docker exec wk bash -lc 'cd /testbed && git apply /tmp/tp.patch'
# 3) search (env-configured):
SWE_CONT=wk SWE_FILE=<src.py> SWE_F2P=<test> SWE_P2P="<p2p tests>" \
SWE_MODE=<pytest|sympy> SWE_TESTCMD="<in-container test cmd>" SWE_STRATA=2 python swe_run.py
```
Image naming: `swebench/sweb.eval.x86_64.<iid with __ → _1776_>`. Cached: seaborn-3010,
sympy-13480/-15346/-18057(+building). WSL disk ~887 G free.

---

## Open threads / next steps (ranked)

1. **Guidance without an LLM** (the crux for structural rewrites). Ladder, cheapest→learned, all
   LLM-free: deterministic pruning (types/scope/localization/Occam) → **verifier gradient**
   (partial-credit, not binary) → **count-based frequency prior** (P(edit | failure-signature)) →
   **self-grown value model** (random-forest/GBT/tiny-MLP on hand AST features, labels from the
   search's own solved traces = AlphaZero flywheel) → **k-NN case retrieval** (= attention, no net)
   → **bandit/MCTS** online allocation. *Concrete demo to build:* a tiny edit-ranker trained on the
   QuixBugs search traces that solves in fewer candidates and reaches bugs that timed out unguided.
2. **Wire the FULL engine into `swe_run`** — it currently only runs stratum-0 grammar. Add strata
   1–2, interpolation, and synthesis as fallback rungs; re-run the reachable set at full strata
   (would catch `reach:expr` like sympy-15346, which failed at stratum 0).
3. **Rich-grammar synthesis** — `synth.py` is numeric-int only. Extend to lists/strings/calls to
   fire on real expression bugs (census: numeric ~1% → rich ~10% of SWE-bench).
4. **Statement-level frames** — guards (`if x: return/continue`), else/elif, assignment-with-RHS.
   Census headroom: +6.3% (assignment) +3% (guard) +2.3% (branch).
5. **Fix `batch_sympy.py` official-verify** (WSL `/tmp` path bug) and finish the measured sympy
   subset; then add django/pytest harness handling for the other 6 reachable instances.
6. **Diverse-witness spec gate + incompleteness detector** (query-by-committee) — makes the
   translator auditable.
7. **Full SWE-bench is an infra wall, not a reasoning choice:** 300 images (~TB, days) + 12 repo
   harnesses, and the census already bounds the result at ~10–25%. Do the affordable subset, not 300.

---

## Status at handoff

- `batch_sympy.py` running (task in the prior session): sympy-13480 **solved** (`cotm→cothm`),
  15346 **unsolved** (ran at stratum 0; it's `reach:expr`, needs stratum 1), 18057/21847 in progress.
  Its official-verify column is unreliable (the `/tmp` path bug) — re-verify solved patches with a
  direct `run_evaluation` call (images are cached, ~1–2 min each).
- Memory: `~/.claude/.../memory/project_reasoning-bugfix-search.md` has the full detailed ledger;
  `MEMORY.md` has the one-line index entry.
