"""REPHRASE -- guessing what a sentence means by guess and check (didyoumean_prereg.md, GUESS_PLAN.md G3). Zero LLM;
holds no word of any language.

A turn nothing answered may carry a symbol no world reads. The text model (core/textmodel.py) names the symbols that
behave most like it in text; of those, the ones some world reads alone are tried in place of it, silently, over the same
worlds and context; the first replacement that yields an answer is OFFERED -- never answered. The person's confirmation
turns the offer into a kept substitution (later turns are read through it, and say so); a refusal is kept too, and the
offer is never made again."""
from .reason import reason, symbols, _spans
from .verdict import ATTRIBUTED, COMMIT, CONJECTURED

OFFER = "OFFER"
ANSWERED = (COMMIT, ATTRIBUTED, CONJECTURED)


def read_positions(fr, strict=False):
    """positions of the turn some NON-quoting world read (a quoted gloss explains a word, it does not bind it). With
    `strict` (a turn nothing answered), a position counts as read only by a reading of one of its world's CONTENT kinds,
    from a world that was not fetched: a live search finds an entry for almost any plain word, and a turn that nothing
    answered may have sent a plain word to the researcher as if it were a name"""
    n = len(fr["syms"]); out = set()
    for r, w in zip(fr.get("readings", []), fr.get("reading_worlds", [])):
        if getattr(w, "quotes", False) or getattr(w, "transcript", False) or r[2] in ("U", "X") or r[0] >= n: continue
        if strict and (getattr(w, "fetched", None) or r[2] not in getattr(w, "content_kinds", {r[2]})): continue
        out.update(range(r[0], min(r[1], n)))
    return out


class Rephraser:
    def __init__(self, model, common=100, candidates=30, tries=8):
        self.model = model; self.tries = tries; self.candidates = candidates
        self.common = {w for w, c in model.uni.most_common(common)}
        self._alone = {}

    def _consolidated(self, session, u):
        """H8: kept substitutions (w -> s) whose w is in u's family -> [(candidate, -1, (w, s))]: s with the same
        alternation first, then s"""
        if not getattr(self, "consolidate", False): return []          # consolidate_prereg.md: off unless asked (run 2 failed)
        out = []
        for w, sub in getattr(session, "subs", {}).items():
            fam = family(w, u)
            if fam is None: continue
            tw, tu = fam
            if tw and sub.endswith(tw): out.append((sub[:len(sub) - len(tw)] + tu, -1, (w, sub)))
            elif not tw and tu: out.append((sub + tu, -1, (w, sub)))
            out.append((sub, -1, (w, sub)))
        return out

    def read_alone(self, worlds, sym):
        if sym not in self._alone:
            ok = False
            for w in worlds:
                if getattr(w, "quotes", False) or getattr(w, "transcript", False): continue
                try:
                    if any(r[2] not in ("U", "X") for r in w.readings([sym])): ok = True; break
                except Exception: continue
            self._alone[sym] = ok
        return self._alone[sym]

    # ---- spelling_prereg.md: a slip one keystroke from a known word ----------------------------------------------------
    def _vocab(self):
        if not hasattr(self, "_V"):
            self._V = {w for w, c in self.model.uni.items() if c >= 3 and w[:1].isalpha()}
            self._alpha = sorted({ch for w in self._V for ch in w})       # the alphabet is the vocabulary's own letters
        return self._V

    def edits(self, u):
        """every word of the vocabulary one edit from u (delete, swap adjacent, replace, insert); knockout: random words"""
        V = self._vocab(); A = self._alpha; out = set()
        for i in range(len(u) + 1):
            a, b = u[:i], u[i:]
            if b: out.add(a + b[1:])
            if len(b) > 1: out.add(a + b[1] + b[0] + b[2:])
            for ch in A:
                if b: out.add(a + ch + b[1:])
                out.add(a + ch + b)
        out = sorted(x for x in out if x in V and x != u)
        if getattr(self, "spell_knockout", False):                      # T4: the same count, drawn at random
            import random
            rng = random.Random(hash(u) & 0xffff); pool = sorted(V); out = rng.sample(pool, len(out)) if out else []
        return out

    def spell(self, session, fr, declined=()):
        """-> {pos, word, sub, fr} when EXACTLY ONE one-edit reading of one unread symbol gives an answer from a
        non-quoting world whose structure reads the replaced position; else None"""
        syms = list(fr["syms"])
        if any(getattr(w, "transcript", False) for w in fr.get("answer_worlds", [])): return None
        read = read_positions(fr, strict=fr["kind"] not in ANSWERED)
        qw = getattr(session, "qwords", set())
        first_q = next((p for p, x in enumerate(syms) if x in qw), None)
        unread = [i for i, x in enumerate(syms) if i not in read and x not in self.common and x[:1].isalpha() and len(x) >= 3
                  and (first_q is None or i > first_q)]
        found = []
        for i in unread:
            for c in self.edits(syms[i]):
                if (syms[i], c) in declined or not self.read_alone(session.worlds, c): continue
                # worldhonesty_prereg.md (A), amended: a KNOWN word is never read as its own relative -- "managed" is not a
                # slip for "manager" (same stem: a converse); a known word one edit from an unrelated word may be ("pairs")
                if syms[i] in self._vocab() and family(syms[i], c) is not None: continue
                text = " ".join(syms[:i] + [c] + syms[i + 1:])
                try:
                    f2 = reason(text, session.worlds, session.df, cats="LN", context=session.context(), ledger=None,
                                shapes=session.shapes(), recent=frozenset())
                except Exception:
                    continue
                if f2["kind"] not in (COMMIT, ATTRIBUTED) or not f2.get("answers"): continue
                if all(getattr(w, "quotes", False) for w in f2["answer_worlds"]): continue
                if not any(a <= i < b for w2, a2 in zip(f2["answer_worlds"], f2["answers"]) for a, b in _spans(w2, a2[4])): continue
                found.append(dict(pos=i, word=syms[i], sub=c, fr=f2))
                if len(found) > 1: return None              # two readings: nothing is assumed
        return found[0] if found else None

    def offer(self, session, fr, declined=()):
        """-> {pos, word, sub, shared, text, original} for the first replacement that yields an answer, or None.
        When the turn WAS answered while leaving the word unread (run 2, didyoumean_prereg.md), a replacement counts only
        if its answer READS the replaced position and differs from the direct answer: the unread word changed the
        question, and the direct answer was to another one."""
        syms = list(fr["syms"])
        direct = {str(a[1]).lower() for a in fr.get("answers", [])} if fr["kind"] in ANSWERED else None
        if direct is not None and any(getattr(w, "transcript", False) for w in fr.get("answer_worlds", [])):
            return None                  # natural_prereg.md (7): an answer recalled from the conversation itself is not re-read
        read = read_positions(fr, strict=direct is None)
        if direct is not None and all(getattr(w, "quotes", False) for w in fr.get("answer_worlds", [])) \
                and not any(syms[p] not in self.common for p in read):
            return None                  # a quoted gloss of the turn's only content: the question was about the word itself
        unread = [i for i, s in enumerate(syms) if i not in read and s not in self.common and s[:1].isalpha()]
        qw = getattr(session, "qwords", set())          # natural2_prereg.md run 2: what frames the question before its first
        first_q = next((p for p, x in enumerate(syms) if x in qw), None)       # learned question word is not a typo
        if first_q is not None: unread = [i for i in unread if i > first_q]
        for i in unread:
            tried = 0
            for c, shared, src in self._consolidated(session, syms[i]) + [(c, n, None) for c, n in self.model.similar(syms[i], self.candidates)]:
                if (syms[i], c) in declined or c in syms or not self.read_alone(session.worlds, c): continue
                tried += 1
                if tried > self.tries: break
                new = syms[:i] + [c] + syms[i + 1:]; text = " ".join(new)
                try:
                    f2 = reason(text, session.worlds, session.df, cats="LN", context=session.context(), ledger=None,
                                shapes=session.shapes(), recent=frozenset())
                except Exception:
                    continue
                if f2["kind"] in ANSWERED and f2.get("answers"):
                    if direct is not None:
                        w2, st2 = f2["answer_worlds"][0], f2["answers"][0][4]
                        if not any(a <= i < b for a, b in _spans(w2, st2)): continue
                        if {str(a[1]).lower() for a in f2["answers"]} == direct: continue
                    out = dict(pos=i, word=syms[i], sub=c, shared=shared, text=text, original=" ".join(syms))
                    if src is not None: out["episode"] = src
                    return out
        return None


def family(a, b):
    """consolidate_prereg.md: (alternation tails) if a and b share a stem -- the shorter >= 4 long, the longer beginning
    with all but at most its last two characters -- else None"""
    if a == b: return None
    s, l = (a, b) if len(a) <= len(b) else (b, a)
    if len(s) < 4: return None
    for cut in (0, 1, 2):
        stem = s[:len(s) - cut]
        if len(stem) >= 4 and l.startswith(stem): return a[len(stem):], b[len(stem):]      # run 2: a stem is >= 4 long
    return None


def rewrite(syms, subs):
    """-> (symbols with every kept substitution applied, [(word, substitute)] applied)"""
    out, used = [], []
    for s in syms:
        if s in subs: out.append(subs[s]); used.append((s, subs[s]))
        else: out.append(s)
    return out, used
