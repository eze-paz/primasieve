# R15 -- THE MODEL AS JUDGE AMONG CANDIDATES FROM THE HIT (2026-10-10)

Registered before any run. R14 showed the rules cannot check what they cannot read. R15 tries the owner's framing on
the model's share: instead of asking the model to *write* the answer, ask it to *choose* among candidates that the
engine extracts exactly from the hits -- the capitalised names and the determiner-led noun phrases of the hit
sentences -- plus "none of these". The engine commits only a candidate (so the answer is read, never produced); the
model's job shrinks to judgment. No training: the R5 checkpoint is prompted
`Question: ...\nHits: ...\nChoices: A) ... B) ... C) ...\nAnswer:` and the first choice letter is read.
Applied to the merged engine's model share on validation first.

| gate | bar |
|---|---|
| **R15-a** | validation (130): on the model's share, right answers >= the free-form model's right and wrong <= 70% of its wrong |
| **R15-b** | test once (`r3_b6real_v3`, R5 model): merged right >= 58, wrong <= 30 |

Prediction: choosing is easier than writing for a 0.4B model; right holds or rises, wrong falls by a third.
If R15-a fails, the judge needs training (candidate-choice fine-tune on the teacher data), registered as R15b.
