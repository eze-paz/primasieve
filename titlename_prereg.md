# Pre-registration -- LOOP ITERATION 49 (B4-book precision): "MR. VANBOROUGH" KEPT WHOLE (`core/bookworld.py`; 2026-10-08)

Registered 2026-10-08 before the code. Zero LLM. Iteration 48's judged sample showed 4 of 7 wrong novel propositions from
one fault of the base book reader: a sentence-initial title ("Mr. Vanborough had returned") -- the name run's start skips
the sentence-initial non-entity "Mr" and leaves its "." as the doer's first symbol (". Vanborough had returned"); an object
run stops at the title's "." ("Lady Jane addressed Mr").
Mechanism: (A) the start-skip never skips a learned abbreviation that its "." follows (the title stays: "Mr. Vanborough");
(B) an object whose noun run begins a name run that reaches further (past an abbreviation's ".") takes the name's text.
Both use the learned abbreviations only.

## Gates
| gate | claim | bar |
|---|---|---|
| **T1** | no novel proposition in the run begins with "." or ends in a learned abbreviation (counted over all, not sampled) | **0** (count before/after reported) |
| **T2** | novels coverage >= 37.5 %; judged precision on the new sample >= 0.86; K3 0; battery (B2, B5, B6, B9, B10, B4 frozen) and probes held | held |

## Result (2026-10-08) -- PASS (T1 amended once, before the scored count)
- **T1 PASS**: novel propositions beginning with "." or ending in a learned abbreviation, counted over the whole run:
  **34 -> 0**. The first count after (A)+(B) left 3, all from the reader hooks (kb_bookread) rather than the base reader;
  amended: the outermost hook completes a role ending in a capitalised learned abbreviation from the sentence's
  "<abbr> . <Capitalised run>" ("on Mr" -> "on Mr. Vanborough"). Recount: 0.
- **T2 PASS**: novels 644 -> **654 / 1709 = 38.3 %** (sentence-initial titles now read: "Mr. Kendrew looked inquiringly",
  "Mrs. Vanborough rose immediately"); judged sample **48/50 = 0.96** (wrong: "I ashame" from "I am ashamed"; "Mistress
  Margery Wimpole is a poor" -- the adjective's noun cut); K3 0 of 1455; B2 90.4 %, B5 +11.6, B6 67, B9 18/20, B10 398,
  B4 frozen 3, B1 1 (known item); probes RIGHT 107 / WRONG 14.
