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
