"""KG MULTI-HOP RUN -- 40 fixed questions with gold (kg_multihop_prereg.md), Wikidata live + cache, gates G1-G6.
The English rendering below is the chat layer's; the core returns structure + certificates only.

Usage:  python kg_multihop.py [--offline]"""
import os, sys, time, random, sqlite3, collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "emergence"))
from core.kg import answer, symbols
from core.verdict import ATTRIBUTED
from core.registry import selfcheck
from kb_wikidata import Wikidata

HERE = os.path.dirname(os.path.abspath(__file__))
T0 = time.time()
SRC = None

Q = [  # (type, question, gold set: any of these labels counts; None = NOT FOUND expected; "READINGS" = ask acceptable)
    ("LOOKUP", "what is the capital of france", {"paris"}),
    ("LOOKUP", "what is the capital of japan", {"tokyo"}),
    ("LOOKUP", "what is the currency of japan", {"japanese yen", "yen"}),
    ("LOOKUP", "what is the official language of brazil", {"portuguese", "brazilian portuguese"}),
    ("LOOKUP", "what is the continent of egypt", {"africa", "asia"}),
    ("LOOKUP", "who is the author of hamlet", {"william shakespeare"}),
    ("LOOKUP", "who is the director of jaws", {"steven spielberg"}),
    ("LOOKUP", "what is the country of the eiffel tower", {"france"}),
    ("LOOKUP", "who is the spouse of barack obama", {"michelle obama"}),
    ("LOOKUP", "what is the place of birth of napoleon", {"ajaccio"}),
    ("CHAIN", "what is the capital of the country of the eiffel tower", {"paris"}),
    ("CHAIN", "what is the official language of the country of the colosseum", {"italian"}),
    ("CHAIN", "what is the currency of the country of mount fuji", {"japanese yen", "yen"}),
    ("CHAIN", "what is the capital of the country of the brandenburg gate", {"berlin"}),
    ("CHAIN", "what is the continent of the country of the taj mahal", {"asia"}),
    ("CHAIN", "what is the capital of the country of citizenship of albert einstein", {"READINGS", "bern", "berlin", "washington, d.c.", "vienna", "rome"}),
    ("CHAIN", "what is the currency of the country of the statue of liberty", {"united states dollar", "us dollar"}),
    ("CHAIN", "what is the official language of the country of machu picchu", {"spanish", "quechua", "aymara", "READINGS"}),
    ("CHAIN", "what is the capital of the country of the acropolis of athens", {"athens"}),
    ("CHAIN", "what is the continent of the place of birth of napoleon", {"europe", None}),
    ("PATH", "how are paris and france related", {"paris", "france"}),
    ("PATH", "how are the eiffel tower and paris related", {"paris", "eiffel tower"}),
    ("PATH", "how are shakespeare and hamlet related", {"william shakespeare", "hamlet"}),
    ("PATH", "how are michelle obama and barack obama related", {"barack obama", "michelle obama"}),
    ("PATH", "how are tokyo and japan related", {"tokyo", "japan"}),
    ("PATH", "how are steven spielberg and jaws related", {"jaws", "steven spielberg"}),
    ("PATH", "how are the amazon river and brazil related", {"brazil", "amazon"}),
    ("PATH", "how are mount everest and nepal related", {"nepal", "mount everest"}),
    ("PATH", "how are the louvre and paris related", {"paris", "louvre"}),
    ("PATH", "how are rome and italy related", {"rome", "italy"}),
    ("MEMBER", "is paris in france", {"france"}),
    ("MEMBER", "is tokyo in japan", {"japan"}),
    ("MEMBER", "is the eiffel tower in paris", {"paris"}),
    ("MEMBER", "is berlin in france", {None}),
    ("MEMBER", "is rome in italy", {"italy"}),
    ("MEMBER", "is madrid in germany", {None}),
    ("MEMBER", "is the louvre in paris", {"paris"}),
    ("MEMBER", "is the colosseum in rome", {"rome"}),
    ("MEMBER", "is kyoto in japan", {"japan"}),
    ("MEMBER", "is lisbon in spain", {None}),
]


def say(s=""): print(s.encode("ascii", "replace").decode(), flush=True)


def make_df():
    db = os.path.join(HERE, "_nldata", "kaikki_all.sqlite")
    if not os.path.exists(db): return None
    con = sqlite3.connect(db); cache = {}
    def df(tok):
        if tok not in cache:
            row = con.execute("select n from df where t=?", (tok,)).fetchone(); cache[tok] = row[0] if row else 0
        return cache[tok]
    return df


def render(src, res):
    """chat-layer English rendering of the structure (NOT the core's)."""
    if res["state"] == ATTRIBUTED:
        parts = []
        for v, lab, edges, certs, kinds in res["answers"]:
            ch = " ; ".join(" -> ".join(f"{src.label(s)} -{src.label(p)}-> {src.label(o)}" for s, p, o in ed) for ed in edges[:1])
            parts.append(f"{lab}  [Wikidata: {ch}]")
        return " | ".join(parts)
    if res["state"] == "READINGS": return "ASK -- " + res["ask"]
    if res["state"] == "PARTIAL": return f"PARTIAL -- resolved {[lab for _, lab, _, _, _ in res['answers']]} but could not apply {res['missing']}"
    if res["state"] == "WEAK":
        w = res["weak"]; return "WEAK -- no direct relation; connected via " + " -> ".join(f"{src.label(s)} -{src.label(p)}-> {src.label(o)}" for s, p, o in w)
    ents = sorted({lab for _, _, k, _, lab in res["readings"] if k == "E"})[:6]; props = sorted({lab for _, _, k, _, lab in res["readings"] if k == "P"})[:6]
    return f"NOT FOUND -- consulted entities {ents} properties {props}"


def judge(res, gold, typ):
    if res["state"] in ("NOT FOUND", "WEAK"):
        return "correct" if None in gold else "none"
    if res["state"] == "PARTIAL": return "none"
    if res["state"] == "READINGS":
        labs = {lab.lower() for _, lab, _, _, _ in res["answers"]}
        return "ask" if ("READINGS" in gold or labs & {g for g in gold if g}) else "ask"
    labs = {lab.lower() for _, lab, _, _, _ in res["answers"]}
    if typ == "PATH":
        for _, _, edges, _, _ in res["answers"]:
            for ed in edges:
                a, b = SRC.label(ed[0][0]).lower(), SRC.label(ed[-1][2]).lower()
                if all(any(g in x for x in (a, b)) for g in gold): return "correct"
        return "confab"
    if None in gold and typ == "MEMBER":
        return "confab"                                         # answered a negative that has no edge in reality
    return "correct" if labs & {g for g in gold if g} else "confab"


if __name__ == "__main__":
    selfcheck(__file__)
    offline = "--offline" in sys.argv
    src = Wikidata(offline=offline); df = make_df(); SRC = src
    say(f"KG MULTI-HOP -- 40 fixed questions, Wikidata {'OFFLINE CACHE' if offline else 'live+cache'}, zero LLM.\n")
    tally = collections.Counter(); per = collections.defaultdict(collections.Counter); certs_ok = certs_total = 0
    for typ, q, gold in Q:
        res = answer(q, src, df)
        v = judge(res, gold, typ)
        if typ == "MEMBER" and res["state"] == ATTRIBUTED and None not in gold:
            v = "correct" if any(g and any(g == src.label(ed[-1][2]).lower() or g == src.label(ed[0][0]).lower() for _, _, edges, _, _ in res["answers"] for ed in edges) for g in gold) else "confab"
        tally[v] += 1; per[typ][v] += 1
        if res["state"] == ATTRIBUTED:
            for _, _, _, certs, _ in res["answers"]: certs_total += 1; certs_ok += bool(certs)
        say(f"  [{typ:<6}] {q}\n           -> {render(src, res)}   => {v.upper()}   [{time.time()-T0:.0f}s]")
    src.save()
    say(f"\nG1  CONFAB (wrong value answered): {tally['confab']}   [gate 0 -> {'PASS' if tally['confab'] == 0 else 'FAIL'}]")
    say(f"G2  CORRECT: {tally['correct']}/40   [gate >= 24 -> {'PASS' if tally['correct'] >= 24 else 'FAIL'}]   per type: " + "; ".join(f"{t}: " + ", ".join(f"{k} {n}" for k, n in sorted(c.items())) for t, c in per.items()))
    say(f"G3  certificates on emitted answers: {certs_ok}/{certs_total}   [100% -> {'PASS' if certs_ok == certs_total else 'FAIL'}]")
    # G4 shuffled symbols
    rng = random.Random(4); sh_correct = sh_confab = 0
    for typ, q, gold in Q[:20]:
        s = symbols(q); rng.shuffle(s)
        res = answer(" ".join(s), src, df); v = judge(res, gold, typ)
        sh_correct += v == "correct"; sh_confab += v == "confab"
    say(f"G4  SHUFFLED symbols (first 20): correct {sh_correct} (real {sum(per[t]['correct'] for t in ('LOOKUP', 'CHAIN'))}), CONFAB {sh_confab}   [correct must fall, confab 0 -> {'PASS' if sh_confab == 0 and sh_correct < sum(per[t]['correct'] for t in ('LOOKUP', 'CHAIN')) else 'FAIL'}]")
    # G5 no source
    class NoSource:
        def entities(self, l): return []
        def properties(self, l): return []
        def claims(self, q): return {}
        def claims_text(self, q): return ""
        def label(self, x): return x
        def consulted(self): return []
    nf = sum(1 for _, q, _ in Q if answer(q, NoSource(), df)["state"] == "NOT FOUND")
    say(f"G5  NO SOURCE: NOT FOUND {nf}/40   [40 -> {'PASS' if nf == 40 else 'FAIL'}]")
    say(f"G6  runtime {time.time()-T0:.0f}s, API calls {src.calls}   [cap 300 s warm]")
    say(f"\nKG MULTI-HOP: {'PASS' if tally['confab'] == 0 and tally['correct'] >= 24 and certs_ok == certs_total else 'FAIL'} -- correct {tally['correct']}/40, ask {tally['ask']}, none {tally['none']}, CONFAB {tally['confab']}")
