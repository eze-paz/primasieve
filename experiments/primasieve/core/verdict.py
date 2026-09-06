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

# ---------------------------------------------------------------------------------------------------------------
# THE THIRD STATE -- ATTRIBUTED (E-7, emergence/em_attributed.py, em_attributed_prereg.md; owner's proposal).
#
# Two buckets, proven or silent, cap the engine's reach at what its oracles can verify. ATTRIBUTED lets it HOLD
# and USE a premise it cannot verify, on one condition: a CERTIFICATE -- (source, span) where the span is a
# verbatim substring of the source and the engine's own reading of the span yields exactly the claim. That check
# is exact, so a new fatal column appears next to confabulation: MISATTRIBUTION. And a third: LAUNDERING -- a
# COMMIT whose provenance is non-empty and was never upgraded by world evidence. All three must sit at zero.
#
#   taint      anything derived from an attributed premise is attributed, provenance = union
#   one-way    world evidence contradicting it RETRACTS it and every dependent (source struck); world evidence
#              uniquely confirming it UPGRADES it to COMMIT; nothing ever moves COMMIT -> ATTRIBUTED
#   no weights the only per-source number is a COUNT of confirmations/strikes, reported, never used to decide
#
# E14 pre-registered a CONJECTURED state and was deleted for want of a certificate; the reference IS the
# certificate. "The core is as wide as its oracles" gets a companion: attributed reach is as wide as its
# SOURCES, and the guarantee shifts from correctness to fidelity. Measurements: see the E-7 row in ARCHITECTURE.
# ---------------------------------------------------------------------------------------------------------------
ATTRIBUTED, RETRACTED = "attributed", "retracted"


def attribute(claim, source_id, source_text, span, reads):
    """Admit `claim` on the word of `source_id` iff the certificate checks: `span` is verbatim in the source
    text and `reads(span) == claim`. -> (claim, ATTRIBUTED, {(source_id, span)}) or (None, ABSTAIN, set()).
    A failed check is a MISATTRIBUTION attempt: it is refused at the door and never held."""
    if span and span in source_text and reads(span) == claim:
        return claim, ATTRIBUTED, {(source_id, span)}
    return None, ABSTAIN, set()


def combine(*states):
    """The taint lattice: any ABSTAIN/RETRACTED -> ABSTAIN; any ATTRIBUTED -> ATTRIBUTED; else COMMIT."""
    if any(s in (ABSTAIN, RETRACTED) for s in states): return ABSTAIN
    if any(s == ATTRIBUTED for s in states): return ATTRIBUTED
    return COMMIT


class Beliefs:
    """Provenance-carrying store. Each key -> dict(value, state, prov: set[(source, span)], deps: set[key],
    upgraded: bool). Derived claims inherit the union of provenance and the lattice state."""

    def __init__(self):
        self.b = {}; self.strikes = {}; self.confirms = {}

    def hold(self, key, value, state, prov=()):
        self.b[key] = dict(value=value, state=state, prov=set(prov), deps=set(), upgraded=False, from_=set())
        for s, _ in prov: self.strikes.setdefault(s, 0); self.confirms.setdefault(s, 0)

    def derive(self, key, value, from_keys):
        prem = [self.b[k] for k in from_keys]
        state = combine(*[p["state"] for p in prem])
        prov = set().union(*[p["prov"] for p in prem]) if prem else set()
        self.b[key] = dict(value=value, state=state, prov=prov, deps=set(), upgraded=False, from_=set(from_keys))
        for k in from_keys: self.b[k]["deps"].add(key)
        return state

    def upgrade(self, key):
        """world evidence uniquely confirms an ATTRIBUTED claim -> COMMIT (provenance kept as history)."""
        e = self.b[key]
        if e["state"] == ATTRIBUTED:
            e["state"] = COMMIT; e["upgraded"] = True
            for s, _ in e["prov"]: self.confirms[s] = self.confirms.get(s, 0) + 1

    def retract(self, key):
        """world evidence contradicts an ATTRIBUTED claim -> RETRACTED, cascading to every dependent."""
        e = self.b[key]
        if e["state"] == COMMIT and not e["prov"]:
            raise AssertionError("a world-verified COMMIT is never retracted")
        out = []
        stack = [key]
        while stack:
            k = stack.pop()
            if self.b[k]["state"] == RETRACTED: continue
            self.b[k]["state"] = RETRACTED; out.append(k)
            stack.extend(self.b[k]["deps"])
        for s, _ in e["prov"]: self.strikes[s] = self.strikes.get(s, 0) + 1
        return out

    def laundered(self):
        """COMMITs carrying provenance that were never upgraded by the world -- must be empty."""
        return [k for k, e in self.b.items() if e["state"] == COMMIT and e["prov"] and not e["upgraded"]]


def summarize3(n, confab, misattrib, laundered, attributed_wrong, attributed, abstain, label=""):
    """The reporting contract with the third state: the three FATAL columns first."""
    n = max(n, 1)
    return (f"{label + ': ' if label else ''}CONFABULATION {confab}/{n}   MISATTRIBUTION {misattrib}   "
            f"LAUNDERING {laundered}   |   attributed {attributed}/{n} (source-wrong {attributed_wrong})   "
            f"abstain {abstain}/{n}")


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


def summarize(n, em=None, confab=0, abstain=0, label=""):
    """The REPORTING CONTRACT, shared: confabulation first, exact match second.

    Threads that tally their own counters (perception, the phase5 grounded-language arc, the E-series, the
    dialogue arc) call this instead of formatting their own line, so the ordering stays uniform. Stage 3d is
    why the ordering is fixed rather than a matter of taste: exact match fell 1.000 -> 0.000 at 1% training
    corruption while confabulation stayed 0.0000, and a report that led with accuracy would have read as a
    total failure rather than as an intact abstaining component."""
    n = max(n, 1)
    em = (n - confab - abstain) if em is None else em
    return (f"{label + ': ' if label else ''}CONFABULATION {confab}/{n} = {confab/n:.4f}   "
            f"abstain {abstain}/{n} = {abstain/n:.4f}   correct {em}/{n} = {em/n:.4f}   "
            f"precision {(em/(em+confab)) if (em+confab) else 1.0:.4f}")
