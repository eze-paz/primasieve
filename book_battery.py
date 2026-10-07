"""B4-BOOK -- reading prose under the owner's ruling (bookworld_prereg.md): every held-out book is its own world; the
share of its sentences that yield a book-local proposition, with precision on a builder-judged sample.

    python book_battery.py [--it N]      (writes tests/bookworld_judged_itN.json with unjudged items the first time;
                                          once judged, prints precision)"""
import os, sys, re, json, random, hashlib, collections, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "emergence"))
import kb_bookworld as KB
from core.bookworld import Book, tokens

GUT = os.path.join(HERE, "_nldata", "gutenberg")
NOVELS = {"1422", "1550", "1553", "1586"}
T0 = time.time()


def say(s=""): print(str(s).encode("ascii", "replace").decode(), flush=True)


def held_book(bid): return int(hashlib.sha256(f"book:{bid}".encode()).hexdigest(), 16) % 10 == 0


def test_books():
    books = sorted(f[:-4] for f in os.listdir(GUT) if f.endswith(".txt"))
    return [b for b in books if held_book(b)][:10]


def units(B, n=500):
    return [i for i, s in enumerate(B.sents) if 4 <= len(s.split()) <= 60][:n]


def run(it=1, judged_n=(50, 50), control_n=50, hooks=None, knockout=False, book_ids=None):
    R, L = KB.build(); abbr = set(L["abbreviations"])
    say(f"learned: {len(L['abbreviations'])} abbreviations {L['abbreviations'][:30]}; determiners {L['determiners']}; "
        f"chain heads {L['chain_heads']}  ({time.time() - T0:.0f} s)")
    stats = collections.defaultdict(collections.Counter); props_all = []; control = []; books = {}
    for b in (book_ids or test_books()):
        B = KB.book(b, R, L, it=it, knockout=knockout); books[b] = B
        if hooks and "after_build" in hooks: hooks["after_build"](B)
        g = "novels" if b in NOVELS else "others"
        U = set(units(B)); per = {}
        for i in range(len(B.sents)):
            ps = B.read(i)
            if i in U: per[i] = ps
        if hooks and "after_read" in hooks: per = hooks["after_read"](B, per)
        R.last_agent = None; R.last_patient = None
        for i in sorted(U):
            ts = B.toks[i]
            for x in (g, "all"):
                stats[x]["units"] += 1; stats[x]["read"] += bool(per[i])
                stats[x]["abbr_end"] += len(ts) >= 2 and ts[-1] == "." and ts[-2] in abbr
                for p in per[i]: stats[x][p["kind"]] += 1; stats[x]["props"] += 1
            for p in per[i]: props_all.append((g, b, i, p))
            for ev in R.read(B.sents[i]):
                if ev["agent"]: control.append((g, b, i, f"{ev['agent']} | {ev['verb']} | {ev['patient']}"))
        say(f"  {b} [{g}] '{B.title}': {len(B.sents)} sentences, {len(B.entities)} entities, titles {sorted(B.titles)[:8]}; "
            f"units {len(U)}, read {sum(1 for i in U if per[i])}  ({time.time() - T0:.0f} s)")
    for x in ("novels", "others", "all"):
        s = stats[x]
        say(f"B4-book {x}: {s['read']}/{s['units']} = {100 * s['read'] / max(1, s['units']):.1f} %  "
            f"(events {s['event']}, roles {s['role']}, supported {s['supported']}, contradicted {s['contradicted']}; "
            f"units ending in an abbreviation {s['abbr_end']} = {100 * s['abbr_end'] / max(1, s['units']):.2f} %)")
    honesty = sum(1 for g, b, i, p in props_all if p.get("real") or not Book.say(p).startswith("according to "))
    say(f"K3 honesty: book propositions said without context or marked real: {honesty} of {len(props_all)}")
    # judged samples (fixed seeds; the file keeps the builder's labels)
    path = os.path.join(HERE, "tests", f"bookworld_judged_it{it}{'ko' if knockout else ''}.json")
    pron = [x for x in props_all if x[3].get("via")]
    say(f"pronoun-resolved propositions: {len(pron)}; units read only through a pronoun: "
        f"{len({(b, i) for g, b, i, p in pron} - {(b, i) for g, b, i, p in props_all if not p.get('via')})}")
    rnd = random.Random(it)
    nov = [x for x in props_all if x[0] == "novels"]; oth = [x for x in props_all if x[0] == "others"]
    samp = rnd.sample(nov, min(judged_n[0], len(nov))) + rnd.sample(oth, min(judged_n[1], len(oth)))
    csamp = random.Random(100 + it).sample(control, min(control_n, len(control)))
    psamp = random.Random(200 + it).sample(pron, min(30 if knockout else 50, len(pron))) if it >= 2 else []
    if knockout: samp, csamp = [], []
    if os.path.exists(path):
        J = json.load(open(path, encoding="utf-8"))
        for name in ("items", "control", "pronouns"):
            if name not in J: continue
            lab = [x for x in J[name] if x.get("ok") is not None]
            for grp in ("novels", "others"):
                lg = [x for x in lab if x["group"] == grp]
                say(f"precision {name} {grp}: {sum(x['ok'] for x in lg)}/{len(lg)}")
            say(f"precision {name} all: {sum(x['ok'] for x in lab)}/{len(lab)} = {sum(x['ok'] for x in lab) / max(1, len(lab)):.2f}")
    else:
        J = dict(note="labels are the BUILDER's judgement (disclosed): ok = the sentence says this", it=it,
                 items=[dict(group=g, book=b, sent=i, text=books[b].sents[i], prop=Book.say(p), kind=p["kind"],
                             check=p.get("check"), ok=None) for g, b, i, p in samp],
                 control=[dict(group=g, book=b, sent=i, text=books[b].sents[i], prop=e, ok=None) for g, b, i, e in csamp],
                 pronouns=[dict(group=g, book=b, sent=i, prev=books[b].sents[i - 1] if i else "", text=books[b].sents[i],
                                prop=Book.say(p), ok=None) for g, b, i, p in psamp])
        json.dump(J, open(path, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
        say(f"wrote {path} for judging")
    return stats, props_all, books


if __name__ == "__main__":
    it = int(sys.argv[sys.argv.index("--it") + 1]) if "--it" in sys.argv else 1
    run(it, knockout="--knockout" in sys.argv)
