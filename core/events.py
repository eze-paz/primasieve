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

    def verb_at(self, toks, k):
        """events6_prereg.md (A): a third-person present form is a verb only right after a subject-like symbol or a noun
        ("the miller owns" / "a pair of boots")"""
        lt = toks[k].lower()
        if lt not in self.verbs or lt in self.closed: return lt in self.verbs and lt not in self.closed
        if lt not in getattr(self, "third", ()) or lt in getattr(self, "past", ()): return True
        if k == 0: return False
        p = toks[k - 1].lower()
        return p in getattr(self, "subjects", ()) or (self.is_word(toks[k - 1]) and p not in self.closed and p not in self.verbs)

    def noun_at(self, toks, k):
        lt = toks[k].lower()
        return self.is_word(toks[k]) and lt not in self.closed and not self.verb_at(toks, k)

    def extend(self, toks, s, e):
        """events6_prereg.md (C): a noun run continued across the learned linker / coordinator ("a pair of boots and a
        bag", "Eva and her uncle Karl")"""
        joins = set(getattr(self, "linkers", ())) | set(getattr(self, "coords", ()))
        if not joins: return s, e
        while e < len(toks) and toks[e].lower() in joins:
            n = e + 1
            if n < len(toks) and toks[n].lower() in self.closed and toks[n].lower() not in joins: n += 1
            if n < len(toks) and self.noun_at(toks, n):
                while n + 1 < len(toks) and self.noun_at(toks, n + 1): n += 1
                e = n + 1
            else: break
        while True:
            q = s - 1
            if q >= 0 and toks[q].lower() in self.closed and toks[q].lower() not in joins: q -= 1
            if q >= 1 and toks[q].lower() in joins and self.noun_at(toks, q - 1):
                q -= 1
                while q - 1 >= 0 and self.noun_at(toks, q - 1): q -= 1
                s = q
            else: break
        return s, e

    def status(self, toks, k):
        """reality_prereg.md: IRREALIS when a learned marker stands in the verb group (up to 3 symbols before the verb, no
        noun among them), or the verb lies in the first clause of a sentence opened by the learned conditional opener"""
        marks = getattr(self, "to_marker", None) or ()
        i = k - 1
        while i >= 0 and k - i <= 3 and self.is_word(toks[i]) and not self.noun_at(toks, i):
            if toks[i].lower() in marks: return "irrealis"
            i -= 1
        words = [j for j, x in enumerate(toks) if self.is_word(x)]
        if words and toks[words[0]].lower() in getattr(self, "cond", ()) and "," not in toks[:k]: return "irrealis"
        return "realis"

    def run_at(self, toks, k, step, limit, pronoun=False):
        """the noun run nearest to position k in direction `step`, skipping at most `limit` closed symbols, inside the
        clause -> ((start, end), is_pronoun) or None. With `pronoun`, a closed symbol right beside k is returned as one."""
        i = k + step; skipped = 0; crossed = False
        while 0 <= i < len(toks):
            t = toks[i]
            if not self.is_word(t) and pronoun and not crossed and i == k + step:      # events3_prereg.md (1): one comma beside the verb
                crossed = True; i += step; continue
            if not self.is_word(t) or self.verb_at(toks, i): break
            if self.noun_at(toks, i):
                j = i
                while 0 <= j + step < len(toks) and self.noun_at(toks, j + step): j += step
                return self.extend(toks, min(i, j), max(i, j) + 1), False
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
            if lemma is not None and not self.verb_at(toks, k) and t.lower() not in self.closed: lemma = None    # events6 (A)
            inf = (lemma is None and k > 0 and toks[k - 1].lower() in (getattr(self, "to_marker", None) or ()) and t[:1].islower()
                   and t.lower() in self.base and t.lower() not in self.closed)          # events5_prereg.md (D): "to fix"
            if inf:
                ag0 = out[-1]["agent"] if out else self.last_agent
                # reality_prereg.md: a doer right before the marker ("his father will buy", "she will wash") is this
                # verb's own; otherwise the previous doer controls it ("Sana wanted to learn")
                if k >= 2 and toks[k - 2].lower() in getattr(self, "subjects", ()): ag0 = self.last_agent
                elif k >= 2 and self.noun_at(toks, k - 2):
                    r0 = self.run_at(toks, k - 1, -1 if self.side == "L" else 1, 0)
                    if r0: ag0 = " ".join(toks[r0[0][0]:r0[0][1]])
                pa = self.run_at(toks, k, 1 if self.side == "L" else -1, 2)
                patient = " ".join(toks[pa[0][0]:pa[0][1]]) if pa else None
                out.append(dict(verb=self.base[t.lower()], pos=k, agent=ag0, patient=patient, adjuncts=[], text=text, status=self.status(toks, k)))
                continue
            main = (lemma is not None and t.lower() in self.closed and k + 1 < len(toks)
                    and toks[k + 1].lower() not in self.participles and toks[k + 1].lower() not in self.verbs
                    and k > 0 and self.is_noun(toks[k - 1]))                          # events3_prereg.md (3): "the crow had the cheese"
            if lemma is not None and k > 0 and toks[k - 1].lower() in getattr(self, "determiners", ()) and k + 1 < len(toks) and self.is_noun(toks[k + 1]):
                continue                     # events5_prereg.md (F): "a lost puppy" -- after a symbol that never precedes a verb
            if (lemma is None or t.lower() in self.closed) and not main:
                # events2_prereg.md: a closed-class finite symbol before a participle -> one event, the participle's verb
                lp = self.participles.get(t.lower())
                if lp is None or t.lower() in self.closed or k == 0 or toks[k - 1].lower() not in getattr(self, "auxiliaries", ()):
                    continue
                lemma = lp
            a_step, p_step = (-1, 1) if self.side == "L" else (1, -1)
            ag = self.run_at(toks, k, a_step, 1, pronoun=True); pa = self.run_at(toks, k, p_step, 2)
            if 0 <= k + a_step < len(toks) and toks[k + a_step].lower() in getattr(self, "subjects", ()):     # events6 (B)
                ag = ((min(k, k + a_step), min(k, k + a_step) + 1), True)
            agent = None
            if ag:
                (s0, e0), pron = ag
                agent = self.last_agent if pron else " ".join(toks[s0:e0])
                # a run that was the previous verb's patient in this sentence is not this verb's doer: two verbs joined
                # in one clause share the first one's agent ("the fox ate the cheese and ran away")
                if out and not pron and agent == out[-1]["patient"]: agent = out[-1]["agent"]
                elif not pron: self.last_agent = agent
            if agent is None and out: agent = out[-1]["agent"]       # events5_prereg.md (C): coordinated verbs share the doer
            patient = " ".join(toks[pa[0][0]:pa[0][1]]) if pa else None
            if pa is None:                                                             # events3_prereg.md (2): "found them" -> the last patient
                nxt = k + 1
                if nxt < len(toks) and self.is_word(toks[nxt]) and toks[nxt].lower() in self.closed and toks[nxt].lower() not in getattr(self, "auxiliaries", ()):
                    patient = getattr(self, "last_patient", None)
            elif patient: self.last_patient = patient
            adj = []; i = (pa[0][1] if pa else k + 1)
            while i < len(toks) - 1 and self.is_word(toks[i]) and not self.is_verb(toks[i]):
                if toks[i].lower() in self.closed:
                    r = self.run_at(toks, i, 1, 1)
                    if r: adj.append(" ".join(toks[i:r[0][1]])); i = r[0][1]; continue
                i += 1
            out.append(dict(verb=lemma, pos=k, agent=agent, patient=patient, adjuncts=adj, text=text, status=self.status(toks, k)))
        return out


class EventMemory:
    """events read from a conversation's statements, and questions answered from them (events_prereg.md)"""
    def __init__(self, reader):
        self.reader = reader; self.events = []; reader.last_agent = None; reader.last_patient = None     # a new conversation starts with no referent

    def ingest(self, text):
        self.events += self.reader.read(text)

    def ask(self, text):
        """-> (answer text, event) or None. The question's first symbol must be closed-class (a question word); its verb
        lemma selects events; the role it leaves empty is the answer"""
        toks = tokens(text); words = [t for t in toks if self.reader.is_word(t)]
        if not words or (words[0].lower() not in self.reader.closed and not text.rstrip().endswith("?")): return None   # events5 (G): or a "?"-ended turn
        lemmas = [self.reader.verbs.get(t.lower()) or self.reader.base.get(t.lower()) or self.reader.participles.get(t.lower()) for t in words[1:]
                  if t.lower() not in self.reader.closed]
        lemmas = [l for l in lemmas if l]
        same = {x for l in lemmas for x in self.reader.same.get(l, ())}                 # events2_prereg.md: synonymous verbs, second
        content = {t.lower() for t in words[1:] if self.reader.is_noun(t)}
        # events5_prereg.md (E): a PASSIVE question -- a learned auxiliary, later a past participle -- names the patient
        lw = [t.lower() for t in words]
        aux_at = [i for i, t in enumerate(lw) if i > 0 and t in getattr(self.reader, "auxiliaries", ())]
        passive = bool(aux_at) and any(t in getattr(self.reader, "past_participles", ()) for t in lw[aux_at[0] + 1:])
        best = None
        irr_ok = any(t in (getattr(self.reader, "to_marker", None) or ()) for t in lw[1:])   # reality_prereg.md (B)
        for ev in reversed(self.events):
            if ev["verb"] not in lemmas and ev["verb"] not in same: continue
            if ev.get("status") == "irrealis" and not irr_ok: continue
            roles = {"agent": ev["agent"] or "", "patient": ev["patient"] or ""}
            filled = {r for r, v in roles.items() if v and set(v.lower().split()) & content}
            if passive and "agent" not in filled:
                if "patient" in filled and ev["adjuncts"]: ans = " ".join(ev["adjuncts"])
                elif "patient" not in filled and ev["patient"]: ans = ev["patient"]
                else: continue
            elif "agent" in filled and ev["patient"] and "patient" not in filled: ans = ev["patient"]
            elif "agent" in filled and "patient" in filled and ev["adjuncts"]: ans = " ".join(ev["adjuncts"])     # (E): every adjunct
            elif "agent" in filled and not ev["patient"] and ev["adjuncts"]: ans = " ".join(ev["adjuncts"])
            elif "agent" not in filled and ev["agent"] and (filled or not content
                                                            or any(set(a.lower().split()) & content for a in ev["adjuncts"])): ans = ev["agent"]   # events3_prereg.md (4); events5 (H): an adjunct shared
            else: continue                      # honesty_prereg.md: no role shared with the question -> no basis to answer
            score = len(filled) + (0.5 if ev["verb"] in lemmas else 0)
            if best is None or score > best[0]: best = (score, ans, ev)
        return (best[1], best[2]) if best else None
