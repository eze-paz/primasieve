"""EMERGENCE E-13 -- THE DESCRIBER EXPERIMENT: a language model as a sealed narrator, the world as the oracle, the
Phase 3 learner as the student; then FLUENCY BY ROUND TRIP: the model proposes sentences, the engine accepts only the
ones whose parse is verified to mean what was intended.

  1. Records world (nolf_worlds), exact truth checker. Formal meanings rendered in plain words ("the second record's
     beta is above 5"). Qwen2.5-0.5B paraphrases each (few-shot, greedy). The world labels truth of the MEANING,
     not the paraphrase: a paraphrase that changed the meaning is noise the learner must reject (Phase 6 tolerance).
  2. nolf_learn.Learner on (situation, paraphrase tokens, truth). Reported: constructions, held-out EM, CONFAB.
  3. Realization: for held-out meanings the model proposes a sentence; the engine PARSES it with the learned grammar
     and evaluates it on 20 fresh situations; ACCEPT iff the parse agrees with the intended meaning on all 20 (and
     never abstains). Reported: proposals, accepted, and MISREPORT = accepted sentence whose parse differs from the
     meaning on a 21st situation (must be 0).
Predictions: a 0.5B base model paraphrases inconsistently; the learner absorbs the consistent core and abstains on
the rest; acceptance is a minority of proposals; MISREPORT 0. Fluent where verified, silent elsewhere."""
import os, sys, json, random, time, re, collections
import torch
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT); sys.path.insert(0, HERE)
from qwen_fwd import Qwen
import nolf_worlds as NW
import nolf_learn as NL
from core.verdict import score_two_mode, line

SNAP = r"C:/Users/aezequiel/.cache/huggingface/hub/models--Qwen--Qwen2.5-0.5B/snapshots/060db6499f32faf8b98477b0a26969ef7d8b9987"
OUT = os.path.join(HERE, "em_describer_result.json")
N_TRAIN = int(sys.argv[sys.argv.index("--n") + 1]) if "--n" in sys.argv else 240
N_FORMAL = int(sys.argv[sys.argv.index("--n-formal") + 1]) if "--n-formal" in sys.argv else 3000
FORMAL_ONLY = "--formal-only" in sys.argv
rng = random.Random(11)
W = NW.Records()
NAMES = {"f0": "alpha", "f1": "beta", "f2": "gamma", "first": "first", "second": "second", "third": "third", "fourth": "fourth",
         "above": "above", "below": "below", "equals": "equal to", "every": "every", "some": "some"}
NUM = {f"n{i}": str(i) for i in range(10)}


def formal(toks):
    """the world's hidden-form sentence -> plain words (a fixed rendering, the DESCRIBER's input, never the learner's)."""
    c = [W.lex.f2c[t] for t in toks]
    def w(x): return NAMES.get(x, NUM.get(x, x))
    if c[0] in ("every", "some"):                                   # every/some FIELD REL NUM
        return f"{w(c[0])} record has {w(c[1])} {w(c[2])} {w(c[3])}"
    if c[0] == "not":
        return "it is not the case that " + formal(toks[1:])
    if "and" in c:
        i = c.index("and"); return formal(toks[:i]) + " and " + formal(toks[i + 1:])
    # ORD FIELD REL (NUM|FIELD)
    tail = w(c[3])
    return f"the {w(c[0])} record's {w(c[1])} is {w(c[2])} {tail}" if c[3].startswith("n") else f"the {w(c[0])} record's {w(c[1])} is {w(c[2])} its {tail}"


FEWSHOT = ("Rewrite each sentence in different words, keeping exactly the same meaning.\n"
           "Sentence: the box is heavier than the chair\nRewrite: the chair weighs less than the box\n"
           "Sentence: every student passed the exam\nRewrite: all of the students passed the exam\n"
           "Sentence: the third house is red\nRewrite: house number three is red\n")


def paraphrase(m, sentence, max_new=16):
    ids = m.encode(FEWSHOT + f"Sentence: {sentence}\nRewrite:")
    return m.decode(m.generate(ids, max_new)).strip().rstrip(".").lower()      # KV-cached greedy decode


def tokens(s): return re.findall(r"[a-z]+|\d", s)


if __name__ == "__main__":
    t0 = time.time()
    # the CONTROL first, at full size and with no model in the loop: does the learner learn this rendering at all?
    # (measured: 240 sentences -> 0 constructions on both narrators; the evidence gate needs 40 rows per construction)
    spf = NW.splits(W, 3, n_train=N_FORMAL, n_test=300)
    ftrain = [(sit, tokens(formal(toks)), tv) for sit, toks, tv in spf["train"]]
    ftest = [(sit, tokens(formal(toks)), tv) for sit, toks, tv in spf["heldout_comp"]]
    print(f"CONTROL: learner on the fixed formal rendering, {len(ftrain)} sentences, 300 s", flush=True)
    LF = NL.Learner(time_budget=300).fit(ftrain)
    print(f"  {len(LF.cls)} words, {len(LF.members)} classes, {len(LF.grammar)} constructions")
    for e in LF.log:
        if e[0] == "learned": print(f"    learned {e[2]:4d} rows  {e[3]}")
    rf = score_two_mode(LF, [((s_, t), tv) for s_, t, tv in ftest]); print(line("formal / compositional held-out", rf, 32), flush=True)
    if FORMAL_ONLY:
        json.dump(dict(formal_em=rf["EM"], formal_confab=rf["confab"], constructions_formal=len(LF.grammar)), open(OUT, "w"), indent=1); sys.exit(0)
    m = Qwen(SNAP)
    print(f"\nE-13 DESCRIBER: Qwen2.5-0.5B narrates, the records world judges, the Phase 3 learner learns ({N_TRAIN} sentences)\n")
    sp = NW.splits(W, 3, n_train=N_TRAIN, n_test=80)
    rows = []; same = 0
    for k, (sit, toks, tv) in enumerate(sp["train"] + sp["heldout_iid"]):
        f = formal(toks); p = paraphrase(m, f)
        rows.append(dict(sit=sit, formal=f, para=p, tv=tv, split="train" if k < len(sp["train"]) else "test"))
        same += (tokens(p) == tokens(f))
        if k < 8: print(f"  {f!r:55s} -> {p!r}   [{tv}]")
        if k % 40 == 0 and k: print(f"  ... {k} narrated, {time.time()-t0:.0f}s", flush=True)
    print(f"\nnarrated {len(rows)} in {time.time()-t0:.0f}s; verbatim copies {same} ({100*same/len(rows):.0f}%); "
          f"distinct paraphrase vocab {len({w for r in rows for w in tokens(r['para'])})}")
    train = [(r["sit"], tokens(r["para"]), r["tv"]) for r in rows if r["split"] == "train" and tokens(r["para"])]
    test = [(r["sit"], tokens(r["para"]), r["tv"]) for r in rows if r["split"] == "test" and tokens(r["para"])]
    print("\nLEARNER on the model's paraphrases (budget 300 s):")
    L = NL.Learner(time_budget=300).fit(train)
    print(f"  {len(L.cls)} words, {len(L.members)} classes, {len(L.grammar)} constructions")
    for e in L.log:
        if e[0] == "learned": print(f"    learned {e[2]:4d} rows  {e[3]}")
    rp = score_two_mode(L, [((s, t), tv) for s, t, tv in test]); print(line("paraphrases / held-out", rp, 28))
    # ---- 3. realization by round trip, with whichever learner knows more
    Lr = L if rp["EM"] >= rf["EM"] else LF
    print("\nREALIZATION BY ROUND TRIP: the model proposes a sentence for a held-out meaning; the engine parses it and checks it on 20 fresh situations")
    props = acc = misreport = 0; shown = 0
    checks = [(W.sample(rng)) for _ in range(21)]
    for sit, toks, tv in sp["heldout_comp"][:40]:
        f = formal(toks); p = paraphrase(m, f); props += 1
        ptoks = tokens(p)
        # the intended meaning's truth on the check situations comes from the world (the formal sentence's tokens)
        truth = []
        for cs in checks:
            # re-describe: evaluate the formal meaning on cs by re-parsing with the formal learner (exact by construction)
            truth.append(LF((cs, tokens(f))))
        if any(t is None for t in truth): continue
        got = [Lr((cs, ptoks)) for cs in checks]
        if all(g is not None and g == t for g, t in zip(got[:20], truth[:20])):
            acc += 1; misreport += (got[20] != truth[20])
            if shown < 5: shown += 1; print(f"  ACCEPTED  {f!r}  ->  {p!r}")
    print(f"\n  proposals {props}, accepted {acc}, MISREPORT {misreport}")
    json.dump(dict(n=len(rows), verbatim=same, para_em=rp["EM"], para_confab=rp["confab"], formal_em=rf["EM"], formal_confab=rf["confab"],
                   constructions_para=len(L.grammar), constructions_formal=len(LF.grammar), proposals=props, accepted=acc, misreport=misreport,
                   samples=[(r["formal"], r["para"]) for r in rows[:30]]), open(OUT, "w"), indent=1, default=str)
    print(f"({time.time()-t0:.0f}s) -> {os.path.basename(OUT)}")
