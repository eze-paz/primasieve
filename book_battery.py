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


def in_sent(patient, low, verb_at=None):
    """bookpronoun run 2: a patient carried over from another sentence (a resolved "them") is not this sentence's; run 3:
    the patient must begin within 3 symbols after its verb (a later verb's object is not this one's)"""
    if not patient: return ""
    w = low.split(); pw = [x.lower() for x in patient.split()]
    at = [j for j in range(len(w)) if w[j:j + len(pw)] == pw]
    if not at: return ""
    if verb_at is not None and not any(verb_at < j <= verb_at + 3 for j in at): return ""
    return patient


def word_index(et, k):
    """position of token k among the sentence's word tokens (in_sent works on words)"""
    return sum(1 for x in et[:k] if x[:1].isalnum())


def describe_hook(R, strict=False, pronouns=False):
    """bookdescribe_prereg.md: for a unit the book reader leaves unread, the story reader's realis events whose doer is
    written in the sentence and begins with a learned determiner or a capital, in sentences without a quotation mark"""
    dets = set(getattr(R, "dets", ()))
    def hook(B, per):
        R.last_agent = None; R.last_patient = None
        for i in sorted(per):
            if per[i]: continue
            sent = B.sents[i]
            if any(q in sent for q in '"“”'): continue
            low = " " + " ".join(t for t in tokens(sent) if t[:1].isalnum()).lower() + " "; got = []
            from core.events import tokens as etoks
            et = etoks(sent); words_at = [j for j, x in enumerate(et) if x[:1].isalnum()]
            for ev in R.read(sent):
                a = ev.get("agent")
                if not a or ev.get("status", "realis") != "realis": continue
                aw = a.split()
                if strict:              # bookdescribe run 2: the main clause's own subject, verb right after it, active, lexical
                    if not words_at or aw[0].lower() in R.closed: continue
                    starts = [j for j in range(len(et)) if et[j:j + len(aw)] == aw]
                    if not starts: continue
                    s0 = starts[0]; e0 = s0 + len(aw); first = words_at[0]
                    if not (s0 == first or (s0 == first + 1 and et[first].lower() in dets)): continue
                    k = ev["pos"]; vt = et[k].lower() if k < len(et) else ""
                    if not (k == e0 or (k == e0 + 1 and et[e0][:1].isalnum() and et[e0].lower() not in R.closed)): continue
                    if vt not in R.verbs or vt in R.closed or ev["verb"] in R.closed: continue
                    if k > 0 and et[k - 1].lower() in getattr(R, "auxiliaries", ()): continue
                if " " + " ".join(aw).lower() + " " not in low: continue
                k = low.split().index(aw[0].lower()) if aw[0].lower() in low.split() else -1
                prev = low.split()[k - 1] if k > 0 else ""
                if not (prev in dets or aw[0][:1].isupper()): continue
                got.append(dict(kind="event", subj=(prev + " " if prev in dets else "") + a, rel=ev["verb"], obj=in_sent(ev.get("patient"), low, word_index(et, ev["pos"])),
                                title=B.title, via=None, described=True))
            if not got and pronouns and words_at:          # bookpronoun_prereg.md: the referent said as unresolved
                f0 = words_at[0]; p0 = et[f0].lower()
                if p0 in getattr(R, "subjects", ()) and not (p0 == "who" and sent.rstrip().endswith("?")):
                    for ev in R.read(sent):
                        k = ev["pos"]; vt = et[k].lower() if k < len(et) else ""
                        if ev.get("status", "realis") != "realis": continue
                        if not (k == f0 + 1 or (k == f0 + 2 and et[f0 + 1][:1].isalnum() and et[f0 + 1].lower() not in R.closed)): continue
                        if vt not in R.verbs or vt in R.closed or ev["verb"] in R.closed: continue
                        got.append(dict(kind="event", subj=et[f0], rel=ev["verb"], obj=in_sent(ev.get("patient"), low, word_index(et, ev["pos"])), title=B.title,
                                        via="referent not resolved", described=True)); break
            per[i] = got
        return per
    return hook


def units(B, n=500):
    return [i for i, s in enumerate(B.sents) if 4 <= len(s.split()) <= 60][:n]


def run(it=1, judged_n=(50, 50), control_n=50, hooks=None, knockout=False, book_ids=None, chains=True):
    R, L = KB.build(); abbr = set(L["abbreviations"])
    if it >= 7 and not hooks: hooks = {"after_read": describe_hook(R, strict=it >= 8, pronouns=it >= 9)}
    base_it = 5 if it >= 7 else it                       # bookdescribe_prereg.md: iteration 5's reader plus the hook
    say(f"learned: {len(L['abbreviations'])} abbreviations {L['abbreviations'][:30]}; determiners {L['determiners']}; "
        f"chain heads {L['chain_heads']}  ({time.time() - T0:.0f} s)")
    stats = collections.defaultdict(collections.Counter); props_all = []; control = []; books = {}; bridges = []
    if it >= 5: ST, lookup, related, common = KB.bridger(); say(f"store loaded  ({time.time() - T0:.0f} s)")
    for b in (book_ids or test_books()):
        B = KB.book(b, R, L, it=base_it, knockout=knockout, chains=chains); books[b] = B
        if hooks and "after_build" in hooks: hooks["after_build"](B)
        g = "novels" if b in NOVELS else "others"
        if it >= 5:
            from core.reason import symbols
            for key, (q, kb_, qb) in B.bridge(lookup, related, common, label=lambda q: ST.lab.get(q, ""),
                                              norm=lambda t: " ".join(symbols(t, "LN"))).items():
                ex = next(n[3] for ns in B._names for n in ns if n[2] == key)
                bridges.append(dict(group=g, book=b, name=ex, item=q, label=ST.lab.get(q), evidence_name=" ".join(kb_),
                                    evidence_item=qb, evidence_label=ST.lab.get(qb), ok=None))
        U = set(units(B)); allps = {i: B.read(i) for i in range(len(B.sents))}
        if it >= 3: Book.check(allps, it)                                   # bookcheck (6): checks from the book's own text
        per = {i: allps[i] for i in U}
        if hooks and "after_read" in hooks: per = hooks["after_read"](B, per)
        R.last_agent = None; R.last_patient = None
        for i in sorted(U):
            ts = B.toks[i]
            for x in (g, "all"):
                stats[x]["units"] += 1; stats[x]["read"] += bool(per[i])
                stats[x]["abbr_end"] += len(ts) >= 2 and ts[-1] == "." and ts[-2] in abbr
                for p in per[i]:
                    stats[x][p["kind"]] += 1; stats[x]["props"] += 1
                    if p.get("check") == "SUPPORTED": stats[x]["supported"] += 1
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
    honesty = sum(1 for g, b, i, p in props_all if p.get("real") or not KB.say(p).startswith("according to "))
    say(f"K3 honesty: book propositions said without context or marked real: {honesty} of {len(props_all)}")
    # judged samples (fixed seeds; the file keeps the builder's labels)
    tag = sys.argv[sys.argv.index("--tag") + 1] if "--tag" in sys.argv else ""      # a fresh judged sample for a new reader
    path = os.path.join(HERE, "tests", f"bookworld_judged_it{it}{'ko' if knockout else ''}{'' if chains else 'nochain'}{tag}.json")
    pron = [x for x in props_all if x[3].get("via")]
    say(f"pronoun-resolved propositions: {len(pron)}; units read only through a pronoun: "
        f"{len({(b, i) for g, b, i, p in pron} - {(b, i) for g, b, i, p in props_all if not p.get('via')})}")
    rnd = random.Random(it)
    nov = [x for x in props_all if x[0] == "novels"]; oth = [x for x in props_all if x[0] == "others"]
    samp = rnd.sample(nov, min(judged_n[0], len(nov))) + rnd.sample(oth, min(judged_n[1], len(oth)))
    csamp = random.Random(100 + it).sample(control, min(control_n, len(control)))
    psamp = random.Random(200 + it).sample(pron, min(30 if knockout else 50, len(pron))) if it >= 2 else []
    if knockout or not chains: samp, csamp, psamp = [], [], []
    for grp in ("novels", "others"):
        say(f"G2 bridges {grp}: {sum(1 for x in bridges if x['group'] == grp)} names tied to a world-store item with evidence")
    say(f"G3 bridged propositions: {sum(1 for x in props_all if x[3].get('ref'))}; marked real: {sum(1 for x in props_all if x[3].get('real'))}")
    sup = [x for x in props_all if x[3].get("check") == "SUPPORTED"]
    say(f"E4 checks: {len(sup)} of {len(props_all)} test-unit propositions SUPPORTED by another sentence of their book "
        f"({100 * len(sup) / max(1, len(props_all)):.1f} %)")
    ssamp = random.Random(300 + it).sample(sup, min(30, len(sup))) if it >= 3 and chains and not knockout else []
    if os.path.exists(path):
        J = json.load(open(path, encoding="utf-8"))
        for name in ("items", "control", "pronouns", "checks", "bridges"):
            if name not in J: continue
            lab = [x for x in J[name] if x.get("ok") is not None]
            for grp in ("novels", "others"):
                lg = [x for x in lab if x["group"] == grp]
                say(f"precision {name} {grp}: {sum(x['ok'] for x in lg)}/{len(lg)}")
            say(f"precision {name} all: {sum(x['ok'] for x in lab)}/{len(lab)} = {sum(x['ok'] for x in lab) / max(1, len(lab)):.2f}")
    else:
        J = dict(note="labels are the BUILDER's judgement (disclosed): ok = the sentence says this", it=it,
                 items=[dict(group=g, book=b, sent=i, text=books[b].sents[i], prop=KB.say(p), kind=p["kind"],
                             check=p.get("check"), ok=None) for g, b, i, p in samp],
                 control=[dict(group=g, book=b, sent=i, text=books[b].sents[i], prop=e, ok=None) for g, b, i, e in csamp],
                 pronouns=[dict(group=g, book=b, sent=i, prev=books[b].sents[i - 1] if i else "", text=books[b].sents[i],
                                prop=KB.say(p), ok=None) for g, b, i, p in psamp],
                 checks=[dict(group=g, book=b, sent=i, text=books[b].sents[i], prop=KB.say(p), other=p["support"],
                              other_text=books[b].sents[p["support"]], ok=None) for g, b, i, p in ssamp],
                 bridges=random.Random(400 + it).sample(bridges, min(40, len(bridges))))
        json.dump(J, open(path, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
        say(f"wrote {path} for judging")
    return stats, props_all, books


if __name__ == "__main__":
    it = int(sys.argv[sys.argv.index("--it") + 1]) if "--it" in sys.argv else 1
    run(it, knockout="--knockout" in sys.argv, chains="--nochains" not in sys.argv)
