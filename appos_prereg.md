# Pre-registration -- LOOP ITERATION 42 (novel 25): DETERMINERS CLEANED; AN APPOSITION BETWEEN SUBJECT AND VERB; YES/NO COPULAR QUESTIONS (`kb_events.py`, `kb_bookread.py`, `core/events.py`; 2026-10-07)

Registered 2026-10-07 before measuring. Zero LLM. From the live-door passage of iteration 41 ("Heart of Darkness").
(A) Determiners: the top-50 rule of iteration 21 admitted pronouns and verbs with one minor determiner sense (he, she, it,
they, said ...), and the dictionary's entry for "a" lacks the sense (letter and symbol senses only). Now: >= 30 %
determiner/article senses, plus closed symbols sharing >= 10 % of the commonest determiner's two-sided slots (learned:
a, an, his, ...). Result: a, all, an, another, any, either, every, few, her, his, more, much, my, no, our, some, such, the,
their, these, this, those, thy, what, whatever, whose, your.
(B) "The Nellie, a cruising yawl, swung to her anchor": a sentence-start name or determiner phrase, a comma, an apposition,
a comma, the verb -> the doer is the sentence-start phrase.
(C) "Was the wind calm?": a question opened by a copula form is answered "yes" from an identity fact whose two sides each
share the question's content words (never "no": a missing fact is not a denial).

## Gates
| gate | claim | bar |
|---|---|---|
| **A1** | book battery: novels read | not lower than 37.0 %; precision (50 judged) >= 0.92 |
| **A2** | B6 >= 56; B2, B9 held; probes WRONG <= 15 | held |
| **A3** | the Conrad passage: the two sentences above read; "Was the wind calm?" -> yes | shown |

## Run (2026-10-07): PASS (A1-A3)
A3, the live door on the "Heart of Darkness" passage: "I read 4 of 6 sentences. According to your text, The Nellie swing;
... the wind is nearly calm; ... A haze rest; ... The air is dark above Gravesend." -- "Was the wind calm?" -> "As you told
it: yes (the wind be nearly calm)"; "What rested on the low shores?" -> "A haze".
A1: book battery novels 37.7 % (645/1,709), others 24.6 %; builder's precision **novels 47/50 = 0.94**
(tests/bookworld_judged_it14_a42.json); K3 0 of 1,443.
A2: **B6 56 -> 58**, B2 90.4 %, B9 18/20, B10 398, B5 +11.6, B1 counted 1 (true); probes **RIGHT 106, WRONG 14**.
Remaining errors: a verb-less reading ("her beauteous lithe limbs"), a participle doer inside a quotation ("Having heard
thy daughter ..."), "ought" read as "owe".
