"""R16: the exact reader induced from teaching cases with the project's inductive core (core/constructions.py), replacing
the hand-written matcher. Nothing here says how any sentence shape means; the shapes are learned.

A teaching case is (window, question, answer). The question is reduced to its SHAPE: its words with the anchor mention
(a name or a determiner noun phrase) replaced by a slot. In the window, the run of symbols strictly between the anchor
mention and the answer mention, with the two mention types as its head and names inside it masked, is observed as an
instance of (shape, direction). The core admits a run for (shape, direction) when it has seen it >= least times and
>= share of its sightings carry that label. Reading a new (window, question): find the anchor in the window; for every
other mention, read the run between them; an admitted run for the question's shape yields that mention; none -> abstain.
Run: python learned/base/induced_reader.py   (validation; growth test; tests once if R16-a passes)"""
import os, sys, re, json, random
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT); sys.path.insert(0, HERE)
from core.constructions import Constructions, FORWARD, BACKWARD
from b6_rwkv import hit

SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'])")
TOK = re.compile(r"[A-Za-z][\w'-]*|[.,;:!?\"]")
DET = {"the", "a", "an", "his", "her", "their", "its", "my", "our", "your", "two", "three", "four", "five", "every", "one", "some"}
QWORDS = {"who", "what", "where", "when", "why", "how", "whom", "whose", "which", "did", "was", "were", "is", "are", "had", "has", "do", "does"}


STARTERS = {"The", "A", "An", "One", "When", "In", "On", "At", "Her", "His", "Their", "After", "Then", "Now", "But", "And", "It", "He", "She", "They", "Every",
            "Two", "Three", "Four", "Five", "By", "For", "From", "With", "There", "This", "That", "Its", "So", "Yet", "Later", "Once", "Soon", "What", "Who", "Where", "When", "Why", "How"}
STOPNP = {"and", "or", "but", "that", "who", "which", "when", "to", "with", "at", "in", "on", "for", "of", "from", "by", "without", "into", "across", "behind", "under", "near"}


def verbish(w):
    w = w.lower()
    return w in IRREG or (w.endswith("ed") and len(w) > 4) or (w.endswith("ing") and len(w) > 5)


def mentions(text):
    """(start, end, type) of names (capitalised words, sentence-initial ones unless common starters) and determiner-led
    noun phrases (determiner + up to two words, never running into a verb-like word)"""
    toks = list(TOK.finditer(text)); out = []; i = 0
    while i < len(toks):
        w = toks[i].group()
        if w[:1].isupper() and w not in STARTERS and w.lower() not in QWORDS and w.isalpha():
            j = i
            while j + 1 < len(toks) and toks[j + 1].group()[:1].isupper() and toks[j + 1].group().isalpha() and toks[j + 1].group() not in STARTERS: j += 1
            out.append((toks[i].start(), toks[j].end(), "name")); i = j + 1; continue
        if w.lower() in DET and i + 1 < len(toks) and toks[i + 1].group()[:1].isalpha() and not verbish(toks[i + 1].group()):
            j = i + 1
            while (j + 1 < len(toks) and toks[j + 1].group()[:1].islower() and toks[j + 1].group().lower() not in DET and j - i < 2
                   and toks[j + 1].group() not in STOPNP and not verbish(toks[j + 1].group())): j += 1
            out.append((toks[i].start(), toks[j].end(), "np")); i = j + 1; continue
        i += 1
    return out


def anchor_of(question):
    """the question's anchor mention: a name if any, else its last noun phrase, else its last bare word; (text, type)"""
    ms = mentions(question)
    names = [m for m in ms if m[2] == "name"]
    if names: m = names[0]; return (question[m[0]:m[1]], "name")
    if ms: m = ms[-1]; return (question[m[0]:m[1]], "np")
    toks = [t for t in TOK.findall(question) if t.isalpha()]
    return (toks[-1], "bare") if len(toks) >= 3 and toks[-1].lower() not in QWORDS else None


def find_anchor(window, anc):
    """spans of the anchor in the window: by mention for names and noun phrases, by word for a bare noun"""
    if anc[1] == "bare":
        return [(m.start(), m.end(), "bare") for m in re.finditer(rf"\b{re.escape(anc[0])}\b", window, re.I)]
    return [m for m in mentions(window) if window[m[0]:m[1]].lower() == anc[0].lower()]


IRREG = {"took": "take", "gave": "give", "went": "go", "found": "find", "bought": "buy", "made": "make", "ate": "eat", "saw": "see", "ran": "run",
         "sold": "sell", "told": "tell", "left": "leave", "wrote": "write", "sat": "sit", "fell": "fall", "came": "come", "began": "begin", "broke": "break",
         "stole": "steal", "stood": "stand", "kept": "keep", "held": "hold", "built": "build", "brought": "bring", "caught": "catch", "taught": "teach",
         "sang": "sing", "drank": "drink", "rang": "ring", "hid": "hide", "lost": "lose", "led": "lead", "fed": "feed", "met": "meet", "sent": "send",
         "spent": "spend", "paid": "pay", "said": "say", "heard": "hear", "knew": "know", "grew": "grow", "flew": "fly", "drew": "draw", "threw": "throw",
         "swam": "swim", "rode": "ride", "drove": "drive", "woke": "wake", "shook": "shake", "forgot": "forget", "got": "get", "put": "put", "cut": "cut",
         "hit": "hit", "let": "let", "shut": "shut", "read": "read", "set": "set", "won": "win", "lit": "light", "slept": "sleep", "swept": "sweep", "crept": "creep",
         "fought": "fight", "thought": "think", "sought": "seek", "wore": "wear", "tore": "tear", "spoke": "speak", "chose": "choose", "froze": "freeze", "rose": "rise"}


def lemma(w):
    w = w.lower()
    if w in IRREG: return IRREG[w]
    for suf in ("ied", "ies", "ed", "ing", "es", "s"):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            stem = w[:-len(suf)] + ("y" if suf in ("ied", "ies") else "")
            return stem[:-1] if suf in ("ed", "ing") and len(stem) > 3 and stem[-1] == stem[-2] else stem
    return w


def same_verb(a, b):
    la, lb = lemma(a), lemma(b)
    return la == lb or (len(la) >= 4 and len(lb) >= 4 and la[:4] == lb[:4])


def verb_of(toks):
    """the question's verb: for 'what/where/when/how did <A> V ...' the word after <A>; for 'who/what V ...' the second word"""
    if len(toks) >= 2 and toks[1] in ("did", "was", "were", "had", "has", "does", "do"):
        if "<a>" in toks:
            k = toks.index("<a>")
            if k + 1 < len(toks) and toks[k + 1] not in DET: return toks[k + 1]
        return None
    return toks[1] if len(toks) >= 2 and toks[1] not in ("was", "were", "is", "are", "had", "has") else None


def shape_of(question, anchor):
    """question words with the anchor as <a> and its verb as <v>; returns (shape, verb)"""
    q = question.replace(anchor, "AAANCHOR") if anchor else question
    toks = [("<a>" if w == "AAANCHOR" else w.lower()) for w in TOK.findall(q) if w not in "?."]
    v = verb_of(toks)
    if v: toks = [("<v>" if t == v else t) for t in toks]
    return tuple(toks), v


def run_between(text, a, b, verb=None):
    """symbols strictly between mention spans a and b (ordered): names masked, the question's verb marked <v>, lowercased"""
    lo, hi = (a[1], b[0]) if a[0] < b[0] else (b[1], a[0])
    toks = []
    for t in TOK.findall(text[lo:hi]):
        if verb and t[:1].islower() and same_verb(t, verb): toks.append("<v>")
        elif t[:1].isupper(): toks.append("NAME")
        else: toks.append(t.lower())
    return tuple(toks)


class InducedReader:
    def __init__(self, least=3, share=0.8, max_len=8):
        self.C = Constructions(least=least, share=share, max_len=max_len); self.cases = 0

    def teach(self, window, question, answer):
        anc = anchor_of(question)
        if not anc: return
        a_hits = find_anchor(window, anc)
        ans_hits = [m for m in mentions(window) if window[m[0]:m[1]].lower() == answer.lower() or window[m[0]:m[1]].lower().endswith(" " + answer.lower())]
        if not a_hits or not ans_hits: return
        shape, v = shape_of(question, anc[0]); a = a_hits[0]; b = ans_hits[0]
        if a[0] == b[0]: return
        d = FORWARD if a[0] < b[0] else BACKWARD
        run = (anc[1], b[2]) + run_between(window, a, b, v)
        if v and "<v>" not in run: return                                    # the question's verb must stand between the mentions
        self.C.observe(run, {(shape, d)}); self.cases += 1

    def settle(self): self.C.settle()

    def read(self, window, question):
        anc = anchor_of(question)
        if not anc: return None
        shape, v = shape_of(question, anc[0]); ms = mentions(window)
        a_hits = find_anchor(window, anc)
        if not a_hits: return None
        found = []
        for a in a_hits:
            for b in ms:
                if b[0] == a[0]: continue
                d = FORWARD if a[0] < b[0] else BACKWARD
                run = (anc[1], b[2]) + run_between(window, a, b, v)
                if v and "<v>" not in run: continue
                if len(run) - 2 > self.C.max_len: continue
                got = self.C.read(run)
                if got and any(lab == (shape, d) for lab, *_ in got): found.append(window[b[0]:b[1]])
        if len(set(f.lower() for f in found)) == 1: return found[0]
        return None


def windows(text):
    s = [x.strip() for x in SENT.split(text) if x.strip()]
    return [" ".join(s[max(0, k - 1):k + 1]) for k in range(len(s))]


def teach_from_stories(R, stories, limit=None):
    for s in stories[:limit] if limit else stories:
        ws = windows(s["text"])
        for q, gold in s["qs"]:
            for w in ws:
                if any(g.lower() in w.lower() for g in gold):
                    R.teach(w, q, next(g for g in gold if g.lower() in w.lower())); break


def evaluate(R, stories, replies, label):
    rep = replies["items"]; i = 0; matched = right = wrong = m_right = model_right = 0
    for s in stories:
        ws = windows(s["text"])
        for q, gold in s["qs"]:
            x = rep[i]; i += 1; ans = None
            for w in ws:
                ans = R.read(w, q)
                if ans: break
            model_right += x["hit"]
            if ans is not None:
                matched += 1; ok = hit(ans, gold); right += ok; wrong += (not ok); final = ans
            else: final = x["reply"]
            m_right += hit(final, gold)
    print(f"{label}: induced reader matched {matched}/{i}, right {right} wrong {wrong} (precision {right / max(1, matched):.2f}) | merged {m_right}/{i} (model alone {model_right})", flush=True)
    return matched, right, wrong, m_right, model_right, i


def main():
    B = HERE; L = lambda n: json.load(open(os.path.join(B, n), encoding="utf-8"))
    stories = L("stories_train_v2.json"); R = InducedReader()
    teach_from_stories(R, stories, limit=4000); R.settle()
    print(f"taught {R.cases} cases from the generated stories; admitted constructions {len(R.C.admitted)}", flush=True)
    vs, vf = L("val_stories.json")["stories"], L("val_fables.json")["stories"]
    rs, rf = L("b6_rwkv_val_ckpt_read1b.json"), L("b6_rwkv_valfables_ckpt_read1b.json")
    a = evaluate(R, vs, rs, "val stories"); b = evaluate(R, vf, rf, "val fables")
    matched, right, wrong = a[0] + b[0], a[1] + b[1], a[2] + b[2]; prec = right / max(1, matched)
    print(f"validation (80): matched {matched} precision {prec:.2f} (R16-a bar: >= 43 at >= 0.95)")
    # R16-b growth: teach the other set's own cases (gold answers stand in for verified answers) and re-read
    Rg = InducedReader(); teach_from_stories(Rg, stories, limit=4000); teach_from_stories(Rg, vs); Rg.settle()
    g1 = evaluate(Rg, vf, rf, "fables after learning from stories")
    Rg2 = InducedReader(); teach_from_stories(Rg2, stories, limit=4000); teach_from_stories(Rg2, vf); Rg2.settle()
    g2 = evaluate(Rg2, vs, rs, "stories after learning from fables")
    res = dict(validation=dict(matched=matched, precision=prec, merged=a[3] + b[3], model=a[4] + b[4]), growth=dict(fables=g1[:3], stories=g2[:3], before=dict(fables=b[:3], stories=a[:3])))
    if matched >= 43 and prec >= 0.95:
        print("R16-a PASS -> B6 once:")
        res["b6"] = evaluate(R, json.load(open(os.path.join(ROOT, "tests", "battery", "stories.json"), encoding="utf-8"))["stories"], L("b6_rwkv_ckpt_read1b.json"), "B6 (0.4B model second)")
    else: print("R16-a MISS -> tests not run")
    json.dump(res, open(os.path.join(B, "r16_results.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
