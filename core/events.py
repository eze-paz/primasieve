"""EVENTS -- who did what to whom (events_prereg.md, FLUENCY_LOOP_PLAN.md P1). Zero LLM; holds no word of any language.

Given DATA from outside -- the finite verb forms with their lemmas (a morphology table), the closed-class symbols (a
corpus count) and the side the doer stands on (learned from a corpus by counting) -- each finite verb in a sentence makes
an EVENT: its agent (the nearest noun run on the agent side, within the clause), its patient (on the other side), and its
adjuncts (a closed-class symbol followed by a noun run, after the patient). A closed-class symbol in the agent position
refers back to the most recent agent entity."""
import re

TOKEN = re.compile(r"[^\W_]+|[^\w\s]")


def tokens(text):
    return [t for t in TOKEN.findall(text)]


class EventReader:
    def __init__(self, verbs, closed, agent_side="L", entities=(), base=None, participles=None, same=None):
        self.verbs = dict(verbs); self.closed = set(closed); self.side = agent_side; self.entities = set(entities)
        self.base = dict(base or {})                 # non-finite verb forms -> lemma (a question's "did ... row")
        self.participles = dict(participles or {})   # events2_prereg.md: participle -> lemma ("was waiting", "had gone")
        self.same = same or {}                       # events2_prereg.md: the dictionary's statements of sameness
        self.last_agent = None

    def is_word(self, t): return t[:1].isalnum()

    def is_verb(self, t):
        lt = t.lower(); return lt in self.verbs and lt not in self.closed        # a closed-class symbol is never a content verb

    def is_noun(self, t):
        lt = t.lower()
        return self.is_word(t) and lt not in self.closed and lt not in self.verbs

    def run_at(self, toks, k, step, limit, pronoun=False):
        """the noun run nearest to position k in direction `step`, skipping at most `limit` closed symbols, inside the
        clause -> ((start, end), is_pronoun) or None. With `pronoun`, a closed symbol right beside k is returned as one."""
        i = k + step; skipped = 0
        while 0 <= i < len(toks):
            t = toks[i]
            if not self.is_word(t) or self.is_verb(t): break
            if self.is_noun(t):
                j = i
                while 0 <= j + step < len(toks) and self.is_noun(toks[j + step]): j += step
                return (min(i, j), max(i, j) + 1), False
            skipped += 1
            if skipped > limit: break
            i += step
        if pronoun and 0 <= k + step < len(toks) and self.is_word(toks[k + step]) and toks[k + step].lower() in self.closed:
            return (min(k, k + step) + (1 if step == 1 else 0), min(k, k + step) + (2 if step == 1 else 1)), True
        return None

    def read(self, text):
        toks = tokens(text); out = []
        for k, t in enumerate(toks):
            lemma = self.verbs.get(t.lower())
            if lemma is None or t.lower() in self.closed:
                # events2_prereg.md: a closed-class finite symbol before a participle -> one event, the participle's verb
                lp = self.participles.get(t.lower())
                if lp is None or t.lower() in self.closed or k == 0 or toks[k - 1].lower() not in getattr(self, "auxiliaries", ()):
                    continue
                lemma = lp
            a_step, p_step = (-1, 1) if self.side == "L" else (1, -1)
            ag = self.run_at(toks, k, a_step, 1, pronoun=True); pa = self.run_at(toks, k, p_step, 2)
            agent = None
            if ag:
                (s0, e0), pron = ag
                agent = self.last_agent if pron else " ".join(toks[s0:e0])
                # a run that was the previous verb's patient in this sentence is not this verb's doer: two verbs joined
                # in one clause share the first one's agent ("the fox ate the cheese and ran away")
                if out and not pron and agent == out[-1]["patient"]: agent = out[-1]["agent"]
                elif not pron: self.last_agent = agent
            patient = " ".join(toks[pa[0][0]:pa[0][1]]) if pa else None
            adj = []; i = (pa[0][1] if pa else k + 1)
            while i < len(toks) - 1 and self.is_word(toks[i]) and not self.is_verb(toks[i]):
                if toks[i].lower() in self.closed:
                    r = self.run_at(toks, i, 1, 1)
                    if r: adj.append(" ".join(toks[i:r[0][1]])); i = r[0][1]; continue
                i += 1
            out.append(dict(verb=lemma, pos=k, agent=agent, patient=patient, adjuncts=adj, text=text))
        return out


class EventMemory:
    """events read from a conversation's statements, and questions answered from them (events_prereg.md)"""
    def __init__(self, reader):
        self.reader = reader; self.events = []; reader.last_agent = None     # a new conversation starts with no referent

    def ingest(self, text):
        self.events += self.reader.read(text)

    def ask(self, text):
        """-> (answer text, event) or None. The question's first symbol must be closed-class (a question word); its verb
        lemma selects events; the role it leaves empty is the answer"""
        toks = tokens(text); words = [t for t in toks if self.reader.is_word(t)]
        if not words or words[0].lower() not in self.reader.closed: return None
        lemmas = [self.reader.verbs.get(t.lower()) or self.reader.base.get(t.lower()) or self.reader.participles.get(t.lower()) for t in words[1:]
                  if t.lower() not in self.reader.closed]
        lemmas = [l for l in lemmas if l]
        same = {x for l in lemmas for x in self.reader.same.get(l, ())}                 # events2_prereg.md: synonymous verbs, second
        content = {t.lower() for t in words[1:] if self.reader.is_noun(t)}
        best = None
        for ev in reversed(self.events):
            if ev["verb"] not in lemmas and ev["verb"] not in same: continue
            roles = {"agent": ev["agent"] or "", "patient": ev["patient"] or ""}
            filled = {r for r, v in roles.items() if v and set(v.lower().split()) & content}
            if "agent" in filled and ev["patient"] and "patient" not in filled: ans = ev["patient"]
            elif "agent" in filled and "patient" in filled and ev["adjuncts"]: ans = ev["adjuncts"][0]
            elif "agent" in filled and not ev["patient"] and ev["adjuncts"]: ans = ev["adjuncts"][0]
            elif "agent" not in filled and ev["agent"] and filled: ans = ev["agent"]
            else: continue                      # honesty_prereg.md: no role shared with the question -> no basis to answer
            score = len(filled) + (0.5 if ev["verb"] in lemmas else 0)
            if best is None or score > best[0]: best = (score, ans, ev)
        return (best[1], best[2]) if best else None
