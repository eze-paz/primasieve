> **Standalone repo (2026-10-02).** Carved out of `sandpie/experiments/primasieve` with its full history
> (`git subtree split`, 3,610 commits). Run everything from this directory: `python core_selftest.py` (the gate
> on the core), `python worlds_general.py` (worlds as data, composition, library, turns, research),
> `python critical.py` (contradictory claims and the record of a source). The regenerable data under
> `_nldata/` (Wiktionary/Kaikki sqlite, the Wikidata cache) is git-ignored and must be present for the
> offline gates; `build_wikt_corpus.py` and `kb_wikidata.py` rebuild it. Baseline-arm commits referenced by
> the runners (`BASELINE = ...`) are hashes of THIS repo's history.

**START HERE: [ARCHITECTURE.md](ARCHITECTURE.md)** — what the code is, the shared `core/`, the
consolidation ledger, and the rule that keeps it from re-fragmenting. `python core_selftest.py`
is the gate on the core itself. This README and the per-arc plans below are history.

# Primasieve Engine

A rejection-first reasoning engine. Zero LLM, pure-Python stdlib, deterministic verification.

**One-sentence claim:** a fixed, domain-free loop — GENERATE → REJECT → COMPRESS → COMPOSE → PROPOSE →
COLLECT, plus inverse spec-inference and primitive-invention — given a compositional object grammar and a
**sound rejection channel**, grounds itself by coverage in an environment nobody authored, **fails closed**
outside its grammar, and invents new operators (which reduce to object-grammar expressions) from real
residuals.

**Shape:** a ~26 KB engine whose entire learned knowledge — across polynomials, code bugs, and a real SQL
engine — is **137 bytes** of verified relations. The opposite shape from an LLM (where billions of parameters
*are* the knowledge and there is no separable engine). *The core is exactly as wide as its oracles.*

See `CONSOLIDATION.md` for the falsifiable claim, the E1–E8 evidence, and the mapped limits.
Files: `meta_forms.py`, `meta_reason.py`, `meta_param.py`, `meta_struct.py`, `meta_codeparam.py`,
`meta_bench.py`, `meta_e1.py … meta_e8.py`, `meta_e7_prereg.md`.
