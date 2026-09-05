"""STAGE 2 -- compositional grammar induction (zero-LLM, pure stdlib). Induces an INTERPRETER from command->output
pairs and generalizes BY CONSTRUCTION to novel combinations and to outputs longer than any seen.

GENERIC combinator inventory (frozen; deliberately contains NO dataset-specific token, count or ordering fact):
  PRIM(seq)              a word denotes a constant output sequence (possibly empty)
  PREPEND(seq)           X -> seq ++ X
  APPEND(seq)            X -> X ++ seq
  REPEAT(k)              X -> X repeated k
  PREPEND_EACH(seq,k)    X -> (seq ++ X) repeated k
  CONCAT / CONCAT_REV    binary connective joining two phrases, in order or reversed
Induction: (1) primitives from one-word commands; (2) binary connectives = words that split a command into two
halves whose outputs compose (order induced); (3) modifier units (1-2 tokens) applied left-to-right to the running
phrase, each operator SOLVED against observed outputs; (4) SOUND gate -- the induced grammar must reproduce EVERY
training pair exactly, else the offending rule is rejected. Test: unique derivation -> COMMIT, else ABSTAIN."""
import os, sys, collections, itertools

def rep(seq, k): return tuple(seq) * k

class Grammar:
    def __init__(self):
        self.prim = {}        # word -> tuple(actions)
        self.unary = {}       # unit(tuple of 1-2 words) -> ('REPEAT',k)|('PREPEND',seq)|('APPEND',seq)|('PREPEND_EACH',seq,k)
        self.binary = {}      # word -> 'CONCAT' | 'CONCAT_REV'

    def apply_unary(self, op, x):
        t = op[0]
        if t == "REPEAT": return rep(x, op[1])
        if t == "PREPEND": return tuple(op[1]) + tuple(x)
        if t == "APPEND": return tuple(x) + tuple(op[1])
        if t == "PREPEND_EACH": return rep(tuple(op[1]) + tuple(x), op[2])
        return None

    def interp(self, cmd):
        """Interpret a command; None if the grammar does not determine an output."""
        cmd = list(cmd)
        # 1. split at a top-level binary connective (rightmost => left-assoc reading)
        for i in range(len(cmd) - 1, -1, -1):
            w = cmd[i]
            if w in self.binary and 0 < i < len(cmd) - 1:
                L = self.interp(cmd[:i]); R = self.interp(cmd[i + 1:])
                if L is None or R is None: return None
                return tuple(L) + tuple(R) if self.binary[w] == "CONCAT" else tuple(R) + tuple(L)
        # 2. phrase = head primitive + modifier units applied left to right
        if not cmd: return None
        head = cmd[0]
        if head not in self.prim: return None
        cur = tuple(self.prim[head]); j = 1
        while j < len(cmd):
            for span in (2, 1):                       # prefer the longer modifier unit
                unit = tuple(cmd[j:j + span])
                if len(unit) == span and unit in self.unary:
                    nxt = self.apply_unary(self.unary[unit], cur)
                    if nxt is None: return None
                    cur = nxt; j += span; break
            else:
                return None
        return cur

def solve_unary(base, out, maxk=8, maxseq=4):
    """Find every generic operator mapping base -> out."""
    base = tuple(base); out = tuple(out); res = []
    for k in range(2, maxk + 1):
        if out == rep(base, k): res.append(("REPEAT", k))
    if len(out) >= len(base) and out[len(out) - len(base):] == base:
        pre = out[:len(out) - len(base)]
        if 0 < len(pre) <= maxseq: res.append(("PREPEND", pre))
    if len(out) >= len(base) and out[:len(base)] == base:
        suf = out[len(base):]
        if 0 < len(suf) <= maxseq: res.append(("APPEND", suf))
    for k in range(2, maxk + 1):
        if len(out) % k: continue
        blk = out[:len(out) // k]
        if rep(blk, k) == out and len(blk) >= len(base) and blk[len(blk) - len(base):] == base:
            pre = blk[:len(blk) - len(base)]
            if 0 < len(pre) <= maxseq: res.append(("PREPEND_EACH", pre, k))
    return res

def _peel(G, cmd):
    """Apply known units left-to-right from the head; return (current_output, index_of_first_unknown) or None."""
    if not cmd or cmd[0] not in G.prim: return None
    cur = tuple(G.prim[cmd[0]]); j = 1
    while j < len(cmd):
        for span in (2, 1):
            unit = tuple(cmd[j:j + span])
            if len(unit) == span and unit in G.unary:
                nxt = G.apply_unary(G.unary[unit], cur)
                if nxt is None: return None
                cur = nxt; j += span; break
        else:
            break
    return cur, j

def induce(train, rounds=8):
    G = Grammar()
    actions = sorted({a for _, seq in train for a in seq})
    for c, a in train:                                        # (1) primitives from one-word commands
        if len(c) == 1: G.prim[c[0]] = tuple(a)
    # (1b) JOINT bootstrap: with no one-word commands the head primitive and the modifier operator are mutually
    # unknown (circular). Solve them together on two-token commands: pick each modifier's most-supported operator,
    # then the head base consistent with it. Generic; the sound gate below discards anything inconsistent.
    bases = [()] + [(x,) for x in actions]
    two = [(c[0], c[1], tuple(a)) for c, a in train if len(c) == 2]
    if two:
        mod_ops = collections.defaultdict(collections.Counter)
        for h, m, out in two:
            seen = set()
            for b in bases:
                for op in solve_unary(b, out): seen.add(op)
            for op in seen: mod_ops[m][op] += 1
        chosen = {m: cc.most_common(1)[0][0] for m, cc in mod_ops.items() if cc}
        head_b = collections.defaultdict(collections.Counter)
        for h, m, out in two:
            op = chosen.get(m)
            if op is None: continue
            for b in bases:
                if G.apply_unary(op, b) == out: head_b[h][b] += 1
        for h, cc in head_b.items():
            if h not in G.prim and cc: G.prim[h] = cc.most_common(1)[0][0]
        for m, op in chosen.items(): G.unary.setdefault((m,), op)
    train_s = sorted(train, key=lambda ca: len(ca[0]))         # shortest first: bootstrap simple units
    for _ in range(rounds):
        added = 0
        # (2) unary units: solve the TRAILING unknown span, preferring a SINGLE token over a 2-token blob
        for span_pref in (1, 2):
            prop = collections.defaultdict(collections.Counter)
            for c, a in train_s:
                if any(w in G.binary for w in c) or len(c) < 2: continue
                p = _peel(G, c)
                if p is None: continue
                cur, j = p
                rem = list(c[j:])
                if len(rem) != span_pref: continue             # only when exactly this span remains
                for op in solve_unary(cur, tuple(a)): prop[tuple(rem)][op] += 1
            for unit, cc in prop.items():
                if unit in G.unary: continue
                b = cc.most_common()
                if len(b) == 1 or b[0][1] > b[1][1]:
                    G.unary[unit] = b[0][0]; added += 1
        # (3) unknown head primitives (incl. the EMPTY primitive) solved from fully-known modifiers
        pp = collections.defaultdict(collections.Counter)
        for c, a in train_s:
            if any(w in G.binary for w in c) or len(c) < 2 or c[0] in G.prim: continue
            for cand in [()] + [(x,) for x in actions]:
                G.prim[c[0]] = cand
                p = _peel(G, c)
                ok = p is not None and p[1] == len(c) and p[0] == tuple(a)
                del G.prim[c[0]]
                if ok: pp[c[0]][cand] += 1
        for w, cc in pp.items():
            b = cc.most_common()
            if len(b) == 1 or b[0][1] > b[1][1]: G.prim[w] = b[0][0]; added += 1
        # (4) binary connectives by MAJORITY, using interpretation of the two halves
        cand = collections.defaultdict(collections.Counter)
        for c, a in train_s:
            for i in range(1, len(c) - 1):
                w = c[i]
                if w in G.binary: continue
                L = G.interp(c[:i]); R = G.interp(c[i + 1:])
                if L is None or R is None: continue
                if tuple(L) + tuple(R) == tuple(a): cand[w]["CONCAT"] += 1
                elif tuple(R) + tuple(L) == tuple(a): cand[w]["CONCAT_REV"] += 1
        for w, cc in cand.items():
            b = cc.most_common()
            if b[0][1] >= 3 and (len(b) == 1 or b[0][1] > 2 * b[1][1]):
                G.binary[w] = b[0][0]; added += 1
        if not added: break
    # (5) SOUND gate: drop rules implicated in training pairs the grammar gets WRONG (not merely undetermined)
    for _ in range(3):
        bad = collections.Counter(); anybad = False
        for c, a in train:
            r = G.interp(c)
            if r is not None and r != tuple(a):
                anybad = True
                for j in range(len(c)):
                    for span in (1, 2):
                        u = tuple(c[j:j + span])
                        if u in G.unary: bad[u] += 1
                    if c[j] in G.binary: bad[c[j]] += 1
        if not anybad: break
        if not bad: break
        worst, _ = bad.most_common(1)[0]
        if isinstance(worst, tuple): G.unary.pop(worst, None)
        else: G.binary.pop(worst, None)
    return G

def reproduces(G, train):
    ok = tot = 0
    for c, a in train:
        r = G.interp(c)
        tot += 1; ok += (r == tuple(a))
    return ok, tot

def evaluate(G, test):
    C = ok = wrong = hard = 0
    for c, a in test:
        r = G.interp(c)
        if r is None: hard += 1
        else:
            C += 1
            if r == tuple(a): ok += 1
            else: wrong += 1
    n = len(test)
    return dict(n=n, C=C, ok=ok, wrong=wrong, hard=hard, EM=ok / n, cover=C / n,
                P=(ok / C if C else 0.0))

if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(__file__))
    from scan_data import load
    split = sys.argv[1] if len(sys.argv) > 1 else "simple"
    tr, te = load(split)
    G = induce(tr)
    r, t = reproduces(G, tr)
    ev = evaluate(G, te)
    print(f"SCAN {split}: train {len(tr)} test {len(te)}")
    print(f"  primitives {G.prim}")
    print(f"  binary     {G.binary}")
    print(f"  unary      { {' '.join(k): v for k, v in G.unary.items()} }")
    print(f"  reproduces train {r}/{t}")
    print(f"  TEST exact-match {ev['EM']:.3f}  coverage {ev['cover']:.3f}  precision {ev['P']:.3f}  wrong {ev['wrong']}")