# Pre-registration -- L3b: THE CLOSED-BOOK SURNAME PROBE WITH FREQUENCY-MATCHED DISTRACTORS (2026-10-09)

**Registered after seeing L3's data** (`L3_prereg.md`, result section): L3's residual preference for true surnames
(0.695) equalled its preference with a neutral context (0.693), i.e. a frequency prior, because distractors were drawn
uniformly from a pool full of rare names. This file fixes the probe and is evaluated on the *existing* L2b and L3
checkpoints; nothing is retrained. Being post hoc, its bars are set before `eval_l3b.py` is run, and a miss is recorded.

## Probe
- The same 200 passages (`cache/name_probes.json`), cut after the first name.
- Distractors: 10 names of the same class from other books whose corpus count (capitalised occurrences across the
  training books) lies within [0.5x, 2x] of the true surname's count; widened to [0.33x, 3x] if fewer than 10 qualify;
  if still fewer, the probe is dropped and the count reported. Seed 7.
- Two contexts per probe: the book passage, and the neutral sentence "It was late in the evening when they came to the
  house of". **Context lift** = top-1 rate with the book context minus top-1 rate with the neutral context; the same for
  win rate. Lift is what the book context, and only the book context, adds -- a model with no memory of the book has
  lift 0 whatever the prior.

## Gates
| gate | claim | bar |
|---|---|---|
| **L3b-1 sanity** | the control (L2b) remembers: its book-context top-1 lift | **>= +0.15** (else the probe is void) |
| **L3b-2** | L3 does not: its book-context top-1 lift | **<= +0.05** |
| **L3b-3** | L3's absolute win rate with the book context, now that the prior is matched | **<= 0.60** |

Prediction: control lift ~ +0.25 (as in the unmatched probe), win ~ 0.85; L3 lift ~ 0, win 0.50-0.58.

## Result (2026-10-09, same day, after `eval_l3b.py`)

200 probes, 0 dropped (every true surname had >= 10 same-class names within [0.5x, 2x] of its corpus count).

| | book context win / top-1 | neutral context win / top-1 | lift win / top-1 |
|---|---|---|---|
| control L2b (unpermuted text) | 0.790 / 0.450 | 0.495 / 0.055 | **+0.295 / +0.395** |
| L3 (name-permuted text) | 0.580 / 0.085 | 0.515 / 0.070 | **+0.065 / +0.015** |

| gate | measured | bar | verdict |
|---|---|---|---|
| **L3b-1 sanity** | control top-1 lift +0.395 | >= +0.15 | PASS (the probe discriminates) |
| **L3b-2** | L3 top-1 lift +0.015 | <= +0.05 | **PASS** |
| **L3b-3** | L3 book-context win 0.580 | <= 0.60 | **PASS** |

With the prior matched, the neutral context is at chance for both models (top-1 0.055 / 0.070, chance 0.09), which
confirms the diagnosis in `L3_prereg.md`. The control, trained on the plain books, picks the right surname 45% of the
time from the passage and 5.5% without it: it remembers who is who. L3, trained on the same books with names permuted,
picks it 8.5% with the passage and 7% without: it does not. Language cost 1.2% (L3a).

**The no-memories mechanism is established for individuals' names.** What it does not yet cover: facts carried by
undetected names (titles, places with events), plot facts, and lexical facts about kinds; `STATE_SPACE_PLAN.md` L4
(retrieval in context during training) and the counterfactual gate SS3 are the next steps.
