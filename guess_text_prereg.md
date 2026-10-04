# Pre-registration -- G2: GUESSING FROM TEXT (`core/guesser.py` text cues, `guess_text.py`; 2026-10-04)

Registered 2026-10-04 before the first run. Zero LLM. Second rung of GUESS_PLAN.md. G1 (guess_prereg.md) guesses from
an entity's stored facts and its name; most things a person asks about have no stored facts but do have TEXT. The gloss
line measured that the dictionary-gloss reader is "sound as a reader and unsound as a voucher" (gloss_width_prereg.md):
words a pattern carries but does not explain become unchecked claims. Under GUESS_PLAN's split that is no longer a wall
for GUESSING: a pattern that holds MOSTLY may speak, labelled, with its counts, and earns its record.

## 1. Mechanism
- **Text cues.** A text becomes cues of two kinds, language-blind: every symbol (`#text:w`) and every pair of adjacent
  symbols (`#text:b`). No stop-word list: a function word never reaches the 0.9 share for one value, so the admission
  bar is the filter. Text cues are claims like any other; the G1 guesser learns and guesses over them unchanged
  (support 5, share 0.9).
- **Data.** The crawl entities whose label has a Wiktionary entry (`_nldata/kaikki_all.sqlite`); the text is the first
  three definitions. Held-out: the same seeded 10 % as G1.
- **In the chat.** When no graph world holds the name, the dictionary world's definitions of the turn's rarest symbol
  are the text, and the guess comes from text cues alone, labelled, its reason naming the words ("12 of 12 with the words
  'town in' ... have that").

## 2. Gates
| gate | claim | bar |
|---|---|---|
| **T1** | text cues ONLY: pooled held-out precision at coverage, over the 8 G1 targets | precision **>= 0.85** at coverage **>= 0.25** |
| **T2** | text added to claims + name, on the same entities: coverage rises and precision holds | coverage **> G1's** on them; precision **>= 0.85** |
| **T3** | KNOCKOUT: texts shuffled across entities | right text-only guesses **< 25 %** of T1's |
| **T4** | of the right text-only guesses, the share whose value is written in the text (reading) vs not (inferring) | printed |
| **T5** | BEYOND THE STORE: dictionary headwords with no crawl entity that receive an "instance of" guess from their definitions; 30 printed for audit | printed |
| **T6** | in a session: a question about a word only the dictionary knows ("what is the country of X") -> a labelled guess from its definition; no value from text ever COMMIT/ATTRIBUTED | all |
| **T7** | G1 and the registered numbers unchanged (guess.py --quick; chat.py) | unchanged |
| **T8** | hygiene: core/guesser.py holds no word of any language | structural |

PASS = T1-T3, T6-T8.

## 3. Predictions
P1 text-only ~0.88 at ~0.35 (definitions name the country or the kind of thing: "A town in central Bulgaria"). P2
combined coverage +0.10 over G1 on these entities. P3 knockout under 5 %. P4 about two thirds of right text guesses
have the value written in the text; one third are inferred ("town in ... Highland" -> United Kingdom). P5 tens of
thousands of headwords beyond the store receive a type guess.

## 4. What a PASS would and would not establish
Would: the engine guesses about things it has never stored, from what is written about them, labelled and with a
record. Would not: understanding arbitrary prose (only definitions are read), guessing what a sentence MEANS (G3).

## 5. Runs (2026-10-04): NOT PASSED (T1 missed by a hair; T2, T3, T6-T8 pass)

14,181 crawl entities with a Wiktionary definition (train 12,752, test 1,429); 4,374 admitted rules, 1,264 on text cues.

- **T1 MISS.** Text cues ONLY: pooled precision **0.846 at coverage 0.238** (bars 0.85 and 0.25). By target: country
  0.42 / 0.882, continent 0.73 / 0.941, sex 0.44 / 1.00, instance of 0.10 / 0.791, country of origin 0.35 / 0.654,
  language 0.34 / 0.706. The weak ones are the KIND of thing ("instance of") and the attributes of works: definitions
  name places well and kinds poorly at this admission bar.
- **T2 PASS.** On the same entities, facts + name (G1) 0.942 at 0.459; with text added 0.901 at **0.518**: text buys
  six points of coverage and costs four of precision.
- **T3 PASS.** Texts shuffled across entities: 12 right text-only guesses, 2.7 % of T1's.
- **T4.** Of 343 right text guesses (sampled), 236 (69 %) have the value written in the text -- reading, labelled as a
  guess because the alignment is unverified -- and 107 (31 %) are inferred: "prefecture-level city ... Tibet" -> People's
  Republic of China (26 of 26 with "level city"), "Native American tribe" -> United States (51 of 56), "southern China"
  -> China. The wrong ones are instructive: Niger -> Nigeria (its definition names its neighbour: "nigeria" 82 of 87),
  San Vicente -> France ("commune in" 27 of 28, but this commune is in Chile), Bruges -> France ("aquitaine"; the second
  sense is a French town of that name).
- **T5.** 179,876 dictionary names outside the store; 2,350 receive an "instance of" guess. The audit sample shows the
  same weakness as T1: "balasore -> modern language because 'odisha' 11/12" -- a cue that mostly co-occurs with
  languages in training is applied to a city. Recorded: a type guess from text is the guesser's weakest output.
- **T6 PASS.** In a session: "what is the country of uluru" -> "My guess for the country of uluru: Australia (because 7
  of 7 with the words 'central australia' in their definition have that)"; nagqu -> People's Republic of China; the
  continent of gabrovo -> Europe. 3 of 8 (five names have no definition, or no admitted rule); fatal 0.
- **T7** guess.py and chat.py unchanged. **T8** structural.

Found on the way, each fixed with its rule: the session's guess chose a graph reading of "what" over the dictionary's
reading of the rarest word -- one rule for the name whichever world holds it (the span of rarest symbol, then the
longest).

### Disposition
Not registered. What stands: text extends the guesser to things the store never held, with a record and a reason
(T2, T6), and the shuffle collapses it (T3). What failed: text alone does not reach the bar, and the KIND of a thing is
poorly guessed from definitions at a single-cue admission rule. The next lever is in G4 (a model of text: which words
go with which), not in lowering this bar.
