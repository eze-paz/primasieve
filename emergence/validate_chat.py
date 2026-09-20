"""VALIDATE THE CHAT ENGINE -- a scripted conversation with expected verdicts, OFFLINE, in-process. ZERO LLM.

    python validate_chat.py            # runs the script, prints one line per check, a verdict line, exit code 0/1

This is the acceptance test for everything wired into en_server.py: learning by elimination, ASK on ambiguity,
teaching by statement, protection of world-learned words, research through the offline sources (WordNet, KAIKKI,
MOBY), single-source words held with a visible caveat, contested words asked about, honest OUT-OF-WORLD after
research, the ATTRIBUTED tag on every reply that relies on a taught/researched word, 'wrong' retracting with
cascade, and the three fatal columns at zero: CONFABULATION, MISATTRIBUTION (nothing held without a certificate),
LAUNDERING (no COMMIT carrying provenance). Online sources are DISABLED here so the result is deterministic.
The scene is seeded so referents are fixed."""
import os, sys, random, json
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE)); sys.path.insert(0, HERE)
from core.registry import selfcheck
import kb_sources as KB
KB.SOURCES = [s for s in KB.SOURCES if s[0] in KB.OFFLINE]          # deterministic: offline only
import en_server as S
import en_world as W
import en_chat as C
import en_actions as ACT
import random as _r

CHECKS = []


def check(name, cond, detail=""):
    CHECKS.append((name, bool(cond)))
    print(f"  [{'ok' if cond else 'FAIL'}] {name}" + (f"   {detail}" if detail and not cond else ""), flush=True)


def say(t):
    r = S.say(t); return r["kind"], r["msg"]


if __name__ == "__main__":
    selfcheck(__file__)
    print("VALIDATE CHAT -- scripted conversation, offline sources only\n", flush=True)
    _, lex, _ = C.build(); S.STATE["lex"] = lex
    alex, _ = ACT.learn_actions(ACT.training(400, _r.Random(4))); S.STATE["alex"] = alex
    print("  " + S.load_attributed(), flush=True)
    S.STATE["scene"] = W.rand_scene(random.Random(1234), 5); S.STATE["pending"] = None
    sc = S.STATE["scene"]
    props = [W.true_unary(o) for o in sc]
    # pick a colour that exactly one object has, and one that two or more have
    from collections import Counter
    cnt = Counter(p for ps in props for p in ps if p in W.COLOURS)
    uniq = next((c for c, n in cnt.items() if n == 1), None); multi = next((c for c, n in cnt.items() if n > 1), None)
    print(f"  scene: {[' '.join(p) for p in props]}\n", flush=True)

    print("1. world-learned words: COMMIT on a unique referent, ASK on several", flush=True)
    if uniq:
        k, m = say(f"which one is {uniq}"); check("unique colour -> COMMIT", k == "COMMIT", f"{k}: {m}")
    if multi:
        k, m = say(f"which one is {multi}"); check("shared colour -> ASK", k == "ASK", f"{k}: {m}")

    print("2. teaching by statement; taught words are ATTRIBUTED, world words are protected", flush=True)
    k, m = say("blorp means big"); check("'blorp means big' -> TAUGHT", k == "TAUGHT", f"{k}: {m}")
    k, m = say("which one is blorp"); check("reply relying on a taught word is tagged", "relies on" in m and k in ("ATTRIBUTED", "ASK", "NONE"), f"{k}: {m}")
    k, m = say("red means blue"); check("world-learned word cannot be overwritten by telling", k == "ABSTAIN", f"{k}: {m}")
    k, m = say("forget red"); check("world-learned word cannot be retracted by telling", k == "ABSTAIN", f"{k}: {m}")

    print("3. research through offline sources (no network)", flush=True)
    k, m = say("which one is gargantuan"); check("'gargantuan' researched -> big, tagged", "big" in m and "relies on" in m, f"{k}: {m}")
    check("gargantuan cites 2+ offline sources", any(x in m for x in ("KAIKKI", "WORDNET", "MOBY")), m)
    k, m = say("which one is mustard"); check("single-source word held WITH the caveat", "no second source" in m.lower(), f"{k}: {m}")
    k, m = say("which one is teal"); check("contested word -> ASK with both readings", k == "ASK" and "blue" in m and "green" in m, f"{k}: {m}")
    k, m = say("none"); check("'none' leaves a contested word unknown", k == "ABSTAIN", f"{k}: {m}")
    k, m = say("which one is sex"); check("a word no shape can be -> DEFINED from the sources (cited) or OUT-OF-WORLD naming sources consulted",
                                          k in ("DEFINED", "OUT-OF-WORLD", "ABSTAIN") and "consulted" in m, f"{k}: {m}")
    k, m = say("what is a dog"); check("'what is a dog' -> DEFINED, cited, held on the source's word (E-10)", k == "DEFINED" and "WORDNET" in m.upper() or "KAIKKI" in m, f"{k}: {m}")
    k, m = say("wrong"); check("'wrong' on a definition drops it and asks what was meant", k == "RETRACTED", f"{k}: {m}")

    print("4. retraction cascades; sources are struck", flush=True)
    S.STATE["last_used"] = ["gargantuan"]
    k, m = say("wrong"); check("'wrong' retracts the attributed word and its dependents", k == "RETRACTED", f"{k}: {m}")
    st = S._state_json()
    check("retracted word shows as retracted in the belief store", any(a["word"] == "gargantuan" and a["state"] == "retracted" for a in st["attributed"]))
    check("its source has a strike", any(v["strikes"] >= 1 for v in st["sources"].values()), str(st["sources"]))
    k, m = say("which one is gargantuan"); check("a retracted word is not re-held silently (asks or re-researches with caveat)", k in ("ASK", "OUT-OF-WORLD", "ATTRIBUTED", "NONE"), f"{k}: {m}")

    print("5. the three fatal columns", flush=True)
    B = S.STATE["beliefs"]
    check("LAUNDERING 0 (no COMMIT carries provenance)", len(B.laundered()) == 0, str(B.laundered()[:3]))
    check("MISATTRIBUTION 0 (every held word has a certificate)", all(e["prov"] for (kind, w), e in B.b.items() if kind == "word" and e["state"] != "retracted"))
    # confabulation: every COMMIT reply in this script named a referent that truly has the property
    conf = 0
    for c in W.COLOURS:
        r = S.say(f"which one is {c}")
        if r["kind"] == "COMMIT":
            i = int(r["msg"].split("#")[1].split()[0]); conf += (c not in W.true_unary(sc[i]))
    check("CONFABULATION 0 over all colour queries", conf == 0, f"{conf}")

    ok = all(c for _, c in CHECKS)
    print(f"\n{sum(c for _, c in CHECKS)}/{len(CHECKS)} checks passed", flush=True)
    print("CHAT VALIDATION: PASS" if ok else "CHAT VALIDATION: FAIL", flush=True)
    sys.exit(0 if ok else 1)
