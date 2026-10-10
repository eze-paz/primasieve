"""R8b': the hand-rule event reader as the check on the learned proposer, offline on saved evaluation files.
For each item: parse the question into (role asked, verb, other role filler); run the EventReader over every hit
sentence; find events whose verb lemma matches; the proposal is COMMITTED if it names the asked role's filler of a
matching event (case-blind, either containing the other); otherwise "unknown". Also scored: the reader's own filler as
the answer (the hand-rule proposer over the same hits), and the union (reader's answer when it has one, else the
learned reply when the reader cannot read the hit).
Run: python learned/base/reader_check.py <eval json> [more]"""
import os, sys, re, json
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
os.chdir(ROOT); sys.path.insert(0, ROOT); sys.path.insert(0, HERE)
from b6_rwkv import hit
from guard import hits_of, norm, with_prompts
import battery

D = battery.door(); R = D.events.reader
SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'])")


AUXQ = ("was", "were", "is", "are", "did", "had", "has", "do", "does")
V2 = "--v2" in sys.argv or "--v22" in sys.argv or "--v3" in sys.argv   # R10: matcher v2 (developed on the validation set)
V22 = "--v22" in sys.argv or "--v3" in sys.argv   # R10b: v2.2


def parse_q(q):
    """-> (asked_role, verb_surface, other_text) for 'Who V X?' and 'What did A V?' shapes; None otherwise"""
    m = re.match(r"Who (\w+) (.+)\?$", q)
    if m and m.group(1).lower() not in AUXQ: return ("agent", m.group(1), m.group(2))
    if V2 and re.search(r"\b(in|with|for|on|at|to|from|of|by)\?$", q): return None     # v2: "...serve dinner in?" asks an adjunct, not a role
    m = re.match(r"What did (.+?) (\w+)(?: (?:to )?\w+)?\?$", q)          # v2: "What did Tomasz leave Rafal?" / "What did A refuse to do?"
    if m:
        if V2:                                                             # v2: the verb is the first KNOWN verb after a short agent
            words = q[len("What did "):-1].split()
            for i in range(1, min(4, len(words))):
                if words[i].lower() in R.verbs and words[i].lower() not in AUXQ: return ("patient", words[i], " ".join(words[:i]))
            if V22 and len(words) >= 2: return ("patient", words[1], words[0])  # v2.2: no known verb -> the word after a one-word agent; an unknown verb matches no event and falls to the model
            return None
        return ("patient", m.group(2), m.group(1))
    m = re.match(r"Who (was|were) (\w+ing)\b(.*)\?$", q)                   # R13: "Who was drinking at the stream?" -> the noun before "drinking"
    if m and V3: return ("progressive", m.group(2), m.group(3).strip())
    m = re.match(r"Who (was|were) (.+)\?$", q)
    if m: return ("agent", None, m.group(2))
    m = re.match(r"Who (had|has|have) (\w+) (.+)\?$", q)                   # R13: "Who had laughed at the mouse?"
    if m and V3: return ("agent", m.group(2), m.group(3))
    if V2:
        m = re.match(r"What (\w+) (.+)\?$", q)                             # v2: "What broke the fence?" asks for the agent
        if m and m.group(1).lower() not in AUXQ and m.group(1) != "was": return ("agent", m.group(1), m.group(2))
        m = re.match(r"Who (\w+) (\w+) (.+)\?$", q)                         # v2: "Who pulled him out?" -> verb + rest (pronoun object dropped)
        if m and m.group(1).lower() not in AUXQ: return ("agent", m.group(1), m.group(3))
    return None


V3 = "--v3" in sys.argv                           # R11: adjuncts (where / when / with what) from the matched event's sentence


def set_version(v="v3"):
    """engine.py: select the matcher version programmatically (the flags above are read from sys.argv at import)"""
    global V2, V22, V3
    V2 = v in ("v2", "v22", "v3"); V22 = v in ("v22", "v3"); V3 = v == "v3"
PLACE = r"(?:to|at|in|on|behind|under|across|near|into|toward|towards|over|through|beside)"
TIME = re.compile(r"\b(on (?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)|(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)|"
                  r"at (?:lunch|noon|dawn|dusk|midnight|night|sunset|sunrise)|the next (?:morning|day|evening|week)|in the (?:spring|autumn|summer|winter|morning|evening|afternoon)|"
                  r"in (?:spring|autumn|summer|winter|early summer|March|April|May|June|July|August|September|October|November|December|January|February)|"
                  r"every (?:\w+ )?(?:morning|evening|day|noon|night|week|Tuesday|Thursday|Monday|Sunday|Friday|winter|summer)|after (?:supper|dinner|lunch|dark|a year|a week)|before dark|"
                  r"one (?:morning|evening|afternoon|night|day|summer|year|foggy evening)|a week later|three days late|within two hours)\b", re.I)


PRONOUNS = {"he", "she", "they", "it", "him", "her", "them"}


def parse_adjunct(q):
    """-> (kind, verb_surface, agent_text) for 'Where did A V ...?', 'When did A V ...?', 'What did A V (it) with?', 'What did A use?'"""
    m = re.match(r"(Where|When|How) (?:did|was|were) (.+?) (\w+)(?: .*)?\?$", q)
    if m and m.group(3).lower() not in AUXQ: return (m.group(1).lower(), m.group(3), m.group(2))
    m = re.match(r"(Where|When) (?:did|was|were) (.+?)\?$", q)                          # "Where were the hives?" / "When were the tomatoes planted?"
    if m: return (m.group(1).lower(), None, m.group(2))
    m = re.match(r"What did (.+?) (\w+)(?: \w+)? with\?$", q)
    if m: return ("with", m.group(2), m.group(1))
    m = re.match(r"What did (.+?) use\?$", q)
    if m: return ("with", None, m.group(1))
    m = re.match(r"On which day (?:did|was|were) (.+?) (\w+)(?: .*)?\?$", q)
    if m: return ("when", m.group(2), m.group(1))
    return None


def adjunct_answer(question, hits):
    p = parse_adjunct(question)
    if p is None: return None
    kind, verb, agent = p
    for h in hits:
        for s in SENT.split(h):
            if norm(agent) not in PRONOUNS and not any(w in norm(s).split() for w in norm(agent).split() if len(w) > 2): continue
            sl = s
            if verb is not None:
                lem = R.verbs.get(verb.lower(), verb.lower()); pos = None
                for m in re.finditer(r"[A-Za-z']+", s):
                    w = m.group().lower()
                    if w == verb.lower() or R.verbs.get(w) == lem or w.startswith(lem[:4]): pos = m.end(); break
                if pos is None: continue
                sl = s[pos:]
            if kind == "where":
                if verb is not None and R.verbs.get(verb.lower(), verb.lower()) in ("reach", "enter", "leave", "visit"):   # R13: arrival verbs take the place as object
                    m = re.match(r"\s*((?:the |a |an |his |her |their )?[a-z][\w-]*(?: [a-z][\w-]*)?)", sl)
                    if m: return m.group(1).strip(), (None, s)
                m = re.search(rf"\b{PLACE} ((?:the |a |an |his |her |their |its )?[a-z][\w-]*(?: (?:of|the)? ?[a-z][\w-]*){{0,2}})", sl)
                if m: return re.sub(r"\s+(instead|and|but|then|where|while)\b.*$", "", m.group(1)).strip(), (None, s)
            elif kind == "how":                                                                  # R13: "How did the traveller cross?" -> "by the ford"
                m = re.search(r"\b(by|with|on|through) ((?:the |a |an |his |her |their )?[a-z][\w-]*(?: [a-z][\w-]*)?)", sl)
                if m: return (m.group(1) + " " + m.group(2)).strip(), (None, s)
            elif kind == "when":
                m = TIME.search(sl) or TIME.search(s)
                if m: return m.group(1), (None, s)
            elif kind == "with":
                m = re.search(r"\bwith ((?:the |a |an |his |her |their )?[a-z][\w-]*(?: [a-z][\w-]*){0,2})", sl)
                if m: return m.group(1).strip(), (None, s)
    return None


def resolve_names(evs):
    """v2: 'a boy named Erlend' / 'A fisherman called Sven' -> the reader gives a 'name'/'call' event; substitute the name
    for that description in the other events' agents"""
    alias = {}
    for e in evs:
        if e.get("verb") in ("name", "call") and e.get("patient") and e["patient"][:1].isupper(): alias[norm(e["agent"])] = e["patient"]
    out = []
    for e in evs:
        e = dict(e)
        if norm(e.get("agent", "")) in alias and e.get("verb") not in ("name", "call"): e["agent"] = alias[norm(e["agent"])]
        if e.get("patient"): e["patient"] = re.sub(r"^(him|her|them|it|me|us) ", "", e["patient"])   # 'gave him a pot of honey'
        out.append(e)
    return out


SEQUENTIAL = "--sequential" in sys.argv       # read each hit window's sentences in order so the reader resolves "He rowed it" from the sentence before


def events_in(hits):
    out = []
    for h in hits:
        if SEQUENTIAL: R.last_agent = None; R.last_patient = None
        for s in SENT.split(h):
            if not SEQUENTIAL: R.last_agent = None; R.last_patient = None
            try: evs = [e for e in R.read(s) if e.get("agent") and e.get("patient")]
            except Exception: evs = []
            for e in evs:
                if V3:                                                   # R13: an agent that follows a preposition ("behind a barrel and carried") is not an agent
                    ia = s.find(e["agent"])
                    if ia > 0 and re.search(r"\b(behind|under|in|on|at|from|with|by|to|into|near|over|across|through|of|for)\s*$", s[:ia], re.I): continue
                out.append(dict(e, _sent=s))
    return out


def match(a, b):
    a, b = norm(a), norm(b)
    return bool(a) and bool(b) and (a in b or b in a)


def check(item):
    p = parse_q(item["q"]); hits = hits_of(item["prompt"])
    if V3 and p is None:
        aa = adjunct_answer(item["q"], hits)
        if aa: return (item["reply"] if match(item["reply"], aa[0]) else "unknown"), aa[0]
    evs = events_in(hits)
    if V2: evs = resolve_names(evs)
    if p is None or not evs: return None, None
    role, verb, other = p
    if role == "progressive":                                                                # R13: the noun phrase right before the -ing verb in a hit
        for h in hits:
            m = re.search(rf"((?:the |a |an |his |her |their )?[A-Z]?[a-z]+) {re.escape(verb)}\b", h)
            if m and m.group(1).lower().split()[-1] not in ("was", "were", "is", "are", "been", "while", "and", "of"):
                return (item["reply"] if match(item["reply"], m.group(1)) else "unknown"), m.group(1)
        return None, None
    other_role = "patient" if role == "agent" else "agent"
    if V3 and re.search(r"\b(have|had|has|let|made|make)$", other): return None, None     # R11: causative tail ("the mayor have marked")
    cands = []; verb_only = []
    for e in evs:
        v_ok = verb is None or e.get("verb", "") and (R.verbs.get(verb.lower()) == e["verb"] or verb.lower().startswith(e["verb"][:4]))
        o_ok = match(other, e[other_role]) or any(w in norm(e[other_role]).split() for w in norm(other).split() if len(w) > 3)
        if v_ok and o_ok: cands.append(e[role])
        elif v_ok and verb is not None:
            # v2: reject when the question's other-role text names the event's ASKED role (a passive read as active)
            if not any(w in norm(e[role]).split() for w in norm(other).split() if len(w) > 3): verb_only.append(e[role])
    if not cands and V2 and len(set(norm(c) for c in verb_only)) == 1: cands = verb_only[:1]   # v2: the verb occurs in exactly one event among the hits
    if V2 and len(set(norm(c) for c in cands)) > 1: return None, None                       # v2: two different fillers match: the reader cannot decide; the model may
    if not cands and V3:                                                                     # R11: a role question with no event may still be an adjunct ("What did Sven use?")
        aa = adjunct_answer(item["q"], hits)
        if aa: return (item["reply"] if match(item["reply"], aa[0]) else "unknown"), aa[0]
    if not cands: return None, None
    committed = item["reply"] if any(match(item["reply"], c) for c in cands) else "unknown"
    return committed, cands[0]


def main():
    out = []
    for path in [a for a in sys.argv[1:] if not a.startswith("--")]:
        os.chdir(HERE); items = with_prompts(path); os.chdir(ROOT)
        raw = sum(x["hit"] for x in items); n = len(items); c_right = c_wrong = r_right = r_wrong = u_right = u_wrong = readable = 0
        for x in items:
            committed, reader_ans = check(x)
            if committed is None:                      # the reader cannot read the hit for this question: keep the proposal
                u = x["reply"]; c = x["reply"]; r = "unknown"
            else:
                readable += 1; c = committed; r = reader_ans; u = reader_ans
            for name, ans in (("c", c), ("r", r), ("u", u)):
                ok = hit(ans, x["gold"]); wrong = (not ok) and "unknown" not in ans.lower()
                if name == "c": c_right += ok; c_wrong += wrong
                elif name == "r": r_right += ok; r_wrong += wrong
                else: u_right += ok; u_wrong += wrong
        print(f"{path}: raw {raw}/{n} | reader could read {readable} | committed-if-reader-agrees {c_right} right {c_wrong} wrong | "
              f"reader alone {r_right} right {r_wrong} wrong | reader-else-model {u_right} right {u_wrong} wrong", flush=True)
        out.append(dict(file=path, raw=raw, n=n, readable=readable, committed=(c_right, c_wrong), reader=(r_right, r_wrong), union=(u_right, u_wrong)))
    json.dump(out, open(os.path.join(HERE, "reader_check_results.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
