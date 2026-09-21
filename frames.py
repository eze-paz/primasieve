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
import re

from core.reason import READINGS, PARTIAL, WEAK, NOT_FOUND, Composite
from core.verdict import ATTRIBUTED, COMMIT

ANSWER, READ, PART, FOUND, PROPOSE = "ANSWER", "READINGS", "PARTIAL", "FOUND", "PROPOSE"
SEP = " ; "

# meaning-preserving variants (the RNG's whole range)
V_PER = ["per", "according to", "as recorded by"]
V_SUPPORT = ["support:", "evidence:", "derived from:"]
V_ASK = ["Which did you mean?", "Which reading do you want?", "Say which one."]
V_MISS = ["could not apply", "did not use", "found no way to apply"]
V_NEXT = ["Next step:", "To resolve this:", "What would settle it:"]


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
    return None


def canonical(frame):
    f = dict(frame)
    for k in ("supports",):
        if k in f: f[k] = sorted(f[k])
    if "options" in f: f["options"] = sorted(f["options"])
    if "quotes" in f: f["quotes"] = sorted(f["quotes"])
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
    if k == READINGS:
        opts = [(str(l), sup_str(sups[0], lab)) for _, l, sups, _, _ in fr["answers"]]
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
