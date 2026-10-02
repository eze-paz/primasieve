"""CHAT PROSE -- the gate for phase C (chat_prose_prereg.md): replies as sentences over the understood structure, zero
LLM; exact inverse; faithfulness to the user's words; variety; the it.10 form judge as the printed frontier.

Usage:  python chat_prose.py"""
import os, sys, time, random, re, collections, statistics

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "emergence"))
from core.reason import READINGS, PARTIAL, Composite, _spans, symbols
from core.verdict import ATTRIBUTED, COMMIT
from core.registry import selfcheck
from core.seqform import ClassBigram, unkify, apply_unk, sentences
import frames
from frames import realize, parse, canonical, ANSWER, READ, PART, FOUND, PROPOSE, CONJ, META_K, CHECK_K, ACK_K
import chat
import chat_acts
import turns as TU
import fluency_form as FF

T0 = time.time()


def say(s=""): print(str(s).encode("ascii", "replace").decode(), flush=True)


def round_trip(frame, seed, k=5):
    ok = 0
    for i in range(k): ok += parse(realize(frame, random.Random(seed * 10 + i))) == canonical(frame)
    return ok, k


if __name__ == "__main__":
    selfcheck(__file__)
    say("CHAT PROSE -- sentences over the understood structure; exact inverse; the user's words; variety; the form judge.\n")
    fails = []
    # ---------------------------------------------------------------- the material: phase A session, acts script, dialogues
    worlds, df = chat.build_worlds(); DA = chat.Door(worlds, df, seed=11)
    recs = []
    for text, typ, gold in chat.held_out(): recs.append(("A", DA.turn(text)))
    msA = [r["ms"] for _, r in recs]
    ws2, df2 = chat.build_worlds(seeded=True); DB = chat.Door(ws2, df2, seed=12)
    for text, label in chat_acts.ACTS: recs.append(("B", DB.turn(text)))
    for d in chat.W4_DIALOGUES + [d for _, d in TU.DIALOGUES]:
        w3, df3 = chat.build_worlds(); D3 = chat.Door(w3, df3, seed=13)
        for text, gold, dep in d: recs.append(("D", D3.turn(text)))
    say(f"    material: {len(recs)} turns in {time.time()-T0:.0f} s")
    say("    sample replies:")
    shown = set()
    for src, r in recs:
        for fr_ in r.get("frames", [r["frame"]]):
            if fr_["kind"] in shown or r.get("error"): continue
            shown.add(fr_["kind"]); say(f"      [{fr_['kind']:9s}] {r['text'][:40]!r:44s} {realize(fr_, random.Random(1))[:150]}")
    # ---------------------------------------------------------------- C1 round trip
    rt_ok = rt_n = 0; bad = []
    for src, r in recs:
        for fr_ in r.get("frames", [r["frame"]]):
            o, k = round_trip(fr_, rt_n); rt_ok += o; rt_n += k
            if o != k and len(bad) < 5: bad.append((r["text"][:40], fr_["kind"], realize(fr_, random.Random(1))[:120]))
    say(f"\nC1  ROUND TRIP: {rt_ok}/{rt_n}; MISREPORT {rt_n - rt_ok} {bad}   [100% -> {'PASS' if rt_ok == rt_n else 'FAIL'}]")
    if rt_ok != rt_n: fails.append("C1")
    # ---------------------------------------------------------------- C2 faithful + the acceptance case
    faith_ok = faith_n = 0; misses = []
    for src, r in recs:
        fr = r.get("_fr")
        if not fr or fr["kind"] not in (ATTRIBUTED, COMMIT) or len(fr["answers"]) != 1 or r["frame"]["kind"] not in (ANSWER, CHECK_K): continue
        w = fr["answer_worlds"][0]; st = fr["answers"][0][4]
        if isinstance(st, Composite) or getattr(w, "quotes", False) or getattr(w, "transcript", False): continue
        n = len(fr["syms"]); ph = r["frame"]["phrase"].lower()
        for i, j in _spans(w, st):
            if i >= n: continue
            faith_n += 1; span = " ".join(fr["syms"][i:j]).lower()
            if span in ph: faith_ok += 1
            elif len(misses) < 6: misses.append((r["text"][:36], span, ph[:60]))
    rf = faith_ok / max(faith_n, 1)
    wq, dq = chat.build_worlds(); DQ = chat.Door(wq, dq, seed=14)
    DQ.turn("what is the capital of france"); acc = DQ.turn("what is japan")
    ph = acc["frame"].get("phrase", "").lower(); accept = acc["frame"]["kind"] == ANSWER and "capital" in ph and "japan" in ph and acc["values"] and acc["values"][0].lower() == "tokyo"
    say(f"C2  FAITHFUL: spans the structure read that appear in the phrase {faith_ok}/{faith_n} = {rf:.3f}; misses {misses}")
    say(f"      ACCEPTANCE after 'what is the capital of france': 'what is japan' -> {acc['reply'][:120]!r}   [capital+japan+Tokyo -> {'PASS' if accept else 'FAIL'}]")
    say(f"    [>= 0.95 and acceptance -> {'PASS' if rf >= 0.95 and accept else 'FAIL'}]")
    if not (rf >= 0.95 and accept): fails.append("C2")
    # ---------------------------------------------------------------- C3 variety
    per_kind = collections.defaultdict(list)
    for src, r in recs:
        for fr_ in r.get("frames", [r["frame"]]):
            per_kind[fr_["kind"]].append(len({realize(fr_, random.Random(1000 + s)) for s in range(5)}))
    var = {k: (round(sum(v) / len(v), 2), len(v)) for k, v in per_kind.items()}
    ok3 = all(m >= 3 for k, (m, c) in var.items() if c >= 5)
    say(f"C3  VARIETY (mean distinct surfaces of 5 per frame kind, count): {var}   [>= 3 where count >= 5 -> {'PASS' if ok3 else 'FAIL'}]")
    if not ok3: fails.append("C3")
    # ---------------------------------------------------------------- C4 the form judge (it.10): Alice, K=64
    train, held = FF.alice()
    tr_unk, keep, _ = unkify(train, 2); m = ClassBigram(tr_unk, 64); m.exchange(60)
    def bits(sents):
        out = []
        for s in apply_unk(sents, keep):
            if len(s) >= 2: out.append(m.sentence(s)[0] / len(s))          # (bits, verdict) -> bits per token
        return out
    ref = bits([s for s in held if 2 <= len(s) <= 12])
    realized_text = [realize(frames.brief(fr_), random.Random(7)) for _, r in recs for fr_ in r.get("frames", [r["frame"]])]
    real_sents = [s for t in realized_text for s in sentences(t, 2, 12)]
    rng = random.Random(3); shuf = [rng.sample(s, len(s)) for s in real_sents]
    rb, sb = bits(real_sents), bits(shuf)
    med = lambda xs: statistics.median(xs) if xs else float("nan")
    ok4 = med(rb) <= med(ref)
    say(f"C4  FORM JUDGE (Alice class bigram K=64; bits/token, median): reference {med(ref):.2f} | realized {med(rb):.2f} ({len(rb)} sentences) | shuffled {med(sb):.2f}   "
        f"[realized <= reference -> {'MET' if ok4 else 'NOT MET (the frontier, as predicted)'}]")
    # ---------------------------------------------------------------- C6 latency, C7 brief
    msA.sort(); p95 = msA[int(0.95 * (len(msA) - 1))] / 1000
    say(f"C6  LATENCY phase A session: p95 {p95:.2f} s   [<= 2.0 -> {'PASS' if p95 <= 2.0 else 'FAIL'}]")
    if p95 > 2.0: fails.append("C6")
    wb, dbb = chat.build_worlds(); DBr = chat.Door(wb, dbb, seed=15)
    DBr.turn("what is the capital of france"); br = DBr.turn("shorter")
    o7, k7 = round_trip(br["frame"], 77)
    ok7 = br.get("act") == "REPEAT" and not br["frame"].get("supports") and o7 == k7
    say(f"C7  BRIEF: 'shorter' -> {br['reply'][:100]!r}; act {br.get('act')}; round trip {o7}/{k7}   [{'PASS' if ok7 else 'FAIL'}]")
    if not ok7: fails.append("C7")
    # ---------------------------------------------------------------- the template vocabulary, counted
    src = open(os.path.join(HERE, "frames.py"), encoding="utf-8").read()
    body = src[src.index("V_PER = "):src.index("def _alt(")]
    words = {w.lower() for lit in re.findall(r'"([^"\n]*)"|\'([^\'\n]*)\'', body) for part in lit for w in re.findall(r"[A-Za-z]+", part)}
    words -= {"f", "rng", "choice", "k", "s", "v", "src", "ev", "p", "sep", "join", "cap", "frame", "kind", "vals", "sup", "x"}
    say(f"      template vocabulary (distinct words in the realization literals): {len(words)}")
    say(f"\n    runtime {time.time()-T0:.0f} s")
    say(f"MISREPORT {rt_n - rt_ok}")
    say(f"PROSE FRAMES: {'PASS' if not fails else 'FAIL ' + ','.join(fails)} -- round trip {rt_ok}/{rt_n}, faithful {rf:.3f}, variety {min((m for m, c in var.values() if c >= 5), default=0):.2f}, judge {'met' if ok4 else 'not met'}")
    sys.exit(0 if not fails else 1)
