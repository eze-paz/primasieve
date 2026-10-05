"""SPEAK -- wording learned from any text, claims checked by re-reading (speak_prereg.md; FLUENCY_HYPOTHESES.md H1, H2,
H7). Zero LLM. Offline: the chat's worlds, the Wiktionary store, Alice in Wonderland, the text model.

Usage:  python speak.py"""
import os, sys, re, json, time, sqlite3, itertools, collections

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "emergence"))
from core.reason import reason, symbols, _spans
from core.verdict import COMMIT, ATTRIBUTED
from core.textmodel import TextModel
from core.registry import selfcheck
import chat as C
from textmodel import MODEL, KAIKKI

T0 = time.time()
ALICE = os.path.join(HERE, "_nldata", "alice.txt")
SLOT = None                      # a slot in a skeleton (never a symbol)
LICENSE = False                  # wordorder_prereg.md H10b: require attested attachments
ORDER = None                     # wordorder_prereg.md (H10): a core.wordorder.WordOrder; a re-read out of order is rejected


def say(s=""): print(str(s).encode("ascii", "replace").decode(), flush=True)


def skeleton(syms, closed):
    out = []
    for s in syms:
        if s in closed: out.append(s)
        elif not out or out[-1] is not SLOT: out.append(SLOT)
    return tuple(out)


def runs(syms, closed):
    """-> the open-class runs of a token list, as (start, end)"""
    out, i = [], 0
    while i < len(syms):
        if syms[i] in closed: i += 1; continue
        j = i
        while j < len(syms) and syms[j] not in closed: j += 1
        out.append((i, j)); i = j
    return out


def skeletons(closed, relation, max_len=10, min_count=3):
    """-> {skeleton: count}, {skeleton: Counter(source)}, {skeleton: [relation-filler count per slot]} (run 2: slot roles)"""
    counts = collections.Counter(); src = collections.defaultdict(collections.Counter); rel = collections.defaultdict(lambda: [0, 0, 0])
    junction = collections.Counter()                # (left symbol, right symbol) where exactly one is closed-class: the joints of form

    def add(syms, kind):
        for a, b in zip(syms, syms[1:]):
            if (a in closed) != (b in closed): junction[(a, b)] += 1
        sk = skeleton(syms, closed)
        if sk.count(SLOT) != 3 or len(sk) > max_len: return
        counts[sk] += 1; src[sk][kind] += 1
        for k, (a, b) in enumerate(runs(syms, closed)):
            if any(t in relation for t in syms[a:b]): rel[sk][k] += 1
    db = sqlite3.connect(KAIKKI)
    for w, v in db.execute("select w, v from e"):
        e = json.loads(v)
        for kind, sents in (("definitions", e.get("defs", [])), ("examples", e.get("ex", []))):
            for s in sents: add(symbols(str(s), "LN"), kind)
    text = open(ALICE, encoding="utf-8", errors="replace").read()
    for s in re.split(r"[.!?;:]+", text): add(symbols(s, "LN"), "alice")
    keep = {sk: n for sk, n in counts.items() if n >= min_count}
    return keep, src, rel, junction


def show(sk, fill=None):
    it = iter(fill or ["_"] * 3)
    return " ".join(next(it) if t is SLOT else t for t in sk)


def main():
    selfcheck(__file__)
    say("SPEAK -- wording learned from any text, claims checked by re-reading (speak_prereg.md)\n")
    tm = TextModel.load(MODEL); closed = {w for w, c in tm.uni.most_common(100)}
    worlds, df = C.build_worlds()
    for w in worlds:
        if hasattr(w, "induce_lexicon") and hasattr(w, "df"): w.df = df
    # RELATION words (run 2, e): the crawl store's property labels and the worlds' table headers -- data, not a list
    relation = set()
    db = sqlite3.connect(os.path.join(HERE, "_nldata", "wikidata_crawl.sqlite"))
    for (lab,) in db.execute("select label from ent where q like 'P%' and label is not null"):
        relation |= {t for t in symbols(lab, "LN") if t not in closed}
    for w in worlds:
        for t in getattr(getattr(w, "recs", None), "tables", {}).values():
            for h in t.headers: relation |= {x for x in symbols(h, "LN") if x not in closed}
    sks, src, rel, junction = skeletons(closed, relation)
    relslot = {}
    for sk, n in sks.items():
        shares = [c / n for c in rel[sk]]; k = max(range(3), key=lambda i: shares[i])
        if shares[k] >= 0.3 and shares.count(shares[k]) == 1: relslot[sk] = k
    say(f"    relation words: {len(relation)}; skeletons with a relation slot (>= 30 %, unique): {len(relslot)}")
    by_src = collections.Counter(k for sk in sks for k in src[sk])
    say(f"    skeletons with three slots (>= 3 sightings): {len(sks)}; attested in {dict(by_src)}  ({time.time() - T0:.0f} s)")
    top_all = sorted(relslot, key=lambda s: (-sks[s], show(s)))
    # ---- the messages and the links, from the engine's own answered questions
    D = C.Door(worlds, df, seed=3)
    msgs = []; links = collections.Counter()
    for text, typ, gold in C.held_out():
        if typ == "STRESS" or gold is None: continue
        rec = D.turn(text)
        if rec["kind"] not in (COMMIT, ATTRIBUTED) or not rec["values"] or C.score(rec, typ, gold, worlds[0].label) != "correct": continue
        fr = rec["_fr"]; syms = list(fr["syms"])
        if any(getattr(w, "quotes", False) for w in fr["answer_worlds"]): continue
        used = sorted({p for a, w in zip(fr["answers"], fr["answer_worlds"]) for i, j in _spans(w, a[4]) for p in range(i, j) if p < len(syms)})
        if not used: continue
        if len(syms) > 1 and syms[1] in closed and 1 < used[0]: links[syms[1]] += 1          # the symbol after the question word
        rs = runs(syms, closed)
        if len(rs) != 2 or any(p not in used for a, b in rs for p in range(a, b)): continue
        fillers = [" ".join(syms[a:b]) for a, b in rs]
        isrel = [any(t in relation for t in syms[a:b]) for a, b in rs]
        value = str(rec["values"][0])
        if value.lower() in [f.lower() for f in fillers] or isrel.count(True) != 1: continue          # (c); one relation filler
        prop = fillers[isrel.index(True)]; arg = fillers[1 - isrel.index(True)]
        msgs.append(dict(q=text, syms=syms, prop=prop, arg=arg, value=value, prop_first=isrel.index(True) == 0))
    n_ans = sum(links.values()) or 1
    L = {w for w, n in links.items() if n >= 0.1 * n_ans}                                                  # (a)
    say(f"\n    links learned from answered questions (the symbol after the question word): {dict(links)}")
    say(f"    messages (answered, two open-class runs): {len(msgs)}  ({time.time() - T0:.0f} s)")
    top = [sk for sk in top_all if any(t in L for t in sk)][:400]          # run 2 fix: a skeleton can carry a claim only through a link
    say(f"    skeletons with a relation slot AND a link: {len([sk for sk in top_all if any(t in L for t in sk)])}; used (top 400 by count): {len(top)}")
    for sk in top[:10]: say(f"      {sks[sk]:6d}  {show(sk)}   {dict(src[sk])}")
    cache = {}

    def read(side):
        if side not in cache:
            f = reason(side, worlds, df, cats="LN"); ok = None
            if f["kind"] in (COMMIT, ATTRIBUTED) and len(f.get("answers", [])) == 1 and not any(getattr(w, "quotes", False) for w in f["answer_worlds"])                     and not (ORDER is not None and (ORDER.violations(f) or (LICENSE and ORDER.licensed(f, wide=LICENSE == "wide")))):
                ss = f["syms"]; usedp = {p for a, w in zip(f["answers"], f["answer_worlds"]) for i, j in _spans(w, a[4]) for p in range(i, j)}
                if all(p in usedp for p in range(len(ss)) if ss[p] not in closed): ok = str(f["answers"][0][1]).lower()
            cache[side] = ok
        return cache[side]

    def candidates(m, sk):
        """-> [(text, value_side_holds, lookup_side_fillers, accepted)] for every assignment and every link split"""
        out = []; fill = {"value": m["value"], "prop": m["prop"], "arg": m["arg"]}
        for perm in itertools.permutations(["prop", "arg", "value"]):
            if perm[relslot[sk]] != "prop": continue                                                          # (e)
            toks, owner = [], []
            it = iter(perm)
            for t in sk:
                if t is SLOT:
                    role = next(it); ws = symbols(fill[role], "LN"); toks += ws; owner += [role] * len(ws)
                else: toks.append(t); owner.append(None)
            for k, t in enumerate(toks):
                if t not in L or owner[k] is not None: continue
                for vs, ls in ((range(0, k), range(k + 1, len(toks))), (range(k + 1, len(toks)), range(0, k))):
                    vroles = {owner[p] for p in vs} - {None}; lroles = {owner[p] for p in ls} - {None}
                    if len(vroles) != 1 or len(lroles) != 2: continue
                    if any(owner[p] is None for p in vs): continue                                         # (b)
                    side = " ".join(toks[p] for p in ls)
                    got = read(side)
                    ok = got is not None and got == m["value"].lower() and lroles == {"prop", "arg"}             # (d)
                    pf = ok and min(p for p in ls if owner[p] == "prop") < min(p for p in ls if owner[p] == "arg")
                    out.append((" ".join(toks), next(iter(vroles)), lroles, ok, pf))
        return out

    acc = collections.defaultdict(set); acc_sk = collections.defaultdict(set); false_acc = 0; ko_total = ko_false = 0
    ungrounded = 0; examples = collections.defaultdict(list); qsub = 0; reversed_order = 0
    best = collections.defaultdict(lambda: (0, None, None, None))      # S9 (declared after run 2): the wording whose weakest joint is best attested
    for m in msgs:
        q2 = [m["value"].lower()] + m["syms"][1:]
        if read(" ".join(m["syms"][2:])) == m["value"].lower(): qsub += 1
        for sk in top:
            for text, vrole, lroles, ok, pf in candidates(m, sk):
                ko_total += 1; ko_false += vrole != "value"
                if not ok: continue
                if vrole != "value": false_acc += 1
                reversed_order += pf != m["prop_first"]
                fills = set(symbols(m["value"] + " " + m["prop"] + " " + m["arg"], "LN"))
                ungrounded += any(t not in closed and t not in fills for t in text.split())
                acc[m["q"]].add(text); acc_sk[m["q"]].add(sk)
                toks = text.split()
                js = [junction[(a, b)] for a, b in zip(toks, toks[1:]) if (a in closed) != (b in closed)]
                score = min(js) if js else 0
                if score > best[m["q"]][0]: best[m["q"]] = (score, text, sk, pf)
                if len(examples[m["q"]]) < 4 and text not in examples[m["q"]]: examples[m["q"]].append(text)
    covered = [m for m in msgs if acc[m["q"]]]
    skel_used = set().union(*acc_sk.values()) if acc_sk else set()
    prose = [sk for sk in skel_used if src[sk]["examples"] or src[sk]["alice"]]
    alice = [sk for sk in skel_used if src[sk]["alice"]]
    for m in covered[:10]: say(f"    {m['q']!r} -> {examples[m['q']]}")
    say(f"\n    the question with its question word filled, read back: {qsub}/{len(msgs)}")
    fails = []
    s1 = len(covered) >= 0.6 * max(1, len(msgs))
    say(f"S1  coverage {len(covered)}/{len(msgs)}   [>= 60 % -> {'PASS' if s1 else 'FAIL'}]")
    mean = sum(len(acc[m['q']]) for m in covered) / max(1, len(covered))
    s2 = len(skel_used) >= 5 and mean >= 2
    say(f"S2  distinct skeletons accepted {len(skel_used)}; mean wordings per covered message {mean:.1f}   [>= 5, >= 2 -> {'PASS' if s2 else 'FAIL'}]")
    for sk in sorted(skel_used, key=lambda s: -sks[s])[:12]: say(f"      {show(sk)}   {dict(src[sk])}")
    s3 = len(prose) >= 0.3 * max(1, len(skel_used))
    say(f"S3  accepted skeletons attested in examples or Alice: {len(prose)}/{len(skel_used)} (in Alice: {len(alice)})   [>= 30 % -> {'PASS' if s3 else 'FAIL'}]")
    s4 = false_acc == 0
    say(f"S4  accepted sentences with a false slot assignment: {false_acc}   [0 -> {'PASS' if s4 else 'FAIL'}]")
    s5 = ko_false > 0 and ko_false > 0.2 * ko_total
    say(f"S5  knockout (no monitor): {ko_false}/{ko_total} candidates false ({ko_false / max(1, ko_total):.0%})   [> 20 % -> {'PASS' if s5 else 'FAIL'}]")
    s6 = ungrounded == 0
    say(f"S6  accepted sentences with an ungrounded open-class symbol: {ungrounded}   [0 -> {'PASS' if s6 else 'FAIL'}]")
    n_acc = sum(len(v) for v in acc.values())
    say(f"S8  accepted sentences whose property/argument order reverses the question's: {reversed_order} of {n_acc} accepted readings   [printed]")
    chosen = [(m, best[m["q"]]) for m in msgs if best[m["q"]][1]]
    rev9 = sum(1 for m, b in chosen if b[3] != m["prop_first"])
    say(f"\nS9  (analysis, declared after run 2) per message, the accepted wording whose weakest joint is most attested in text:")
    for m, b in chosen: say(f"      {m['q']!r:48s} -> {b[1]!r}  (weakest joint seen {b[0]} times)")
    say(f"    chosen wordings whose property/argument order reverses the question's: {rev9}/{len(chosen)}")
    me = open(__file__, encoding="utf-8").read(); body = me[me.index("def skeleton"):]
    s7 = not re.search(r"""["'](is|the|of|was|and)["']""", body)
    say(f"S7  no English literal in the mechanism: {s7}   [{'PASS' if s7 else 'FAIL'}]")
    for ok, g in ((s1, "S1"), (s2, "S2"), (s3, "S3"), (s4, "S4"), (s5, "S5"), (s6, "S6"), (s7, "S7")):
        if not ok: fails.append(g)
    say(f"\nSPEAK: {'PASS' if not fails else 'FAIL ' + ','.join(fails)}; {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
