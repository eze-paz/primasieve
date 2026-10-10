# R17 -- THE EMERGENT ENGLISH READER: INDUCE THE GRAMMAR FROM VERIFIED CASES (scoped 2026-10-10, not yet run)

Scoping registration. R16 showed that the construction learner needs word classes under it. The project already owns
a grammar inducer that learns word classes, lemma maps, determiners, suffix rules, gap constructions and frame-to-role
tables from (sentence, logical form) pairs, sound-gated by reproduction: `cogs_gram.py` (stages 3a/3b), proven on COGS.
It has never been fed English text because English text comes without logical forms.

## The route
1. **Silver logical forms from verified readings.** Every case where the merged engine's answer is verified -- the
   hand reader's event reproduces a known answer, or the model's answer passes the exact checks -- yields a
   (sentence, event) pair: `agent VERB patient [place] [time]`. The teacher traces (`r5_train.json`, 699 events over
   real sentences) and the generated stories (40,000 questions with gold) are the first corpus; verified answers from
   use grow it.
2. **Induce with `cogs_gram.py`'s machinery** over those pairs: word classes by alignment (the event's fillers are
   spans in the sentence), lemma map, determiners, suffix rules ("-ed" past), frames (who-did-what-to-whom order and the
   prepositions that mark place and time), each admitted only if it reproduces every pair it covers (stage 3b's rule).
3. **Read** new sentences with the induced grammar; abstain where no parse reproduces; the model fills the gap, and
   its verified answers feed step 1. That is the crystal growing from experience with every rule inspectable and
   nothing written by hand except the inventory of generic combinators that COGS already fixed.

## Gates (to be fixed before the first run)
| gate | bar |
|---|---|
| **R17-a** | on the validation sets, the induced reader's coverage >= the hand reader's (43 / 80) at precision >= 0.95, with zero hand-written sentence shapes |
| **R17-b** | growth: coverage on real-text validation traces rises monotonically as verified cases are added (three checkpoints of the corpus) |
| **R17-c** | the merged engine (induced reader first) matches or beats R9-R13 on the tests, run once |

Scope: days, not a session -- `cogs_gram.py` assumes COGS's token-position alignment and terminator; English needs
span alignment, punctuation, and noisy silver forms (epsilon-tolerant induction, `core/tolerance.py`). This is the
emergence campaign's open item for English and the piece that makes the exact component emergent.

## Feasibility probe (2026-10-10, `r17_probe.py`, run once before any gate)

2,583 unique English rows built from verified story events (fillers a name or determiner + noun; COGS logical-form
syntax with token positions). `cogs_gram.induce` ran on 1,500 of them without modification: it induced word classes,
lemma suffix rules and a frame, and produced structured readings of real book sentences it had never seen
("Sheldon glanced at the thermometer." -> glanc.agent(x1, Sheldon), glanc.theme(x1, x4), * thermometer(x4)).
Numbers: reproduction on its own training rows 98 ok / 63 wrong / 1,339 no parse; held-out story sentences 16 / 300
parsed, 14 exact; real book sentences 5 / 200 parsed.

Reading: the machinery accepts English and generalises (the suffix rules reach "glanced", "held", "chose"), but the
silver forms describe only agent-verb-theme and leave the rest of each sentence unexplained ("with Gussie for being
kind", "first and won a lantern"), and the inducer, built for complete logical forms, refuses to parse what it cannot
account for. Two routes from here, both registered before use: (a) complete the silver forms (places, times, second
clauses) from the hand reader's adjunct and coordination output; (b) let the inducer tolerate unannotated spans as
noise (`core/tolerance.py`'s epsilon ladder, stage 3d) so a partial form still admits the sentence. A second probe on
sentences the forms cover completely says which: if reproduction is high there, (a) is the bottleneck.
