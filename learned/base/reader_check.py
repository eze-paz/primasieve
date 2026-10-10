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


def parse_q(q):
    """-> (asked_role, verb_surface, other_text) for 'Who V X?' and 'What did A V?' shapes; None otherwise"""
    m = re.match(r"Who (\w+) (.+)\?$", q)
    if m and m.group(1).lower() not in ("was", "were", "is", "are", "did", "had", "has"): return ("agent", m.group(1), m.group(2))
    m = re.match(r"What did (.+?) (\w+)\?$", q)
    if m: return ("patient", m.group(2), m.group(1))
    m = re.match(r"Who (was|were) (.+)\?$", q)
    if m: return ("agent", None, m.group(2))
    return None


def events_in(hits):
    out = []
    for h in hits:
        for s in SENT.split(h):
            try: out += [e for e in R.read(s) if e.get("agent") and e.get("patient")]
            except Exception: pass
    return out


def match(a, b):
    a, b = norm(a), norm(b)
    return bool(a) and bool(b) and (a in b or b in a)


def check(item):
    p = parse_q(item["q"]); hits = hits_of(item["prompt"]); evs = events_in(hits)
    if p is None or not evs: return None, None
    role, verb, other = p; other_role = "patient" if role == "agent" else "agent"
    cands = []
    for e in evs:
        v_ok = verb is None or e.get("verb", "") and (R.verbs.get(verb.lower()) == e["verb"] or verb.lower().startswith(e["verb"][:4]))
        o_ok = match(other, e[other_role]) or any(w in norm(e[other_role]).split() for w in norm(other).split() if len(w) > 3)
        if v_ok and o_ok: cands.append(e[role])
    if not cands: return None, None
    committed = item["reply"] if any(match(item["reply"], c) for c in cands) else "unknown"
    return committed, cands[0]


def main():
    out = []
    for path in sys.argv[1:]:
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
