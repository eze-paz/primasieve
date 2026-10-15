"""R27 P1: answers realised as full sentences (R27_prereg.md). Run: py -3.12 r27_answer.py"""
import os, sys, re, json, statistics as st
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE)); os.chdir(HERE)
import r24_dict as Dct
from b6_rwkv import hit
Dct.load(); PAST = {}
for f, b in Dct.EXC.items():
    if f != b and not f.endswith(("n", "ing", "s")) and (b not in PAST or len(f) < len(PAST[b])): PAST[b] = f
PAST.update({"be": "was", "have": "had", "do": "did", "go": "went", "see": "saw", "come": "came", "give": "gave", "take": "took", "get": "got", "make": "made", "know": "knew", "find": "found", "tell": "told", "say": "said", "leave": "left", "bring": "brought", "buy": "bought", "think": "thought", "put": "put", "set": "set", "let": "let", "cut": "cut", "read": "read", "keep": "kept", "hold": "held", "run": "ran", "win": "won", "sit": "sat", "stand": "stood", "lose": "lost", "pay": "paid", "send": "sent", "build": "built", "fall": "fell", "eat": "ate", "drink": "drank", "write": "wrote", "ride": "rode", "fly": "flew", "grow": "grew", "throw": "threw", "draw": "drew", "wear": "wore", "sell": "sold", "teach": "taught", "catch": "caught", "feel": "felt", "meet": "met", "lead": "led", "hide": "hid", "spend": "spent", "lend": "lent", "sleep": "slept", "swim": "swam", "sing": "sang", "begin": "began", "break": "broke", "speak": "spoke", "steal": "stole", "wake": "woke", "choose": "chose", "forget": "forgot", "hang": "hung", "shake": "shook", "dig": "dug", "feed": "fed", "light": "lit", "bite": "bit", "blow": "blew"})
def past(v):
    v = v.lower()
    if v in PAST: return PAST[v]
    if v.endswith("e"): return v + "d"
    if v.endswith("y") and len(v) > 2 and v[-2] not in "aeiou": return v[:-1] + "ied"
    if len(v) <= 4 and len(v) >= 3 and v[-1] not in "aeiouwxy" and v[-2] in "aeiou" and v[-3] not in "aeiou": return v + v[-1] + "ed"
    return v + "ed"
QUOTE = '--quote' in sys.argv or os.environ.get('R27_QUOTE') == '1'
AUX_PAST = {"did": None, "does": None, "do": None}
def cap(s): s = s.strip(); return (s[0].upper() + s[1:]) if s else s
def sentence(q, a, text=''):
    qw = q.strip().rstrip("?").split(); wh = qw[0].lower(); rest = qw[1:]
    if not rest: return None
    if text:                                                                                  # P1d: the story's determiner before the answer
        m0 = re.search(r"\b(the|a|an|his|her|their|its|my|our)\s+" + re.escape(a) + r"\b", text, re.I)
        if m0 and a.split()[0].lower() not in ("the", "a", "an", "his", "her", "their", "its", "my", "our"): a = m0.group(1).lower() + m0.group(0)[len(m0.group(1)):]
        if wh in ("where", "when") and a.split()[0].lower() not in ("in", "on", "at", "into", "onto", "under", "near", "behind", "by", "to", "from", "inside", "beside", "across", "over", "through", "outside", "before", "after", "during", "until"):
            m1 = re.search(r"\b(in|on|at|into|onto|under|near|behind|by|to|from|inside|beside|across|over|through|outside|before|after|during|until)\s+" + re.escape(a) + r"\b", text, re.I)
            if m1: a = m1.group(1).lower() + " " + a                                          # P1e (1): the story's preposition
    if a.split()[0].lower() in ("at", "on", "in", "by", "the", "a", "an", "near", "under", "behind", "before", "after", "every", "that", "this", "last", "next", "one", "early", "late"):
        a = a[0].lower() + a[1:]                                                              # P1b: no capital mid-sentence
    front = ""
    m_ = re.search(r"\s+(at the end|in the end|finally|at first|now)$", " ".join(rest), re.I)
    if m_: front = m_.group(1)[0].upper() + m_.group(1)[1:] + ", "; rest = " ".join(rest)[:m_.start()].split()   # P1b: modifier to the front
    story_words = set(w.lower() for w in re.findall(r"[A-Za-z']+", text))
    def fin(s):
        s = re.sub(r"\s+", " ", s).strip(); s = (front + s) if front else cap(s); return s + ("" if s.endswith((".", "!", "?")) else ".")
    if wh in ("who", "what", "which") and rest[0].lower() not in ("did", "does", "do", "was", "were", "is", "are", "had", "has", "will", "would", "could"):
        return fin(a + " " + " ".join(rest))                                                  # subject question
    if rest[0].lower() in ("did", "does", "do"):
        aux = rest[0].lower(); body = rest[1:]
        cands = [i for i, w in enumerate(body) if i > 0 and (Dct.mainly_verb(w) or Dct.verb_base(w.lower()))]
        vi = next((i for i in cands if past(body[i]) in story_words), next((i for i in cands if (body[i].lower() + "s") in story_words), cands[-1] if cands else None))   # P1b: a verb shows its past form in the story
        if vi is None: return None
        if QUOTE and text and (body[-1].lower() == "do" or not (past(body[vi]) in story_words or (body[vi].lower() + "s") in story_words)): return "__QUOTE__"   # P1e (2)
        v = body[vi]; vf = past(v) if aux == "did" else (v + "s" if aux == "does" else v)
        subj, after = " ".join(body[:vi]), " ".join(body[vi + 1:])
        PREPS = ("to", "at", "in", "on", "from", "with", "for", "into", "by", "near", "under", "behind", "after", "before", "over", "onto", "towards", "toward", "about")
        if after.split() and after.split()[-1].lower() in PREPS and a.split()[0].lower() == after.split()[-1].lower(): after = " ".join(after.split()[:-1])   # P1c (a)
        if after.lower() in PREPS: return fin(f"{subj} {vf} {after} {a}" if not a.lower().startswith(after.lower() + " ") else f"{subj} {vf} {a}")   # P1c (b)
        if wh in ("who", "what", "whom"):
            if after and after.split()[0].lower() not in ("to", "at", "in", "on", "from", "with", "for", "into", "by", "near", "under", "behind", "after", "before", "while", "when", "during", "about", "over"):
                return fin(f"{subj} {vf} {after} {a}")                                          # P1b: 'gave Osip the pot of honey'
            return fin(f"{subj} {vf} {a} {after}")
        if wh == "why": return fin(f"{subj} {vf} {after} because {a}")
        if wh in ("where", "when", "how"):
            if after.split() and a.split() and after.split()[-1].lower() == a.split()[0].lower(): after = " ".join(after.split()[:-1])   # P1c (a)
            return fin(f"{subj} {vf} {after} {a}")
        return None
    if rest[0].lower() in ("had", "has") and wh == "who": return fin(f"{a} {rest[0].lower()} {' '.join(rest[1:])}")   # P1b
    if rest[0].lower() in ("was", "were", "is", "are", "had", "has"):
        be, bw = rest[0].lower(), rest[1:]
        k = 0
        if bw and bw[0].lower() in ("the", "a", "an", "his", "her", "their", "its", "my") : k = 2
        while k < len(bw) and bw[k][0].isupper(): k += 1
        k = max(k, 1)
        if wh == "who": return fin(f"{a} {be} {' '.join(bw)}")                                # P1c (c)
        if k < len(bw) and wh in ("where", "when", "why"):                                   # P1b: copula after the subject phrase
            subj, pred = " ".join(bw[:k]), " ".join(bw[k:])
            mt = re.match(r"^((?:at|by|in|on|during)\s+(?:the\s+)?(?:dawn|dusk|noon|midnight|night|lunchtime|morning|evening|afternoon|end|first|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|\d+)\b.*?)$", pred, re.I)
            if mt and wh == "where":                                                         # P1c (d): 'At dawn, the van was outside the bakery'
                return fin(f"{mt.group(1)[0].upper() + mt.group(1)[1:]}, {subj[0].lower() + subj[1:] if subj.split()[0].lower() in ('the', 'a', 'an', 'his', 'her', 'their', 'its', 'my') else subj} {be} {a}")
            if wh == "why": return fin(f"{subj} {be} {pred} because {a}")
            return fin(f"{subj} {be} {pred} {a}")
        body = " ".join(bw)
        if wh in ("who", "what") and body: return fin(f"{a} {be} {body}") if wh == "who" and len(body.split()) <= 3 else fin(f"{body} {be} {a}")
        if wh in ("where", "when"): return fin(f"{body} {be} {a}")
        if wh == "why": return fin(f"{body} {be} so because {a}")
    if wh == "how" and rest and rest[0].lower() in ("many", "much"):
        noun = rest[1] if len(rest) > 1 else ""; tail = rest[2:]
        if tail and tail[0].lower() in ("did", "does", "do"):
            body = tail[1:]; vi = next((i for i, w in enumerate(body) if i > 0 and Dct.mainly_verb(w)), None)
            if vi is not None: return fin(f"{' '.join(body[:vi])} {past(body[vi]) if tail[0].lower() == 'did' else body[vi]} {a} {noun} {' '.join(body[vi + 1:])}")
        return fin(f"There were {a} {noun} {' '.join(tail)}")
    if wh == "whose": return fin(f"It was {a}'s {' '.join(rest[0:1])}")
    return None
if __name__ == "__main__":
    st_ = json.load(open("val_all13.json", encoding="utf-8"))["stories"]; items = [(s["text"], q, g) for s in st_ for q, g in s["qs"]]
    pol = json.load(open("r26_policy_answers.json", encoding="utf-8"))
    UN = list(range(310, 510)) + list(range(910, 2510)) if '--untouched' in sys.argv else list(range(310)) + list(range(510, 910))   # P1b: develop on practice
    rows = []
    for i in UN:
        a = pol[i]
        if not a: continue
        text, q, g = items[i]; s = sentence(q, a, text)
        story_s = next((x for x in re.split(r"(?<=[.!?])\s+", text) if a.lower() in x.lower()), None)
        if s == "__QUOTE__": s = story_s                                                       # P1e (2): quote the story
        rows.append(dict(i=i, q=q, a=a, s=s, story=story_s, gold_span=bool(hit(a, g)), gold_sent=bool(s and hit(s, g))))
    json.dump(rows, open("r27_p1_sentences.json", "w", encoding="utf-8"), indent=0)
    made = [r for r in rows if r["s"]]; print(f"P1 answers {len(rows)}, sentences made {len(made)}; gold kept where the span had it: {sum(r['gold_sent'] for r in made if r['gold_span'])} / {sum(r['gold_span'] for r in made)}", flush=True)
    for r in made[:12]: print("  ", r["q"], "->", r["s"])
