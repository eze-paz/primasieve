# Decision-map validation: 100 prompts, map-v1 vs instinct

Method: each prompt is routed twice — once by mechanically applying map-v1's router
(pick the single best-matching of its 8 shapes, follow its leaf procedure), and once by
introspecting what I would actually do. **Agree = N** means following v1's leaf would have
produced observably different (worse) behavior than instinct, not merely a different label.

Prompt sources: ~40 adapted from our real chat history (which skews heavily to coding,
research, and report writing — noted bias), ~60 deliberately outside that scope
(everyday facts, personal decisions, emotional, creative, math, ambiguous, meta).

Instinct routes are named in v2 vocabulary, which is itself the output of this exercise.

| # | Prompt (abridged) | map-v1 route | Instinct | Agree |
|---|---|---|---|---|
| 1 | Capital of Mongolia? | FACT_LOOKUP (must retrieve) | RECALL from weights, instantly | N |
| 2 | How does HTTPS work? | FACT_LOOKUP | RECALL/TEACH — stable knowledge, no retrieval | N |
| 3 | When did WW2 end? | FACT_LOOKUP | RECALL | N |
| 4 | Boiling point of water at 3000m? | COMPUTE | RECALL + quick COMPUTE | Y |
| 5 | Who won the 2026 World Cup? | FACT_LOOKUP | LOOKUP (post-cutoff → web) | Y |
| 6 | Current Chrome WebGPU flags? | FACT_LOOKUP | LOOKUP (docs, volatile info) | Y |
| 7 | Is Pluto a planet? | FACT_LOOKUP | RECALL | N |
| 8 | News on AI regulation this week | FACT_LOOKUP | LOOKUP | Y |
| 9 | What does tools.js export? | FACT_LOOKUP (repo as corpus) | INSPECT — open the file; grep is not "retrieval+cite" | N |
| 10 | Where is compaction triggered? | FACT_LOOKUP (repo) | INSPECT — close enough to v1 leaf | Y |
| 11 | Is our deploy script idempotent? | FACT_LOOKUP | INSPECT + INVESTIGATE — requires analysis, not lookup | N |
| 12 | How many lines is sandpie.html? | COMPUTE | COMPUTE | Y |
| 13 | Add a dark-mode toggle | AGENTIC | ORCHESTRATE (inspect → create → verify) | Y |
| 14 | Rename this function everywhere | AGENTIC | ORCHESTRATE (mechanical edit + verify) | Y |
| 15 | Write a script to dedupe my photos | GENERATE (draft→critique→final) | CREATE-precise: write, RUN, verify — critique loop is the wrong verifier for code | N |
| 16 | Fix the failing test | AGENTIC (decompose, do) | INVESTIGATE first (why does it fail?), then patch | N |
| 17 | Port this Python to Rust | TRANSFORM (no verify step in leaf) | TRANSFORM + compile/test — executable output demands execution check | N |
| 18 | Bump version and deploy | AGENTIC | ORCHESTRATE | Y |
| 19 | Make this query faster | AGENTIC (just optimize) | INVESTIGATE — measure/profile BEFORE touching anything | N |
| 20 | Add error handling to fetchUser | AGENTIC | CREATE-precise, small | Y |
| 21 | Why is my build failing? | no fit → FACT_LOOKUP? | INVESTIGATE: evidence → hypotheses → discriminating test → explain | N |
| 22 | App crashes on iPhone only | AGENTIC? | INVESTIGATE | N |
| 23 | Why does deepseek garble Catalan? | FACT_LOOKUP? | INVESTIGATE | N |
| 24 | Memory doubles after each run | AGENTIC? | INVESTIGATE | N |
| 25 | Is this a race condition? | FACT_LOOKUP? | INVESTIGATE | N |
| 26 | Tests pass locally, fail in CI | AGENTIC? | INVESTIGATE | N |
| 27 | Why is output different each run? | FACT_LOOKUP? | INVESTIGATE | N |
| 28 | Users report slow loads at 9am | AGENTIC? | INVESTIGATE | N |
| 29 | Any progress in edge inference this August? | FACT_LOOKUP | LOOKUP then synthesize+contextualize — a composition, v1 has no composition rule | N |
| 30 | WebGPU vs WASM for inference? | DECIDE | DECIDE (knowledge-heavy) | Y |
| 31 | Survey ternary quantization methods | GENERATE | ORCHESTRATE: research sweep → synthesize → write | N |
| 32 | Is Bergamot QE feasible for us? | FACT_LOOKUP | INVESTIGATE (feasibility = evidence + experiment) | N |
| 33 | Find 3 PDF-signing libs, recommend one | DECIDE | LOOKUP + DECIDE | Y |
| 34 | What's SOTA on ARC-AGI now? | FACT_LOOKUP | LOOKUP | Y |
| 35 | Write a proposal for client X | GENERATE | ORCHESTRATE: gather context → outline → draft → check facts | N |
| 36 | Summarize this 40-page PDF | TRANSFORM | TRANSFORM | Y |
| 37 | Turn these notes into a status report | TRANSFORM | TRANSFORM (+light CREATE) | Y |
| 38 | Write a README for this repo | GENERATE | INSPECT first, then CREATE — never describe unread code | N |
| 39 | Draft email declining a meeting | GENERATE | CREATE-expressive-lite | Y |
| 40 | Exec summary of our Q3 metrics (data attached) | TRANSFORM | TRANSFORM | Y |
| 41 | Write a poem about entropy | GENERATE (draft→critique→final) | CREATE-expressive: single flow; critique loops flatten voice | N |
| 42 | Name ideas for a cat cafe | GENERATE (best-of-N) | CREATE-expressive, variants — best-of-N is right here | Y |
| 43 | Noir short story, 500 words | GENERATE (critique loop) | CREATE-expressive, single flow | N |
| 44 | Make this paragraph funnier | TRANSFORM | TRANSFORM-expressive | Y |
| 45 | Slogan for a bakery | GENERATE | CREATE-expressive, variants | Y |
| 46 | Limerick about JavaScript | GENERATE | trivial CREATE, no scaffold | Y |
| 47 | 7023 × 5817? | COMPUTE | COMPUTE (exact) | Y |
| 48 | Piano tuners in Chicago? | COMPUTE | COMPUTE-estimate with stated assumptions | Y |
| 49 | Prove √2 is irrational | COMPUTE (write code??) | RECALL/derive in prose — proofs aren't scripts | N |
| 50 | Solve this ODE | COMPUTE | COMPUTE (sympy) | Y |
| 51 | Sample size for 5% MDE? | COMPUTE | COMPUTE | Y |
| 52 | Is 2^61−1 prime? | COMPUTE | COMPUTE | Y |
| 53 | Odds of shared birthday among 30? | COMPUTE | COMPUTE | Y |
| 54 | Estimate tok/s for 8B Q4 on my CPU | COMPUTE | COMPUTE-estimate + RECALL | Y |
| 55 | Tabs or spaces? | DECIDE (criteria matrix) | direct recommendation, one line — matrix is absurd here | N |
| 56 | Postgres or Mongo for this app? | DECIDE | DECIDE, full treatment | Y |
| 57 | Should I take the job offer? | DECIDE (score options) | DECIDE-personal: elicit values first; scoring THEIR life on MY criteria is wrong | N |
| 58 | Which laptop under 1000€ for LLMs? | DECIDE | LOOKUP + DECIDE | Y |
| 59 | Worth migrating to TypeScript? | DECIDE | DECIDE | Y |
| 60 | Pick a name: sandpie vs sandcastle | DECIDE (matrix) | quick take + reasons — effort mismatch | N |
| 61 | Should we ship Friday? | DECIDE | DECIDE, quick but real (stakes) | Y |
| 62 | Vue or React for a solo dev? | DECIDE | DECIDE | Y |
| 63 | Coworker takes credit for my work | CHAT? DECIDE? | RESPOND-counsel: acknowledge, explore, then options — not a matrix, not banter | N |
| 64 | I'm burned out, can't focus | CHAT | RESPOND-counsel | N |
| 65 | How do I tell my boss I'm quitting? | GENERATE | counsel + CREATE (script), register first | N |
| 66 | My PR got torn apart, I feel dumb | CHAT ("just answer") | RESPOND-counsel — "just answer" is exactly wrong | N |
| 67 | Cofounder equity fight | DECIDE | RESPOND-counsel + DECIDE later | N |
| 68 | What did we ship yesterday? | FACT_LOOKUP (git/memory) | INSPECT history — matches leaf | Y |
| 69 | Why did you choose SQLite there? | FACT_LOOKUP | recall own reasoning + INSPECT — near enough | Y |
| 70 | Summarize this conversation | TRANSFORM | TRANSFORM | Y |
| 71 | How confident are you in that fix? | CHAT | mini-INVESTIGATE: re-examine evidence, quantify — not vibes | N |
| 72 | What would you do differently? | CHAT | RESPOND-reflect | Y |
| 73 | Remember: always use pnpm | no shape (AGENTIC?) | tiny state-change: save it, confirm, done — needs a micro-action path | N |
| 74 | "No — blue, not green" | re-enters router as GENERATE | G1: patch live work, keep everything uncontested | N |
| 75 | "That broke the tests, revert" | AGENTIC (fresh) | G1: targeted undo + re-verify | N |
| 76 | "Actually target ES2018" | AGENTIC (fresh) | G1: delta patch | N |
| 77 | "Shorter." | GENERATE (fresh) | G1: compress prior output, keep decisions | N |
| 78 | "You misread — the OTHER config" | CLARIFY? | G1: re-inspect + patch, apologize once | N |
| 79 | "Good — now same for mobile view" | AGENTIC (fresh plan) | G1-extend: reuse established patterns/decisions | N |
| 80 | "Make it better" (doc attached) | CLARIFY (forbidden to guess) | infer axis from context, state assumption, proceed | N |
| 81 | "Handle the edge cases" | CLARIFY | enumerate edge cases myself, cover them | N |
| 82 | "Look at the thing from yesterday" (no referent) | CLARIFY | CLARIFY — genuinely unresolvable | Y |
| 83 | "Fix the date bug" (several exist) | CLARIFY | INSPECT first; ask only if still ambiguous | Y* |
| 84 | "Add auth" (huge unstated scope) | CLARIFY | propose default plan + assumptions, confirm — don't just ask open-ended | N |
| 85 | Good morning! | CHAT | RESPOND | Y |
| 86 | Thanks, that worked | CHAT | RESPOND | Y |
| 87 | Thoughts on tabs in YAML lol | CHAT | RESPOND | Y |
| 88 | Tell me something interesting | CHAT | RESPOND | Y |
| 89 | Profile which tool eats our latency | AGENTIC | ORCHESTRATE (instrument → measure → report) | Y |
| 90 | Set up per-turn timing metrics | AGENTIC | ORCHESTRATE | Y |
| 91 | Why do 100-turn loops happen? | FACT_LOOKUP? | INVESTIGATE (this was the shell↔OPFS split hunt) | N |
| 92 | Translate UI strings to Catalan | TRANSFORM | TRANSFORM | Y |
| 93 | Does node:sqlite have db.transaction()? | FACT_LOOKUP (docs) | verify by EXECUTION — run a 3-line node check; docs lie, runtimes don't | N |
| 94 | Convert this LaTeX to HTML | TRANSFORM | TRANSFORM (+pipeline) | Y |
| 95 | Benchmark Q4 vs Q8 on this box | COMPUTE | COMPUTE-experiment | Y |
| 96 | Design the schema for usage metrics | GENERATE | CREATE-precise + DECIDE on tradeoffs; critique-loop ≠ schema validation | N |
| 97 | Review this PR | DECIDE? TRANSFORM? | EVALUATE — no v1 shape for critique-against-criteria | N |
| 98 | Audit repo for secrets | AGENTIC | ORCHESTRATE sweep | Y |
| 99 | Watch the deploy, tell me if it fails | no shape | MONITOR — standing task, no v1 concept | N |
| 100 | Teach me how attention works | FACT_LOOKUP/GENERATE | TEACH: calibrate to learner, build up, check understanding | N |

\* row 83 counted as agree: v1's CLARIFY fires, instinct also ends in a question if inspection fails — same observable behavior in the worst case.

## Tally

**Agree: 49 / 100. Disagree: 51 / 100.**

Mechanical application of map-v1 misroutes half of real traffic. The disagreements are not
noise — they cluster into 8 themes:

| Theme | Rows | Correction in v2 |
|---|---|---|
| A. Forced retrieval for stable knowledge | 1,2,3,7 | Split FACT_LOOKUP → RECALL (weights, default for stable facts) vs LOOKUP (external, for volatile/post-cutoff/cited). Retrieval is a tripwire (entity-dense, time-sensitive, low confidence), not a default. |
| B. INVESTIGATE missing — the biggest hole | 11,16,19,21–28,32,71,91 (14) | New shape: evidence → hypotheses → discriminating test → explanation. Deliverable is the diagnosis, not a fix, unless a fix was asked. Subsumes measure-before-optimize. |
| C. No continuation/steering path | 73–79 (7) | New gate G1 before the router: if the prompt is feedback on live work, do NOT re-route — patch the delta, keep every uncontested decision, re-verify. |
| D. Register-blindness (one GENERATE, one CHAT) | 15,41,43,49,63–67,96,100 (11) | CREATE split into precise (spec + mechanical verify) vs expressive (taste, single flow, variants-over-critique-loops). CHAT widened to RESPOND with a counsel register. TEACH added. COMPUTE gets a derive-in-prose mode for proofs. |
| E. No composition rule | 29,31,35,38 | ORCHESTRATE formalized: complex prompts compile to a plan of leaf-shaped steps, each re-routed; research→synthesize→write is a pipeline, not a GENERATE. |
| F. CLARIFY as a shape is wrong | 80,81,84 | Demoted to gate G3 with a threshold: ask only if interpretations diverge materially AND a wrong guess is expensive/irreversible. Otherwise: assume, state the assumption, proceed. Prefer propose-plan-and-confirm over open-ended questions for big scope. |
| G. DECIDE has no effort gate | 55,57,60 | Small stakes → direct recommendation + one-line why. High stakes → criteria matrix. Personal/life stakes → elicit the person's values before any scoring. |
| H. Missing minor leaves | 9,17,93,97,99 | EVALUATE (review/critique), MONITOR (standing watch), INSPECT promoted to first-class (source-before-claim), verify-by-execution preferred over doc lookup when testable, TRANSFORM of executable content must execute the result. |

## v3 addendum: the corrections above went the wrong direction

User correction (2026-08-27), accepted: v2 aligned the map to the strong model's *instinct*,
but instinct shortcuts are capability substitutes — reliable priors, calibration, taste, a
world model — that the target executor does not have. The map exists precisely because the
executor can't do what instinct does. Therefore:

- **Instinct is the target OUTPUT, not the procedure.** The map's job is to force a weak
  executor through explicit steps that land on the conclusion instinct reaches in one hop.
- **The 51 disagreements are not map errors — they are the capability-delta map**: the exact
  list of nodes where ability, not procedure, was doing the work. Those are where the tree
  must be densest, i.e. where v2 removed machinery, v3 re-adds it in explicit form:
  weights may draft but retrieval judges (RECALL atom-check); ambiguity is resolved by
  mandatory enumeration, not silent inference (G3); every DECIDE gets a matrix, sized not
  skipped; expressive CREATE replaces "taste" with best-of-N + tournament selection
  (verification asymmetry: weak models rank far better than they generate); counsel and
  teaching become scripts.
- v2's structural additions (INVESTIGATE, continuation gate G1, source split, composition
  rules, EVALUATE/MONITOR) survive unchanged — they added structure, which was the right
  direction all along.

See map.json v3 `executor_model` for the governing rules (collapse only via external
verifier; generation never judges itself; latency is the currency we have).

## Meta-observations

1. The 51% disagree rate is itself the finding: a shape taxonomy is necessary but the real
   routing signal is **(shape × source-of-truth × register × stakes × is-this-a-continuation)**.
   v1 collapsed five dimensions into one.
2. Nearly all corrections REMOVE scaffolding rather than add it (don't retrieve trivia, don't
   matrix small decisions, don't critique-loop poems, don't interrogate vague-but-inferable
   requests). Instinct's main advantage over the mechanical map is knowing when NOT to deploy
   machinery. Any small-model harness built from this map should bias the same way.
3. History bias check: our chat history is ~90% coding/research/reports. The themes that
   ONLY surfaced from out-of-scope prompts were D (counsel/teach registers) and G
   (values-elicitation). A map built purely from our history would have silently lacked them.
4. Continuations (theme C) are invisible in any prompt-level taxonomy because they're not
   prompts — they're deltas against session state. Any deployed router needs conversation
   state as an input, not just the message.
