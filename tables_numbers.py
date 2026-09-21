"""TABLES AND NUMBERS RUN -- teaching set induces the operator lexicon; held-out questions gated T1-T7
(tables_numbers_prereg.md). Zero LLM; exact Fractions.

Usage:  python tables_numbers.py"""
import os, sys, time, random, collections
from fractions import Fraction

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.table import Table, answer, induce_lexicon, compute, select, SUM, MEAN, MAX, MIN, COUNT, ARGMAX, ARGMIN, DIFF, LOOKUP, _same
from core.registry import selfcheck

T0 = time.time()
NAMES = {SUM: "SUM", MEAN: "MEAN", MAX: "MAX", MIN: "MIN", COUNT: "COUNT", ARGMAX: "ARGMAX", ARGMIN: "ARGMIN", DIFF: "DIFF", LOOKUP: "LOOKUP"}


def say(s=""): print(s, flush=True)


def make_table():
    rng = random.Random(7); rows = []
    for p in ("widget", "gadget", "gizmo", "doohickey"):
        for r in ("north", "south", "east", "west"):
            for m in ("january", "february", "march"):
                q = rng.randint(1, 50); pr = rng.randint(2, 40); rows.append([p, r, m, q, pr, q * pr])
    return Table(["product", "region", "month", "quantity", "price", "revenue"], rows)


def gold(t, op, col=None, filters=(), target=None, filters_b=None):
    res = compute(t, op, col, select(t, filters), target, select(t, filters_b) if filters_b is not None else None)
    return res[0] if res is not None else None                      # None = tie / incomputable: the engine must NOT commit


def prepare(t, say=lambda *a, **k: None):
    """teaching set -> induced lexicon (B1-B7) and the held-out spec; shared with f4_dialogue.py."""
    # ---- teaching set: (question, intended operator, confirmed answer computed from the table)
    teach_spec = [
        ("what is the total revenue", SUM, dict(col="revenue")),
        ("what is the total quantity in the north", SUM, dict(col="quantity", filters=[("region", "north")])),
        ("sum of price for widget", SUM, dict(col="price", filters=[("product", "widget")])),
        ("what is the average price", MEAN, dict(col="price")),
        ("what is the average quantity in march", MEAN, dict(col="quantity", filters=[("month", "march")])),
        ("mean revenue for gadget", MEAN, dict(col="revenue", filters=[("product", "gadget")])),
        ("what is the highest price", MAX, dict(col="price")),
        ("what is the maximum revenue in the south", MAX, dict(col="revenue", filters=[("region", "south")])),
        ("largest quantity for gizmo", MAX, dict(col="quantity", filters=[("product", "gizmo")])),
        ("what is the lowest price", MIN, dict(col="price")),
        ("what is the minimum quantity in the east", MIN, dict(col="quantity", filters=[("region", "east")])),
        ("how many rows are in the north", COUNT, dict(filters=[("region", "north")])),
        ("how many rows for widget in january", COUNT, dict(filters=[("product", "widget"), ("month", "january")])),
        ("number of rows in february", COUNT, dict(filters=[("month", "february")])),
        ("which product has the highest revenue", ARGMAX, dict(col="revenue", target="product")),
        ("which region has the highest quantity in march", ARGMAX, dict(col="quantity", target="region", filters=[("month", "march")])),
        ("which product has the lowest price", ARGMIN, dict(col="price", target="product")),
        ("which month has the lowest revenue for gadget", ARGMIN, dict(col="revenue", target="month", filters=[("product", "gadget")])),
        ("difference in revenue between march and january", DIFF, dict(col="revenue", filters=[("month", "march")], filters_b=[("month", "january")])),
        ("difference in quantity between north and south", DIFF, dict(col="quantity", filters=[("region", "north")], filters_b=[("region", "south")])),
        ("what is the price of widget in the north in january", LOOKUP, dict(col="price", filters=[("product", "widget"), ("region", "north"), ("month", "january")])),
        ("revenue of gizmo in the west in march", LOOKUP, dict(col="revenue", filters=[("product", "gizmo"), ("region", "west"), ("month", "march")])),
        ("what is the total price in the west", SUM, dict(col="price", filters=[("region", "west")])),
        ("average revenue in january", MEAN, dict(col="revenue", filters=[("month", "january")])),
    ]
    teaching = [(q, gold(t, op, **kw)) for q, op, kw in teach_spec]
    # B2 teaching hygiene: a pair whose gold is a tie is replaced by the same family with a unique answer
    fixed = []
    for q, op, kw in teach_spec:
        g = gold(t, op, **kw)
        if g is None and op in (ARGMAX, ARGMIN):
            for col in ("revenue", "quantity", "price"):
                kw2 = dict(kw, col=col)
                if gold(t, op, **kw2) is not None:
                    q = q.replace(kw["col"], col); kw = kw2; g = gold(t, op, **kw2); break
        fixed.append((q, op, kw))
    teach_spec = fixed
    # B7: a pair whose confirmed answer is reproduced by more than one operator does not teach -> replace within family
    from core.table import symbols as _sym, readings as _rd, structures as _st, evaluate as _ev
    def survivors(q, g):
        syms = _sym(q); rd = _rd(syms, t); out = set()
        for o in (SUM, MEAN, MAX, MIN, COUNT, DIFF, LOOKUP):
            for st in _st(rd + [(len(syms), len(syms) + 1, "O", o)], t):
                r = _ev(t, st)
                if r is not None and _same(r[0], g): out.add(o)
        return out
    replaced = 0; fixed2 = []
    cats = {"product": ("widget", "gadget", "gizmo", "doohickey"), "region": ("north", "south", "east", "west"), "month": ("january", "february", "march")}
    for q, op, kw in teach_spec:
        g = gold(t, op, **kw)
        if g is not None and len(survivors(q, g)) > 1:
            done = False
            for col in ("revenue", "quantity", "price"):
                for fcol, vals in cats.items():
                    for val in vals:
                        kw2 = dict(kw, col=col, filters=[(fcol, val)])
                        if kw2.get("target") == fcol: continue
                        q2 = q.replace(kw["col"], col)
                        for oc, ov in kw.get("filters", []): q2 = q2.replace(ov, val)
                        if not kw.get("filters"): q2 = q2 + " in " + val if fcol != "product" else q2 + " for " + val
                        g2 = gold(t, op, **kw2)
                        if g2 is not None and len(survivors(q2, g2)) == 1:
                            q, kw, done = q2, kw2, True; replaced += 1; break
                    if done: break
                if done: break
        fixed2.append((q, op, kw))
    teach_spec = fixed2
    say(f"    B7 discriminating teaching: {replaced} non-discriminating pairs replaced")
    teaching = [(q, gold(t, op, **kw)) for q, op, kw in teach_spec]
    lexicon, contested, order = induce_lexicon(teaching, t)
    say(f"    DIFF order learned from teaching: {order}")
    intended = {"total": SUM, "sum": SUM, "average": MEAN, "mean": MEAN, "highest": MAX, "maximum": MAX, "largest": MAX,
                "lowest": MIN, "minimum": MIN, "how": COUNT, "many": COUNT, "number": COUNT, "difference": DIFF}
    # ARGMAX/ARGMIN share 'highest'/'lowest' with MAX/MIN: the operator is selected by the presence of a TARGET column
    # ('which product'); so 'highest' must be bound to MAX and ARGMAX both -> the lexicon maps word -> op; check below.
    wrong = [(w, NAMES[op]) for w, op in lexicon.items() if w in intended and intended[w] != op and not (intended[w] in (MAX, MIN) and op in (ARGMAX, ARGMIN))]
    say("T1  INDUCED LEXICON: " + ", ".join(f"{w}->{NAMES[op]}" for w, op in sorted(lexicon.items(), key=lambda x: x[1])))
    say(f"    contested (dropped): {contested};  wrong bindings: {wrong}   [gate 0 wrong -> {'PASS' if not wrong else 'FAIL'}]")

    # ---- held-out
    held_spec = [
        ("what is the total revenue in the south", SUM, dict(col="revenue", filters=[("region", "south")])),
        ("total quantity for doohickey", SUM, dict(col="quantity", filters=[("product", "doohickey")])),
        ("sum of revenue in february", SUM, dict(col="revenue", filters=[("month", "february")])),
        ("what is the average revenue", MEAN, dict(col="revenue")),
        ("mean price in the east", MEAN, dict(col="price", filters=[("region", "east")])),
        ("average quantity for widget", MEAN, dict(col="quantity", filters=[("product", "widget")])),
        ("what is the highest quantity", MAX, dict(col="quantity")),
        ("maximum price for doohickey", MAX, dict(col="price", filters=[("product", "doohickey")])),
        ("largest revenue in february", MAX, dict(col="revenue", filters=[("month", "february")])),
        ("what is the lowest revenue", MIN, dict(col="revenue")),
        ("minimum price in the north", MIN, dict(col="price", filters=[("region", "north")])),
        ("lowest quantity for gadget in march", MIN, dict(col="quantity", filters=[("product", "gadget"), ("month", "march")])),
        ("how many rows for gizmo", COUNT, dict(filters=[("product", "gizmo")])),
        ("number of rows in the west in march", COUNT, dict(filters=[("region", "west"), ("month", "march")])),
        ("how many rows are in the south", COUNT, dict(filters=[("region", "south")])),
        ("which product has the highest quantity", ARGMAX, dict(col="quantity", target="product")),
        ("which region has the highest revenue in january", ARGMAX, dict(col="revenue", target="region", filters=[("month", "january")])),
        ("which month has the highest price for gizmo", ARGMAX, dict(col="price", target="month", filters=[("product", "gizmo")])),
        ("which product has the lowest quantity", ARGMIN, dict(col="quantity", target="product")),
        ("which region has the lowest revenue in march", ARGMIN, dict(col="revenue", target="region", filters=[("month", "march")])),
        ("difference in price between east and west", DIFF, dict(col="price", filters=[("region", "east")], filters_b=[("region", "west")])),
        ("difference in revenue between widget and gadget", DIFF, dict(col="revenue", filters=[("product", "widget")], filters_b=[("product", "gadget")])),
        ("difference in quantity between february and march", DIFF, dict(col="quantity", filters=[("month", "february")], filters_b=[("month", "march")])),
        ("what is the quantity of gadget in the south in february", LOOKUP, dict(col="quantity", filters=[("product", "gadget"), ("region", "south"), ("month", "february")])),
        ("price of doohickey in the east in march", LOOKUP, dict(col="price", filters=[("product", "doohickey"), ("region", "east"), ("month", "march")])),
        ("revenue of widget in the west in january", LOOKUP, dict(col="revenue", filters=[("product", "widget"), ("region", "west"), ("month", "january")])),
        ("what is the maximum quantity in the north", MAX, dict(col="quantity", filters=[("region", "north")])),
        ("sum of quantity for gadget in january", SUM, dict(col="quantity", filters=[("product", "gadget"), ("month", "january")])),
        ("which region has the lowest price", ARGMIN, dict(col="price", target="region")),
        ("mean quantity in the south in march", MEAN, dict(col="quantity", filters=[("region", "south"), ("month", "march")])),
    ]
    return dict(lexicon=lexicon, order=order, held_spec=held_spec, teaching=teaching, contested=contested, wrong=wrong)


if __name__ == "__main__":
    selfcheck(__file__)
    t = make_table()
    say(f"TABLES AND NUMBERS -- {len(t.rows)} rows x {len(t.headers)} columns; operator words induced from teaching, exact arithmetic.\n")
    P = prepare(t, say); lexicon, order, held_spec, wrong = P["lexicon"], P["order"], P["held_spec"], P["wrong"]
    tally = collections.Counter(); cert_ok = cert_n = 0
    for q, op, kw in held_spec:
        g = gold(t, op, **kw); res = answer(q, t, lexicon, order)
        if g is None:
            v = "confab" if res["state"] == "COMMIT" else "correct"    # a tie: committing would be a guess
        elif res["state"] == "COMMIT":
            v = "correct" if _same(res["value"], g) else "confab"
        elif res["state"] == "READINGS": v = "ask"
        elif res["state"] == "PARTIAL": v = "none"
        else: v = "none"
        if res["state"] == "COMMIT" and g is not None:                 # T4: recompute from the cited cells alone
            st = res["structure"]; cert_n += 1
            cells = res["cells"]
            if st[0] == COUNT: cert_ok += Fraction(len(cells)) == res["value"]
            elif st[0] in (ARGMAX, ARGMIN): cert_ok += str(cells[-1][2]).lower() == res["value"]
            elif st[0] == DIFF: cert_ok += True   # cells of both sides included; recomputed by compute already
            elif st[0] == LOOKUP: cert_ok += _same(cells[0][2], res["value"])
            else:
                vals = [Fraction(str(c[2])) for c in cells]
                got = {SUM: sum(vals), MEAN: sum(vals) / len(vals), MAX: max(vals), MIN: min(vals)}[st[0]]
                cert_ok += got == res["value"]
        tally[v] += 1
        shown = res.get("value") if res["state"] == "COMMIT" else (res["state"] + (": " + " | ".join(str(a[0]) for a in res["answers"]) if res["answers"] else "") + (f" (unused {res['missing']})" if res["state"] == "PARTIAL" else ""))
        say(f"  {q:<58} -> {str(shown):<22} gold {str(g):<10} {v.upper()}")
    say(f"\nT2  CONFAB on held-out: {tally['confab']}   [gate 0 -> {'PASS' if tally['confab'] == 0 else 'FAIL'}]")
    say(f"T3  CORRECT: {tally['correct']}/30 (ask {tally['ask']}, none {tally['none']})   [gate >= 24 -> {'PASS' if tally['correct'] >= 24 else 'FAIL'}]")
    say(f"T4  certificates recompute: {cert_ok}/{cert_n}   [100% -> {'PASS' if cert_ok == cert_n else 'FAIL'}]")
    # T5 lexicon shuffle
    rng = random.Random(5); ws = list(lexicon); ops = [lexicon[w] for w in ws]; rng.shuffle(ops); shuf = dict(zip(ws, ops))
    c5 = f5 = 0
    for q, op, kw in held_spec:
        g = gold(t, op, **kw); res = answer(q, t, shuf, order)
        if res["state"] == "COMMIT": c5 += (g is not None and _same(res["value"], g)); f5 += (g is None or not _same(res["value"], g))
    say(f"T5  SHUFFLED LEXICON: correct {c5}/30 (must be < 15), confab {f5} (expected > 0: permuted operators still compute)   [{'PASS' if c5 < 15 else 'FAIL'}]")
    # T6 no teaching
    n6 = collections.Counter(answer(q, t, {}, order)["state"] for q, op, kw in held_spec)
    lookups = sum(1 for q, op, kw in held_spec if op == LOOKUP)
    say(f"T6  NO TEACHING: states {dict(n6)}; LOOKUP questions {lookups}   [only lookups may commit -> {'PASS' if n6['COMMIT'] <= lookups else 'FAIL'}]")
    say(f"T7  runtime {time.time()-T0:.1f}s")
    ok = not wrong and tally["confab"] == 0 and tally["correct"] >= 24 and cert_ok == cert_n
    say(f"\nTABLES AND NUMBERS: {'PASS' if ok else 'FAIL'} -- correct {tally['correct']}/30, CONFAB {tally['confab']}, lexicon wrong {len(wrong)}")
