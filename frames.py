"""FRAMES -- the chat layer's realization of the epistemic frames as SENTENCES, and its exact inverse (f4_prereg.md
Part 2; chat_acts_prereg.md phase B; chat_prose_prereg.md phase C). English lives HERE, not in core/. The RNG ranges only
over meaning-preserving surfaces (which sentence shape, the provenance phrase, the order of support items); parse()
inverts realize() exactly, so a realized reply carries its frame and nothing else. No probability is emitted.

Phase C: every content frame carries the UNDERSTOOD STRUCTURE as a PHRASE in the user's own words (`phrase_of`): the
text spans the structure read are rendered as the user wrote them, a reading borrowed from context by its label. So an
elliptical turn shows the reading the loop took ("what is japan" after a capital question -> "the capital of japan is
Tokyo"), and evidence is written with the world's labels, not identifiers.

Frame shapes (dicts):
  ANSWER    {kind, phrase, values: [str], supports: [str], sources: [str]}
  READINGS  {kind, options: [(value, phrase[+record])], split: str}
  PARTIAL   {kind, phrase, values: [str], supports: [str], missing: [str]}
  FOUND     {kind, quotes: [(text, source)]}
  PROPOSE   {kind, consulted: [str], action: str}
  CONJECTURE{kind, choice: (value, source, confirmed, contradicted), rivals: [...]}
  META      {kind, question, field, content}          CHECK {kind, phrase, value, stated|None, sources}
  ACK       {kind, acts: [(word, act)], offers: [str]}"""
import os
import re
import sys

from core.reason import READINGS, PARTIAL, WEAK, NOT_FOUND, Composite, symbols, _spans
from core.verdict import ATTRIBUTED, COMMIT, CONJECTURED
from core import table as T
from core import kg as K

ANSWER, READ, PART, FOUND, PROPOSE, CONJ = "ANSWER", "READINGS", "PARTIAL", "FOUND", "PROPOSE", "CONJECTURE"
META_K, CHECK_K, ACK_K = "META", "CHECK", "ACK"          # phase B frames (chat_acts_prereg.md)
SEP = " ; "

# The transcript world's field names, as DATA (core/transcript.py holds no word): the realization words this file
# already speaks -- support / evidence / source / answer / question -- plus FOUR authored words, counted in
# chat_acts_prereg.md: why -> support, again / repeat -> the previous frame re-realized, shorter -> that frame briefed.
META = {"support": "support", "evidence": "support", "source": "source", "sources": "source", "answer": "answer",
        "question": "question", "why": "support", "again": "frame", "repeat": "frame", "shorter": "brief"}
DENY = ("no",)                                            # beside a choice, denies the previous answer (core.session)


def speech_act(word):
    """WordNet's own classification of a word as a conversational move (emergence/wn_acquire.speech_act): a noun sense
    filed under the communication lexicographer file; the act label is the gloss head. No list of acts here."""
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "emergence"))
        from wn_acquire import speech_act as _sa
        return _sa(word)
    except Exception:
        return None


# ---- meaning-preserving variants: the RNG's whole range (the form side, where a temperature is admissible) -----------
V_PER = ["per", "according to", "as recorded by"]
V_ASK = ["Which did you mean?", "Which reading do you want?", "Say which one."]
V_MISS = ["could not apply", "did not use", "found no way to apply"]
V_NEXT = ["Next step:", "To resolve this:", "What would settle it:"]
V_CORRECT = ["Correct me if wrong.", "Say so if that is wrong.", "Tell me if not."]
V_RATHER = ["rather than", "over", "and not"]
V_ASKED = ["You asked", "Earlier you asked", "Looking back, you asked"]
V_NOT = ["not", "rather than", "and not"]
V_NOTED = ["Noted", "Understood", "Acknowledged"]
V_YES = ["Yes:", "Correct:", "Right:"]
V_NO = ["No:", "Not quite:", "Actually:"]
V_COULD = ["It could be", "Two readings survive:", "Either"]
V_NOTHING = ["I found nothing for that.", "Nothing I hold answers that.", "No world of mine reads that."]
V_DICT = ["The dictionary says", "By the dictionary", "As defined"]


def _cap(s): return s[:1].upper() + s[1:] if s else s


def _low(s): return s[:1].lower() + s[1:] if s else s


def realize(frame, rng):
    k = frame["kind"]
    if k == ANSWER:
        vals = SEP.join(frame["values"]); sup = list(frame["supports"]); src = SEP.join(frame["sources"]); P = frame["phrase"]
        if rng.random() < 0.5: sup = sup[::-1]
        ev = f"; evidence: {SEP.join(sup)}" if sup else ""
        shape = rng.choice([1, 2] if " is " in P else [0, 1, 2])          # a phrase carrying "is" keeps to the two shapes that invert it
        if shape == 0: s = f"{_cap(P)} is {vals} ({rng.choice(V_PER)} {src}{ev})."
        elif shape == 1: s = f"As for {P}: {vals} ({rng.choice(V_PER)} {src}{ev})."
        else: s = f"{_cap(P)}: {vals} ({rng.choice(V_PER)} {src}{ev})."
    elif k == READ:
        opts = list(frame["options"])
        if rng.random() < 0.5: opts = opts[::-1]
        s = f"{rng.choice(V_COULD)} " + SEP.join(f"{v} [{ph}]" for v, ph in opts) + f". {rng.choice(V_ASK)} {frame['split']}"
    elif k == PART:
        sup = list(frame["supports"])
        if rng.random() < 0.5: sup = sup[::-1]
        ev = f" ({SEP.join(sup)})" if sup else ""
        s = f"{_cap(frame['phrase'])} is {SEP.join(frame['values'])}{ev}, but I {rng.choice(V_MISS)} {SEP.join(frame['missing'])}."
    elif k == FOUND:
        qs = list(frame["quotes"])                 # the dictionary's own sense order stands (first sense first, E-8)
        s = f"{rng.choice(V_DICT)} " + SEP.join(f"({src}): {t}" for t, src in qs)
    elif k == PROPOSE:
        s = f"{rng.choice(V_NOTHING)} I looked in {SEP.join(frame['consulted']) or 'no source'}. {rng.choice(V_NEXT)} {frame['action']}"
    elif k == CONJ:
        v, src, c, d = frame["choice"]; riv = list(frame["rivals"])
        if rng.random() < 0.5: riv = riv[::-1]
        s = (f"Probably {v} (per {src}; record {c} confirmed, {d} contradicted) {rng.choice(V_RATHER)} "
             + SEP.join(f"{v2} (per {s2}; record {c2} confirmed, {d2} contradicted)" for v2, s2, c2, d2 in riv) + f". {rng.choice(V_CORRECT)}")
    elif k == META_K:
        s = f'{rng.choice(V_ASKED)} "{frame["question"]}"; the {frame["field"]} was {frame["content"]}.'
    elif k == CHECK_K:
        src = list(frame["sources"])
        if rng.random() < 0.5: src = src[::-1]
        if frame["stated"] is None: s = f"{rng.choice(V_YES)} {frame['phrase']} is {frame['value']} ({rng.choice(V_PER)} {SEP.join(src)})."
        else: s = f"{rng.choice(V_NO)} {frame['phrase']} is {frame['value']} ({rng.choice(V_PER)} {SEP.join(src)}), {rng.choice(V_NOT)} {frame['stated']}."
    elif k == ACK_K:
        acts = list(frame["acts"])
        if rng.random() < 0.5: acts = acts[::-1]
        s = f"{rng.choice(V_NOTED)} ({SEP.join(f'{w}: {a}' for w, a in acts)}). I can answer about {SEP.join(frame['offers']) or 'nothing yet'}."
    else:
        raise ValueError(k)
    return s


def _alt(xs): return "(?:" + "|".join(re.escape(x) for x in xs) + ")"


PER = _alt(V_PER)
RX_A1 = re.compile(rf"^(.+?) is (.+?) \({PER} (.+?)(?:; evidence: (.*))?\)\.$")
RX_A2 = re.compile(rf"^As for (.+?): (.+?) \({PER} (.+?)(?:; evidence: (.*))?\)\.$")
RX_A3 = re.compile(rf"^(.+?): (.+?) \({PER} (.+?)(?:; evidence: (.*))?\)\.$")
RX_READ = re.compile(rf"^{_alt(V_COULD)} (.+?)\. {_alt(V_ASK)} (.*)$")
RX_PART = re.compile(rf"^(.+?) is (.+?)(?: \((.*?)\))?, but I {_alt(V_MISS)} (.*)\.$")
RX_FOUND = re.compile(rf"^{_alt(V_DICT)} (.*)$", re.S)
RX_QUOTE = re.compile(r"^\((.+?)\): (.*)$", re.S)
RX_PROPOSE = re.compile(rf"^{_alt(V_NOTHING)} I looked in (.+?)\. {_alt(V_NEXT)} (.*)$")
RX_REC = r"(.+?) \(per (.+?); record (\d+) confirmed, (\d+) contradicted\)"
RX_CONJ = re.compile(rf"^Probably {RX_REC} {_alt(V_RATHER)} (.+)\. {_alt(V_CORRECT)}$")
RX_META = re.compile(rf'^{_alt(V_ASKED)} "(.*)"; the (\w+) was (.*)\.$', re.S)
RX_CHECK_Y = re.compile(rf"^{_alt(V_YES)} (.+?) is (.+?) \({PER} (.+?)\)\.$")
RX_CHECK_N = re.compile(rf"^{_alt(V_NO)} (.+?) is (.+?) \({PER} (.+?)\), {_alt(V_NOT)} (.+)\.$")
RX_ACK = re.compile(rf"^{_alt(V_NOTED)} \((.+)\)\. I can answer about (.*)\.$")


def parse(text):
    """-> canonical frame dict (order-normalized) or None. Specific prefixes first; the plain ANSWER shapes last."""
    m = RX_META.match(text)
    if m: return dict(kind=META_K, question=m.group(1), field=m.group(2), content=m.group(3))
    m = RX_CHECK_Y.match(text)
    if m: return dict(kind=CHECK_K, phrase=_low(m.group(1)), value=m.group(2), stated=None, sources=sorted(m.group(3).split(SEP)))
    m = RX_CHECK_N.match(text)
    if m: return dict(kind=CHECK_K, phrase=_low(m.group(1)), value=m.group(2), stated=m.group(4), sources=sorted(m.group(3).split(SEP)))
    m = RX_ACK.match(text)
    if m:
        acts = []
        for a in m.group(1).split(SEP):
            if ": " not in a: return None
            w, lab = a.split(": ", 1); acts.append((w, lab))
        off = m.group(2); return dict(kind=ACK_K, acts=sorted(acts), offers=[] if off == "nothing yet" else off.split(SEP))
    m = RX_CONJ.match(text)
    if m:
        riv = []
        for r in m.group(5).split(SEP):
            mm = re.match("^" + RX_REC + "$", r)
            if not mm: return None
            riv.append((mm.group(1), mm.group(2), int(mm.group(3)), int(mm.group(4))))
        return dict(kind=CONJ, choice=(m.group(1), m.group(2), int(m.group(3)), int(m.group(4))), rivals=sorted(riv))
    m = RX_READ.match(text)
    if m:
        opts = []
        for o in m.group(1).split(SEP):
            mm = re.match(r"^(.*?) \[(.*)\]$", o, re.S)
            if not mm: return None
            opts.append((mm.group(1), mm.group(2)))
        return dict(kind=READ, options=sorted(opts), split=m.group(2))
    m = RX_FOUND.match(text)
    if m:
        qs = []
        for q in m.group(1).split(SEP):
            mm = RX_QUOTE.match(q)
            if not mm: return None
            qs.append((mm.group(2), mm.group(1)))
        return dict(kind=FOUND, quotes=sorted(qs))
    m = RX_PROPOSE.match(text)
    if m:
        c = m.group(1); return dict(kind=PROPOSE, consulted=[] if c == "no source" else c.split(SEP), action=m.group(2))
    m = RX_PART.match(text)
    if m:
        return dict(kind=PART, phrase=_low(m.group(1)), values=m.group(2).split(SEP), supports=sorted(m.group(3).split(SEP)) if m.group(3) else [], missing=m.group(4).split(SEP))
    m = RX_A2.match(text)
    if m: return _answer(m)
    m = RX_A1.match(text)
    if m: return _answer(m)
    m = RX_A3.match(text)
    if m: return _answer(m)
    return None


def _answer(m):
    ev = m.group(4)
    return dict(kind=ANSWER, phrase=_low(m.group(1)), values=m.group(2).split(SEP), sources=m.group(3).split(SEP),
                supports=sorted(ev.split(SEP)) if ev else [])


def canonical(frame):
    f = dict(frame)
    for k in ("supports", "sources"):
        if k in f: f[k] = sorted(f[k])
    if "options" in f: f["options"] = sorted(f["options"])
    if "quotes" in f: f["quotes"] = sorted(f["quotes"])
    if "rivals" in f: f["rivals"] = sorted(f["rivals"])
    if "acts" in f: f["acts"] = sorted(f["acts"])
    if "phrase" in f: f["phrase"] = _low(f["phrase"])                      # capitalization is form
    if f.get("kind") == ANSWER: f["sources"] = list(frame["sources"])          # ANSWER's sources are ordered in the surface
    return f


def brief(frame):
    """the same frame, shortened: no evidence trailer, one quote / consulted item / rival; options stay (a choice needs them all)."""
    f = dict(frame)
    if "supports" in f: f["supports"] = []
    for k in ("quotes", "consulted", "rivals"):
        if k in f and len(f[k]) > 1: f[k] = list(f[k])[:1]
    return f


def fields_of(frame, text):
    """what the chat layer said, as the transcript world's record fields (core/transcript.py reads these as data)."""
    k = frame["kind"]; f = {"question": text, "frame": frame, "brief": frame, "recallable": k not in (META_K, ACK_K)}
    if k == ANSWER: f.update(answer=SEP.join(frame["values"]), support=SEP.join(frame["supports"]) or frame["phrase"], source=SEP.join(frame["sources"]))
    elif k == READ: f.update(answer=SEP.join(v for v, _ in frame["options"]), support=SEP.join(s for _, s in frame["options"]),
                             source=SEP.join(s for _, s in frame["options"]))
    elif k == PART: f.update(answer=SEP.join(frame["values"]), support=SEP.join(frame["supports"]) or frame["phrase"])
    elif k == FOUND: f.update(answer=SEP.join(t for t, _ in frame["quotes"]), source=SEP.join(s for _, s in frame["quotes"]))
    elif k == PROPOSE: f.update(answer=frame["action"], source=SEP.join(frame["consulted"]))
    elif k == CONJ: f.update(answer=frame["choice"][0], source=frame["choice"][1], support=SEP.join(v for v, _, _, _ in frame["rivals"]))
    elif k == CHECK_K: f.update(answer=frame["value"], source=SEP.join(frame["sources"]), support=frame["phrase"])
    elif k == META_K: f.update(answer=frame["content"])
    return f


# ---- the understood structure, in the user's words (phase C) ------------------------------------------------------------
def phrase_of(w, st, syms):
    """-> the structure as a phrase: a text span as the user wrote it, a context reading by its label. World knowledge:
    none beyond the structure tuples each world builds. Unknown shapes fall back to the question text."""
    n = len(syms)

    def txt(r):
        if r[0] >= n or len(r) > 5: return str(r[4])
        return " ".join(syms[r[0]:r[1]])

    try:
        if isinstance(st, Composite):
            inner = phrase_of(st.inner[0], st.inner[1], syms)
            a, b, L = st.a, st.b, st.L
            def txt2(r):
                i, j = r[0], r[1]
                if len(r) > 5 or i >= n - (b - a) + L: return str(r[4])
                if i >= a and j <= a + L: return inner
                lo, hi = st.back(i, j); return " ".join(syms[lo:hi])
            return _phrase(st.outer[0], st.outer[1], txt2) or " ".join(syms)
        return _phrase(w, st, txt) or " ".join(syms)
    except Exception:
        return " ".join(syms)


def _phrase(w, st, txt):
    if isinstance(st, tuple) and st and st[0] in (K.LOOKUP, K.CHAIN, K.PATH, K.MEMBER) and len(st) == 3:        # graph
        kind, ents, props = st
        def of(p, e):             # a property whose own label already ends in "of" (capital of, part of) takes no second "of"
            return f"the {p} {e}" if p.endswith(" of") or p == "of" else f"the {p} of {e}"
        if kind == K.LOOKUP: return of(txt(props[0]), txt(ents[0]))
        if kind == K.CHAIN: return of(txt(props[1]), of(txt(props[0]), txt(ents[0])))
        if kind == K.MEMBER: return f"{txt(ents[0])} {txt(props[0])} {txt(ents[1])}"
        if kind == K.PATH: return f"{txt(ents[0])} and {txt(ents[1])}"
    if isinstance(st, tuple) and len(st) == 10 and isinstance(st[0], int):                                    # table
        op, col, filters, target, filters_b, fs, owords, hops, table, tsp = st
        opw = " ".join(txt(o) for o in owords)
        colr = [r for r in fs if r[2] == "C"]; colw = txt(colr[0]) if colr else (col or "")
        filt = [txt(r) for r in fs if r[2] == "F"]; fstr = " and ".join(filt)
        hopstr = "".join(f"the {txt(h)} of " for h in hops)
        tablew = txt(tsp[0]) if tsp else str(table)
        if tablew.isdigit(): tablew = opw or "rows"            # an unnamed table: the user's own counting word names its rows
        if op == T.LOOKUP: return f"the {colw} of {hopstr}{fstr}" if (hopstr or fstr) else f"the {colw}"
        if op == T.COUNT:
            base = f"{hopstr}{fstr}"
            return f"the number of {tablew} of {base}" if base else f"the number of {tablew}"
        if op in (T.ARGMAX, T.ARGMIN): return f"the {target} with the {opw} {colw}" + (f" of {fstr}" if fstr else "")
        if op == T.DIFF: return f"the {opw} in {colw} between {txt(fs[0])} and {txt(fs[1])}"
        return f"the {opw} {colw}" + (f" of {hopstr}{fstr}" if (hopstr or fstr) else "")
    if isinstance(st, tuple) and len(st) == 1 and isinstance(st[0], tuple):                                   # exec tree
        def render(node, top=True):
            if not isinstance(node[0], tuple): return txt(node)
            op, kids = node[0], node[1:]
            parts = [render(k, False) for k in kids]
            parts = [f"({p})" if (isinstance(kd[0], tuple) and len(kd) == 3) else p for p, kd in zip(parts, kids)]
            if len(parts) == 2: return f"{parts[0]} {txt(op)} {parts[1]}"
            return f"the {txt(op)} of {parts[0]}"
        return render(st[0])
    return None


# ---- core result -> one frame (the chat layer's decision, deterministic) ------------------------------------------------
def sup_str(sup, lab=str):
    if isinstance(sup, list) and sup and isinstance(sup[0], tuple) and len(sup[0]) == 3 and all(isinstance(x, str) and x[:1] in "QP" for x in sup[0]):
        return " -> ".join(f"{lab(s)} -{lab(p)}-> {lab(o)}" for s, p, o in sup)
    if isinstance(sup, list) and sup and isinstance(sup[0], tuple) and len(sup[0]) == 3:
        return ", ".join(f"row {r} {h}={v}" for r, h, v in sup[:6]) + (f", +{len(sup)-6} cells" if len(sup) > 6 else "")
    if isinstance(sup, list) and sup and isinstance(sup[0], tuple) and len(sup[0]) == 2:
        if isinstance(sup[0][1], list): return f"computed over {', '.join(sup[0][1])}"             # exec: the operator words applied
        return ", ".join(f"{a} in {b}" for a, b in sup)
    if isinstance(sup, list) and len(sup) == 2 and all(isinstance(x, list) for x in sup):          # a pipe: both halves
        return sup_str(sup[0], lab) + " => " + sup_str(sup[1], lab)
    return str(sup)


def _labeller(w, default):
    return w.label if (w is not None and hasattr(w, "label")) else default


def to_frame(fr, world=None, kind_hint=None):
    """core.reason result -> frame dict. `world`/`kind_hint` are the single-world callers' (f4_dialogue); the
    multi-world loop carries its worlds in fr["answer_worlds"] and its provenance names in fr["sources"]."""
    k = fr["kind"]
    worlds = fr.get("answer_worlds") or ([world] * len(fr["answers"]) if world is not None else [])
    lab = (world.label if world is not None and hasattr(world, "label") else str)
    syms = fr.get("syms", [])
    quotes = kind_hint == "gloss" or any(getattr(w, "quotes", False) for w in worlds)
    # ---- phase B acts by affordance (chat_acts_prereg.md), decided before the content frames
    if k in (ATTRIBUTED, COMMIT) and worlds and getattr(worlds[0], "transcript", False) and len(fr["answers"]) == 1:
        v = fr["answers"][0][0]; field, _, qtext = v; content = worlds[0].content(v)
        if field == "frame": return dict(content)
        if field == "brief": return brief(content)
        return dict(kind=META_K, question=str(qtext), field=str(field), content=str(content))
    ack = _ack(fr)
    if ack is not None: return ack
    chk = _check(fr)
    if chk is not None: return chk
    if k in (ATTRIBUTED, COMMIT):
        if quotes:
            def src_of(sups):
                try: return str(sups[0][0][1])
                except (IndexError, TypeError): return "source"
            return dict(kind=FOUND, quotes=[(str(v), src_of(sups)) for v, l, sups, certs, st in fr["answers"]])
        sources = fr.get("sources") or ([getattr(world, "name", "source")] if world is not None else ["source"])
        if kind_hint == "kg": sources = ["Wikidata"]          # f4_dialogue's provenance labels, unchanged
        elif kind_hint == "table": sources = ["the table"]
        w0 = worlds[0] if worlds else world
        return dict(kind=ANSWER, phrase=phrase_of(w0, fr["answers"][0][4], syms), values=[str(l) for _, l, _, _, _ in fr["answers"]],
                    supports=[sup_str(s, _labeller(ww, lab)) for (_, _, sups, _, _), ww in zip(fr["answers"], worlds or [world] * len(fr["answers"])) for s in sups[:1]],
                    sources=list(sources))
    if k == CONJECTURED:
        ct = fr["contest"]; choice = (str(ct[0][0]), "+".join(ct[0][1]), ct[0][2], ct[0][3])
        return dict(kind=CONJ, choice=choice, rivals=[(str(v), "+".join(src), c, d) for v, src, c, d in ct[1:]])
    if k == READINGS:
        recs = {str(v): f" [{'+'.join(src)}: {c} confirmed, {d} contradicted]" for v, src, c, d in fr.get("contest", [])}
        opts = [(str(l), phrase_of(ww, st, syms) + recs.get(str(l), "")) for (_, l, sups, _, st), ww in zip(fr["answers"], worlds or [world] * len(fr["answers"]))]
        return dict(kind=READ, options=opts, split="one of: " + " / ".join(o[0] for o in opts))
    if k == PARTIAL and quotes:          # the dictionary alone spoke, and a symbol stayed unresolved: research, not an answer
        consulted = [f"readings {', '.join(str(l) for _, l, _, _, _ in fr['answers'])[:120]}"] + sources_of(fr)
        return dict(kind=PROPOSE, consulted=consulted, action="name the thing you mean, or give a source that has it: " + ", ".join(str(m) for m in fr["missing"]))
    if k == PARTIAL:
        w0 = worlds[0] if worlds else world
        return dict(kind=PART, phrase=phrase_of(w0, fr["answers"][0][4], syms), values=[str(l) for _, l, _, _, _ in fr["answers"]],
                    supports=[sup_str(s, _labeller(ww, lab)) for (_, _, sups, _, _), ww in zip(fr["answers"], worlds or [world] * len(fr["answers"])) for s in sups[:1]],
                    missing=[str(m) for m in fr["missing"]])
    if k == WEAK:
        v, l, w = fr["weak"]
        return dict(kind=PROPOSE, consulted=[f"weak connection {sup_str(w, lab)}"], action="confirm that a 2-step connection counts as the relation you meant")
    ents = sorted({r[4] for r in fr["readings"] if r[2] in ("E", "C", "F", "G", "N")})[:5]; props = sorted({r[4] for r in fr["readings"] if r[2] in ("P", "O")})[:5]
    consulted = [f"readings {', '.join(ents) or 'none'}"] + ([f"relations {', '.join(props)}"] if props else [])
    consulted += sources_of(fr)
    action = "name the thing you mean, or give a source that has it" if not ents else "check the name, or supply a table or source holding it"
    return dict(kind=PROPOSE, consulted=consulted, action=action)


def _ack(fr):
    """a conversational move: no non-quoting world read any symbol of the text, and WordNet classifies at least one
    symbol as a move (chat_acts_prereg.md). The offer is what the worlds consulted: their sources, by name."""
    rw = fr.get("reading_worlds")
    if rw is None: return None
    n = len(fr["syms"])
    if any(r[0] < n and not getattr(w, "quotes", False) for w, r in zip(rw, fr["readings"])): return None
    acts = []
    for s in dict.fromkeys(fr["syms"]):
        if len(s) < 2: continue                   # WordNet files single letters under communication; a letter is not a move
        a = speech_act(s)
        if a: acts.append((s, a[0]))
    if not acts: return None
    return dict(kind=ACK_K, acts=acts, offers=[c[len("source "):] for c in sources_of(fr)])


def _check(fr):
    """the text names, unused, a value of the kind the answer world reads its own answer as: a yes/no question or an
    assertion. The world's value is reported against it; equal label = match. No ledger write (chat_acts_prereg.md)."""
    # a unique answer, or a PARTIAL whose only unused content reading is the stated value itself (a table reads a
    # stated city as a filter value: "is the city of research berlin")
    if fr["kind"] not in (ATTRIBUTED, COMMIT, PARTIAL) or len(fr["answers"]) != 1 or not fr.get("answer_worlds"): return None
    w = fr["answer_worlds"][0]
    if getattr(w, "quotes", False) or getattr(w, "transcript", False): return None
    v, lab, sups, certs, st = fr["answers"][0]; n = len(fr["syms"])
    if isinstance(st, Composite): return None
    if isinstance(st, tuple) and st and st[0] in (K.PATH, K.MEMBER): return None     # their value IS one of the text's entities: nothing is stated against it
    used = [(i, j) for i, j in _spans(w, st) if i < n]
    ls = symbols(str(lab), "LN")
    if not ls: return None
    vk = {r[2] for r in w.readings(ls) if r[0] == 0 and r[1] == len(ls)}
    if not vk: return None
    df = fr.get("df")
    def rarity(s): return min((df(t) if df(t) > 0 else -1) for t in (symbols(s, "LN") or [s]))
    stated = {}
    for ww, r in zip(fr.get("reading_worlds") or [], fr["readings"]):
        if ww is not w or r[0] >= n or len(r) > 5 or r[2] not in vk: continue
        if any(a < r[1] and r[0] < b for a, b in used): continue
        # a stated value is at least as specific as the answer's own label (the offline graph reads common words as
        # entities: a question word is not a stated capital)
        if df is not None and rarity(" ".join(fr["syms"][r[0]:r[1]])) > rarity(str(lab)): continue
        stated[str(r[4]).lower()] = True
    if len(stated) != 1: return None
    s = next(iter(stated))
    if fr["kind"] == PARTIAL and {str(m).lower() for m in fr["missing"]} - {s}: return None     # something else was left unread
    return dict(kind=CHECK_K, phrase=phrase_of(w, st, fr["syms"]), value=str(lab), stated=None if s == str(lab).lower() else s,
                sources=list(fr.get("sources") or [getattr(w, "name", "source")]))


def sources_of(fr):
    """the sources every world consulted, by name, for PROPOSE (general_prereg.md W5)."""
    names = []
    for c in fr.get("consulted", []):
        nm = None
        if isinstance(c, tuple) and c and isinstance(c[0], str):
            if c[0] in ("item", "property"): nm = "Wikidata"
            elif len(c) == 2 and isinstance(c[1], str): nm = None                 # a per-symbol lookup log entry
            else: nm = str(c[0]) + ("" if len(c) < 2 or not isinstance(c[1], tuple) else " " + "/".join(map(str, c[1])))
        if nm and nm not in names: names.append(nm)
    return [f"source {n}" for n in names]
