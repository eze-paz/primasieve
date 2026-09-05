"""STAGE 3d -- corruption models for the noise experiment, and the two-mode soundness scorer.

Noise goes into the TRAINING pairs only; the test set stays clean gold. That is the question that decides
whether this engine meets real data: did it learn the right grammar despite dirty supervision.

Scoring follows Phase 6 (f3c09bb) rather than reporting one accuracy number, because the two failure modes
are not interchangeable and only one of them is fatal:

    CONFABULATION  committed an answer and it was wrong          <- the engine's value proposition dies here
    ABSTENTION     declined to answer                            <- the honest price of noise

An engine whose exact-match falls while its confabulation stays at zero is still deployable on dirty data; one
whose exact-match holds up by guessing is not. So confabulation is reported first, above any EM."""
import os, sys, random, collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cogs_lf import parse_lf, serialize, norm_lf

TYPES = ("drop_conjunct", "add_conjunct", "swap_roles", "perturb_token", "mispair")


def _roles_in(conj):
    out = []
    for i, (pred, args) in enumerate(conj):
        segs = [x.strip() for x in pred.split(" . ")]
        if len(segs) == 2 and len(args) == 2:
            out.append((i, segs[0], segs[1]))
    return out


def corrupt_row(kind, s, lf, rng, vocab, pool):
    """-> a corrupted (sentence, logical form), or the original when this row admits no such corruption."""
    if kind == "mispair":
        return s, rng.choice(pool)
    if kind == "perturb_token":
        toks = s.split()
        if len(toks) < 2:
            return s, lf
        i = rng.randrange(len(toks))
        toks[i] = rng.choice(vocab)
        return " ".join(toks), lf
    p = parse_lf(lf)
    if p is None or p[0] == "LAMBDA":
        return s, lf
    defs, conj = list(p[0]), list(p[1])
    if kind == "drop_conjunct":
        if not conj:
            return s, lf
        del conj[rng.randrange(len(conj))]
    elif kind == "add_conjunct":
        if not conj:
            return s, lf
        pred, args = conj[rng.randrange(len(conj))]
        conj.insert(rng.randrange(len(conj) + 1), (pred, args))
    elif kind == "swap_roles":
        rs = _roles_in(conj)
        if len(rs) < 2:
            return s, lf
        a, b = rng.sample(rs, 2)
        if a[2] == b[2]:
            return s, lf
        conj[a[0]] = (a[1] + " . " + b[2], conj[a[0]][1])
        conj[b[0]] = (b[1] + " . " + a[2], conj[b[0]][1])
    return s, serialize(defs, conj)


def corrupt(train, rate, kind=None, seed=0):
    """Corrupt a fraction `rate` of the SENTENCE rows. kind=None mixes the five types uniformly."""
    rng = random.Random(90000 + seed)
    idx = [i for i, (s, lf, c) in enumerate(train)
           if c != "primitive" and not lf.startswith("LAMBDA") and len(s.split()) > 1]
    vocab = sorted({w for s, lf, c in train for w in s.split()})
    pool = [lf for s, lf, c in train if c != "primitive" and not lf.startswith("LAMBDA")]
    hit = set(rng.sample(idx, int(round(rate * len(idx)))))
    out = []
    counts = collections.Counter()
    for i, (s, lf, c) in enumerate(train):
        if i not in hit:
            out.append((s, lf, c))
            continue
        k = kind or rng.choice(TYPES)
        s2, lf2 = corrupt_row(k, s, lf, rng, vocab, pool)
        counts[k] += (s2 != s or lf2 != lf)
        out.append((s2, lf2, c))
    return out, counts


def score(model, rows, generate):
    """Phase-6-style two-mode scoring. -> dict with confabulation reported as its own quantity."""
    a = collections.Counter()
    for s, gold, cat in rows:
        pred = generate(model, s)
        a["n"] += 1
        if pred is None:
            a["abstain"] += 1
        elif pred == norm_lf(gold):
            a["em"] += 1
        else:
            a["confab"] += 1
    n = max(a["n"], 1)
    return dict(n=a["n"], EM=a["em"] / n, confab=a["confab"] / n, abstain=a["abstain"] / n,
                precision=(a["em"] / (a["em"] + a["confab"])) if (a["em"] + a["confab"]) else 1.0)
