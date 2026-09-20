"""DEGREE 4 -- representation extension by COLLISION-DRIVEN SELECTION (fable's one genuine new degree).

Every earlier degree lives inside one TYPE of logical form: a flat conjunct bag. New combinators grow the
vocabulary but never change the expressive class. SCOPE changes the class -- a bag of conjuncts cannot hold
"every scopes over some" vs "some scopes over every", no matter how many combinators you add over it (Stage 5
demonstrated this null: the two readings serialize to a byte-identical flat set). This module tests whether a
rejection-first engine can EXTEND the representation to hold scope, soundly, and only when forced to.

THE MECHANISM (bounded, honest -- the type-constructor library is HAND-GIVEN, exactly as l0 was one level
down; the claim is "selection over a hand-given extension library", never "inventing representations"):
  1. an EXTERNAL DISCRIMINATOR scores two inputs differently (here: truth against a supplied situation -- pure
     set membership, zero-LLM)
  2. the current representation forces the SAME form on those two inputs -> a representational COLLISION
  3. select the MINIMAL extension from a hand-given library that (a) resolves the collision, (b) raises
     held-out discriminator accuracy, (c) is inert where no collision exists
  4. THE KNOCKOUT (the anti-relabel device): ablate the discriminator so the two inputs share a truth value.
     No collision now exists. The engine MUST NOT propose the extension. If it does, "collision-driven" is
     false -- the proposal was driven by priors, not the signal, and the degree is not earned.

The two quantifier readings of `every cat R some dog`:
  AE (forall > exists):  every cat R'd some (possibly different) dog   -- true iff  for all c, exists d: R(c,d)
  EA (exists > forall):  some one dog every cat R'd                    -- true iff  exists d, for all c: R(c,d)
A situation is a relation R subset of C x D. AE and EA DISAGREE on some situations and AGREE on others (they
always agree when |D| = 1). The agreeing situations are the discriminator-ablation knockout."""
import itertools
import random


def truth(reading, C, D, R):
    if reading == "AE":
        return all(any((c, d) in R for d in D) for c in C)
    return any(all((c, d) in R for c in C) for d in D)     # EA


def rand_situation(rng, C, D, force_agree=False):
    """A random relation R subset of C x D. force_agree restricts to situations where AE == EA (the knockout):
    the cleanest such family is |D| == 1, where 'some dog' has a unique witness so the readings coincide."""
    if force_agree:
        D = D[:1]
    R = {(c, d) for c in C for d in D if rng.random() < 0.5}
    return D, R


# ---------------------------------------------------------------- the two representations
def R0(item):
    """FLAT form: scope-free. Drops the reading, so AE and EA map to the SAME frozenset -- the collision."""
    q1, q2, reading = item["q1"], item["q2"], item["reading"]
    return frozenset({("Q", q1, "x"), ("Q", q2, "y"), ("R", "x", "y")})


def R1(item):
    """EXTENDED form: adds a WIDE(quantifier) atom naming which quantifier scopes wider. Distinct per reading."""
    wide = "x" if item["reading"] == "AE" else "y"
    return R0(item) | {("WIDE", wide)}


def eval_form(form, reading_of_form, C, D, R):
    """Truth predicted from a FORM. A flat form has no scope, so it must PICK a default reading (AE); the
    extended form carries the reading and evaluates it correctly."""
    if reading_of_form is None:
        return truth("AE", C, D, R)         # scope-free: forced to guess one reading
    return truth(reading_of_form, C, D, R)


def reading_from_R1(form):
    for atom in form:
        if atom[0] == "WIDE":
            return "AE" if atom[1] == "x" else "EA"
    return None


# ---------------------------------------------------------------- data
def make_items(rng, n, force_agree=False, quantifier_free=False):
    """Generate items. For the scope test, BOTH readings of the SAME situation are emitted, so a scope-free
    form that drops the reading produces a same-form same-situation pair with (on a discriminating situation)
    two different truths -- the collision. Situations are drawn to DISCRIMINATE (AE != EA) unless force_agree
    (the knockout) restricts to |D| = 1, where the readings necessarily coincide."""
    C, D0 = ["c0", "c1"], ["d0", "d1"]
    items = []
    while len(items) < n:
        D, R = rand_situation(rng, C, D0, force_agree=force_agree)
        if quantifier_free:
            it = dict(q1="every", q2="some", reading="AE", C=C, D=D, R=R, single=True)
            it["truth"] = truth("AE", C, D, R)
            items.append(it)
            continue
        disc = truth("AE", C, D, R) != truth("EA", C, D, R)
        if not force_agree and not disc and rng.random() < 0.6:
            continue                                    # keep the mix discriminating so the flat baseline is low
        for reading in ("AE", "EA"):
            it = dict(q1="every", q2="some", reading=reading, C=C, D=D, R=R)
            it["truth"] = truth(reading, C, D, R)
            items.append(it)
    return items[:n]
