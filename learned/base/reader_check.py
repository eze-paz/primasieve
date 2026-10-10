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
V2 = "--v2" in sys.argv or "--v22" in sys.argv   # R10: matcher v2 (developed on the validation set)
V22 = "--v22" in sys.argv                         # R10b: v2.2


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
    m = re.match(r"Who (was|were) (.+)\?$", q)
    if m: return ("agent", None, m.group(2))
    if V2:
        m = re.match(r"What (\w+) (.+)\?$", q)                             # v2: "What broke the fence?" asks for the agent
        if m and m.group(1).lower() not in AUXQ and m.group(1) != "was": return ("agent", m.group(1), m.group(2))
        m = re.match(r"Who (\w+) (\w+) (.+)\?$", q)                         # v2: "Who pulled him out?" -> verb + rest (pronoun object dropped)
        if m and m.group(1).lower() not in AUXQ: return ("agent", m.group(1), m.group(3))
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
            try: out += [e for e in R.read(s) if e.get("agent") and e.get("patient")]
            except Exception: pass
    return out


def match(a, b):
    a, b = norm(a), norm(b)
    return bool(a) and bool(b) and (a in b or b in a)


def check(item):
    p = parse_q(item["q"]); hits = hits_of(item["prompt"]); evs = events_in(hits)
    if V2: evs = resolve_names(evs)
    if p is None or not evs: return None, None
    role, verb, other = p; other_role = "patient" if role == "agent" else "agent"
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
