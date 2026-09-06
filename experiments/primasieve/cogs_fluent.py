"""STAGE 8 -- MEANING FIRST, then fluent realization. RNG ranges ONLY over meaning-preserving choices.

The architecture: the engine writes the MEANING first -- a voice-neutral, order-free content structure (the
"caveman" form: an event and its role fillers, no grammar) -- and a REALIZER then applies the induced grammar
to produce fluent English, choosing at random among options that PROVABLY do not change the meaning:
  SYNONYM   a different surface word for the same concept (man / guy)
  VOICE     active vs passive -- foregrounds a different argument, same roles
  (word-order variants the grammar licenses would go here too)

This keeps primasieve's identity intact: the abstain-not-guess rule is about MEANING, never surface. The RNG
never picks a wrong meaning; it ranges over the SET of realizations the engine has already verified equivalent.
The soundness invariant that makes it honest: every realized sentence must PARSE BACK to the same meaning
(round-trip). If a synonym or voice choice altered the meaning, the round-trip would catch it as a confabulation.

This module is a synthetic demonstration of the architecture on a grammar we induce; passively learning the
realization grammar + synonym classes from raw text (alice.txt, WordNet) is the next stage."""
import os, sys, random

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cogs_lf import serialize, parse_lf, norm_lf
from cogs_gram import induce, generate

# ---------------------------------------------------------------- a synthetic world with synonyms + voice
CONCEPTS_N = [f"C{i}" for i in range(8)]                       # entity concepts (the meaning-level lemmas)
CONCEPTS_V = [f"E{i}" for i in range(5)]                       # event concepts
SYN = {c: [c.lower() + "a", c.lower() + "b"] for c in CONCEPTS_N + CONCEPTS_V}   # 2 surface synonyms per concept


def meaning(rng):
    """A voice-neutral, order-free 'caveman' meaning: an event with an agent and a theme concept."""
    return dict(event=rng.choice(CONCEPTS_V), agent=rng.choice(CONCEPTS_N), theme=rng.choice(CONCEPTS_N))


def _lf(event_surf, ag_surf, ag_c, th_surf, th_c, order):
    """Build the gold logical form for a chosen surface. Variables ARE token positions. `order` is the token
    sequence with the event/agent/theme placed; roles are attached by CONCEPT, voice-neutral in the LF's role
    assignments (agent stays agent in both voices; only surface order and function words differ)."""
    toks, pos = [], {}
    for role, surf in order:
        pos[role] = len(toks)
        toks.append(surf)
    conj = []
    # entity self-predicates (concept lemma at the token position)
    conj.append((ag_c, (("v", pos["agent"]),)))
    conj.append((th_c, (("v", pos["theme"]),)))
    ev = ("v", pos["event"])
    conj.append((event_surf_lemma(event_surf) + " . agent", (ev, ("v", pos["agent"]))))
    conj.append((event_surf_lemma(event_surf) + " . theme", (ev, ("v", pos["theme"]))))
    return toks, conj


def event_surf_lemma(surf):
    return surf[:-1].upper()          # 'e0a' -> 'E0'  (surface -> concept lemma)


def realize_variants(m, rng, n_samples=6):
    """All the ways this meaning can be realized -- (voice x synonyms) -- as (sentence, gold LF). The generator
    is DETERMINISTIC given the choices; the RNG is applied by the caller sampling from these."""
    out = []
    for _ in range(n_samples):
        ev = rng.choice(SYN[m["event"]])
        ag = rng.choice(SYN[m["agent"]])
        th = rng.choice(SYN[m["theme"]])
        voice = rng.choice(["active", "passive"])
        if voice == "active":
            order = [("agent", ag), ("event", ev), ("theme", th)]          # AG V TH
            toks = [ag, ev, th, "T"]
        else:
            order = [("theme", th), ("was",), ("event", ev), ("by",), ("agent", ag)]   # TH was V by AG
            toks = [th, "was", ev, "by", ag, "T"]
        # place tokens and roles by concept, voice-neutral role assignment
        pos = {}
        seq = []
        for slot in order:
            if len(slot) == 2:
                pos[slot[0]] = len(seq)
                seq.append(slot[1])
            else:
                seq.append(slot[0])
        # role conjuncts in SURFACE-SLOT order (the subject's role first): the engine's role-induction
        # consistency check is order-aware, so an active sentence emits agent-then-theme and a passive
        # sentence theme-then-agent -- the same role ASSIGNMENTS, ordered by where they surface.
        elem = event_surf_lemma(ev)
        roles_by_pos = sorted([("agent", pos["agent"]), ("theme", pos["theme"])], key=lambda rp: rp[1])
        conj = [(m["agent"], (("v", pos["agent"]),)),
                (m["theme"], (("v", pos["theme"]),))]
        conj += [(elem + " . " + role, (("v", pos["event"]), ("v", p))) for role, p in roles_by_pos]
        out.append((" ".join(toks), serialize([], conj), voice))
    return out


def build_train(rng, n=2500):
    """Training pairs: every voice x synonym combination appears, so the grammar induces both voices and every
    synonym as a surface for its concept."""
    seen, rows = set(), []
    while len(rows) < n:
        m = meaning(rng)
        for s, lf, voice in realize_variants(m, rng, n_samples=4):
            if s not in seen:
                seen.add(s)
                rows.append((s, lf, "fluent"))
    return rows[:n]


def role_set(lf):
    """The voice-neutral MEANING recovered from a logical form: {(role, concept)} plus the entity concepts.
    This is what a round trip must preserve -- active and passive of one meaning map to the SAME role set."""
    p = parse_lf(lf)
    if p is None or p[0] == "LAMBDA":
        return None
    ent = {}                                          # variable -> concept lemma (from unary self-predicates)
    roles = set()
    for pred, args in p[1]:
        segs = [x.strip() for x in pred.split(" . ")]
        if len(segs) == 1 and len(args) == 1:
            ent[args[0][1]] = segs[0]
    for pred, args in p[1]:
        segs = [x.strip() for x in pred.split(" . ")]
        if len(segs) == 2 and len(args) == 2:
            filler = ent.get(args[1][1], args[1][1])
            roles.add((segs[0], segs[1], filler))     # (event-concept, role, filler-concept)
    return frozenset(roles)
