# Pre-registration -- LOOP ITERATION 26 (novel 11): A CHARACTER'S WORDS ARE A SOURCE INSIDE THE BOOK (`book_battery.py` hook; 2026-10-07)

Registered 2026-10-07 before the code. Zero LLM. Owner's ruling: every source has its own context. After iteration 25,
1,320 of the 1,709 real-novel test sentences are unread and **609 of them hold quotation marks** -- dialogue ("You are a
stranger to me from this moment.", "\"I am thy Dad,\" he said."). A quotation is a nested source: what a character says
is that character's claim, inside the book, never the book's narration and never world fact.

## Mechanism
For a still-unread test sentence with quotation marks: each quoted segment (text between marks; a sentence opening
inside a quotation runs to the first closing mark) is read by the same readers as iterations 23-25 (strict main-clause
events, pronoun doers said unresolved, copular readings), as a sentence of its own. The SPEAKER is the name (or a pronoun,
said unresolved) standing next to a verb right after the closing mark or right before the opening one ('"...," said
Porbus'; 'Porbus said, "..."'); otherwise "a speaker (not resolved)". Inside the quotation "I" is the speaker and "you"
the one addressed. The proposition is said "according to <title>, <speaker>'s words: <reading>".

## Gates
| gate | claim | bar |
|---|---|---|
| **W1** | B4-book real novels read | **>= 28 %** |
| **W2** | builder-judged precision (50 novels): the quotation says this, and the speaker is right or said unresolved | **>= 0.85** |
| **W3** | K3: nothing said without its book (and speaker) context | 0 |

## Prediction
W1 ~30 %; W2 ~0.88 (speaker attribution errors are the risk).

## Run (2026-10-07): W2 PASS, W1 NOT met
**Novels 25.1 % (429/1,709)**, others 12.3 %; builder's precision **novels 44/50 = 0.88** (tests/bookworld_judged_it11.json);
K3 0 of 817. Quoted readings judged right include '"Sir Jeoffry missed his mark ...," said the woman who had nursed her'
(speaker said unresolved: not a name), '"Rake is my horse," she answered' (speaker "she", unresolved), '"Women are poor
things"'. Errors: a narration segment read as speech when the sentence OPENS inside a quotation and its narration holds
commas ('My good Porbus," he added, turning to his friend, "is it ...' -> "he add" as quoted words); a hyphenated word
cutting a predicate ("a well-bred English servant" -> "The man is a well"); older-reader patient slips.
**Verdict: W1 NOT met (25.1 vs 28 %), W2 met (0.88), W3 met.** Next: the book reader's own paragraph-level quotation
state (core/bookworld.inside) instead of pairing marks within the sentence; hyphen-joined words.
