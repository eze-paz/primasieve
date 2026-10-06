# COMPREHENSION -- a reader of ordinary sentences, order-aware, learned from exposure (2026-10-06)

The fluency loop (FLUENCY_HYPOTHESES.md, section 7) ended on one wall seen twice: the engine's reader is ORDER-BLIND,
and it can read almost no real text (0 of 20,000 dictionary phrases as a complete reading). Fluent speech needs a monitor
that understands sentences, and the monitor is the reader. This campaign builds the reader.

## What "comprehension" is measured as
A sentence is understood, here, as far as the engine can say WHAT IT CLAIMS in a form it can check: (subject, relation,
object) propositions over things its worlds know. Every rung is measured against the 65,263-entity crawl store, on
sentences the learner never saw, with a knockout. A sentence's unread remainder is reported, never filled in.

## The theory it rests on (from FLUENCY_HYPOTHESES.md)
Usage-based grammar: constructions are learned from exposure, as form-meaning pairs, and their ORDER is part of the form
(H4, H10). The meaning side comes free here: when a sentence mentions two things the store already relates, the relation
is the sentence's likely meaning (distant supervision). Order matters because the store's relations have a direction.

## Rungs (one prereg + one gate each; nulls reported)

| rung | what | measured by |
|---|---|---|
| **C1** | **Constructions from exposure.** Dictionary sentences about a stored entity that mention a second stored entity it is related to -> the words between the two mentions, IN ORDER, become a construction for that relation (with its direction). | held-out precision of extracted propositions against the store; order test (mentions swapped -> no false extraction); knockout (relations shuffled) |
| **C2** | **Reading prose with a residue.** The constructions read held-out sentences, including book quotations and a novel: propositions extracted, the rest of the sentence marked unread. | share of sentences with a checkable proposition (from 0); precision; residue size |
| **C3** | **The order-aware monitor.** SPEAK's monitor reads its wordings with these constructions instead of the order-blind loop. | reversed wordings 0 at coverage >= 60 % (the wall of H10b) |
| **C4** | **Statements in the chat.** "Tokyo is the capital of Japan" is read as a claim and checked (true / false / unknown); a new statement the person makes is kept as THEIR claim, attributed, never as a fact. | true / false / unknown accuracy on generated statements; attribution |
| **C5** | **Composition.** Two constructions in one sentence ("Paris, the capital of France, lies on the Seine") -> two propositions. | multi-proposition sentences read; precision held |

## Rules carried over
Facts certificate-bound; anything read from text is a reading with its construction as the reason, checked against a
world when one holds the fact, labelled when none does. Prereg before code, one gate per rung, misses recorded as misses.
