"""S1/S2 (sieve_lang_prereg.md): Sieve on morphology. Points = attested word pairs from the training books' vocabulary;
object grammar y = drop_k(x) + c; COMPRESS adopts the most recurring program (core.generate.compress_recurring's plurality rule, counts kept
incrementally for speed) while it covers >= 50 unexplained pairs; the residual triggers the deeper space y = drop_k(x) + f(x) + c (E5); commit/abstain
on 900 held-out novel forms with an exceptionless shape guard (core.verdict.score_two_mode). Knockouts: DECOY
(doubled letters replaced by random consonants), SHUFFLE (outputs shuffled within an ending). Stdlib only.
Run: py -3.12 sieve_morph.py"""
import os, sys, json, time, random, collections
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from core.generate import compress_recurring
from core.vote import plurality
from core.verdict import score_two_mode, line
LX = os.path.join(HERE, "learned", "lx"); t0 = time.time(); MIN = 50
VB = "--b" in sys.argv     # post hoc variant (disclosed in sieve_lang_prereg.md): cleaner pairs, one joint COMPRESS, searched guard
def log(*a): print(*a, f"({time.time() - t0:.0f} s)", flush=True)
V = json.load(open(os.path.join(LX, "lx_vocab.json"), encoding="utf-8"))
cnt = dict(zip(V["words"], V["counts"])); W = sorted(w for w, c in cnt.items() if c >= 3 and w.isalpha() and len(w) >= 3)
gi = os.path.join(LX, "lx_gold_items.json")
if not os.path.exists(gi):
    sys.path.insert(0, LX); import lx_gold; json.dump(lx_gold.items, open(gi, "w"))
GOLD = [tuple(x) for x in json.load(open(gi))]
FUN = {"last": lambda x: x[-1], "second-last": lambda x: x[-2], "first": lambda x: x[0]}
VOW = set("aeiou")
def shape(x): return ("".join("V" if ch in VOW else "C" for ch in x[-3:]), x[-1])

# ---------------- points: attested pairs, endings chosen by frequency ----------------
by_pre = collections.defaultdict(list)
for w in W:
    for n in range(2, len(w) + 1): by_pre[w[:n]].append(w)
pairs = set()
for x in W:
    for k in (0, 1, 2):
        stem = x[:len(x) - k]
        if len(stem) < (3 if VB else 2) or (VB and len(x) < 4): continue
        for y in by_pre.get(stem, ()):
            if y != x and len(x) < len(y) <= len(x) + 4: pairs.add((x, y))
end = collections.Counter(y[-2:] for _, y in pairs); TOP = {e for e, _ in end.most_common(10)}
pairs = sorted(p for p in pairs if p[1][-2:] in TOP)
log(f"{len(W):,} words; {len(pairs):,} pairs ending in the 10 most frequent endings {sorted(TOP)}")

def base_progs(x, y):
    out = []
    for k in (0, 1, 2):
        stem = x[:len(x) - k]
        if len(stem) >= 2 and y.startswith(stem) and len(y) > len(stem): out.append(("B", k, y[len(stem):]))
    return out
def deep_progs(x, y):
    out = []
    for k in (0, 1, 2):
        stem = x[:len(x) - k]
        if len(stem) < 2 or not y.startswith(stem) or len(y) <= len(stem): continue
        for fn, f in FUN.items():
            if y[len(stem)] == f(x): out.append(("D", k, fn, y[len(stem) + 1:]))
    return out
def apply(p, x):
    stem = x[:len(x) - p[1]]
    return stem + p[2] if p[0] == "B" else stem + FUN[p[2]](x) + p[3]
def name(p): return f"drop {p[1]} + '{p[2]}'" if p[0] == "B" else f"drop {p[1]} + {p[2]}(x) + '{p[3]}'"

def sieve(P):
    """COMPRESS the base grammar, then (E5) the deeper space over the residual. -> library [(prog, n)], used-by"""
    lib = []; used = {}; todo = list(P)
    joint = lambda x, y: base_progs(x, y) + deep_progs(x, y)                   # --b: SLEEP over all solutions (emergence.py)
    for space in ((joint,) if VB else (base_progs, deep_progs)):
        # compress_recurring's rule (plurality of the recurring fragment, >= MIN), with the counts kept incrementally
        frag = {p: space(*p) for p in todo}; cc = collections.Counter(f for it in todo for f in frag[it])
        holders = collections.defaultdict(list)
        for it in todo:
            for f in frag[it]: holders[f].append(it)
        alive = set(todo)
        while cc:
            top = plurality(cc); n = cc[top]
            if n < MIN: break
            lib.append((top, n))
            for it in holders[top]:
                if it in alive:
                    alive.discard(it); used[it] = top
                    for f in frag[it]:
                        cc[f] -= 1
                        if cc[f] <= 0: del cc[f]
        todo = [it for it in todo if it in alive]
        if space is base_progs or VB: residual = len(todo)
    return lib, used, residual, todo

lib, used, residual, left = sieve(pairs)
deep = [(p, n) for p, n in lib if p[0] == "D"]
log(f"Sieve: {len(lib)} operators adopted ({len(lib) - len(deep)} base); residual after the base grammar {residual:,} pairs; "
    f"invented from the residual {len(deep)}: " + "; ".join(f"{name(p)} ({n})" for p, n in deep[:12]))
print("   base operators (most used):", "; ".join(f"{name(p)} ({n})" for p, n in lib[:12]))
ex = collections.defaultdict(list)
for it, p in used.items(): ex[p].append(f"{it[0]}->{it[1]}")
for p, n in deep[:6]: print(f"   {name(p)}: e.g. {', '.join(ex[p][:6])}")
print(f"   still unexplained {len(left):,}, e.g. {', '.join(f'{x}->{y}' for x, y in left[:8])}")

# ---------------- S2: commit / abstain on held-out novel forms ----------------
guard = collections.defaultdict(set); slotuse = collections.defaultdict(collections.Counter)
for (x, y), p in used.items(): guard[(shape(x), y[-2:])].add(p); slotuse[y[-2:]][p] += 1
def sieve_predict(q):
    x, slot = q; ps = guard.get((shape(x), slot), set())
    return apply(next(iter(ps)), x) if len(ps) == 1 else None
if VB:                                                                                # guard detail chosen by search (core.search style), leave-one-out on training
    def key(x, n): return ("".join("V" if ch in VOW else "C" for ch in x[-3:]), x[-n:])
    best = None
    for n in (1, 2, 3, 4):
        G = collections.defaultdict(collections.Counter)
        for (x, y), p in used.items(): G[(key(x, n), y[-2:])][p] += 1
        em = cf = 0
        for (x, y), p in used.items():
            c = G[(key(x, n), y[-2:])]; alive = [q for q, v in c.items() if v - (q == p) > 0]
            if len(alive) == 1: em += alive[0] == p; cf += alive[0] != p
        print(f"   guard = last {n} letters + consonant/vowel shape: leave-one-out on training EM {em / len(used):.4f}, confabulation {cf / len(used):.4f}")
        if cf / len(used) <= 0.05 and (best is None or em > best[0]): best = (em, n, G)
    _, NB, GB = best; print(f"   chosen: last {NB} letters")
    def sieve_predict(q):
        x, slot = q; c = GB.get((key(x, NB), slot))
        return apply(next(iter(c)), x) if c and len(c) == 1 else None
def base_predict(q):
    x, slot = q; c = slotuse.get(slot)
    return apply(c.most_common(1)[0][0], x) if c else None
rows = [((l, f[-2:]), f, "invented" if any(apply(p, l) == f for p, _ in deep) and not any(apply(p, l) == f for p, _ in lib if p[0] == "B") else "") for l, f in GOLD]
rs = score_two_mode(sieve_predict, rows); rb = score_two_mode(base_predict, rows)
print("S2, the 900 held-out novel forms (lemma + wanted ending):"); print(line("Sieve (guarded)", rs)); print(line("most frequent op (baseline)", rb))
inv_ok = sum(1 for q, f, tg in rows if tg == "invented" and sieve_predict(q) == f)
print(f"   rows only an invented operator explains: {sum(tg == 'invented' for _, _, tg in rows)}; Sieve committed correctly on {inv_ok}")
bad = [(q[0], f, sieve_predict(q)) for q, f, _ in rows if sieve_predict(q) not in (None, f)]
print(f"   confabulations, e.g. {bad[:10]}")

# ---------------- knockouts ----------------
rng = random.Random(0); CONS = "bcdfghjklmnpqrstvwxz"
def decoy(P):
    out = []
    for x, y in P:
        if y.startswith(x) and len(y) > len(x) and y[len(x)] == x[-1]:
            y = x + rng.choice([c for c in CONS if c != x[-1]]) + y[len(x) + 1:]
        out.append((x, y))
    return out
def shuffle(P):
    by = collections.defaultdict(list)
    for x, y in P: by[y[-2:]].append(y)
    for v in by.values(): rng.shuffle(v)
    it = {e: iter(v) for e, v in by.items()}; return [(x, next(it[y[-2:]])) for x, y in P]
for nm, f in (("DECOY", decoy), ("SHUFFLE", shuffle)):
    lb, _, res, _ = sieve(f(pairs)); dd = [(p, n) for p, n in lb if p[0] == "D"]
    log(f"{nm}: residual {res:,}; invented {len(dd)}: " + "; ".join(f"{name(p)} ({n})" for p, n in dd[:8]) + f"; last-letter operators {sum(p[2] == 'last' for p, _ in dd)}")
