"""THE UNIFIED ANSWER LOOP -- research every symbol, intent by affordance, answer by certificate
(emergence/no_paradigm_prereg.md section 5; emergence/em_resolve_prereg.md, E-10).

The acceptance case the owner named: the engine sees "What is a dog?" knowing no word and must research, derive
the intent, and answer with a cited source -- with no authored behaviour. So this module holds no word of any
language, no question form, no punctuation glyph, no reply sentence. It knows four things:

  SEGMENT   symbols are maximal runs of one Unicode major category; separators are dropped AS A CATEGORY.
  RESOLVE   every symbol is looked up through an injected `sources` object (the core imports no source module
            and no world): readings of three KINDS -- bound to an attached world's predicate, bound to an
            executable primitive, or a quotable gloss with a certificate.
  TOPIC     the symbol the utterance is about = the unique most SPECIFIC symbol among those with a reading,
            specificity = how many dictionary definitions mention it (the sources' own base rate; E-9's key).
            A tie -> ASK. This is the loop's one declared bias.
  INTENT    by AFFORDANCE: the candidate actions are the reading kinds the topic actually has. One kind -> held
            CONJECTURED (the sole thing the engine CAN do with it; the user never said so). Several -> the
            cheapest reversible kind, CONJECTURED, with the alternatives named. None -> refuse, naming what
            was consulted. Intent reaches COMMIT only when the user confirms it.
  ANSWER    the action's output shown as itself: the gloss verbatim with source (held ATTRIBUTED), the referent
            set, or the executed value. No sentence is composed here; the caller formats structure.
  LEARN     accepted (symbols, topic, kind) observations are anti-unified: two that agree everywhere but at the
            topic yield a FRAME (skeleton with one hole -> kind) held CONJECTURED. A frame fires before
            affordance and is retracted on rejection like any conjecture (core.verdict rules).

"I hate my dog" at cold start resolves to the gloss of dog, because that is the only affordance. That is the
child's "goed": visible, tagged, and corrected by one word from the user. It is not hidden and not a COMMIT."""
import unicodedata

from .verdict import COMMIT, ABSTAIN, ATTRIBUTED, CONJECTURED, RETRACTED, attribute

# reading KINDS, in COST order (cheapest reversible first). Integers, not names: a name here would be a word.
WORLD, EXEC, GLOSS = 0, 1, 2
KINDS = (WORLD, EXEC, GLOSS)


def segment(raw):
    """maximal runs of one Unicode major category; category Z (separators) dropped."""
    out, cur, cat = [], "", None
    for ch in raw:
        c = unicodedata.category(ch)[0]
        if c == cat:
            cur += ch
        else:
            if cur and cat != "Z": out.append(cur)
            cur, cat = ch, c
    if cur and cat != "Z": out.append(cur)
    return out


def _lookup(symbols, sources):
    """symbol -> dict(kind -> list of readings). `sources.readings(symbol)` returns {WORLD: [...], EXEC: [...],
    GLOSS: [(gloss, source_id, certificate_text), ...]}; `sources.df(symbol)` its definition count."""
    return {i: sources.readings(s) for i, s in enumerate(symbols)}


def topic_of(symbols, readings, sources):
    """-> (index, tie: bool). The unique most specific symbol that has at least one reading."""
    cands = [i for i, r in readings.items() if any(r.get(k) for k in KINDS)]
    if not cands:
        return None, False
    ranked = sorted(cands, key=lambda i: (sources.df(symbols[i]), i))
    if len(ranked) > 1 and sources.df(symbols[ranked[0]]) == sources.df(symbols[ranked[1]]):
        return None, True
    return ranked[0], False


def match_frame(symbols, frames):
    """-> (frame, hole index) for the first live frame whose skeleton matches, else (None, None)."""
    for fr in frames:
        if fr["state"] == RETRACTED or len(fr["skeleton"]) != len(symbols):
            continue
        hole = None; ok = True
        for i, (a, b) in enumerate(zip(fr["skeleton"], symbols)):
            if a is None:
                hole = i
            elif a.lower() != b.lower():
                ok = False; break
        if ok and hole is not None:
            return fr, hole
    return None, None


def resolve(raw, sources, beliefs=None, frames=None):
    """-> dict(symbols, readings, topic, tie, kind, state, alternatives, answer, via_frame, consulted).
    `beliefs` (core.verdict.Beliefs) receives the gloss held ATTRIBUTED; `frames` is the caller's list."""
    frames = frames if frames is not None else []
    symbols = segment(raw)
    readings = _lookup(symbols, sources)
    consulted = list(getattr(sources, "consulted", []))
    out = dict(symbols=symbols, readings=readings, topic=None, tie=False, kind=None, state=ABSTAIN,
               alternatives=(), answer=None, via_frame=None, consulted=consulted)
    fr, hole = match_frame(symbols, frames)
    if fr is not None and readings[hole].get(fr["kind"]):
        out.update(topic=hole, kind=fr["kind"], via_frame=fr)
    else:
        t, tie = topic_of(symbols, readings, sources)
        out["tie"] = tie
        if t is None:
            return out
        feasible = [k for k in KINDS if readings[t].get(k)]          # affordances, in cost order
        out.update(topic=t, kind=feasible[0], alternatives=tuple(feasible[1:]))
    t, k = out["topic"], out["kind"]
    out["state"] = CONJECTURED                                          # intent is never more than a guess here
    rd = readings[t][k]
    if k == GLOSS:
        glosses = [(g, sid) for g, sid, _ in rd]
        out["answer"] = glosses
        if beliefs is not None:
            g0, sid, text = rd[0]
            claim, st, prov = attribute((symbols[t], tuple(g for g, _ in glosses)), sid, text, g0,
                                        lambda span: (symbols[t], tuple(g for g, _ in glosses)) if span == g0 else None)
            if st == ATTRIBUTED:
                beliefs.hold(("gloss", symbols[t].lower()), claim[1], ATTRIBUTED, prov)
    else:
        out["answer"] = list(rd)
    return out


def accept(frames, symbols, topic, kind, history):
    """The user accepted the action. Record the observation; anti-unify against earlier accepted ones: same
    length, equal everywhere except the topic slot -> a FRAME held CONJECTURED. -> the new frame or None."""
    obs = (tuple(s.lower() for s in symbols), topic, kind)
    for (sy, tp, kd) in history:
        if kd == kind and tp == topic and len(sy) == len(obs[0]) and \
           all(a == b for i, (a, b) in enumerate(zip(sy, obs[0])) if i != topic) and sy[topic] != obs[0][topic]:
            skel = tuple(None if i == topic else s for i, s in enumerate(obs[0]))
            if not any(f["skeleton"] == skel and f["state"] != RETRACTED for f in frames):
                fr = dict(skeleton=skel, kind=kind, state=CONJECTURED, support=[sy, obs[0]], deps=[])
                frames.append(fr); history.append(obs); return fr
    history.append(obs)
    return None


def reject(frames, frame):
    """The user rejected an answer given through a frame: the frame is RETRACTED (one contradiction is enough)."""
    frame["state"] = RETRACTED
    return frame
