"""TRANSCRIPT -- the conversation as a WORLD (chat_acts_prereg.md; CHAT_PLAN.md phase B). Zero LLM; holds no word of
any language: the words that name a record's fields are DATA handed in by the chat layer (frames.py's own realization
vocabulary), the way worlds/orgchart.json is data.

A session's turns are records {text, syms, frame kind, and the fields the chat layer extracted from the realized frame:
answer, support, source, question, frame}. A symbol that names a field is a reading of kind "M"; the structure RECALL
(field) evaluates to that field's content on the most recent turn that is not retracted and holds the field. The value
is exact (attributed=False): it is the record of what was said. A recall word the answer did not use is not PARTIAL
(content kinds empty): "the source of the nile" is a Wikidata question, and coverage decides it.

Measured on the way (phase A, run 1): nothing here existed and "why" was answered with the dictionary's definition of
the word why."""


class TranscriptWorld:
    content_kinds = set()
    attributed = False
    transcript = True

    def __init__(self, fields, name=None):
        self.fields = dict(fields)          # word -> field name (data)
        self.name = name or "transcript"
        self.session = None                 # set by core.session.Session: the history and the chat layer's memory
        self.log = []

    # ---- the records: aligned with the session's history ---------------------------------------------------------
    def turns(self):
        S = self.session
        if S is None: return []
        out = []
        for k, (text, fr) in enumerate(S.history):
            mem = S.memory[k] if k < len(S.memory) else {}
            out.append(dict(index=k, text=text, kind=fr.get("kind"), retracted=bool(fr.get("retracted")), **mem))
        return out

    # ---- the World interface --------------------------------------------------------------------------------------
    def readings(self, syms):
        self.log.append((self.name, " ".join(syms)))
        return [(i, i + 1, "M", self.fields[s], s) for i, s in enumerate(syms) if s in self.fields]

    def structures(self, rd): return [("RECALL", r) for r in rd if r[2] == "M"]

    def spans_of(self, st): return [(st[1][0], st[1][1])]

    def key(self, st): return ("RECALL", st[1][3])

    def shape(self, st): return ("RECALL", st[1][3])

    def evaluate(self, st):
        """-> value (field, turn index, question text): a hashable handle; `content(value)` returns the field itself."""
        field = st[1][3]
        for t in reversed(self.turns()):
            if t["retracted"] or not t.get(field) or t.get("recallable") is False: continue      # a recall of a recall is not a turn to recall
            return (field, t["index"], t["text"]), [(t["index"], field)], {(self.name, t["text"])}
        return None

    def content(self, v):
        field, k, text = v
        mem = self.session.memory[k] if self.session is not None and k < len(self.session.memory) else {}
        return mem.get(field)

    def label(self, v):
        c = self.content(v)
        return str(c if not isinstance(c, dict) else c.get("kind", ""))

    def consulted(self): return [(self.name, len(self.turns()))] + list(self.log)
