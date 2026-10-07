"""B4-BOOK -- reading prose under the owner's ruling (bookworld_prereg.md): every held-out book is its own world; the
share of its sentences that yield a book-local proposition, with precision on a builder-judged sample.

    python book_battery.py [--it N]      (writes tests/bookworld_judged_itN.json with unjudged items the first time;
                                          once judged, prints precision)"""
import os, sys, re, json, random, hashlib, collections, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "emergence"))
import kb_bookworld as KB
from core.bookworld import Book, tokens

GUT = os.path.join(HERE, "_nldata", "gutenberg")
NOVELS = {"1422", "1550", "1553", "1586"}
T0 = time.time()


def say(s=""): print(str(s).encode("ascii", "replace").decode(), flush=True)


def held_book(bid): return int(hashlib.sha256(f"book:{bid}".encode()).hexdigest(), 16) % 10 == 0


def test_books():
    books = sorted(f[:-4] for f in os.listdir(GUT) if f.endswith(".txt"))
    return [b for b in books if held_book(b)][:10]


DETS_FOR_OBJECTS = set()


def in_sent(patient, low, verb_at=None):
    """bookpronoun run 2: a patient carried over from another sentence (a resolved "them") is not this sentence's; run 3:
    the patient must begin within 3 symbols after its verb (a later verb's object is not this one's)"""
    if not patient: return ""
    w = low.split(); pw = [x.lower() for x in patient.split()]
    at = [j for j in range(len(w)) if w[j:j + len(pw)] == pw]
    if not at: return ""
    if verb_at is not None and not any(verb_at < j <= verb_at + 3 for j in at): return ""
    if verb_at is not None:                 # bookshapes run 3: only determiners between the verb and its object ("sat WITH his lips")
        j = min(j for j in at if verb_at < j <= verb_at + 3)
        if any(w[m] not in DETS_FOR_OBJECTS for m in range(verb_at + 1, j)): return ""
        end = j + len(pw)
        if end < len(w) and w[end] == "-": return ""          # a hyphen-cut object ("knee" of "knee-breeches")
    return patient


def word_index(et, k):
    """position of token k among the sentence's word tokens (in_sent works on words)"""
    return sum(1 for x in et[:k] if x[:1].isalnum())


def copula_forms(R):
    """copula_prereg.md (B): the closed form the verb table gives the lemma of the commonest finite closed verb ("is" ->
    be), plus the closed symbols sharing its two-sided slots that have a dictionary verb sense and no OTHER lemma in the
    verb table, with >= 10 % of the top one's shared slots (learned: was, are, were)"""
    import sqlite3, json as _j
    from core.textmodel import TextModel
    from core.synonyms import Synonyms
    from textmodel import MODEL
    import kb_events as KE
    db = sqlite3.connect(os.path.join(HERE, "_nldata", "kaikki_all.sqlite"))
    closed = R.closed
    finite_closed = [w for w in _j.load(open(KE.CLOSED_CACHE, encoding="utf-8"))
                     if R.verbs.get(w) not in (None, w) and KE.pos_senses(db, w).get("verb")]     # a form of ANOTHER lemma
    if not finite_closed: return set()
    c0 = finite_closed[0]; lem = R.verbs[c0]
    sims = [(w, n) for w, n in Synonyms(TextModel.load(MODEL)).two_sided(c0, 60) if w in closed]
    if not sims: return {c0}
    top = sims[0][1]
    def mostly_verb(w):
        ps = KE.pos_senses(db, w); return ps.get("verb", 0) >= 0.5 * max(1, sum(ps.values()))
    out = {c0} | {w for w, n in sims if n >= 0.1 * top and mostly_verb(w) and R.verbs.get(w) in (None, lem)}
    say(f"copula forms learned: {sorted(out)} (from {c0!r})")
    return out


def existential_word(R, n_books=60):
    """bookshapes_prereg.md (B): the closed sentence-initial symbol without a dictionary pronoun sense most often followed
    by a copula form"""
    import re as _re, sqlite3, kb_events as KE
    db = sqlite3.connect(os.path.join(HERE, "_nldata", "kaikki_all.sqlite")); cop = copula_forms(R)
    c = collections.Counter()
    for b in KE.books(False)[:n_books]:
        for st in _re.split(r"(?<=[.!?])\s+", open(os.path.join(GUT, b + ".txt"), encoding="utf-8", errors="replace").read()):
            w = [x.lower() for x in tokens(st) if x[:1].isalnum()]
            if len(w) >= 3 and w[0] in R.closed and w[1] in cop and not KE.pos_senses(db, w[0]).get("pron"): c[w[0]] += 1
    ex = c.most_common(1)[0][0] if c else None
    say(f"existential word learned: {ex!r} ({c.most_common(3)})")
    return ex


def describe_hook(R, strict=False, pronouns=False, copula=None):
    """bookdescribe_prereg.md: for a unit the book reader leaves unread, the story reader's realis events whose doer is
    written in the sentence and begins with a learned determiner or a capital, in sentences without a quotation mark"""
    dets = set(getattr(R, "dets", ())); DETS_FOR_OBJECTS.update(dets)
    import sqlite3, kb_events as KE
    _db = sqlite3.connect(os.path.join(HERE, "_nldata", "kaikki_all.sqlite"))
    def _share(w, pos):
        ps = KE.pos_senses(_db, w); return ps.get(pos, 0) / max(1, sum(ps.values()))
    # amended (run 2): >= 30 % pronoun senses ("at" has a minor one)
    pron_sense = {w for w in R.closed if _share(w, "pron") >= 0.3} - set(getattr(R, "subjects", ())) - set(getattr(R, "negatives", ()))
    existential = existential_word(R) if copula else None
    copula_lemma = R.verbs.get(next(iter(sorted(copula))), None) if copula else None
    def hook(B, per):
        R.last_agent = None; R.last_patient = None
        for i in sorted(per):
            if per[i]: continue
            sent = B.sents[i]
            if any(q in sent for q in '"“”'): continue
            low = " " + " ".join(t for t in tokens(sent) if t[:1].isalnum()).lower() + " "; got = []
            from core.events import tokens as etoks
            et = etoks(sent); words_at = [j for j, x in enumerate(et) if x[:1].isalnum()]
            for ev in R.read(sent):
                a = ev.get("agent")
                if not a or ev.get("status", "realis") != "realis": continue
                aw = a.split()
                if strict:              # bookdescribe run 2: the main clause's own subject, verb right after it, active, lexical
                    if not words_at or (aw[0].lower() in R.closed and aw[0].lower() not in pron_sense): continue
                    if not aw[0][:1].isupper() and (aw[0].lower() in R.participles or aw[0].lower() in R.verbs): continue   # bookshapes guard
                    starts = [j for j in range(len(et)) if et[j:j + len(aw)] == aw]
                    if not starts: continue
                    s0 = starts[0]; e0 = s0 + len(aw); first = words_at[0]
                    poss = (s0 >= first + 3 and et[s0 - 1].lower() == "s" and et[s0 - 2] in "'’"
                            and all(x[:1].isupper() or x == "." for x in et[first:s0 - 2]))          # bookshapes (A): "Mr. Vanborough's temper"
                    if not (s0 == first or (s0 == first + 1 and et[first].lower() in dets) or poss): continue
                    if poss: a = " ".join(x for x in et[first:s0 - 2] if x != ".") + "'s " + a; aw = a.split()
                    k = ev["pos"]; vt = et[k].lower() if k < len(et) else ""
                    if not (k == e0 or (k == e0 + 1 and et[e0][:1].isalnum() and et[e0].lower() not in R.closed)): continue
                    possess = (vt in R.closed and R.verbs.get(vt) not in (None, vt) and R.verbs.get(vt) != copula_lemma
                               and k + 1 < len(et) and et[k + 1].lower() in dets)          # bookhave (A): "has a soul"
                    if vt not in R.verbs or ((vt in R.closed or ev["verb"] in R.closed) and not possess): continue
                    if k > 0 and et[k - 1].lower() in getattr(R, "auxiliaries", ()): continue
                if " " + " ".join(aw).lower() + " " not in low: continue
                k = low.split().index(aw[0].lower()) if aw[0].lower() in low.split() else -1
                prev = low.split()[k - 1] if k > 0 else ""
                if not (prev in dets or aw[0][:1].isupper()): continue
                got.append(dict(kind="event", subj=(prev + " " if prev in dets else "") + a, rel=ev["verb"], obj=in_sent(ev.get("patient"), low, word_index(et, ev["pos"])),
                                title=B.title, via=None, described=True))
            if not got and pronouns and words_at:          # bookpronoun_prereg.md: the referent said as unresolved
                f0 = words_at[0]; p0 = et[f0].lower()
                if p0 in getattr(R, "subjects", ()) and not (p0 == "who" and sent.rstrip().endswith("?")):
                    for ev in R.read(sent):
                        k = ev["pos"]; vt = et[k].lower() if k < len(et) else ""
                        if ev.get("status", "realis") != "realis": continue
                        if not (k == f0 + 1 or (k == f0 + 2 and et[f0 + 1][:1].isalnum() and et[f0 + 1].lower() not in R.closed)): continue
                        possess = (vt in R.closed and R.verbs.get(vt) not in (None, vt) and R.verbs.get(vt) != copula_lemma
                                   and k + 1 < len(et) and et[k + 1].lower() in dets)          # bookhave (A): "has a soul"
                        if vt not in R.verbs or ((vt in R.closed or ev["verb"] in R.closed) and not possess): continue
                        got.append(dict(kind="event", subj=et[f0], rel=ev["verb"], obj=in_sent(ev.get("patient"), low, word_index(et, ev["pos"])), title=B.title,
                                        via="referent not resolved", described=True)); break
            if not got and copula and words_at:            # copula_prereg.md (B): "<doer> is <predicate>"
                wl = [et[j] for j in words_at]; low_w = [x.lower() for x in wl]
                negs = getattr(R, "negatives", ()); subj = None; cpos = None
                for c in range(1, min(6, len(wl))):
                    if low_w[c] in copula: cpos = c; break
                if cpos is not None:
                    head = wl[:cpos]
                    if cpos == 1 and low_w[0] in getattr(R, "subjects", ()) and low_w[0] != "who": subj = (wl[0], "referent not resolved")
                    elif cpos == 1 and low_w[0] == existential: subj = ("there", None)                       # bookshapes (B)
                    elif cpos == 1 and low_w[0] in pron_sense: subj = (wl[0], "referent not resolved")        # bookshapes (C)
                    elif all(x[:1].isupper() for x in head) and head[0].lower() not in R.closed: subj = (" ".join(head), None)
                    elif low_w[0] in dets and cpos >= 2 and all(x not in R.closed and x not in R.verbs for x in low_w[1:cpos]): subj = (" ".join(head), None)
                if subj is not None:
                    # the predicate: the words after the copula up to the next punctuation, 1-6 of them, not negated, not
                    # opened by a participle (passive / progressive) or a verb
                    k = words_at[cpos]; pred = []
                    j = k + 1
                    while j < len(et):
                        if et[j] == "-" and pred and j + 1 < len(et) and et[j + 1][:1].isalnum():   # (B) "well-bred"
                            pred[-1] += "-" + et[j + 1]; j += 2; continue
                        if et[j] in "'’" and pred and j + 1 < len(et) and et[j + 1].lower() == "s":   # bookposs (A): "Jane's"
                            pred[-1] += "'s"; j += 2; continue
                        if not et[j][:1].isalnum(): break
                        pred.append(et[j]); j += 1
                    pl = [x.lower() for x in pred]
                    if (1 <= len(pred) <= 8 and pl[0] not in negs and pl[0] not in R.participles and pl[0] not in R.verbs
                            and not any(x in negs for x in pl)):
                        got.append(dict(kind="event", subj=subj[0], rel="is", obj=" ".join(pred), title=B.title, via=subj[1], described=True))
            per[i] = [p for p in got if keep_prop(p, sent)]
        return per
    def keep_prop(p, sent):
        """bookhave guards: a verb is needed; an object-less 'do' is empty; an object cut at a hyphen is dropped"""
        if not p.get("rel"): return False
        if p.get("obj") and p.get("rel") != "is":                # bookposs (B): an object opened by a verb form is not one
            f = p["obj"].split()[0].lower()
            if f in R.participles or f in R.verbs: p["obj"] = ""
        if p["rel"] in ("do",) and not p.get("obj"): return False
        if p.get("obj"):
            last = p["obj"].split()[-1]
            if re.search(re.escape(last) + r"-[^\W\d_]", sent): p["obj"] = ""
        return True
    return hook


QUOTES = '"“”'


def clause_hook(R, inner):
    """bookclause_prereg.md (B): a sentence opened by a closed symbol (not subject-like, not a determiner, not the
    conditional opener) and holding a comma is read from after its first comma as a clause of its own"""
    class One:
        def __init__(self, sent, title): self.sents = [sent]; self.title = title
    dets = set(getattr(R, "dets", ()))
    import sqlite3, kb_events as KE
    _db = sqlite3.connect(os.path.join(HERE, "_nldata", "kaikki_all.sqlite"))
    def linking(w):
        ps = KE.pos_senses(_db, w); return (ps.get("conj", 0) + ps.get("adv", 0)) >= 0.5 * max(1, sum(ps.values()))
    def hook(B, per):
        per = inner(B, per)
        for i in sorted(per):
            if per[i]: continue
            sent = B.sents[i]
            if any(q in sent for q in QUOTES): continue
            w = [t for t in tokens(sent) if t[:1].isalnum()]
            if not w: continue
            f = w[0].lower()
            if f not in R.closed or f in getattr(R, "subjects", ()) or f in dets or f in getattr(R, "cond", ()): continue
            if f in getattr(R, "negatives", ()): continue
            if "," in sent: rest = sent[sent.index(",") + 1:].strip()
            elif linking(f): rest = sent[sent.lower().index(f) + len(f):].strip()     # booklink: "And he caught up a brush"
            else: continue
            if len([t for t in tokens(rest) if t[:1].isalnum()]) < 3: continue
            per[i] = inner(One(rest, B.title), {0: []})[0]
        return per
    return hook


def segment_hook(R, inner, cut2=False):
    """booksegment_prereg.md: unread non-question sentences cut at ';' and at ', <linking word | subject-like>' and read
    clause by clause by the whole chain; question sentences and verb-less readings dropped"""
    class One:
        def __init__(self, sent, title): self.sents = [sent]; self.title = title; self.toks = [tokens(sent)]
        def inside(self, ts, k, i=None): return False
    import sqlite3, kb_events as KE
    _db = sqlite3.connect(os.path.join(HERE, "_nldata", "kaikki_all.sqlite"))
    def linking(w):
        ps = KE.pos_senses(_db, w); return (ps.get("conj", 0) + ps.get("adv", 0)) >= 0.5 * max(1, sum(ps.values()))
    subj = set(getattr(R, "subjects", ())); dets2 = set(getattr(R, "dets", ()))
    def clauses(sent):
        out = []; cur = []; ts = tokens(sent)
        for j, t in enumerate(ts):
            nxt = ts[j + 1].lower() if j + 1 < len(ts) else ""
            nraw = ts[j + 1] if j + 1 < len(ts) else ""
            cut = t == ";" or (t == "," and nxt and nxt in R.closed and (linking(nxt) or nxt in subj))
            if cut2:                                     # booksegment2: dashes, colons, a comma before a new subject phrase
                cut = cut or t == ":" or (t == "-" and nxt == "-") or (t == "-" and j > 0 and ts[j - 1] == "-")
                cut = cut or (t == "," and nraw and (nxt in dets2 or (nraw[:1].isupper() and nxt not in R.closed)))
            if cut:
                if cur: out.append(" ".join(cur))
                cur = []; continue
            cur.append(t)
        if cur: out.append(" ".join(cur))
        return out if len(out) > 1 else []
    def hook(B, per):
        per = inner(B, per)
        for i in sorted(per):
            sent = B.sents[i]
            if sent.rstrip().rstrip('"”').endswith("?"): per[i] = []; continue     # (B): a question is not a claim
            per[i] = [p for p in per[i] if p.get("rel")]                                     # (B): a reading needs a verb
            if per[i]: continue
            got = []
            for c in clauses(sent):
                if len([t for t in tokens(c) if t[:1].isalnum()]) < 3: continue
                got += [dict(p, title=B.title if p.get("title") in (None, "") or p["title"].startswith(B.title) is False and False else p["title"]) for p in inner(One(c, B.title), {0: []})[0] if p.get("rel")]
            per[i] = got
        return per
    return hook


def quote_hook(R, inner):
    """bookquote_prereg.md: quoted segments of still-unread sentences read as sentences of their own, said as a speaker's
    words inside the book; the speaker from the words next to the marks, "I" the speaker, "you" the one addressed"""
    class One:                                     # a one-sentence book for the inner readers
        def __init__(self, sent, title): self.sents = [sent]; self.title = title
    def speaker_of(sent, a, b):
        """name or pronoun next to a verb right after the closing mark (a "said Porbus") or right before the opening"""
        after = [t for t in tokens(sent[b:]) if t[:1].isalnum()][:2]
        before = [t for t in tokens(sent[:a]) if t[:1].isalnum()][-2:]
        for pair in (after, before[::-1] if before else []):
            if len(pair) == 2:
                v = [x for x in pair if x.lower() in R.verbs]; n = [x for x in pair if x not in v]
                if v and n:
                    w = n[0]
                    if w in abbr and pair.index(w) == 0 and pair[1][:1].isupper(): w = w + ". " + pair[1]
                    elif w in abbr: return None, None                                 # amended: "Mr" alone is not a speaker
                    if w[:1].isupper() and w.lower() not in R.closed: return w, None
                    if w.lower() in getattr(R, "subjects", ()): return w, "referent not resolved"
        return None, None
    def text_ends_q(B, i, text):
        """the run is followed in the sentence by a question mark before any other word ('"Can you see anything?" whispered')"""
        sent = B.sents[i]; at = sent.find(text[-12:]) if text else -1
        if at < 0: return False
        rest = sent[at + len(text[-12:]):]
        for ch in rest:
            if ch == "?": return True
            if ch.isalnum(): return False
        return False
    def quoted_runs(B, i):
        """-> [(text, words before, words after)] for the token runs Book.inside marks as quoted (marks excluded)"""
        ts = B.toks[i]; flags = [B.inside(ts, k, i) and ts[k] not in QUOTES for k in range(len(ts))]
        out = []; k = 0
        while k < len(ts):
            if flags[k]:
                j = k
                while j < len(ts) and flags[j]: j += 1
                text = " ".join(ts[k:j]).strip(" ,")
                out.append((text, [t for t in ts[:k] if t[:1].isalnum()][-2:], [t for t in ts[j:] if t[:1].isalnum()][:2])); k = j
            else: k += 1
        return out
    def speaker_near(before, after):
        for pair in (after, before[::-1] if before else []):
            if len(pair) == 2:
                v = [x for x in pair if x.lower() in R.verbs]; n = [x for x in pair if x not in v]
                if v and n:
                    w = n[0]
                    if w in abbr and pair.index(w) == 0 and pair[1][:1].isupper(): w = w + ". " + pair[1]
                    elif w in abbr: return None, None                                 # amended: "Mr" alone is not a speaker
                    if w[:1].isupper() and w.lower() not in R.closed: return w, None
                    if w.lower() in getattr(R, "subjects", ()): return w, "referent not resolved"
        return None, None
    import sqlite3, kb_events as KE
    _db = sqlite3.connect(os.path.join(HERE, "_nldata", "kaikki_all.sqlite"))
    pron_subjects = {w for w in R.closed if KE.pos_senses(_db, w).get("pron", 0) >= 0.3 * max(1, sum(KE.pos_senses(_db, w).values()))} - set(getattr(R, "negatives", ()))
    abbr = set()
    try: abbr = set(KB.build()[1]["abbreviations"])
    except Exception: pass
    def hook(B, per):
        per = inner(B, per)
        for i in sorted(per):
            if per[i]: continue
            sent = B.sents[i]
            if not any(q in sent for q in QUOTES): continue
            got = []
            for text, before, after in quoted_runs(B, i):        # bookquote2_prereg.md (A): the book's own quote state
                if len([t for t in tokens(text) if t[:1].isalnum()]) < 3: continue
                if text.rstrip().endswith("?") or "?" in "".join(after[:0]) or text_ends_q(B, i, text): continue   # bookclause (A)
                spk, how = speaker_near(before, after)
                ctx = f"{B.title}, {spk + (' (' + how + ')' if how else '') if spk else 'a speaker (not resolved)'}'s words"
                saved = R.subjects; R.subjects = set(saved) | pron_subjects    # bookquote3 (A): dialogue's pronoun subjects
                try: sub = inner(One(text, ctx), {0: []})[0]
                finally: R.subjects = saved
                if not sub:                                                  # bookquote3 (B): a command is a speech act
                    tw = [t for t in tokens(text) if t[:1].isalnum()]
                    v0 = tw[0].lower() if tw else ""
                    ps0 = KE.pos_senses(_db, v0)
                    if (v0 in R.base and v0 not in R.verbs and v0 not in R.closed and v0 not in R.participles
                            and not (len(tw) > 1 and tw[1][:1].isupper())             # bookshapes guard: "Mother Posset" is a vocative
                            and ps0.get("verb", 0) >= 0.5 * max(1, sum(ps0.values()))):   # amended: mostly a verb ("wise", "long" are not)
                        rest = [t for t in tw[1:6]]
                        obj = " ".join(rest[:3]) if rest else ""
                        sub = [dict(kind="event", subj="(an order to the one addressed)", rel=R.base[v0], obj=obj, title=ctx,
                                    via=None, described=True, command=True)]
                for p in sub:
                    if p["subj"].lower() == "i": p["subj"] = "I"; p["via"] = "the speaker"
                    elif p["subj"].lower() == "you": p["via"] = "the one addressed"
                    elif p.get("via") == "referent not resolved" and p["subj"].lower() in pron_subjects: pass
                    p["quoted"] = True; got.append(p)
            per[i] = got
        return per
    return hook


def units(B, n=500):
    return [i for i, s in enumerate(B.sents) if 4 <= len(s.split()) <= 60][:n]


def run(it=1, judged_n=(50, 50), control_n=50, hooks=None, knockout=False, book_ids=None, chains=True):
    R, L = KB.build(); abbr = set(L["abbreviations"])
    if it >= 7 and not hooks:
        h = describe_hook(R, strict=it >= 8, pronouns=it >= 9, copula=copula_forms(R) if it >= 10 else None)
        hooks = {"after_read": quote_hook(R, h) if it >= 11 else h}
        if it >= 12: hooks = {"after_read": clause_hook(R, hooks["after_read"])}
        if it >= 13: hooks = {"after_read": segment_hook(R, hooks["after_read"], cut2=it >= 14)}
    base_it = 5 if it >= 7 else it                       # bookdescribe_prereg.md: iteration 5's reader plus the hook
    say(f"learned: {len(L['abbreviations'])} abbreviations {L['abbreviations'][:30]}; determiners {L['determiners']}; "
        f"chain heads {L['chain_heads']}  ({time.time() - T0:.0f} s)")
    stats = collections.defaultdict(collections.Counter); props_all = []; control = []; books = {}; bridges = []
    if it >= 5: ST, lookup, related, common = KB.bridger(); say(f"store loaded  ({time.time() - T0:.0f} s)")
    for b in (book_ids or test_books()):
        B = KB.book(b, R, L, it=base_it, knockout=knockout, chains=chains); books[b] = B
        if hooks and "after_build" in hooks: hooks["after_build"](B)
        g = "novels" if b in NOVELS else "others"
        if it >= 5:
            from core.reason import symbols
            for key, (q, kb_, qb) in B.bridge(lookup, related, common, label=lambda q: ST.lab.get(q, ""),
                                              norm=lambda t: " ".join(symbols(t, "LN"))).items():
                ex = next(n[3] for ns in B._names for n in ns if n[2] == key)
                bridges.append(dict(group=g, book=b, name=ex, item=q, label=ST.lab.get(q), evidence_name=" ".join(kb_),
                                    evidence_item=qb, evidence_label=ST.lab.get(qb), ok=None))
        U = set(units(B)); allps = {i: B.read(i) for i in range(len(B.sents))}
        if it >= 3: Book.check(allps, it)                                   # bookcheck (6): checks from the book's own text
        per = {i: allps[i] for i in U}
        if hooks and "after_read" in hooks: per = hooks["after_read"](B, per)
        R.last_agent = None; R.last_patient = None
        for i in sorted(U):
            ts = B.toks[i]
            for x in (g, "all"):
                stats[x]["units"] += 1; stats[x]["read"] += bool(per[i])
                stats[x]["abbr_end"] += len(ts) >= 2 and ts[-1] == "." and ts[-2] in abbr
                for p in per[i]:
                    stats[x][p["kind"]] += 1; stats[x]["props"] += 1
                    if p.get("check") == "SUPPORTED": stats[x]["supported"] += 1
            for p in per[i]: props_all.append((g, b, i, p))
            for ev in R.read(B.sents[i]):
                if ev["agent"]: control.append((g, b, i, f"{ev['agent']} | {ev['verb']} | {ev['patient']}"))
        say(f"  {b} [{g}] '{B.title}': {len(B.sents)} sentences, {len(B.entities)} entities, titles {sorted(B.titles)[:8]}; "
            f"units {len(U)}, read {sum(1 for i in U if per[i])}  ({time.time() - T0:.0f} s)")
    for x in ("novels", "others", "all"):
        s = stats[x]
        say(f"B4-book {x}: {s['read']}/{s['units']} = {100 * s['read'] / max(1, s['units']):.1f} %  "
            f"(events {s['event']}, roles {s['role']}, supported {s['supported']}, contradicted {s['contradicted']}; "
            f"units ending in an abbreviation {s['abbr_end']} = {100 * s['abbr_end'] / max(1, s['units']):.2f} %)")
    honesty = sum(1 for g, b, i, p in props_all if p.get("real") or not KB.say(p).startswith("according to "))
    say(f"K3 honesty: book propositions said without context or marked real: {honesty} of {len(props_all)}")
    # judged samples (fixed seeds; the file keeps the builder's labels)
    tag = sys.argv[sys.argv.index("--tag") + 1] if "--tag" in sys.argv else ""      # a fresh judged sample for a new reader
    path = os.path.join(HERE, "tests", f"bookworld_judged_it{it}{'ko' if knockout else ''}{'' if chains else 'nochain'}{tag}.json")
    pron = [x for x in props_all if x[3].get("via")]
    say(f"pronoun-resolved propositions: {len(pron)}; units read only through a pronoun: "
        f"{len({(b, i) for g, b, i, p in pron} - {(b, i) for g, b, i, p in props_all if not p.get('via')})}")
    rnd = random.Random(it)
    nov = [x for x in props_all if x[0] == "novels"]; oth = [x for x in props_all if x[0] == "others"]
    samp = rnd.sample(nov, min(judged_n[0], len(nov))) + rnd.sample(oth, min(judged_n[1], len(oth)))
    csamp = random.Random(100 + it).sample(control, min(control_n, len(control)))
    psamp = random.Random(200 + it).sample(pron, min(30 if knockout else 50, len(pron))) if it >= 2 else []
    if knockout or not chains: samp, csamp, psamp = [], [], []
    for grp in ("novels", "others"):
        say(f"G2 bridges {grp}: {sum(1 for x in bridges if x['group'] == grp)} names tied to a world-store item with evidence")
    say(f"G3 bridged propositions: {sum(1 for x in props_all if x[3].get('ref'))}; marked real: {sum(1 for x in props_all if x[3].get('real'))}")
    sup = [x for x in props_all if x[3].get("check") == "SUPPORTED"]
    say(f"E4 checks: {len(sup)} of {len(props_all)} test-unit propositions SUPPORTED by another sentence of their book "
        f"({100 * len(sup) / max(1, len(props_all)):.1f} %)")
    ssamp = random.Random(300 + it).sample(sup, min(30, len(sup))) if it >= 3 and chains and not knockout else []
    if os.path.exists(path):
        J = json.load(open(path, encoding="utf-8"))
        for name in ("items", "control", "pronouns", "checks", "bridges"):
            if name not in J: continue
            lab = [x for x in J[name] if x.get("ok") is not None]
            for grp in ("novels", "others"):
                lg = [x for x in lab if x["group"] == grp]
                say(f"precision {name} {grp}: {sum(x['ok'] for x in lg)}/{len(lg)}")
            say(f"precision {name} all: {sum(x['ok'] for x in lab)}/{len(lab)} = {sum(x['ok'] for x in lab) / max(1, len(lab)):.2f}")
    else:
        J = dict(note="labels are the BUILDER's judgement (disclosed): ok = the sentence says this", it=it,
                 items=[dict(group=g, book=b, sent=i, text=books[b].sents[i], prop=KB.say(p), kind=p["kind"],
                             check=p.get("check"), ok=None) for g, b, i, p in samp],
                 control=[dict(group=g, book=b, sent=i, text=books[b].sents[i], prop=e, ok=None) for g, b, i, e in csamp],
                 pronouns=[dict(group=g, book=b, sent=i, prev=books[b].sents[i - 1] if i else "", text=books[b].sents[i],
                                prop=KB.say(p), ok=None) for g, b, i, p in psamp],
                 checks=[dict(group=g, book=b, sent=i, text=books[b].sents[i], prop=KB.say(p), other=p["support"],
                              other_text=books[b].sents[p["support"]], ok=None) for g, b, i, p in ssamp],
                 bridges=random.Random(400 + it).sample(bridges, min(40, len(bridges))))
        json.dump(J, open(path, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
        say(f"wrote {path} for judging")
    return stats, props_all, books


if __name__ == "__main__":
    it = int(sys.argv[sys.argv.index("--it") + 1]) if "--it" in sys.argv else 1
    run(it, knockout="--knockout" in sys.argv, chains="--nochains" not in sys.argv)
