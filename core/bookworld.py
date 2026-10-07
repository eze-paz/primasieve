"""BOOKWORLD -- every book its own world (bookworld_prereg.md; the owner's ruling of 2026-10-07: "every source should
have its own context unless we know we are talking about the real world"). Zero LLM; holds no word of any language.

A Book reads one text. Its people are found in the text itself (capitalised names, textworld.find_entities); its
propositions are events with a NAMED doer and roles by apposition, each kept with its context (the book, the sentence)
and said "according to <book>". Nothing here is a world fact: `real` is False unless a bridge finds evidence that the
source speaks of the real world. Data from outside: the event reader's verb tables, the closed class, the learned
abbreviations, determiners and verb-chain heads (emergence/kb_bookworld.py)."""
import re, collections
from core.textworld import find_entities

TOKEN = re.compile(r"[^\W_]+|[^\w\s]")
SPLIT = re.compile(r"(?<=[.!?])\s+")


def tokens(s): return TOKEN.findall(s)


def is_word(t): return t[:1].isalnum()


def abbreviations(texts, least=20, share=0.9):
    """symbols followed by "." in >= `share` of their >= `least` occurrences (counted, case kept)"""
    dot = collections.Counter(); allc = collections.Counter()
    for text in texts:
        toks = tokens(text)
        for a, b in zip(toks, toks[1:]):
            if a[:1].isalpha(): allc[a] += 1; dot[a] += b == "."
    return {w for w, n in allc.items() if n >= least and dot[w] >= share * n}


def split(text, abbr):
    """sentences; a split right after "<abbreviation>." is undone"""
    out = []
    for p in SPLIT.split(text):
        p = " ".join(p.split())
        if not p: continue
        if out:
            t = tokens(out[-1])
            if len(t) >= 2 and t[-1] == "." and t[-2] in abbr: out[-1] += " " + p; continue
        out.append(p)
    return out


def heading(t): return len(t) > 1 and t.isupper()


class Book:
    def __init__(self, bid, text, closed, abbr, reader, determiners=(), chain_heads=(), title=None, least=5, verbish=(), skippable=(),
                 nounish=(), preplike=()):
        self.verbish = set(verbish); self.skip = set(skippable); self.nounish = set(nounish); self.prep = set(preplike)
        self.bid = bid; self.closed = set(closed); self.R = reader; self.det = set(determiners); self.heads = set(chain_heads)
        self.title = title or ("book " + str(bid)); self.real = False
        self.sents = split(text, abbr); self.toks = [tokens(s) for s in self.sents]
        raw = [[t for t in ts if t[:1].isalpha() and not heading(t)] for ts in self.toks]
        self.entities = find_entities(raw, least=least, closed=self.closed)
        # titles: an entity symbol followed (past an abbreviation's ".") by another capitalised symbol >= 80 % of the time
        cap = collections.Counter(); nxt = collections.Counter(); low = collections.Counter()
        for ts in self.toks:
            for k, t in enumerate(ts):
                if t[:1].islower(): low[t.lower()] += 1
                if t.lower() in self.entities and t[:1].isupper():
                    cap[t.lower()] += 1; j = k + 1
                    if j < len(ts) and ts[j] == ".": j += 1
                    if j < len(ts) and ts[j][:1].isupper() and is_word(ts[j]): nxt[t.lower()] += 1
        self.titles = {e for e in cap if nxt[e] >= 0.8 * cap[e]}
        self.low = low

    # ---- names
    def names(self, ts):
        """-> [(start, end, key, text)]: maximal runs of capitalised tokens (a title's "." kept inside) holding a book
        entity; key = the run's non-title entity symbols"""
        out = []; k = 0
        cap = lambda t: is_word(t) and t[:1].isupper() and not heading(t)
        while k < len(ts):
            if cap(ts[k]):
                j = k
                while j + 1 < len(ts) and (cap(ts[j + 1]) or (ts[j + 1] == "." and j + 2 < len(ts) and cap(ts[j + 2])
                                                              and ts[j].lower() in self.titles)):
                    j += 1 if cap(ts[j + 1]) else 2
                run = list(range(k, j + 1))
                ents = [i for i in run if ts[i].lower() in self.entities]
                key = tuple(ts[i].lower() for i in ents if ts[i].lower() not in self.titles)
                if key:
                    s = k
                    while s < ents[0] and (ts[s].lower() in self.closed or (s == 0 and ts[s].lower() not in self.entities)): s += 1
                    out.append((s, j + 1, key, " ".join(ts[s:j + 1]).replace(" .", ".")))
                k = j + 1
            else: k += 1
        return out

    # ---- propositions of one sentence
    def verb_at(self, ts, k):
        """-> (lemma, position of the content verb) for a finite verb at k, following a learned chain head or auxiliary
        to the verb it carries ("had gone", "did not go")"""
        t = ts[k].lower(); R = self.R; auxs = getattr(R, "auxiliaries", ())
        finite = t in R.verbs and ((t not in self.closed and t not in self.nounish) or t in self.verbish or t in auxs)
        if not finite and t not in self.heads: return None
        if t in auxs or t in self.heads:
            for j in range(k + 1, min(len(ts), k + 4)):
                if not is_word(ts[j]): break
                tj = ts[j].lower()
                if tj in R.participles and t in auxs: return R.participles[tj], j
                if t in self.heads and tj in R.base and tj not in self.closed: return R.base[tj], j
                if tj not in self.skip: break
        if finite: return R.verbs[t], k
        return None

    def doer_of(self, ts, k, vp, ends, starts):
        """(a) a name ending before the verb chain, at most two learned skippable symbols between ("never"), no punctuation; (b) dialogue
        attribution: two punctuation marks (a quotation closing), verb, name -> (name, is_dialogue)"""
        for e in range(k, max(-1, k - 3), -1):
            if e in ends and all(is_word(x) and x.lower() in self.skip for x in ts[e:k]):
                if self.outside(ts, ends[e][0]): return None, False
                return ends[e], False
        if k > 1 and not is_word(ts[k - 1]) and not is_word(ts[k - 2]) and vp == k and k + 1 in starts: return starts[k + 1], True
        return None, False

    def outside(self, ts, s):
        """a name right after a learned preposition-like symbol ("the coach from Wildairs Hall") is not the subject"""
        return s > 0 and ts[s - 1][:1].islower() and ts[s - 1].lower() in self.prep

    @staticmethod
    def asked(ts, k):
        """the clause holding position k ends in a question mark"""
        for t in ts[k:]:
            if t in ".!?": return t == "?"
        return False

    def read(self, i):
        ts = self.toks[i]; ns = self.names(ts); out = []
        ends = {n[1]: n for n in ns}; starts = {n[0]: n for n in ns}
        used = set()
        for k in range(len(ts)):
            if k in used or not is_word(ts[k]): continue
            v = self.verb_at(ts, k)
            if v is None: continue
            lemma, vp = v
            doer, dialogue = self.doer_of(ts, k, vp, ends, starts)
            if doer is None or self.asked(ts, vp): continue
            used.update(range(k, vp + 1))
            obj = None
            if not dialogue:
                pa = self.R.run_at(ts, vp, 1 if self.R.side == "L" else -1, 2)
                if pa: obj = " ".join(ts[vp + 1:pa[0][1]])
            out.append(self.prop("event", doer, " ".join(ts[k:vp + 1]), obj, i, lemma=lemma))
        out += self.roles(ts, ns, starts, i)
        return out

    def roles(self, ts, ns, starts, i):
        """roles by apposition: NAME , [closed] w1..w3 <closed> NAME2 ; NAME , <determiner> w1..w3 ,"""
        out = []
        for s, e, key, text in ns:
            if not (e < len(ts) and ts[e] == ",") or self.outside(ts, s): continue
            j = e + 1
            if j < len(ts) and ts[j].lower() in self.closed: j += 1
            w = j
            while (w < len(ts) and w - j < 3 and is_word(ts[w]) and ts[w][:1].islower() and ts[w].lower() not in self.closed
                   and ts[w].lower() not in self.entities): w += 1
            if w == j or w >= len(ts): continue
            if ts[w].lower() in self.closed and w + 1 in starts:
                n2 = starts[w + 1]; out.append(self.prop("role", (s, e, key, text), " ".join(ts[j:w + 1]), n2[3], i, okey=n2[2]))
            elif ts[w] == "," and e + 1 < j and ts[e + 1].lower() in self.det:
                out.append(self.prop("role", (s, e, key, text), "is", " ".join(ts[e + 1:w]), i))
        return out

    def prop(self, kind, subj, rel, obj, i, lemma=None, okey=None):
        return dict(kind=kind, subj=subj[3], skey=subj[2], rel=rel, obj=obj, okey=okey, lemma=lemma, sent=i,
                    context=self.bid, title=self.title, real=self.real)

    @staticmethod
    def say(p):
        """a book proposition is always said in its book's context"""
        body = " ".join(x for x in (p["subj"], p["rel"], p["obj"]) if x)
        return body if p.get("real") else f"according to {p['title']}, {body}"
