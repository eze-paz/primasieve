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

    def offer(self, session, fr, declined=()):
        """-> {pos, word, sub, shared, text, original} for the first replacement that yields an answer, or None.
        When the turn WAS answered while leaving the word unread (run 2, didyoumean_prereg.md), a replacement counts only
        if its answer READS the replaced position and differs from the direct answer: the unread word changed the
        question, and the direct answer was to another one."""
        syms = list(fr["syms"])
        direct = {str(a[1]).lower() for a in fr.get("answers", [])} if fr["kind"] in ANSWERED else None
        read = read_positions(fr, strict=direct is None)
        if direct is not None and all(getattr(w, "quotes", False) for w in fr.get("answer_worlds", [])) \
                and not any(syms[p] not in self.common for p in read):
            return None                  # a quoted gloss of the turn's only content: the question was about the word itself
        unread = [i for i, s in enumerate(syms) if i not in read and s not in self.common and s[:1].isalpha()]
        for i in unread:
            tried = 0
            for c, shared in self.model.similar(syms[i], self.candidates):
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
                    return dict(pos=i, word=syms[i], sub=c, shared=shared, text=text, original=" ".join(syms))
        return None


def rewrite(syms, subs):
    """-> (symbols with every kept substitution applied, [(word, substitute)] applied)"""
    out, used = [], []
    for s in syms:
        if s in subs: out.append(subs[s]); used.append((s, subs[s]))
        else: out.append(s)
    return out, used
