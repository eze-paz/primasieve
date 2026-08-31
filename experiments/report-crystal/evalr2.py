"""Eval v2 for the hybrid report (template numbers + crystal narrative).

Axes:
  structure  : 4 section headers present, in order                 [0..1]
  numbers    : JSON numbers present in report AND none spurious    [0..1]
               (1.0 by construction from the template renderer)
  alarms     : all alarms covered / correct "sense alarmes"        [0..1]
  narr_clean : narrative contains NO digit (qualitative contract)  [0..1]
               -> a stray figure in the crystal output is a hard fail
  catalan    : ca vs es/en stopword ratio on the narrative         [0..1]
  length     : narrative word count (reported, not scored)
"""
from __future__ import annotations
import re
import evalr   # reuse canon-number + catalan helpers
import render

SECTIONS = ["## Resum", "## Estat dels tancs", "## Alarmes",
            "## Observacions i recomanacions"]
_DIGIT = re.compile(r"\d")
_TANKID = re.compile(r"\bT\d+\b")


def legit_numbers(inp):
    """Numbers CODE is allowed to emit = everything in the template sections
    (JSON leaves + computed deltas + totals + durations + week). The template
    is trusted, so this set defines what is NOT a hallucination."""
    tmpl = "\n".join([render.render_header(inp), render.render_tanks(inp),
                      render.render_alarms(inp)])
    return evalr._nums_in_text(tmpl)


def score_structure(text):
    pos, hit = -1, 0
    for s in SECTIONS:
        p = text.find(s)
        if p > pos:
            hit += 1; pos = p
    return hit / len(SECTIONS)


def narr_body(narrative):
    # strip section headers, then tank IDs (T1/T2..) which are refs, not figures
    body = re.sub(r"##[^\n]*", "", narrative)
    return _TANKID.sub("", body)


def score_report(inp, full_report, narrative):
    st = score_structure(full_report)
    # coverage: every JSON leaf number appears in the report
    want = evalr._canon_nums(inp)
    have = evalr._nums_in_text(full_report)
    cov = len(want & have) / max(1, len(want))
    # spurious: any report number not producible by the trusted template
    spur = len(have - legit_numbers(inp))
    numbers = 1.0 if (cov == 1.0 and spur == 0) else min(cov, 1.0 - min(spur, 10) * 0.1)
    al = evalr.score_alarms(inp, full_report)
    body = narr_body(narrative)
    ca = evalr.score_catalan(body)
    clean = 0.0 if _DIGIT.search(body) else 1.0
    words = len(body.split())
    overall = (0.15 * st + 0.30 * numbers + 0.15 * al + 0.20 * clean +
               0.20 * ca)
    return {"structure": st, "numbers": numbers, "num_cov": cov, "spurious": spur,
            "alarms": al, "narr_clean": clean, "catalan": ca,
            "words": words, "overall": overall}
