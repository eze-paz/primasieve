"""THE REQUEST ACT -- the gate (chat_request_prereg.md): a multi-word text only the dictionary can gloss is an INTENT GUESS,
confirmed or declined per skeleton by feedback (E-10's frames and their negative half); a lone word stays a definition.
Zero LLM. Offline sources only.

Usage:  python chat_request.py"""
import os, sys, time, random, re

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "emergence"))
from core.registry import selfcheck
from frames import realize, parse, canonical, FOUND, ACK_K, REQUEST
import chat
import chat_acts

T0 = time.time()


def say(s=""): print(str(s).encode("ascii", "replace").decode(), flush=True)


def rt(frame, seed):
    return sum(parse(realize(frame, random.Random(seed * 10 + i))) == canonical(frame) for i in range(5)), 5


if __name__ == "__main__":
    selfcheck(__file__)
    say("REQUEST ACT -- guess, then learn per skeleton; a lone word is a definition.\n")
    fails = []; rt_ok = rt_n = 0
    requests = [t for t, l in chat_acts.ACTS if l == "PROPOSE" and len(t.split()) >= 2 and t not in ("what is the capital of", "???")]
    # ---- Q1 cold
    w, df = chat.build_worlds(); D = chat.Door(w, df, seed=21)
    plain = 0; acts = {}
    for t in requests:
        r = D.turn(t); acts[t] = r.get("act"); plain += (r["frame"]["kind"] == FOUND and not r["frame"].get("guess"))
        o, k = rt(r["frame"], rt_n); rt_ok += o; rt_n += k
        say(f"    {t[:40]!r:44s} {str(r.get('act')):8s} {r['reply'][:120]}")
    ga = sum(1 for a in acts.values() if a in ("GUESS", ACK_K, "PROPOSE")); ok1 = plain == 0 and ga >= 0.90 * len(requests)
    say(f"\nQ1  COLD over {len(requests)} requests: plain definitions {plain}; handled (GUESS+ACK+PROPOSE) {ga}; acts {dict((a, list(acts.values()).count(a)) for a in set(acts.values()))}   [0, >= 0.90 -> {'PASS' if ok1 else 'FAIL'}]")
    if not ok1: fails.append("Q1")
    # ---- Q2 learning
    w2, df2 = chat.build_worlds(); D2 = chat.Door(w2, df2, seed=22); line = []
    # the hole is E-10's topic (the rarest symbol): the slot words are rarer than "poem" (291) and than "what" (2194)
    for t in ["write a poem about paris", "wrong", "write a poem about lisbon", "wrong", "write a poem about kyoto",
              "what is a dog", "correct", "what is a cat", "correct", "what is a fox", "a quick brown dog"]:
        r = D2.turn(t); line.append((t, r.get("act"), bool(r["frame"].get("guess"))))
        if r.get("act") in ("GUESS", REQUEST, FOUND): o, k = rt(r["frame"], rt_n); rt_ok += o; rt_n += k
    for t, a, g in line: say(f"    {t[:30]!r:34s} {str(a):9s} guess={g}")
    got = {t: (a, g) for t, a, g in line}
    ok2 = got["write a poem about kyoto"][0] == REQUEST and got["what is a fox"] == (FOUND, False) and got["a quick brown dog"][0] == "GUESS" \
        and got["write a poem about paris"][0] == "GUESS" and got["what is a dog"][0] == "GUESS"
    say(f"Q2  LEARNING: declined skeleton -> REQUEST {got['write a poem about kyoto']}; accepted skeleton -> plain FOUND {got['what is a fox']}; a new skeleton -> GUESS {got['a quick brown dog']}; frames {[(' '.join(s or '_' for s in f['skeleton']), f['state']) for f in D2.S.frames]}   [{'PASS' if ok2 else 'FAIL'}]")
    if not ok2: fails.append("Q2")
    # ---- Q3 lone word
    w3, df3 = chat.build_worlds(); D3 = chat.Door(w3, df3, seed=23); lone = {}
    for t in ["serendipity", "pomegranate", "dog?"]:
        r = D3.turn(t); lone[t] = (r["frame"]["kind"], bool(r["frame"].get("guess")))
        o, k = rt(r["frame"], rt_n); rt_ok += o; rt_n += k
    ok3 = all(v == (FOUND, False) for v in lone.values())
    say(f"Q3  LONE WORD: {lone}   [plain FOUND -> {'PASS' if ok3 else 'FAIL'}]")
    if not ok3: fails.append("Q3")
    say(f"Q4  ROUND TRIP: {rt_ok}/{rt_n}   [100% -> {'PASS' if rt_ok == rt_n else 'FAIL'}]")
    if rt_ok != rt_n: fails.append("Q4")
    # ---- Q6 no words
    lits = set()
    for m in ("resolve.py", "session.py"):
        src = open(os.path.join(HERE, "core", m), encoding="utf-8").read()
        body = src[src.index("def decline("):] if m == "resolve.py" else src
        lits |= {(m, l) for l in re.findall(r'"([^"\n]*)"', body.split('"""', 2)[-1])}
    frame_keys = set(re.findall(r'"([^"\n]*)"', open(os.path.join(HERE, "core", "reason.py"), encoding="utf-8").read()))
    words = {x for t in requests + list(got) + list(lone) for x in t.lower().split()}
    leak = sorted((m, l) for m, l in lits if l.lower() in words and l not in frame_keys)
    say(f"Q6  NO WORDS: literals sharing a token with an utterance: {leak}   [none -> {'PASS' if not leak else 'FAIL'}]")
    if leak: fails.append("Q6")
    say(f"\n    runtime {time.time()-T0:.0f} s")
    say(f"REQUEST ACT: {'PASS' if not fails else 'FAIL ' + ','.join(fails)} -- cold plain definitions {plain}/{len(requests)}, learning {'ok' if ok2 else 'no'}, round trip {rt_ok}/{rt_n}")
    sys.exit(0 if not fails else 1)
