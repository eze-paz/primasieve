"""R5 data: binding supervision from REAL text, with the hand-rule reader as the teacher. For sentences of training
Gutenberg books, the EventReader (core/events.py) gives (agent, verb, patient); kept only when the sentence is short,
holds one realis event, the agent is a name or a 'the X' noun, the patient a short phrase without coordination, and no
pronoun stands in either. Each kept event yields two questions ("Who kept bees?" -> Nadia; "What did Nadia keep?" ->
bees) and a v3 trace (grep over the surrounding ~1,500 words of the same book, two-sentence hits).
Run: python learned/base/real_qa.py [--books N] [--time-one]  -> r5_train.json, r5_val.json"""
import os, sys, re, json, random, time
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "learned")); sys.path.insert(0, HERE)
from data import books, read
from store import Store, render, query_for, SENT

PRON = {"he", "she", "it", "they", "him", "her", "them", "his", "their", "its", "i", "you", "we", "me", "us", "this", "that", "these", "those", "who", "which", "what"}
AUX = {"was", "were", "is", "are", "be", "been", "being", "had", "have", "has", "do", "did", "does", "could", "would", "should", "might", "may", "can", "will", "shall", "must"}


def clean_event(e, sent):
    toks = re.findall(r"[A-Za-z']+|[^\sA-Za-z']", sent)
    if not (6 <= len(toks) <= 22): return None
    a, p, v = e.get("agent") or "", e.get("patient") or "", e.get("verb") or ""
    if e.get("status") != "realis" or not a or not p or not v or v in AUX: return None
    if any(w.lower() in PRON for w in a.split() + p.split()): return None
    if " and " in a or " and " in p or "," in a or "," in p or len(p.split()) > 4 or len(a.split()) > 3: return None
    if not (a[:1].isupper() or a.lower().startswith("the ")): return None
    pos = e.get("pos");  wt = re.findall(r"[A-Za-z']+", sent)
    if pos is None or pos >= len(wt): return None
    surface = wt[pos]                                                   # the verb as it stands in the sentence ("kept")
    if surface.lower() == v or not surface.islower(): return None       # past/finite form only, so "Who kept ...?" reads well
    if pos > 0 and wt[pos - 1].lower() in AUX: return None              # "is cultivated": a passive read as active
    if a[:1].isupper() and not a.lower().startswith("the ") and sent.startswith(a) and a.split()[0] not in NAMES: return None   # "Cotton is ..." is not a name
    if sent.rstrip().endswith("?") or re.search(r"\b(Mr|Mrs|Dr|St|Messrs)\.$", sent.rstrip()): return None
    pw = p.split()[0]
    if not (pw.lower() in ("the", "a", "an", "his", "her", "their", "its", "my", "our", "your", "this", "that") or (pw[:1].isupper() and pw in NAMES)):
        return None                                                     # the patient must be a noun phrase, not "audibly" / "open" / "still alive"
    ia, ip = sent.find(a), sent.find(p)
    if ia < 0 or ip < 0: return None                                    # the reader resolved a pronoun from an earlier sentence: not this sentence's own
    before = sent[:ia].rstrip()
    if before and not re.search(r"(^|\b(and|but|then|when|as|while|so|where|though|for)\b|[,;:])$", before, re.I):
        return None                                                     # the agent must open its clause ("In the afternoon we went" / "a shriek from Europe made" are not its agent)
    iv = sent.find(surface)
    if not (ia < iv < ip): return None                                   # agent, verb, patient in that order inside the sentence
    if a.lower().startswith("the "): a = "the " + a[4:]
    return dict(agent=a, patient=p, verb=v, surface=surface)


NAMES = set()
try:
    _n = json.load(open(os.path.join(ROOT, "learned", "cache", "names.json"), encoding="utf-8"))["pool"]
    NAMES = set(_n["f"]) | set(_n["m"]) | set(_n["o"])
except Exception: pass


def questions(c):
    return [(f"Who {c['surface']} {c['patient']}?", [c["agent"].lower(), c["agent"].lower().replace("the ", "")]),
            (f"What did {c['agent']} {c['verb']}?", [c["patient"].lower(), c["patient"].lower().replace("the ", "").replace("a ", "").replace("an ", "")])]


def main():
    n_books = int(sys.argv[sys.argv.index("--books") + 1]) if "--books" in sys.argv else 40
    import battery
    D = battery.door(); reader = D.events.reader
    train_ids, _ = books(); R = random.Random(9); ids = R.sample(train_ids, n_books + 5)
    out = {"train": [], "val": []}; T0 = time.time(); kept = seen = 0
    for bi, b in enumerate(ids):
        split = "val" if bi >= n_books else "train"
        text = read(b); sents = [s.strip() for s in SENT.split(text.replace("\n", " ")) if s.strip()]
        for i in range(0, len(sents)):
            s = sents[i]
            if len(s) > 160 or '"' in s or "'" in s[:1]: continue
            seen += 1
            try: ev = reader.read(s)
            except Exception: continue
            if len(ev) != 1: continue
            c = clean_event(ev[0], s)
            if not c: continue
            kept += 1
            lo = max(0, i - 40); hi = min(len(sents), i + 40); st = Store(" ".join(sents[lo:hi]))
            for q, gold in questions(c):
                query = query_for(q); hits = st.grep(query, 3, window=1)
                found = any(any(re.sub(r"[^a-z0-9 ]", " ", g.lower()).strip() in re.sub(r"[^a-z0-9 ]", " ", h.lower()) for g in gold) for _, h in hits)
                if not found: continue
                out[split].append(dict(book=b, sentence=s, q=q, gold=gold, prompt=render(q, query, hits), answer=gold[0]))
            if "--time-one" in sys.argv and kept >= 30: break
        print(f"book {b}: {len(sents)} sentences, kept so far {kept} of {seen} seen, {len(out['train'])} train / {len(out['val'])} val examples ({time.time() - T0:.0f} s)", flush=True)
        if "--time-one" in sys.argv: break
    # unknown cases: a train question asked over a store from a different book (15%)
    R.shuffle(out["train"]); extra = []
    for ex in out["train"][: len(out["train"]) // 6]:
        other = R.choice(out["train"])
        if other["book"] == ex["book"]: continue
        st = Store(other["prompt"].split("Hits:\n")[1].split("\nAnswer:")[0]) if False else None
        extra.append(dict(book=ex["book"], sentence=ex["sentence"], q=ex["q"], gold=["unknown"], prompt=other["prompt"].replace(other["q"], ex["q"]).replace(other["prompt"].split("\n")[1], "Search: " + query_for(ex["q"])), answer="unknown"))
    out["train"] += extra; R.shuffle(out["train"])
    json.dump(out["train"], open(os.path.join(HERE, "r5_train.json"), "w", encoding="utf-8"), indent=0)
    json.dump(out["val"], open(os.path.join(HERE, "r5_val.json"), "w", encoding="utf-8"), indent=1)
    print(f"done: {len(out['train'])} train (incl. {len(extra)} unknown), {len(out['val'])} val; kept events {kept} of {seen} sentences ({time.time() - T0:.0f} s)")
    for ex in out["train"][:3]: print(ex["q"], "->", ex["answer"], "|", ex["sentence"][:100])


if __name__ == "__main__":
    main()
