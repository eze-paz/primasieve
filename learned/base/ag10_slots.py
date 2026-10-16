"""AG10 (AG_prereg.md): a rigid formal language the model writes directly: one slot line per event,
WHO | DID | WHAT | WHERE | WHEN | WHY, for sentences and for questions ('?' in the asked slot). The engine parses the lines
exactly, verifies word provenance, and answers by matching lines. No learned translator.
Run: py -3.12 ag10_slots.py            (stages 1-2, resumable, writes ag10_lines.json; then scores)
     py -3.12 ag10_slots.py --score    (score only)"""
import os, sys, re, json, time, collections
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); os.chdir(HERE)
import torch
ARGV = list(sys.argv); sys.argv = [sys.argv[0]]
import ag1_translator as A
from ag3_canon import STOP, ent, content, toks
from b6_rwkv import hit
CKPT = ARGV[ARGV.index("--ckpt") + 1] if "--ckpt" in ARGV else os.path.join("rwkv7", "RWKV-x070-World-1.5B-v3-20250127-ctx4096.pth")
ALL = "--all" in ARGV; STORIES = list(range(502)) if ALL else list(range(62, 102)); FROM_CANON = "--from-canon" in ARGV
WITH_SENT = "--with-sentence" in ARGV
CANON_FILE = ARGV[ARGV.index("--canon-file") + 1] if "--canon-file" in ARGV else "ag4_canon.json"
QLINES = ARGV[ARGV.index("--qlines") + 1] if "--qlines" in ARGV else None
OUT_OVERRIDE = ARGV[ARGV.index("--out") + 1] if "--out" in ARGV else None
OUT = OUT_OVERRIDE or ("ag13_lines.json" if (FROM_CANON and WITH_SENT) else "ag12all_lines.json" if (FROM_CANON and ALL) else "ag12_lines.json" if FROM_CANON else "ag10_lines.json")
S_PROMPT3 = ("Instruction: Describe the clause as one line of slots. Take WHEN and WHY from the sentence when the sentence gives them. "
             "Use only words from the clause or the sentence. Write - for an empty slot.\n\n"
             "Sentence: In the morning Rosa took the key to the well because the bucket was lost.\nClause: Rosa took the key to the well.\n"
             "WHO: Rosa | DID: took | WHAT: the key | WHERE: to the well | WHEN: in the morning | WHY: because the bucket was lost\n\n"
             "Sentence: The jar was full of flour.\nClause: The jar was full of flour.\n"
             "WHO: The jar | DID: was | WHAT: full of flour | WHERE: - | WHEN: - | WHY: -\n\n"
             "Sentence: {sent}\nClause: {clause}\n")
SLOTS = ["WHO", "DID", "WHAT", "WHERE", "WHEN", "WHY"]
LINE = re.compile(r"WHO:\s*(.*?)\s*\|\s*DID:\s*(.*?)\s*\|\s*WHAT:\s*(.*?)\s*\|\s*WHERE:\s*(.*?)\s*\|\s*WHEN:\s*(.*?)\s*\|\s*WHY:\s*(.*?)\s*$")
PRON = {"he", "she", "they", "it", "him", "her", "them", "his", "their", "its"}
S_PROMPT = ("Instruction: Describe every event in the sentence as one line of slots. Use only words from the sentence. Write - for an empty slot.\n\n"
            "Sentence: Rosa took the key to the well in the morning.\n"
            "WHO: Rosa | DID: took | WHAT: the key | WHERE: to the well | WHEN: in the morning | WHY: -\n\n"
            "Sentence: Greta sold her roses at the market and bought seed for Ilse because the hail had flattened the cabbages.\n"
            "WHO: Greta | DID: sold | WHAT: her roses | WHERE: at the market | WHEN: - | WHY: because the hail had flattened the cabbages\n"
            "WHO: Greta | DID: bought | WHAT: seed for Ilse | WHERE: - | WHEN: - | WHY: because the hail had flattened the cabbages\n\n"
            "Sentence: The jar was full of flour.\n"
            "WHO: The jar | DID: was | WHAT: full of flour | WHERE: - | WHEN: - | WHY: -\n\n"
            "Sentence: {sent}\n")
Q_PROMPT = ("Instruction: Write the question as one line of slots. Put ? in the slot that is asked. Use only words from the question. Write - for an empty slot.\n\n"
            "Question: Who took the key to the well?\nWHO: ? | DID: took | WHAT: the key | WHERE: to the well | WHEN: - | WHY: -\n\n"
            "Question: What did Keiko paint?\nWHO: Keiko | DID: paint | WHAT: ? | WHERE: - | WHEN: - | WHY: -\n\n"
            "Question: Where did Rosa drop the key?\nWHO: Rosa | DID: drop | WHAT: the key | WHERE: ? | WHEN: - | WHY: -\n\n"
            "Question: When did the bees find the bear?\nWHO: the bees | DID: find | WHAT: the bear | WHEN: ? | WHERE: - | WHY: -\n\n"
            "Question: Why did the ring fall?\nWHO: the ring | DID: fall | WHAT: - | WHERE: - | WHEN: - | WHY: ?\n\n"
            "Question: What was in the jar?\nWHO: the jar | DID: was | WHAT: ? | WHERE: - | WHEN: - | WHY: -\n\n"
            "Question: {q}\n")


@torch.no_grad()
def gen(m, tok, prompt, n=140):
    st = m.new_state(); logits = m(torch.tensor([tok.encode(prompt)]), st); out = []
    for _ in range(n):
        nxt = logits[0, -1].argmax().item(); out.append(nxt); s = tok.decode(out)
        if "\n\n" in s or s.count("\n") >= 6: break
        logits = m(torch.tensor([[nxt]]), st)
    return tok.decode(out).split("\n\n")[0]


def load_canon():
    """the AG4 clause file is being written by another process; retry a torn read"""
    for _ in range(10):
        try: return json.load(open(CANON_FILE, encoding="utf-8"))
        except json.JSONDecodeError: time.sleep(3)
    return {}


def parse(text):
    out = []
    for line in text.split("\n"):
        m = LINE.search(line.strip())
        if m:
            d = {k: (v.strip() if v.strip() not in ("-", "") else None) for k, v in zip(SLOTS, m.groups())}
            if d not in out: out.append(d)
    return out


def provenance_ok(d, allowed):
    for k in SLOTS:
        v = d.get(k)
        if v and v != "?":
            for w in content(v):
                if w not in allowed and A.lemma(w) not in allowed: return False
    return True


def main():
    from rwkv7 import RWKV7, tokenizer
    m = RWKV7.load(CKPT); m.eval(); tok = tokenizer()
    S = json.load(open("val_all13.json", encoding="utf-8"))["stories"]
    done = json.load(open(OUT, encoding="utf-8")) if os.path.exists(OUT) else {}
    stats = collections.Counter(done.pop("_stats", {})); t0 = time.time()
    for k in STORIES:
        s = S[k]
        if s["id"] in done and done[s["id"]].get("qs"): continue
        if FROM_CANON and s["id"] not in load_canon(): stats["story:canon not ready"] += 1; continue
        rec = done.get(s["id"]) or {}
        if "lines" not in rec:
            sents = [x.strip() for x in A.SENT.split(s["text"]) if x.strip()]; names = set(); prev = ""; lines = []; last_who = None
            units = [(x, x) for x in sents]
            if FROM_CANON:                                                            # AG12: units are the AG4 canonical clauses
                CAN = load_canon(); sents = [x.strip() for x in A.SENT.split(CAN[s["id"]]["canon"]) if x.strip()]; units = [(x, x) for x in sents]
                if WITH_SENT:                                                         # AG13: each clause with its source sentence
                    units = [(c, l["sent"]) for l in CAN[s["id"]]["log"] for c in (l["kept"] or [l["sent"]])]
            for sent, src in units:
                tk = toks(sent); names |= {t.lower() for t in tk[1:] if t[0].isupper()} | ({tk[0].lower()} if tk and tk[0][0].isupper() and tk[0].lower() not in STOP else set())
                allowed = set(content(sent)) | {A.lemma(w) for w in content(sent)} | set(content(src)) | {A.lemma(w) for w in content(src)} | set(content(prev)) | names | {"the", "a", "an"}
                for d in parse(gen(m, tok, S_PROMPT3.format(sent=src, clause=sent) if WITH_SENT else S_PROMPT.format(sent=sent))):
                    if not d["WHO"] or not d["DID"]: stats["line:no who/did"] += 1; continue
                    if not provenance_ok(d, allowed): stats["line:invented"] += 1; continue
                    if d["WHO"].lower() in PRON:
                        if last_who: d["WHO"] = last_who; stats["line:pronoun resolved"] += 1
                    elif content(d["WHO"]): last_who = d["WHO"]
                    d["sent"] = sent; lines.append(d); stats["line:kept"] += 1
                prev = sent
            rec["lines"] = lines
        qs = []
        QF = QLINES or ("ag12_lines.json" if ALL else "ag10_lines.json")
        if FROM_CANON and os.path.exists(QF):                                          # AG12: question lines reused where they exist
            Q10 = json.load(open(QF, encoding="utf-8")).get(s["id"], {}).get("qs")
            if Q10: rec["qs"] = Q10; done[s["id"]] = rec; done["_stats"] = dict(stats); json.dump(done, open(OUT, "w", encoding="utf-8"), indent=1); print(f"  story {k} {s['id']} ({time.time() - t0:.0f} s) {dict(stats)}".encode("ascii", "replace").decode(), flush=True); continue
        for q, g in s["qs"]:
            allowed = set(content(q)) | {A.lemma(w) for w in content(q)} | {"the", "a", "an"}
            ds = parse(gen(m, tok, Q_PROMPT.format(q=q), n=60)); qd = None
            for d in ds:
                if sum(1 for v in d.values() if v == "?") > 1: stats["q:blanks"] += 1; continue          # AG13c allowance: the syntax rule places a missing "?"
                if not d["DID"] or d["DID"] == "?": stats["q:no did"] += 1; continue
                if not provenance_ok(d, allowed): stats["q:invented"] += 1; continue
                qd = d; stats["q:kept"] += 1; break
            if qd is None and not ds: stats["q:unparsed"] += 1
            qs.append(dict(q=q, gold=g, qline=qd))
        rec["qs"] = qs; done[s["id"]] = rec; done["_stats"] = dict(stats)
        json.dump(done, open(OUT, "w", encoding="utf-8"), indent=1)
        print(f"  story {k} {s['id']} ({time.time() - t0:.0f} s) {dict(stats)}".encode("ascii", "replace").decode(), flush=True)
    print(f"AG10 stages done ({time.time() - t0:.0f} s)", flush=True)


def match(filler, span):
    f = [w for w in ent(filler).split() if w not in STOP]; s = [w for w in ent(span or "").split() if w not in STOP]
    if not f: return True
    if not s: return False
    return bool(set(f) & set(s)) or bool({A.lemma(w) for w in f} & {A.lemma(w) for w in s}) or f[-1] == s[-1]


def answer(lines, qd):
    asked = next((k for k, v in qd.items() if v == "?"), None)
    if asked is None or not qd.get("DID"): return None
    qv = {A.lemma(w) for w in qd["DID"].lower().split() if w not in STOP and A.lemma(w) not in ("be", "do", "have") or len(qd["DID"].split()) == 1}
    if not qv: qv = {A.lemma(qd["DID"].split()[-1])}
    for d in lines:
        if not d.get("DID"): continue
        dv = {A.lemma(w) for w in d["DID"].lower().split()}
        if not (qv & dv): continue                                                     # AG16: any shared word lemma
        if all(match(qd[k], d.get(k)) for k in SLOTS if k != asked and qd.get(k)):
            a = d.get(asked)
            if a and ent(a) and ent(a) not in PRON: return a
    return None


def grammar(q, qd):
    """AG10b: the formal question language's syntax decides which slot is asked"""
    if not qd: return None
    w = q.lower().rstrip("?").split(); asked = next((k for k, v in qd.items() if v == "?"), None)
    aux = len(w) > 1 and re.fullmatch(r"did|does|do|had|has|was|were|is|are", w[1]) is not None
    want = {"who": "WHAT" if aux else "WHO", "what": "WHAT", "where": "WHERE", "when": "WHEN", "why": "WHY"}.get(w[0])
    if want is None or asked == want: return qd
    d = dict(qd)
    if want == "WHO" and asked == "WHAT" and d.get("WHO"): d["WHO"], d["WHAT"] = "?", d["WHO"]; return d
    if want == "WHAT" and asked == "WHO" and d.get("WHAT"): d["WHO"], d["WHAT"] = d["WHAT"], "?"; return d
    if d.get(want) in (None, "-"):
        if asked: d[asked] = None
        d[want] = "?"; return d
    return None


def score():
    D = json.load(open(OUT, encoding="utf-8")); D.pop("_stats", None); G = "--grammar" in ARGV
    r = w = sil = 0; byk = collections.defaultdict(lambda: [0, 0, 0]); rows = []
    for sid, rec in D.items():
        for qq in rec.get("qs", []):
            qd = grammar(qq["q"], qq["qline"]) if G else qq["qline"]
            a = answer(rec["lines"], qd) if qd else None; kind = qq["q"].split()[0].lower()
            if a is None: sil += 1; byk[kind][2] += 1
            elif hit(a, qq["gold"]): r += 1; byk[kind][0] += 1
            else: w += 1; byk[kind][1] += 1
            rows.append(dict(q=qq["q"], gold=qq["gold"], answer=a, qline=qq["qline"]))
    json.dump(rows, open(OUT.replace("_lines", "_rows"), "w", encoding="utf-8"), indent=1)
    print(f"AG10 untouched val_fresh2: {r} right / {w} wrong / {sil} silent / fitness {r - 3 * w} / precision {r / max(1, r + w):.2f}")
    print("AG10 by kind (right, wrong, silent):", dict(byk))
    print("AG10 stats:", json.load(open(OUT, encoding="utf-8")).get("_stats"))


if __name__ == "__main__":
    if "--score" not in ARGV: main()
    score()
