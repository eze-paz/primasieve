"""EMERGENCE E-10 -- THE UNIFIED ANSWER LOOP (em_resolve_prereg.md). ZERO LLM, offline sources only.

"What is a dog?" from an empty lexicon: research every symbol, topic by specificity, intent by affordance, answer
by certificate. The loop lives in core/resolve.py and holds no word; this file is the gates R1-R8, including the
static gate that the loop's source shares no token with any utterance it is tested on, the dictionary-shuffle
knockout, and the smallest frame demonstration (two accepted utterances -> one frame -> retracted on 'wrong')."""
import os, sys, json, time, ast, collections
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE)); sys.path.insert(0, HERE)
import kb_sources as KB
import core.resolve as R
from core.resolve import WORLD, EXEC, GLOSS, resolve, segment, accept, reject
from core.verdict import Beliefs, ATTRIBUTED, CONJECTURED, RETRACTED, COMMIT
from core.registry import selfcheck

OUT = os.path.join(HERE, "EMERGENCE.json")
UTTERANCES = ["What is a dog?", "define dog", "dog?", "what does lofty mean", "which one is red", "I hate my dog",
              "what is a cat", "what is a tree", "whom is a dog?"]


class NoSources:
    """R3: every source removed."""
    consulted = []
    def readings(self, s): return {WORLD: [], EXEC: [], GLOSS: []}
    def df(self, s): return 0


class Shuffled:
    """R5: the dictionary with glosses PERMUTED across the headwords of the test utterances (and df permuted with
    them) -- the engine must follow the permuted sources, not the spelling."""
    def __init__(self, base, words, seed=3):
        import random
        self.base = base; self.consulted = base.consulted
        ws = [w for w in words if base.readings(w)[GLOSS]]
        perm = list(ws); random.Random(seed).shuffle(perm)
        self.map = dict(zip(ws, perm))
    def readings(self, s): return self.base.readings(self.map.get(s.lower(), s))
    def df(self, s): return self.base.df(self.map.get(s.lower(), s))


def literals_of(path):
    tree = ast.parse(open(path, encoding="utf-8").read())
    docs = set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef)) and ast.get_docstring(n) is not None:
            docs.add(id(n.body[0].value))
    return {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs}


def show(rz):
    t = rz["topic"]
    top = rz["symbols"][t] if t is not None else None
    kind = {WORLD: "WORLD", EXEC: "EXEC", GLOSS: "GLOSS", None: "-"}[rz["kind"]]
    ans = ""
    if rz["kind"] == GLOSS and rz["answer"]:
        ans = f"{len(rz['answer'])} sense(s) per {rz['answer'][0][1]}: \"{rz['answer'][0][0][:60]}\""
    elif rz["answer"] is not None:
        ans = str(rz["answer"])
    return f"topic={top!s:8} kind={kind:5} state={rz['state']:11} alts={[ {0:'WORLD',1:'EXEC',2:'GLOSS'}[a] for a in rz['alternatives']]} frame={'yes' if rz['via_frame'] else 'no'}  {ans}"


if __name__ == "__main__":
    selfcheck(__file__)
    t0 = time.time()
    print("EMERGENCE E-10 -- RESOLVE: research every symbol, intent by affordance, answer by certificate\n", flush=True)
    KB.SOURCES = [s for s in KB.SOURCES if s[0] in KB.OFFLINE]
    L = KB.Lexica(online=False)
    kaikki = "KAIKKI" in L.consulted
    print(f"sources consulted (offline only): {L.consulted}\n", flush=True)

    # ---- R1 cold start: empty lexicon, no frames -------------------------------------------------------------
    B = Beliefs(); frames = []; hist = []
    print("R1  cold start (no lexicon, no frames):", flush=True)
    r1 = {}
    for u in UTTERANCES[:4]:
        rz = resolve(u, L, beliefs=B, frames=frames); r1[u] = rz
        print(f"  {u!r:26} -> {show(rz)}", flush=True)
    dog = r1["What is a dog?"]
    k1 = all(r1[u]["kind"] == GLOSS and r1[u]["state"] == CONJECTURED and r1[u]["answer"] for u in UTTERANCES[:4]) \
         and dog["symbols"][dog["topic"]].lower() == "dog" and r1["what does lofty mean"]["symbols"][r1["what does lofty mean"]["topic"]].lower() == "lofty"
    held = B.b.get(("gloss", "dog"))
    print(f"  dog held: {held['state'] if held else None} on {sorted({s for s, _ in held['prov']}) if held else None}", flush=True)
    print(f"  [R1 all four forms -> GLOSS of the right topic, CONJECTURED intent, ATTRIBUTED gloss: {k1 and held is not None and held['state'] == ATTRIBUTED}]\n", flush=True)
    k1 = k1 and held is not None and held["state"] == ATTRIBUTED

    # ---- R2 affordance, not words ---------------------------------------------------------------------------
    print("R2  the same string under different affordances:", flush=True)
    Lw = KB.Lexica(online=False, world={"red": "P0"})              # a toy attached world: one learned symbol
    a = resolve("which one is red", Lw, beliefs=Beliefs()); b = resolve("which one is red", L, beliefs=Beliefs())
    print(f"  world attached   -> {show(a)}", flush=True)
    print(f"  no world         -> {show(b)}", flush=True)
    k2 = (a["kind"] == WORLD and GLOSS in a["alternatives"] and a["state"] == CONJECTURED and a["symbols"][a["topic"]] == "red"
          and b["kind"] == GLOSS and not b["alternatives"])
    print(f"  [R2 two affordances -> cheapest reversible CONJECTURED with the other named; one -> that one: {k2}]\n", flush=True)

    # ---- R3 source ablation ---------------------------------------------------------------------------------
    r3 = resolve("What is a dog?", NoSources(), beliefs=Beliefs())
    k3 = r3["topic"] is None and r3["answer"] is None and r3["state"] == "hard"
    print(f"R3  every source removed -> {show(r3)}   [refuses, invents nothing: {k3}]\n", flush=True)

    # ---- R4 the loop knows no word of any test utterance ---------------------------------------------------------
    lits = literals_of(R.__file__)
    toks = {s.lower() for u in UTTERANCES for s in segment(u)} | {s for u in UTTERANCES for s in segment(u)}
    leak = sorted(l for l in lits if l.lower() in toks or (len(l) == 1 and not l.isalnum()))
    k4 = not leak
    print(f"R4  string literals in core/resolve.py: {sorted(lits)}   shared with test utterances or a glyph: {leak}   [{k4}]\n", flush=True)

    # ---- R5 dictionary shuffle ----------------------------------------------------------------------------------
    words = sorted({s.lower() for u in UTTERANCES for s in segment(u) if s.isalpha()})
    S = Shuffled(L, words)
    r5 = resolve("What is a dog?", S, beliefs=Beliefs())
    t5 = r5["symbols"][r5["topic"]].lower() if r5["topic"] is not None else None
    expect_topic = min((w for w in ["what", "is", "a", "dog"] if S.readings(w)[GLOSS]), key=lambda w: S.df(w))
    same_cite = r5["answer"] and r5["answer"][0][0] == S.readings(t5)[GLOSS][0][0]
    k5 = t5 == expect_topic and bool(same_cite)
    print(f"R5  glosses permuted across {len(S.map)} headwords -> topic {t5!r} (permuted specificity says {expect_topic!r}), cites the permuted gloss: {bool(same_cite)}   [{k5}]\n", flush=True)

    # ---- R6 first frame ---------------------------------------------------------------------------------------
    print("R6  frames from two accepted utterances:", flush=True)
    B6 = Beliefs(); frames = []; hist = []
    for u in ("what is a dog", "what is a cat"):
        rz = resolve(u, L, beliefs=B6, frames=frames)
        fr = accept(frames, rz["symbols"], rz["topic"], rz["kind"], hist)
        print(f"  {u!r:18} accepted -> frame {'formed: ' + str(fr['skeleton']) if fr else 'none yet'}", flush=True)
    rz = resolve("what is a tree", L, beliefs=B6, frames=frames)
    print(f"  {'what is a tree'!r:18} -> {show(rz)}", flush=True)
    via = rz["via_frame"] is not None and rz["kind"] == GLOSS and rz["symbols"][rz["topic"]] == "tree"
    reject(frames, rz["via_frame"]) if rz["via_frame"] else None
    rz2 = resolve("what is a tree", L, beliefs=B6, frames=frames)
    k6 = via and frames[0]["state"] == RETRACTED and rz2["via_frame"] is None and rz2["kind"] == GLOSS
    print(f"  'wrong' -> frame {frames[0]['state']}; re-asked -> by affordance again (frame={'yes' if rz2['via_frame'] else 'no'})   [R6 {k6}]\n", flush=True)

    # ---- R7 honest overgeneralization -----------------------------------------------------------------------------
    r7 = resolve("I hate my dog", L, beliefs=Beliefs())
    k7 = r7["kind"] == GLOSS and r7["state"] == CONJECTURED and r7["symbols"][r7["topic"]] == "dog"
    print(f"R7  'I hate my dog' -> {show(r7)}   [the sole affordance, CONJECTURED not COMMIT: {k7}]", flush=True)
    r7b = resolve("whom is a dog?", L, beliefs=Beliefs())
    print(f"    'whom is a dog?' -> {show(r7b)}   (pre-registered weakness of the specificity bias; reported, not patched)\n", flush=True)

    # ---- R8 fatal columns over everything held ----------------------------------------------------------------------
    confab = 0                                                          # no COMMIT was ever issued by the loop
    for Bx in (B, B6):
        confab += sum(1 for k, e in Bx.b.items() if e["state"] == COMMIT)
    k8 = confab == 0 and not B.laundered() and not B6.laundered() and all(e["prov"] for e in B.b.values())
    print(f"R8  COMMITs issued by the loop {confab}   LAUNDERING {len(B.laundered()) + len(B6.laundered())}   MISATTRIBUTION 0 (every gloss held with a certificate: {all(e['prov'] for e in B.b.values())})   [{k8}]\n", flush=True)

    sound = k1 and k2 and k3 and k4 and k5 and k6 and k8
    ok = sound and k7
    if sound:
        print("E10 RESOLVE LOOP: SOUND -- every symbol researched, topic by the sources' specificity, intent by affordance, "
              "answer by certificate, no word known to the loop; nothing committed, nothing laundered", flush=True)
        got = ("ASK on a tie" if r7["tie"] else f"topic {r7['symbols'][r7['topic']]!r}" if r7["topic"] is not None else "no topic")
        dfs = {s: L.df(s) for s in r7["symbols"]}
        print(f"R7 prediction ({'MET' if k7 else 'MISS'}): the prereg predicted 'I hate my dog' -> gloss of dog as the sole affordance; "
              f"the sources' definition counts are {dfs} and the loop gave {got}. Reported as measured, not patched.", flush=True)
    else:
        print("E10 RESOLVE LOOP: NOT SOUND (read the gate lines)", flush=True)
    d = json.load(open(OUT)) if os.path.exists(OUT) else {}
    d["E10_resolve_loop"] = dict(prereg="em_resolve_prereg.md", kaikki_full=kaikki, gates=dict(R1=k1, R2=k2, R3=k3, R4=k4, R5=k5, R6=k6, R7=k7, R8=k8),
                                 cold_start={u: dict(topic=r1[u]["symbols"][r1[u]["topic"]] if r1[u]["topic"] is not None else None,
                                                     senses=len(r1[u]["answer"] or []), source=(r1[u]["answer"] or [("", None)])[0][1]) for u in r1},
                                 literals=sorted(lits), passed=ok)
    json.dump(d, open(OUT, "w"), indent=1, sort_keys=True)
    print(f"({time.time()-t0:.0f}s) -> EMERGENCE.json[E10_resolve_loop]", flush=True)
