"""FRAMES -- the chat layer's realization of the five epistemic frames, and its inverse (f4_prereg.md Part 2).
English lives HERE, not in core/. The RNG ranges only over meaning-preserving surface choices (connectives, the
order of support items, the provenance phrase); parse() inverts realize() exactly, so a realized reply carries its
frame and nothing else. No probability is emitted.

Frame shapes (dicts):
  ANSWER    {kind, values: [str], supports: [str], sources: [str]}
  READINGS  {kind, options: [(value, support)], split: str}
  PARTIAL   {kind, values: [str], supports: [str], missing: [str]}
  FOUND     {kind, quotes: [(text, source)]}
  PROPOSE   {kind, consulted: [str], action: str}"""
import os
import re
import sys

from core.reason import READINGS, PARTIAL, WEAK, NOT_FOUND, Composite, symbols, _spans
from core.verdict import ATTRIBUTED, COMMIT, CONJECTURED

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

# meaning-preserving variants (the RNG's whole range)
V_PER = ["per", "according to", "as recorded by"]
V_SUPPORT = ["support:", "evidence:", "derived from:"]
V_ASK = ["Which did you mean?", "Which reading do you want?", "Say which one."]
V_MISS = ["could not apply", "did not use", "found no way to apply"]
V_NEXT = ["Next step:", "To resolve this:", "What would settle it:"]
V_CORRECT = ["Correct me if wrong.", "Say so if that is wrong.", "Tell me if not."]
V_RATHER = ["rather than", "over", "and not"]
V_BACK = ["Looking back at", "Earlier, for", "On your question"]
V_MATCH = ["which matches what you said", "as you said", "as stated"]
V_NOT = ["not", "rather than", "and not"]
V_NOTED = ["Noted", "Understood", "Acknowledged"]


def realize(frame, rng):
    k = frame["kind"]
    if k == ANSWER:
        vals = frame["values"]; sup = list(frame["supports"]); src = frame["sources"]
        if rng.random() < 0.5: sup = sup[::-1]
        s = f"Answer: {SEP.join(vals)} ({rng.choice(V_PER)} {SEP.join(src)}). {rng.choice(V_SUPPORT)} {SEP.join(sup)}"
    elif k == READ:
        opts = list(frame["options"])
        if rng.random() < 0.5: opts = opts[::-1]
        s = "Several readings survive: " + SEP.join(f"{v} [via {sp}]" for v, sp in opts) + f". {rng.choice(V_ASK)} {frame['split']}"
    elif k == PART:
        sup = list(frame["supports"])
        if rng.random() < 0.5: sup = sup[::-1]
        s = f"Partial: resolved {SEP.join(frame['values'])} ({rng.choice(V_SUPPORT)} {SEP.join(sup)}) but {rng.choice(V_MISS)} {SEP.join(frame['missing'])}"
    elif k == FOUND:
        qs = list(frame["quotes"])
        if rng.random() < 0.5: qs = qs[::-1]
        s = "Found: " + SEP.join(f'"{t}" ({rng.choice(V_PER)} {src})' for t, src in qs)
    elif k == PROPOSE:
        s = f"Nothing found. Consulted: {SEP.join(frame['consulted']) or 'no source'}. {rng.choice(V_NEXT)} {frame['action']}"
    elif k == CONJ:
        v, src, c, d = frame["choice"]; riv = list(frame["rivals"])
        if rng.random() < 0.5: riv = riv[::-1]
        s = (f"Probably {v} (per {src}; record {c} confirmed, {d} contradicted) {rng.choice(V_RATHER)} "
             + SEP.join(f"{v2} (per {s2}; record {c2} confirmed, {d2} contradicted)" for v2, s2, c2, d2 in riv) + f". {rng.choice(V_CORRECT)}")
    elif k == META_K:
        s = f'{rng.choice(V_BACK)} "{frame["question"]}": the {frame["field"]} was {frame["content"]}.'
    elif k == CHECK_K:
        src = list(frame["sources"])
        if rng.random() < 0.5: src = src[::-1]
        tail = rng.choice(V_MATCH) if frame["stated"] is None else f"{rng.choice(V_NOT)} {frame['stated']}"
        s = f"Checked: {frame['value']} ({rng.choice(V_PER)} {SEP.join(src)}), {tail}."
    elif k == ACK_K:
        acts = list(frame["acts"])
        if rng.random() < 0.5: acts = acts[::-1]
        s = f"{rng.choice(V_NOTED)} ({SEP.join(f'{w}: {a}' for w, a in acts)}). I can answer about: {SEP.join(frame['offers']) or 'nothing yet'}."
    else:
        raise ValueError(k)
    return s


def _alt(xs): return "(?:" + "|".join(re.escape(x) for x in xs) + ")"


RX_ANSWER = re.compile(rf"^Answer: (.+?) \({_alt(V_PER)} (.+?)\)\. {_alt(V_SUPPORT)} (.*)$")
RX_READ = re.compile(rf"^Several readings survive: (.+?)\. {_alt(V_ASK)} (.*)$")
RX_PART = re.compile(rf"^Partial: resolved (.+?) \({_alt(V_SUPPORT)} (.*?)\) but {_alt(V_MISS)} (.*)$")
RX_FOUND = re.compile(rf"^Found: (.*)$")
RX_PROPOSE = re.compile(rf"^Nothing found\. Consulted: (.+?)\. {_alt(V_NEXT)} (.*)$")
RX_QUOTE = re.compile(rf'^"(.*)" \({_alt(V_PER)} (.+)\)$')
RX_REC = r"(.+?) \(per (.+?); record (\d+) confirmed, (\d+) contradicted\)"
RX_CONJ = re.compile(rf"^Probably {RX_REC} {_alt(V_RATHER)} (.+)\. {_alt(V_CORRECT)}$")
RX_META = re.compile(rf'^{_alt(V_BACK)} "(.*)": the (\w+) was (.*)\.$', re.S)
RX_CHECK_M = re.compile(rf"^Checked: (.+?) \({_alt(V_PER)} (.+?)\), {_alt(V_MATCH)}\.$")
RX_CHECK_N = re.compile(rf"^Checked: (.+?) \({_alt(V_PER)} (.+?)\), {_alt(V_NOT)} (.+)\.$")
RX_ACK = re.compile(rf"^{_alt(V_NOTED)} \((.+)\)\. I can answer about: (.*)\.$")


def parse(text):
    """-> canonical frame dict (order-normalized) or None."""
    m = RX_ANSWER.match(text)
    if m:
        return dict(kind=ANSWER, values=m.group(1).split(SEP), sources=m.group(2).split(SEP), supports=sorted(m.group(3).split(SEP)))
    m = RX_READ.match(text)
    if m:
        opts = []
        for o in m.group(1).split(SEP):
            mm = re.match(r"^(.*) \[via (.*)\]$", o)
            if not mm: return None
            opts.append((mm.group(1), mm.group(2)))
        return dict(kind=READ, options=sorted(opts), split=m.group(2))
    m = RX_PART.match(text)
    if m:
        return dict(kind=PART, values=m.group(1).split(SEP), supports=sorted(m.group(2).split(SEP)), missing=m.group(3).split(SEP))
    m = RX_FOUND.match(text)
    if m:
        qs = []
        for q in m.group(1).split(SEP):
            mm = RX_QUOTE.match(q)
            if not mm: return None
            qs.append((mm.group(1), mm.group(2)))
        return dict(kind=FOUND, quotes=sorted(qs))
    m = RX_PROPOSE.match(text)
    if m:
        c = m.group(1); return dict(kind=PROPOSE, consulted=[] if c == "no source" else c.split(SEP), action=m.group(2))
    m = RX_CONJ.match(text)
    if m:
        riv = []
        for r in m.group(5).split(SEP):
            mm = re.match("^" + RX_REC + "$", r)
            if not mm: return None
            riv.append((mm.group(1), mm.group(2), int(mm.group(3)), int(mm.group(4))))
        return dict(kind=CONJ, choice=(m.group(1), m.group(2), int(m.group(3)), int(m.group(4))), rivals=sorted(riv))
    m = RX_META.match(text)
    if m: return dict(kind=META_K, question=m.group(1), field=m.group(2), content=m.group(3))
    m = RX_CHECK_M.match(text)
    if m: return dict(kind=CHECK_K, value=m.group(1), stated=None, sources=sorted(m.group(2).split(SEP)))
    m = RX_CHECK_N.match(text)
    if m: return dict(kind=CHECK_K, value=m.group(1), stated=m.group(3), sources=sorted(m.group(2).split(SEP)))
    m = RX_ACK.match(text)
    if m:
        acts = []
        for a in m.group(1).split(SEP):
            if ": " not in a: return None
            w, lab = a.split(": ", 1); acts.append((w, lab))
        off = m.group(2); return dict(kind=ACK_K, acts=sorted(acts), offers=[] if off == "nothing yet" else off.split(SEP))
    return None


def canonical(frame):
    f = dict(frame)
    for k in ("supports", "sources"):
        if k in f: f[k] = sorted(f[k])
    if "options" in f: f["options"] = sorted(f["options"])
    if "quotes" in f: f["quotes"] = sorted(f["quotes"])
    if "rivals" in f: f["rivals"] = sorted(f["rivals"])
    if "acts" in f: f["acts"] = sorted(f["acts"])
    if f.get("kind") == ANSWER: f["sources"] = list(frame["sources"])          # ANSWER's sources are ordered in the surface
    return f


def brief(frame):
    """the same frame, shortened: one support / quote / consulted item / rival; options stay (a choice needs them all)."""
    f = dict(frame)
    for k in ("supports", "quotes", "consulted", "rivals"):
        if k in f and len(f[k]) > 1: f[k] = list(f[k])[:1]
    return f


def fields_of(frame, text):
    """what the chat layer said, as the transcript world's record fields (core/transcript.py reads these as data)."""
    k = frame["kind"]; f = {"question": text, "frame": frame, "brief": frame, "recallable": k not in (META_K, ACK_K)}
    if k == ANSWER: f.update(answer=SEP.join(frame["values"]), support=SEP.join(frame["supports"]), source=SEP.join(frame["sources"]))
    elif k == READ: f.update(answer=SEP.join(v for v, _ in frame["options"]), support=SEP.join(s for _, s in frame["options"]),
                             source=SEP.join(s for _, s in frame["options"]))
    elif k == PART: f.update(answer=SEP.join(frame["values"]), support=SEP.join(frame["supports"]))
    elif k == FOUND: f.update(answer=SEP.join(t for t, _ in frame["quotes"]), source=SEP.join(s for _, s in frame["quotes"]))
    elif k == PROPOSE: f.update(answer=frame["action"], source=SEP.join(frame["consulted"]))
    elif k == CONJ: f.update(answer=frame["choice"][0], source=frame["choice"][1], support=SEP.join(v for v, _, _, _ in frame["rivals"]))
    elif k == CHECK_K: f.update(answer=frame["value"], source=SEP.join(frame["sources"]))
    elif k == META_K: f.update(answer=frame["content"])
    return f


# ---- core result -> one of the five frames (the chat layer's decision, deterministic) ------------------------------
def sup_str(sup, lab=str):
    if isinstance(sup, list) and sup and isinstance(sup[0], tuple) and len(sup[0]) == 3 and all(isinstance(x, str) and x[:1] in "QP" for x in sup[0]):
        return " -> ".join(f"{lab(s)} -{lab(p)}-> {lab(o)}" for s, p, o in sup)
    if isinstance(sup, list) and sup and isinstance(sup[0], tuple) and len(sup[0]) == 3:
        return ", ".join(f"row {r} {h}={v}" for r, h, v in sup[:6]) + (f", +{len(sup)-6} cells" if len(sup) > 6 else "")
    if isinstance(sup, list) and sup and isinstance(sup[0], tuple) and len(sup[0]) == 2:
        if isinstance(sup[0][1], list): return f"{sup[0][0]} over {', '.join(sup[0][1])}"        # exec: expression over words
        return ", ".join(f"{a} in {b}" for a, b in sup)
    if isinstance(sup, list) and len(sup) == 2 and all(isinstance(x, list) for x in sup):          # a pipe: both halves
        return sup_str(sup[0], lab) + " => " + sup_str(sup[1], lab)
    return str(sup)


def to_frame(fr, world=None, kind_hint=None):
    """core.reason result -> frame dict. `world`/`kind_hint` are the single-world callers' (f4_dialogue); the
    multi-world loop carries its worlds in fr["answer_worlds"] and its provenance names in fr["sources"]."""
    k = fr["kind"]
    worlds = fr.get("answer_worlds") or ([world] * len(fr["answers"]) if world is not None else [])
    lab = (world.label if world is not None and hasattr(world, "label") else str)
    quotes = kind_hint == "gloss" or any(getattr(w, "quotes", False) for w in worlds)
    # ---- phase B acts by affordance (chat_acts_prereg.md), decided before the five content frames
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
        return dict(kind=ANSWER, values=[str(l) for _, l, _, _, _ in fr["answers"]],
                    supports=[sup_str(s, lab) for _, _, sups, _, _ in fr["answers"] for s in sups[:1]], sources=list(sources))
    if k == CONJECTURED:
        ct = fr["contest"]; choice = (str(ct[0][0]), "+".join(ct[0][1]), ct[0][2], ct[0][3])
        return dict(kind=CONJ, choice=choice, rivals=[(str(v), "+".join(src), c, d) for v, src, c, d in ct[1:]])
    if k == READINGS:
        recs = {str(v): f" [{'+'.join(src)}: {c} confirmed, {d} contradicted]" for v, src, c, d in fr.get("contest", [])}
        opts = [(str(l), sup_str(sups[0], lab) + recs.get(str(l), "")) for _, l, sups, _, _ in fr["answers"]]
        return dict(kind=READ, options=opts, split="one of: " + " / ".join(o[0] for o in opts))
    if k == PARTIAL and quotes:          # the dictionary alone spoke, and a symbol stayed unresolved: research, not an answer
        consulted = [f"readings {', '.join(str(l) for _, l, _, _, _ in fr['answers'])[:120]}"] + sources_of(fr)
        return dict(kind=PROPOSE, consulted=consulted, action="name the thing you mean, or give a source that has it: " + ", ".join(str(m) for m in fr["missing"]))
    if k == PARTIAL:
        return dict(kind=PART, values=[str(l) for _, l, _, _, _ in fr["answers"]],
                    supports=[sup_str(s, lab) for _, _, sups, _, _ in fr["answers"] for s in sups[:1]], missing=[str(m) for m in fr["missing"]])
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
    return dict(kind=CHECK_K, value=str(lab), stated=None if s == str(lab).lower() else s, sources=list(fr.get("sources") or [getattr(w, "name", "source")]))


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
