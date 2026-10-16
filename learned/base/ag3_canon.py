"""AG3 (AG_prereg.md): converge each sentence onto canonical clauses that keep the signal.
Stage 1 (model): the pretrained 0.4B model rewrites one sentence (with its predecessor as context) into numbered simple
sentences. Stage 2 (engine, the verifier): a clause is kept only if every content word comes from the sentence, its
predecessor or a name seen so far (no invention), it parses to an event with an agent (AG1 translator), and its
agent is not the original reading's patient for the same verb (no swap); a sentence with no accepted clause is retried
once with a stricter prompt, then kept as written. Stage 3 (--read): World3 with the hand reader and with the AG1
translator answers the questions from the original and from the canonical text; practice = val_more stories (22-61),
untouched = val_fresh2 stories (62-101).
Run: py -3.12 ag3_canon.py            (stages 1-2, resumable, writes ag3_canon.json)
     py -3.12 ag3_canon.py --read     (stage 3)"""
import os, sys, re, json, time, random, collections
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE)); os.chdir(HERE)
import torch
ARGV = list(sys.argv); sys.argv = [sys.argv[0]]
import ag1_translator as A
STORIES = list(range(62, 102)) if "--untouched" in ARGV else list(range(22, 102)); PRACTICE = set(range(22, 62)); UNTOUCHED = set(range(62, 102))
CKPT = ARGV[ARGV.index("--ckpt") + 1] if "--ckpt" in ARGV else os.path.join("rwkv7", "RWKV-x070-World-0.4B-v2.9-20250107-ctx4096.pth")
OUTF = ARGV[ARGV.index("--out") + 1] if "--out" in ARGV else "ag3_canon.json"
STOP = set("""a an the and or but so of to in on at by for with from into onto over under near behind across along up down out off
his her their its he she it they him them this that these those who whom which what when where why how was were is are be been being
had has have did do does not no yes as than then there here very one two three first second last next some any all each every
own back again once more most much many few little own same other such only just also still yet even ever never now soon later
after before until while because if though although when whenever where wherever""".split())


def toks(s): return A.toks(s)


def content(s): return {t.lower() for t in toks(s) if t[0].isalpha() and t.lower() not in STOP}


def ent(x):
    x = re.sub(r"[^a-z0-9 ]", " ", (x or "").lower()).split()
    while x and x[0] in ("the", "a", "an", "his", "her", "their", "its"): x = x[1:]
    return " ".join(x)


PROMPT = ("Instruction: Rewrite the sentence as a numbered list of short, simple sentences. One fact per sentence. "
          "Use only words from the sentence. Keep every name, object, place and time.\n\n"
          "Sentence: {sent}\n\nSimple sentences:\n1.")
PROMPT2 = ("Instruction: Split the sentence into very short sentences of the form WHO DID WHAT WHERE. Use only words that "
           "appear in the sentence.\n\nSentence: {sent}\n\nShort sentences:\n1.")


@torch.no_grad()
def gen(m, tok, prompt, n=90):
    st = m.new_state(); logits = m(torch.tensor([tok.encode(prompt)]), st); out = []
    for _ in range(n):
        nxt = logits[0, -1].argmax().item(); out.append(nxt); s = tok.decode(out)
        if "\n\n" in s or s.count("\n") >= 7: break
        logits = m(torch.tensor([[nxt]]), st)
    return tok.decode(out).split("\n\n")[0]


def clauses(text):
    out = []
    for line in ("1." + text).split("\n"):
        line = re.sub(r"^\s*\d+[.)]\s*", "", line).strip().strip('"')
        if line and line not in out: out.append(line)
    return out


def verify(T, clause, sent, prev, names, orig_events, stats):
    allowed = content(sent) | content(prev) | {n.lower() for n in names}
    extra = content(clause) - allowed
    if extra: stats["reject:invented " + ",".join(sorted(extra))[:40]] += 1; stats["reject:invented"] += 1; return None
    own = content(clause) & (content(sent) - content(prev))
    if not own and content(sent) - content(prev): stats["reject:copies context"] += 1; return None
    if toks(clause)[-1].lower() in STOP or len(content(clause)) < 2: stats["reject:fragment"] += 1; return None
    evs = T.read(clause)
    if not evs: stats["reject:no event"] += 1; return None
    for e in evs:
        for o in orig_events:
            if o["verb"] == e["verb"] and o.get("patient") and ent(e["agent"]) == ent(o["patient"]) and ent(e["agent"]) != ent(o["agent"]):
                stats["reject:swap"] += 1; return None
    stats["accept"] += 1; return clause


def main():
    from rwkv7 import RWKV7, tokenizer
    data = [s for s in json.load(open("stories_train_v2.json", encoding="utf-8")) if s.get("events")]
    random.Random(0).shuffle(data); F = A.Feats([tk for st in data[:2240] for tk, _ in A.gold_examples(st)])
    vm = A.Tagger(F, 2, False); am = A.Tagger(F, len(A.ATAGS), True); sd = torch.load("ag1_translator.pt"); vm.load_state_dict(sd["vm"]); am.load_state_dict(sd["am"]); vm.eval(); am.eval()
    T = A.Translator(F, vm, am)
    m = RWKV7.load(CKPT); m.eval(); tok = tokenizer()
    S = json.load(open("val_all13.json", encoding="utf-8"))["stories"]
    OUT = OUTF; done = json.load(open(OUT, encoding="utf-8")) if os.path.exists(OUT) else {}
    stats = collections.Counter(done.pop("_stats", {})); t0 = time.time()
    for k in STORIES:
        s = S[k]
        if s["id"] in done: continue
        sents = [x.strip() for x in A.SENT.split(s["text"]) if x.strip()]; names = set(); prev = ""; canon = []; log = []
        for sent in sents:
            names |= {t for t in toks(sent)[1:] if t[0].isupper()} | ({toks(sent)[0]} if toks(sent) and toks(sent)[0][0].isupper() and toks(sent)[0].lower() not in STOP else set())
            orig = T.read(sent); kept = []
            for p in (PROMPT, PROMPT2):
                for c in clauses(gen(m, tok, p.format(prev=prev or "(none)", sent=sent))):
                    v = verify(T, c, sent, prev, names, orig, stats)
                    if v and v not in kept: kept.append(v)
                if kept: break
            if kept: canon.extend(kept); stats["sentence:rewritten"] += 1
            else: canon.append(sent); stats["sentence:kept"] += 1
            # signal check: how many of the original reading's events reappear in the kept clauses
            if kept and orig:
                got = {(e["verb"], ent(e["agent"])) for c in kept for e in T.read(c)}
                stats["signal:events"] += len(orig); stats["signal:recovered"] += sum((o["verb"], ent(o["agent"])) in got for o in orig)
            log.append(dict(sent=sent, kept=kept)); prev = sent
        done[s["id"]] = dict(k=k, canon=" ".join(c if c.endswith((".", "!", "?")) else c + "." for c in canon), log=log)
        done["_stats"] = dict(stats); json.dump(done, open(OUT, "w", encoding="utf-8"), indent=1)
        print(f"  story {k} {s['id']} ({time.time() - t0:.0f} s) {dict(stats)}".encode("ascii", "replace").decode(), flush=True)
    print(f"AG3 stages 1-2 done ({time.time() - t0:.0f} s)", flush=True)


def read():
    import r25_world3 as W3, battery
    from b6_rwkv import hit
    H = battery.door().events.reader; os.chdir(HERE)
    data = [s for s in json.load(open("stories_train_v2.json", encoding="utf-8")) if s.get("events")]
    random.Random(0).shuffle(data); F = A.Feats([tk for st in data[:2240] for tk, _ in A.gold_examples(st)])
    vm = A.Tagger(F, 2, False); am = A.Tagger(F, len(A.ATAGS), True); sd = torch.load("ag1_translator.pt"); vm.load_state_dict(sd["vm"]); am.load_state_dict(sd["am"]); vm.eval(); am.eval()
    T = A.Translator(F, vm, am)
    S = json.load(open("val_all13.json", encoding="utf-8"))["stories"]; C = json.load(open("ag3_canon.json", encoding="utf-8"))
    print("AG3 verifier stats:", C.get("_stats"))
    res = collections.defaultdict(lambda: [0, 0])
    for k in STORIES:
        s = S[k]
        if s["id"] not in C: continue
        for rname, rd in (("hand", H), ("translator", T)):
            for tname, text in (("original", s["text"]), ("canonical", C[s["id"]]["canon"])):
                W = W3.World3(rd)
                try: W.read(text)
                except Exception as e: print("read error", s["id"], e)
                for q, g in s["qs"]:
                    try: a = W.ask(q)
                    except Exception: a = None
                    if a is None: continue
                    res[(rname, tname, "practice" if k in PRACTICE else "untouched")][0 if hit(a, g) else 1] += 1
    for key in sorted(res):
        r, w = res[key]; print(f"AG3 {key[0]:10s} reader, {key[1]:9s} text, {key[2]:9s}: {r} right / {w} wrong / fitness {r - 3 * w} / precision {r / max(1, r + w):.2f}")


if __name__ == "__main__":
    read() if "--read" in ARGV else main()
