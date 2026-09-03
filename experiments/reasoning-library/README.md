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
