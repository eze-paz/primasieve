"""GLOSS -- the dictionary WORLD for core.reason: E-10's DESCRIBE affordance as a world (f4_prereg.md U4).
core/resolve.py is not modified; this adapter reuses its segmentation and reading kinds. A symbol with a gloss
reading affords DESCRIBE; the certificate is the gloss verbatim with its source id (core.verdict.attribute).
Specificity (the loop's third rank key) is the source's own definition count, E-10's declared bias: reason() is
called with df = sources.df, so the rarest-defined symbol wins and a tie becomes READINGS (= E-10's ASK)."""
from .resolve import GLOSS
from .verdict import attribute, ATTRIBUTED


class GlossWorld:
    content_kinds = set()
    attributed = True

    def __init__(self, sources):
        self.sources = sources; self.log = []

    def readings(self, syms):
        out = []
        for i, s in enumerate(syms):
            r = self.sources.readings(s); self.log.append(("gloss", s))
            for gloss, sid, cert in r.get(GLOSS, []): out.append((i, i + 1, "G", (s, gloss, sid, cert), s))
        return out

    def structures(self, rd): return [("DESCRIBE", r) for r in rd if r[2] == "G"]

    def spans_of(self, st): return [(st[1][0], st[1][1])]

    def key(self, st): return ("DESCRIBE", st[1][3][0])

    def evaluate(self, st):
        s, gloss, sid, cert = st[1][3]
        claim, state, prov = attribute(gloss, sid, cert, gloss, lambda x: x)
        if state != ATTRIBUTED: return None
        return gloss, [(s, sid)], {(sid, gloss)}

    def label(self, v): return str(v)

    def consulted(self): return list(self.log)
