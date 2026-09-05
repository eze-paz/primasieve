"""COMMIT/ABSTAIN, and the two-mode soundness score.

The project's standing invariant since Stage 1: NO probabilistic output. A predictor either commits to an
answer or declines. That makes the failure modes DISTINGUISHABLE, and Phase 6 established they are not
interchangeable:

    CONFABULATION  committed an answer and it was wrong   -- fatal; the whole value proposition dies here
    ABSTENTION     declined to answer                     -- the honest price of noise or ambiguity

Report confabulation FIRST, above any accuracy number. Stage 3d is the case in point: the eps = 0 engine's
exact match fell 1.000 -> 0.000 at 1% training corruption while confabulation stayed at 0.0000, i.e. it
collapsed into abstention and remained deployable in a way an accuracy column alone would have hidden."""
COMMIT, ABSTAIN = "commit", "hard"


def commit(x):
    return (x, COMMIT) if x is not None else (None, ABSTAIN)


def score_two_mode(predict, rows, equal=None):
    """predict(input) -> answer or None. rows -> (input, gold[, tag]). -> dict, confabulation included.

    `precision` is accuracy AMONG COMMITTED answers, which is the number that says whether an abstaining
    component can be trusted when it does speak."""
    equal = equal or (lambda a, b: a == b)
    n = em = confab = abstain = 0
    per = {}
    for row in rows:
        inp, gold = row[0], row[1]
        tag = row[2] if len(row) > 2 else ""
        pred = predict(inp)
        n += 1
        d = per.setdefault(tag, dict(n=0, em=0, confab=0, abstain=0))
        d["n"] += 1
        if pred is None:
            abstain += 1
            d["abstain"] += 1
        elif equal(pred, gold):
            em += 1
            d["em"] += 1
        else:
            confab += 1
            d["confab"] += 1
    d = max(n, 1)
    return dict(n=n, EM=em / d, confab=confab / d, abstain=abstain / d,
                precision=(em / (em + confab)) if (em + confab) else 1.0, per=per)


def line(label, r, width=22):
    """One row of the standard report, confabulation before exact match -- deliberately."""
    return (f"  {label:<{width}} n {r['n']:6d}  CONFAB {r['confab']:.4f}  abstain {r['abstain']:.4f}  "
            f"EM {r['EM']:.4f}  precision {r['precision']:.4f}")
