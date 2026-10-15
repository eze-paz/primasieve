"""AG9 (AG_prereg.md): the question converged to a canonical statement with one blank by the same propose-and-verify
loop; the answer is the blank's role in the first canonical clause whose event matches. No hand question shapes.
Run: py -3.12 ag9_qcanon.py          (stage 1, resumable, writes ag9_qstatements.json)
     py -3.12 ag9_qcanon.py --score  (stage 2 on AG4 canonical text and on the original)"""
import os, sys, re, json, time, random, collections
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); os.chdir(HERE)
import torch
ARGV = list(sys.argv); sys.argv = [sys.argv[0]]
import ag1_translator as A
from ag3_canon import STOP, ent, content, toks, gen
from b6_rwkv import hit
STORIES = list(range(22, 102)); PRACTICE = set(range(22, 62))
OUT = "ag9_qstatements.json"
FEW = ("Instruction: Turn the question into a statement. Put ___ in place of the asked part. Use only words from the question.\n\n"
       "Question: Who planted the rows?\nStatement: ___ planted the rows.\n\n"
       "Question: Where did Rosa drop the key?\nStatement: Rosa dropped the key ___.\n\n"
       "Question: What did Keiko paint?\nStatement: Keiko painted ___.\n\n"
       "Question: Who did the fox invite?\nStatement: The fox invited ___.\n\n"
       "Question: {q}\nStatement:")
FEW2 = ("Instruction: Rewrite the question as a sentence with ___ for the missing part. Keep every word of the question.\n\n"
        "Question: Who took the boots to the river?\nStatement: ___ took the boots to the river.\n\n"
        "Question: What did the goat leave?\nStatement: The goat left ___.\n\n"
        "Question: {q}\nStatement:")
FEW3 = ("Instruction: Turn the question into an active sentence. The doer comes first. Write ___ for the unknown part.\n\n"
        "Question: Who stacked the shelves?\nStatement: ___ stacked the shelves.\n\n"
        "Question: Who repaired bicycles?\nStatement: ___ repaired bicycles.\n\n"
        "Question: Where was the field?\nStatement: The field was ___.\n\n"
        "Question: What did Keiko paint?\nStatement: Keiko painted ___.\n\n"
        "Question: {q}\nStatement:")


def load_translator():
    data = [s for s in json.load(open("stories_train_v2.json", encoding="utf-8")) if s.get("events")]
    random.Random(0).shuffle(data); F = A.Feats([tk for st in data[:2240] for tk, _ in A.gold_examples(st)])
    vm = A.Tagger(F, 2, False); am = A.Tagger(F, len(A.ATAGS), True); sd = torch.load("ag1_translator.pt"); vm.load_state_dict(sd["vm"]); am.load_state_dict(sd["am"]); vm.eval(); am.eval()
    return A.Translator(F, vm, am)


def qevent(T, statement, q):
    """the event the statement describes, with the blank's role; None if the verifier rejects"""
    st = statement.strip().split("\n")[0].strip()
    if st.count("___") != 1: return None, "blanks"
    qw = {A.lemma(w) for w in content(q)} | {w for w in content(q)}
    extra = [w for w in content(st.replace("___", "")) if w not in qw and A.lemma(w) not in qw and w not in ("the", "a", "an")]
    if extra: return None, "invented"
    if re.search(r"\b(was|were|is|are|been)\b.*\bby ___", st.lower()): return None, "passive"   # the canonical grammar is active voice
    for ph in ("somebody", "something", "the blank", "to the blank", "somewhere"):            # the placeholder must be read as one whole role
        evs = T.read(st.replace("___", ph))
        for e in evs:
            for role in ("agent", "patient", "place"):
                if e.get(role) and ent(e[role]) == ent(ph):
                    return dict(verb=e["verb"], asked=role, agent=None if role == "agent" else e.get("agent"), patient=None if role == "patient" else e.get("patient"), place=None if role == "place" else e.get("place"), statement=st), "ok"
    return None, "no event with blank"


def main():
    from rwkv7 import RWKV7, tokenizer
    T = load_translator()
    m = RWKV7.load(os.path.join("rwkv7", "RWKV-x070-World-0.4B-v2.9-20250107-ctx4096.pth")); m.eval(); tok = tokenizer()
    S = json.load(open("val_all13.json", encoding="utf-8"))["stories"]
    done = json.load(open(OUT, encoding="utf-8")) if os.path.exists(OUT) else {}
    stats = collections.Counter(done.pop("_stats", {})); t0 = time.time(); k = 0
    for si in STORIES:
        s = S[si]
        for q, g in s["qs"]:
            key = f"{s['id']}|{q}"; k += 1
            if key in done: continue
            qe = None; log = []
            for p in (FEW, FEW2, FEW3):
                st = gen(m, tok, p.format(q=q), n=30).split("\n")[0]
                qe, why = qevent(T, st, q); log.append((st, why)); stats["stage1:" + why] += 1
                if qe: break
            done[key] = dict(story=s["id"], q=q, gold=g, qevent=qe, log=log)
            if k % 25 == 0:
                done["_stats"] = dict(stats); json.dump(done, open(OUT, "w", encoding="utf-8"), indent=1)
                print(f"  {k} questions ({time.time() - t0:.0f} s) {dict(stats)}".encode("ascii", "replace").decode(), flush=True)
    done["_stats"] = dict(stats); json.dump(done, open(OUT, "w", encoding="utf-8"), indent=1)
    print(f"AG9 stage 1 done ({time.time() - t0:.0f} s) {dict(stats)}", flush=True)


def match(filler, span):
    if not filler: return True
    f = [w for w in ent(filler).split() if w not in STOP]; s = [w for w in ent(span or "").split() if w not in STOP]
    if not f: return True
    if not s: return False
    return bool(set(f) & set(s)) or f[-1] == s[-1]


def score():
    T = load_translator()
    S = json.load(open("val_all13.json", encoding="utf-8"))["stories"]; C = json.load(open("ag4_canon.json", encoding="utf-8"))
    Q = json.load(open(OUT, encoding="utf-8")); Q.pop("_stats", None)
    res = collections.defaultdict(lambda: [0, 0, 0]); rows = []
    for si in STORIES:
        s = S[si]; evs = {}
        for tname, text in (("original", s["text"]), ("canonical", C[s["id"]]["canon"])):
            E = [e for sent in [x.strip() for x in A.SENT.split(text) if x.strip()] for e in T.read(sent)]
            last = None
            for e in E:
                a = (e.get("agent") or "").strip()
                if a.lower() in ("he", "she", "they"):
                    if last: e["agent"] = last
                elif a and a[0].isupper(): last = a
            evs[tname] = E
        for q, g in s["qs"]:
            qe = Q.get(f"{s['id']}|{q}", {}).get("qevent"); row = dict(q=q, gold=g, qevent=qe)
            for tname in ("original", "canonical"):
                a = None
                if qe:
                    for e in evs[tname]:
                        if e["verb"] != qe["verb"]: continue
                        if all(match(qe[r], e.get(r)) for r in ("agent", "patient", "place") if r != qe["asked"] and qe[r]):
                            x = e.get(qe["asked"])
                            if x and ent(x) and ent(x) not in ("it", "them", "him", "her", "he", "she", "they"): a = x; break
                row[tname] = a; cell = res[(tname, "practice" if si in PRACTICE else "untouched")]
                if a is None: cell[2] += 1
                elif hit(a, g): cell[0] += 1
                else: cell[1] += 1
            rows.append(row)
    json.dump(rows, open("ag9_rows.json", "w", encoding="utf-8"), indent=1)
    for key in sorted(res):
        r, w, sil = res[key]; print(f"AG9 {key[0]:9s} text, {key[1]:9s}: {r} right / {w} wrong / {sil} silent / fitness {r - 3 * w} / precision {r / max(1, r + w):.2f}")
    print("AG9 question events formed:", sum(1 for x in rows if x["qevent"]), "of", len(rows))


if __name__ == "__main__":
    score() if "--score" in ARGV else main()
