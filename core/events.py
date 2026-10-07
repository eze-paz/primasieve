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
        if (0 < k < len(toks) - 1 and toks[k - 1].lower() in getattr(self, "dets", ()) and self.is_word(toks[k + 1])
                and toks[k + 1].lower() not in self.closed and toks[k + 1].lower() not in self.verbs):
            return False                 # lostdet (A): "a lost puppy" -- a form between a determiner and a noun modifies it
        if lt not in getattr(self, "third", ()) or lt in getattr(self, "past", ()): return True
        if k == 0: return False
        if k + 1 < len(toks) and toks[k + 1].lower() in self.verbs and toks[k + 1].lower() not in getattr(self, "third", ()):
            return False                 # bookposs run 2: "classes is", "locks scattered" -- two finite verbs do not stand together
        p = toks[k - 1].lower()
        if p.isdigit() or p in getattr(self, "numwords", ()): return False   # phrases (B), booktm: "12 apples", "two oranges"
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
        marks = getattr(self, "to_marker", None) or (); negs = getattr(self, "negatives", ())
        i = k - 1
        while i >= 0 and k - i <= 3 and self.is_word(toks[i]) and not self.noun_at(toks, i):
            if toks[i].lower() in negs: return "negated"                     # negation_prereg.md (C)
            if toks[i].lower() in marks: return "irrealis"
            i -= 1
        # bookpronoun run 2: a negative right after the verb ("did not possess", "does not mention")
        for j in (k + 1, k + 2):
            if j < len(toks) and toks[j].lower() in negs and (j == k + 1 or toks[k + 1] in "'’"): return "negated"
        # bookquote2 run 2: a contraction piece that is a learned marker ("won't": won ' t) -- not told as happened; and a
        # learned negative later in the same clause ("feared him no more than ...")
        if k + 2 < len(toks) and toks[k + 1] in "'’" and toks[k + 2].lower() in marks: return "negated"
        if k + 2 < len(toks) and toks[k + 1] in "'’" and (toks[k] + "'" + toks[k + 2]).lower() in getattr(self, "neg_contractions", ()):
            return "negated"                                     # bookshapes run 2: the dictionary's negative contractions
        j = k + 1
        clause_negs = getattr(self, "clause_negatives", negs)   # negatives with a preposition sense ("without") open a phrase
        while j < len(toks) and j <= k + 4 and self.is_word(toks[j]):
            if toks[j].lower() in clause_negs: return "negated"
            j += 1
        words = [j for j, x in enumerate(toks) if self.is_word(x)]
        if words and toks[words[0]].lower() in getattr(self, "cond", ()) and "," not in toks[:k]: return "irrealis"
        j = k - 1                                    # bookhave run 2: the conditional opener earlier in the same clause
        while j >= 0 and self.is_word(toks[j]):
            if toks[j].lower() in getattr(self, "cond", ()): return "irrealis"
            j -= 1
        return "realis"

    def phrase(self, toks, s, e):
        """roles2_prereg.md (A): a role's words with the learned determiner or numeral right before its run ("a small boat")"""
        while s > 0 and self.is_word(toks[s - 1]) and (toks[s - 1].lower() in getattr(self, "dets", ()) or toks[s - 1].isdigit()
                                                        or toks[s - 1].lower() in getattr(self, "numwords", ())):
            s -= 1
        return " ".join(toks[s:e])

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
                patient = self.phrase(toks, *pa[0]) if pa else None
                out.append(dict(verb=self.base[t.lower()], pos=k, agent=ag0, patient=patient, adjuncts=[], text=text, status=self.status(toks, k)))
                continue
            lt_ = t.lower()                          # phrases_prereg.md amendment: "started eating the leaves" -- a present
            if (lemma is None and out and out[-1]["pos"] == k - 1 and lt_ in self.participles          # participle right after
                    and lt_ not in getattr(self, "past_participles", ()) and lt_ not in self.closed):      # a verb shares its doer
                pa = self.run_at(toks, k, 1 if self.side == "L" else -1, 2)
                out.append(dict(verb=self.participles[lt_], pos=k, agent=out[-1]["agent"], patient=" ".join(toks[pa[0][0]:pa[0][1]]) if pa else None,
                                adjuncts=[], text=text, status=out[-1].get("status", "realis")))
                continue
            main = (lemma is not None and t.lower() in self.closed and k + 1 < len(toks)
                    and toks[k + 1].lower() not in self.participles and toks[k + 1].lower() not in self.verbs
                    and k > 0 and self.is_noun(toks[k - 1]))                          # events3_prereg.md (3): "the crow had the cheese"
            if lemma is not None and k > 0 and toks[k - 1].lower() in (getattr(self, "determiners", None) or getattr(self, "dets", ())) and k + 1 < len(toks) and self.is_noun(toks[k + 1]):
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
                rel = k + 2 * a_step
                if 0 <= rel < len(toks) and self.noun_at(toks, rel):          # phrases_prereg.md (C): "the boy who broke" -> the boy
                    r0 = self.run_at(toks, k + a_step, a_step, 0)
                    if r0: ag = (r0[0], False)
            agent = None
            if ag:
                (s0, e0), pron = ag
                agent = self.last_agent if pron else self.phrase(toks, s0, e0)
                # a run that was the previous verb's patient in this sentence is not this verb's doer: two verbs joined
                # in one clause share the first one's agent ("the fox ate the cheese and ran away")
                if out and not pron and agent == out[-1]["patient"]: agent = out[-1]["agent"]
                elif not pron: self.last_agent = agent
            if agent is None and out: agent = out[-1]["agent"]       # events5_prereg.md (C): coordinated verbs share the doer
            patient = self.phrase(toks, *pa[0]) if pa else None
            recipient = None
            if pa is not None:                       # phrases_prereg.md (A): "gave Leo a book" -- a determiner and a second run
                e = pa[0][1]
                if (e + 1 < len(toks) and toks[e].lower() in getattr(self, "dets", ()) and self.noun_at(toks, e + 1)
                        and pa[0][0] > 0 and toks[pa[0][0]][:1].isupper()):     # amended: the recipient is a name ("Leo", not "the piano")
                    r2 = self.run_at(toks, e, 1, 0)
                    if r2: recipient = patient; patient = self.phrase(toks, *r2[0]); pa = (r2[0], False)
            if pa is None:                                                             # events3_prereg.md (2): "found them" -> the last patient
                nxt = k + 1
                if (nxt < len(toks) and self.is_word(toks[nxt]) and toks[nxt].lower() in self.closed and toks[nxt].lower() not in getattr(self, "auxiliaries", ())
                        and toks[nxt].lower() not in getattr(self, "adverbs", ())):      # proverb: "flew away" has no patient
                    patient = getattr(self, "last_patient", None)
            elif patient: self.last_patient = patient
            adj = []; i = (pa[0][1] if pa else k + 1)
            while i < len(toks) - 1 and self.is_word(toks[i]) and not self.is_verb(toks[i]):
                if toks[i].lower() in self.closed:
                    r = self.run_at(toks, i, 1, 1)
                    if r: adj.append(" ".join(toks[i:r[0][1]])); i = r[0][1]; continue
                i += 1
            st_ = self.status(toks, k)
            if ag and not ag[1] and ag[0][0] > 0 and toks[ag[0][0] - 1].lower() in getattr(self, "negatives", ()): st_ = "negated"   # "No guest drank"
            out.append(dict(verb=lemma, pos=k, agent=agent, patient=patient, adjuncts=adj, text=text, status=st_, recipient=recipient))
        return out


class EventMemory:
    """events read from a conversation's statements, and questions answered from them (events_prereg.md)"""
    def __init__(self, reader):
        self.reader = reader; self.events = []; reader.last_agent = None; reader.last_patient = None     # a new conversation starts with no referent
        self.facts = []                     # identity_prereg.md: (side, side) identity facts from appositions and copulas

    def ingest(self, text):
        # identity_prereg.md amendment: a statement cut after a learned abbreviation ("Her teacher, Mrs.") is held and
        # joined to the next one -- a sentence splitter that cuts at every full stop split "Mrs. Kato"
        text = (getattr(self, "pending", "") + " " + text).strip(); self.pending = ""
        last = tokens(text)[-2:] if len(tokens(text)) >= 2 else []
        if len(last) == 2 and last[1] == "." and last[0] in getattr(self.reader, "abbr", ()):
            self.pending = text; return
        self.events += self.reader.read(text)
        self.facts += self.identities(text)

    def identities(self, text):
        """identity_prereg.md (B): appositions "<det phrase> , <Name> ," / "<Name> , <det phrase> ," and copular clauses"""
        R = self.reader; toks = tokens(text); dets = getattr(R, "dets", ()); cop = getattr(R, "copula", ()); out = []
        ab = getattr(R, "abbr", ()); merged = []        # amendment: "Mrs . Kato" is one name (a learned abbreviation's full stop)
        for t in toks:
            if merged and t == "." and merged[-1] in ab: merged[-1] += "."; continue
            if merged and merged[-1].endswith(".") and merged[-1][:-1] in ab and t[:1].isupper(): merged[-1] += " " + t; continue
            merged.append(t)
        toks = merged
        def run(i, step):            # a noun/name run from i in direction step -> (s, e) or None
            j = i
            while 0 <= j < len(toks) and R.is_word(toks[j]) and (toks[j].lower() not in R.closed or toks[j].lower() in dets)                     and toks[j].lower() not in R.verbs:
                j += step
            s, e = (i, j) if step == 1 else (j + 1, i + 1)
            return (s, e) if e > s else None
        for k, t in enumerate(toks):
            if t != ",": continue
            a = run(k - 1, -1); b = run(k + 1, 1)
            if not a or not b or not (b[1] < len(toks) and toks[b[1]] in ",."): continue
            A = toks[a[0]:a[1]]; B = toks[b[0]:b[1]]
            if A and B and A[0].lower() in dets and B[0][:1].isupper(): out.append((" ".join(B), " ".join(A)))
            elif A and B and A[0][:1].isupper() and B[0].lower() in dets: out.append((" ".join(A), " ".join(B)))
        pp = getattr(R, "past_participles", ())
        for k, t in enumerate(toks):                # roles2 (C): "a girl named Petra" -> Petra = a girl
            if 0 < k < len(toks) - 1 and t.lower() in pp and toks[k + 1][:1].isupper() and toks[k + 1].lower() not in R.closed:
                a = run(k - 1, -1); b = run(k + 1, 1)
                if a and b:
                    A = toks[a[0]:a[1]]
                    if A and A[0].lower() in dets: out.append((" ".join(toks[b[0]:b[1]]), " ".join(A)))
        qw = getattr(self, "qwords", ())
        for k, t in enumerate(toks):
            if t.lower() not in cop or k == 0: continue
            if toks[k - 1].lower() in qw or (k + 1 < len(toks) and toks[k + 1].lower() in qw): continue   # "what is", "is what": a question
            j = k - 1
            while j >= 0 and R.is_word(toks[j]): j -= 1
            subj = toks[j + 1:k]
            if not subj and j >= 0 and toks[j] == ",":          # "The youngest, Elin, was": the name before the comma
                jj = j - 1
                while jj >= 0 and R.is_word(toks[jj]): jj -= 1
                subj = toks[jj + 1:j]
            pred = []
            m = k + 1
            while m < len(toks) and R.is_word(toks[m]): pred.append(toks[m]); m += 1
            # amendment: a subject or predicate holding a verb form is not a phrase ("please tell me what is the country ...",
            # "... is do you know what"): questions the turn splitter took for statements made junk identities
            verbish = lambda w: w.lower() in R.verbs or w.lower() in getattr(R, "base", {}) and w.lower() not in R.closed and not w[:1].isupper()
            def verb_use(i_, w):                # a finite form, or a bare form with a word after it inside the phrase ("tell me")
                lw_ = w.lower()
                if w[:1].isupper() or lw_ in R.closed: return False
                return lw_ in R.verbs or (lw_ in getattr(R, "base", {}) and i_ + 1 < len(subj))
            if subj and any(verb_use(i_, w) for i_, w in enumerate(subj)): continue
            content_ = lambda ws: any(w.lower() not in R.closed for w in ws)           # each side needs an open-class word
            if not (subj and pred and content_(subj) and content_(pred)): continue
            if subj and pred and pred[0].lower() in R.verbs and pred[0].lower() not in R.closed: continue     # a finite verb opens no predicate
            if subj and pred and pred[0].lower() not in getattr(R, "participles", {}) and pred[0].lower() not in getattr(R, "negatives", ()):
                out.append((" ".join(subj), " ".join(pred)))
        return out

    def ask(self, text):
        """-> (answer text, event) or None. The question's first symbol must be closed-class (a question word); its verb
        lemma selects events; the role it leaves empty is the answer"""
        toks = tokens(text); words = [t for t in toks if self.reader.is_word(t)]
        if not words or (words[0].lower() not in self.reader.closed and not text.rstrip().endswith("?")): return None   # events5 (G): or a "?"-ended turn
        dets_q = getattr(self.reader, "dets", ())
        lemmas = [self.reader.verbs.get(t.lower()) or self.reader.base.get(t.lower()) or self.reader.participles.get(t.lower())
                  for j, t in enumerate(words) if j > 0 and t.lower() not in self.reader.closed
                  and not (j >= 2 and (words[j - 1].lower() in dets_q or words[j - 1].lower() in getattr(self.reader, "numwords", ())))]   # copq: a word after a determiner is a noun ("the keys");
                                                                          # not right after the question word ("What fell")
        lemmas = [l for l in lemmas if l]
        lex_lemmas = list(lemmas)
        if not {ev["verb"] for ev in self.events if ev.get("status", "realis") == "realis"} & set(lemmas):   # haveq_prereg.md (A, amended: "cat" is a verb too) --
                                               # no lexical lemma told of -> the closed verb forms ("Who had a clever cat?")
            cop_l = {self.reader.verbs.get(c) for c in getattr(self.reader, "copula", ())}
            cl = [self.reader.verbs.get(t.lower()) or self.reader.base.get(t.lower()) for j, t in enumerate(words)
                  if j > 0 and t.lower() in self.reader.closed]
            lemmas = lemmas + [l for l in cl if l and l not in cop_l]
        same = {x for l in lex_lemmas for x in self.reader.same.get(l, ())}   # haveq: closed lemmas bring no synonyms                 # events2_prereg.md: synonymous verbs, second
        pl = getattr(self.reader, "plural", {})
        def base(x): x = x.lower(); return pl.get(x, x)                 # phrases amendment: "shelves" is "shelf"
        content = {base(t) for i, t in enumerate(words) if i > 0 and self.reader.noun_at(words, i)}    # phrases (B): by position ("apples")
        # events5_prereg.md (E): a PASSIVE question -- a learned auxiliary, later a past participle -- names the patient
        lw = [t.lower() for t in words]
        aux_at = [i for i, t in enumerate(lw) if i > 0 and t in getattr(self.reader, "auxiliaries", ())]
        passive = bool(aux_at) and any(t in getattr(self.reader, "past_participles", ()) for t in lw[aux_at[0] + 1:])
        for a_, b_ in getattr(self, "facts", ()):             # roles2 (B): identities widen the question ("petra" -> "girl")
            A_ = {base(w) for w in a_.split() if w.lower() not in self.reader.closed}
            B_ = {base(w) for w in b_.split() if w.lower() not in self.reader.closed}
            if A_ & content and not B_ & content: content = content | B_
            elif B_ & content and not A_ & content: content = content | A_
        # proverb_prereg.md: "did ... do" -- the auxiliary's lemma is the main verb's lemma -> answer an event, not a role
        aux_lem = self.reader.verbs.get(lw[1]) if len(lw) > 1 else None
        lem_of = lambda t: self.reader.verbs.get(t) or self.reader.base.get(t)
        if aux_lem and any(lem_of(t) == aux_lem for t in lw[2:]) and all(l == aux_lem for l in lemmas):
            for ev in reversed(self.events):
                if ev.get("status", "realis") != "realis" or not ev.get("agent"): continue
                if {base(w) for w in ev["agent"].split()} & content:
                    toks_e = tokens(ev.get("text", ""))
                    vform = toks_e[ev["pos"]] if ev.get("pos") is not None and ev["pos"] < len(toks_e) else ev["verb"]
                    p_ = ev.get("pos")
                    if p_ is not None and p_ + 1 < len(toks_e) and toks_e[p_ + 1].lower() in getattr(self.reader, "adverbs", ()):
                        vform += " " + toks_e[p_ + 1]                           # the particle belongs to the verb ("flew away")
                    rest = " ".join(x for x in [ev.get("patient") or ""] + list(ev.get("adjuncts", [])) if x)
                    return (vform + (" " + rest if rest else "")), ev
        # appos_prereg.md (C): "Was the wind calm?" -> yes, from a fact whose two sides each share the question's words
        if lw and lw[0] in getattr(self.reader, "copula", ()) and getattr(self, "facts", None):
            qc = {base(t) for t in words[1:] if t.lower() not in self.reader.closed}
            for a_, b_ in reversed(self.facts):
                A_ = {base(w) for w in a_.split()}; B_ = {base(w) for w in b_.split()}
                if A_ & qc and B_ & qc and not (A_ & B_):
                    return "yes", dict(verb="be", agent=a_, patient=b_, adjuncts=[], text="")
        # identity_prereg.md (C): "Who/What was X?" from identity facts (not a passive: no past participle)
        if len(lw) > 2 and lw[1] in getattr(self.reader, "copula", ()) and not passive and self.facts:
            ql = [base(t) for t in words[2:] if t.lower() not in self.reader.closed]; q = set(ql)
            head = ql[-1] if ql else None            # amendment: the question's head noun ("Hana's HUSBAND") outweighs a possessor
            bestf = None
            for a, b in reversed(self.facts):
                for x, y in ((a, b), (b, a)):
                    xs = {base(w) for w in x.split()}
                    ov = len(xs & q) + (0.5 if head in xs else 0) if xs & q else 0
                    if ov and (bestf is None or ov > bestf[0] or (ov == bestf[0] and y[:1].isupper() and not bestf[1][:1].isupper())):
                        bestf = (ov, y, x)
            if bestf: return bestf[1], dict(verb="be", agent=bestf[2], patient=bestf[1], adjuncts=[], text="")
        # copq_prereg.md: a copular question with no lexical verb -> the adjuncts of the latest realis event whose role the
        # question's content fills (patient first)
        if len(lw) > 2 and lw[1] in getattr(self.reader, "copula", ()) and not passive and not lemmas:
            for role in ("patient", "agent"):
                for ev in reversed(self.events):
                    if ev.get("status", "realis") != "realis" or not ev.get("adjuncts") or not ev.get(role): continue
                    if {base(w) for w in ev[role].split()} & content:
                        return " ".join(ev["adjuncts"]), ev
        best = None
        irr_ok = any(t in (getattr(self.reader, "to_marker", None) or ()) for t in lw[1:])   # reality_prereg.md (B)
        for ev in reversed(self.events):
            if ev["verb"] not in lemmas and ev["verb"] not in same: continue
            if ev["verb"] not in lex_lemmas and ev["verb"] not in same:      # haveq (amended): a closed-verb match only when
                allw = {base(x) for r in ("agent", "patient", "recipient") for x in (ev.get(r) or "").split()}   # every content
                if not content or not content <= allw: continue                                             # word is in its roles
            if ev.get("status") == "irrealis" and not irr_ok: continue
            if ev.get("status") == "negated": continue                          # negation_prereg.md (C)
            roles = {"agent": ev["agent"] or "", "patient": ev["patient"] or "", "recipient": ev.get("recipient") or ""}
            filled = {r for r, v in roles.items() if v and {base(x) for x in v.split()} & content}
            num = None                               # phrases_prereg.md (B): the numeral a matched role holds and the question lacks
            for r in ("patient", "agent"):
                if r in filled:
                    rt = roles[r].split(); hit_i = next((i for i, x in enumerate(rt) if base(x) in content), None)
                    nums = [i for i, x in enumerate(rt) if (x.isdigit() or x.lower() in getattr(self.reader, "numwords", ())) and x.lower() not in lw and (hit_i is None or i < hit_i)]
                    if nums: num = rt[nums[-1]]
            strand = [a for a in ev["adjuncts"] if lw[-1] in self.reader.closed and a.lower().split()[0] == lw[-1]
                      and len(a.split()) > 1] if len(lw) > 2 else []     # lostdet (B): "dry it with?" -> the "with ..." adjunct
            if strand and filled: ans = strand[0].split(" ", 1)[1]
            elif num is not None: ans = num
            elif passive and "agent" not in filled:
                if "patient" in filled and ev["adjuncts"]: ans = " ".join(ev["adjuncts"])
                elif "patient" not in filled and ev["patient"]: ans = ev["patient"]
                else: continue
            elif "agent" in filled and ev["patient"] and "patient" not in filled: ans = ev["patient"]
            elif "agent" in filled and "patient" in filled and ev["adjuncts"]: ans = " ".join(ev["adjuncts"])     # (E): every adjunct
            elif "agent" in filled and not ev["patient"] and ev["adjuncts"]: ans = " ".join(ev["adjuncts"])
            elif "agent" not in filled and ev["agent"] and (filled or not content
                                                            or any({base(x) for x in a.split()} & content for a in ev["adjuncts"])): ans = ev["agent"]   # events3_prereg.md (4); events5 (H): an adjunct shared
            else: continue                      # honesty_prereg.md: no role shared with the question -> no basis to answer
            score = len(filled) + (0.5 if ev["verb"] in lemmas else 0)
            if best is None or score > best[0]: best = (score, ans, ev)
        return (best[1], best[2]) if best else None
