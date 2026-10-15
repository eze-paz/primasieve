"""AG4 (AG_prereg.md): AG3's verified rewriting loop, one level deeper and on every story.
Changes from AG3: (1) a clause rejected as 'no event' or 'fragment' is itself sent back to the model once
('WHO DID WHAT WHERE'), and its pieces pass the same verifier; (2) a copular clause ('X was ADJ / NP / PP') counts as
an event (verb 'be') when the translator finds none; (3) all 502 stories of val_all13.json, the 80 AG3 stories first
(dev: stories 22-101), then the rest. Resumable; writes ag4_canon.json. Run: py -3.12 ag4_canon.py"""
import os, sys, re, json, time, random, collections
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); os.chdir(HERE)
import torch
sys.argv = [sys.argv[0]]
import ag1_translator as A
import ag3_canon as G
from ag3_canon import toks, content, ent, clauses, gen, STOP, PROMPT, PROMPT2
COP = re.compile(r"^((?:the |a |an |his |her |their |its )?[A-Z][\w'-]*(?: [\w'-]+){0,3}?) (was|were|is|are) (.+)$")
ORDER = list(range(22, 102)) + [k for k in range(502) if k < 22 or k >= 102]
PROMPT3 = ("Instruction: Rewrite the sentence as one or two very short sentences of the form WHO DID WHAT WHERE. "
           "Use only words that appear in the sentence.\n\nSentence: {sent}\n\nShort sentences:\n1.")


def events_of(T, clause):
    evs = T.read(clause)
    if evs: return evs
    m = COP.match(clause.strip().rstrip("."))
    if m and m.group(1).split()[0].lower() not in STOP: return [dict(agent=m.group(1), verb="be", patient=m.group(3), place=None, recip=None, copular=True)]
    return []


def verify(T, clause, sent, prev, names, orig_events, stats):
    allowed = content(sent) | content(prev) | {n.lower() for n in names}
    extra = content(clause) - allowed
    if extra: stats["reject:invented"] += 1; return None, "invented"
    own = content(clause) & (content(sent) - content(prev))
    if not own and content(sent) - content(prev): stats["reject:copies context"] += 1; return None, "copies"
    if not toks(clause) or toks(clause)[-1].lower() in STOP or len(content(clause)) < 2: stats["reject:fragment"] += 1; return None, "fragment"
    evs = events_of(T, clause)
    if not evs: stats["reject:no event"] += 1; return None, "no event"
    for e in evs:
        for o in orig_events:
            if o["verb"] == e["verb"] and o.get("patient") and ent(e["agent"]) == ent(o["patient"]) and ent(e["agent"]) != ent(o["agent"]):
                stats["reject:swap"] += 1; return None, "swap"
    stats["accept"] += 1
    if any(e.get("copular") for e in evs): stats["accept:copular"] += 1
    return clause, "ok"


def main():
    from rwkv7 import RWKV7, tokenizer
    data = [s for s in json.load(open("stories_train_v2.json", encoding="utf-8")) if s.get("events")]
    random.Random(0).shuffle(data); F = A.Feats([tk for st in data[:2240] for tk, _ in A.gold_examples(st)])
    vm = A.Tagger(F, 2, False); am = A.Tagger(F, len(A.ATAGS), True); sd = torch.load("ag1_translator.pt"); vm.load_state_dict(sd["vm"]); am.load_state_dict(sd["am"]); vm.eval(); am.eval()
    T = A.Translator(F, vm, am)
    m = RWKV7.load(os.path.join("rwkv7", "RWKV-x070-World-0.4B-v2.9-20250107-ctx4096.pth")); m.eval(); tok = tokenizer()
    S = json.load(open("val_all13.json", encoding="utf-8"))["stories"]
    OUT = "ag4_canon.json"; done = json.load(open(OUT, encoding="utf-8")) if os.path.exists(OUT) else {}
    stats = collections.Counter(done.pop("_stats", {})); t0 = time.time()
    for k in ORDER:
        s = S[k]
        if s["id"] in done: continue
        sents = [x.strip() for x in A.SENT.split(s["text"]) if x.strip()]; names = set(); prev = ""; canon = []; log = []
        for sent in sents:
            tk = toks(sent)
            names |= {t for t in tk[1:] if t[0].isupper()} | ({tk[0]} if tk and tk[0][0].isupper() and tk[0].lower() not in STOP else set())
            orig = events_of(T, sent); kept = []; rejected = []
            for p in (PROMPT, PROMPT2):
                for c in clauses(gen(m, tok, p.format(sent=sent))):
                    v, why = verify(T, c, sent, prev, names, orig, stats)
                    if v and v not in kept: kept.append(v)
                    elif why in ("no event", "fragment") and c not in rejected: rejected.append(c)
                if kept: break
            for c in rejected[:3]:                                                   # depth 2: the rejected clause is rewritten itself
                for c2 in clauses(gen(m, tok, PROMPT3.format(sent=c), n=50)):
                    v, why = verify(T, c2, sent, prev, names, orig, stats)
                    if v and v not in kept: kept.append(v); stats["accept:depth2"] += 1
            if kept: canon.extend(kept); stats["sentence:rewritten"] += 1
            else: canon.append(sent); stats["sentence:kept"] += 1
            if kept and orig:
                got = {(e["verb"], ent(e["agent"])) for c in kept for e in events_of(T, c)}
                stats["signal:events"] += len(orig); stats["signal:recovered"] += sum((o["verb"], ent(o["agent"])) in got for o in orig)
            log.append(dict(sent=sent, kept=kept, rejected=rejected)); prev = sent
        done[s["id"]] = dict(k=k, canon=" ".join(c if c.endswith((".", "!", "?")) else c + "." for c in canon), log=log)
        done["_stats"] = dict(stats); json.dump(done, open(OUT, "w", encoding="utf-8"), indent=1)
        print(f"  story {k} {s['id']} ({time.time() - t0:.0f} s) {dict(stats)}".encode("ascii", "replace").decode(), flush=True)
    print(f"AG4 done ({time.time() - t0:.0f} s)", flush=True)


if __name__ == "__main__":
    main()
