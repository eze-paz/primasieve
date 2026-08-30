"""Machine-checkable eval for Catalan telemetry reports.

A report is scored on four axes, all programmatic (no human/judge):
  structure : required section headers present and in order        [0..1]
  numbers   : fraction of input-JSON numbers that appear verbatim  [0..1]
              (+ spurious-number count as a hallucination diagnostic)
  alarms    : each alarm's type+tank mentioned; or the explicit
              "sense alarmes" sentence when there are none         [0..1]
  catalan   : distinctive-stopword ratio ca vs es/en               [0..1]

Report spec (what the model is asked to produce):
  # Informe setmanal - <instalacio> (setmana <n>)
  ## Resum
  ## Estat dels tancs
  ## Alarmes
  ## Observacions i recomanacions
"""
from __future__ import annotations
import re

SECTIONS = ["## Resum", "## Estat dels tancs", "## Alarmes",
            "## Observacions i recomanacions"]

CA_MARKERS = ["els ", "amb ", "aquesta ", "dels ", "s'ha ", "setmana", "nivell",
              "pressio", "pressió", "tancs", "durant", "cap ", "sense ",
              "més ", "també", "fins ", "després", "correctament"]
ES_MARKERS = ["los ", "las ", "con ", "esta semana", "presión", "nivel ",
              "tanques", "durante", "ningún", "también", "hasta ", "después",
              "correctamente", "sin alarmas", "ha sido"]
EN_MARKERS = ["the ", "with ", "this week", "pressure", "level ", "tanks",
              "during", "no alarms", "was ", "were "]

_NUM = re.compile(r"\d+(?:[.,]\d+)?")

def _canon_nums(x):
    """All numeric leaf values of the input as canonical strings."""
    out = set()
    def walk(v):
        if isinstance(v, dict):
            for k, u in v.items():
                if k in ("setmana",):  # header number, checked via structure
                    continue
                walk(u)
        elif isinstance(v, list):
            for u in v: walk(u)
        elif isinstance(v, bool):
            pass
        elif isinstance(v, (int, float)):
            out.add(_fmt(v))
    walk(x)
    return out

def _fmt(v):
    v = abs(float(v))  # sign-insensitive: '-182.4' may render as '-182.4 C' or '182.4 C sota zero'
    if v == int(v):
        return str(int(v))
    return ("%g" % v)

def _nums_in_text(text):
    return set(_fmt(float(m.group(0).replace(",", "."))) for m in _NUM.finditer(text))

def score_structure(text):
    pos = -1
    hit = 0
    for s in SECTIONS:
        p = text.find(s)
        if p > pos:
            hit += 1; pos = p
    return hit / len(SECTIONS)

def score_numbers(inp, text):
    want = _canon_nums(inp)
    have = _nums_in_text(text)
    cov = len(want & have) / max(1, len(want))
    # spurious: numbers in text not in input and not small counts/weeks/durations
    whitelist = {_fmt(inp.get("setmana", -1))} | {_fmt(i) for i in range(0, 11)}
    whitelist |= {_fmt(a["durada_min"]) for a in inp.get("alarmes", [])}
    spurious = len(have - want - whitelist)
    return cov, spurious

def score_alarms(inp, text):
    low = text.lower()
    alarms = inp.get("alarmes", [])
    if not alarms:
        return 1.0 if ("sense alarmes" in low or "cap alarma" in low) else 0.0
    ok = 0
    for a in alarms:
        if a["tipus"] in low and a["tanc"].lower() in low:
            ok += 1
    return ok / len(alarms)

def score_catalan(text):
    low = " " + text.lower() + " "
    ca = sum(low.count(m) for m in CA_MARKERS)
    es = sum(low.count(m) for m in ES_MARKERS)
    en = sum(low.count(m) for m in EN_MARKERS)
    return ca / max(1, ca + es + en)

def score_report(inp, text):
    st = score_structure(text)
    cov, spur = score_numbers(inp, text)
    al = score_alarms(inp, text)
    ca = score_catalan(text)
    overall = 0.25 * st + 0.35 * cov + 0.2 * al + 0.2 * ca
    return {"structure": st, "num_cov": cov, "spurious": spur,
            "alarms": al, "catalan": ca, "overall": overall}
