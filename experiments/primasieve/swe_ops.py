"""SWE-OPS -- can a recurring restructure be held as a PRIMITIVE the engine applies? (post hoc to swe_mine_prereg.md)

Owner's requirement: restructure must appear as a coherent primitive the model learns, not a statistic. A
recurring pattern at some abstraction level is only a primitive if it can be APPLIED: given a new function body,
the operator must produce the gold after-state from the gold before-state using nothing but (a) the pattern's
structure, (b) sub-trees copied from the before-state, (c) hole values that occur in the before-state. If the
after-state needs material that appears nowhere in the before-state, the pattern is a description, not a move.

    python swe_ops.py [--level d2] [--min-count 2]

For every abstraction level: the recurring patterns in the training years become candidate operators; for every
held-out structural edit whose pattern recurs, the operator is INSTANTIATED from the before-state and compared
to the gold after-state (ast.dump equality). Reports: recurring patterns, held-out edits they match, and how many
of those are REPRODUCED -- the number that says whether restructure is a primitive here."""
import os, sys, ast, json, collections, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "_nldata", "swe_mine_edits.json")
STRUCTURAL = {"small-mixed-rewrite", "large-rewrite", "add-def/class", "insert:large", "insert:else/elif-branch"}
LEAF_FIELDS = {"id", "attr", "arg", "name", "value", "asname", "module"}


def undump(d):
    """ast.dump -> node (the dump is constructor syntax over the ast namespace)."""
    return eval(d, {k: getattr(ast, k) for k in dir(ast)})


def abstract(node, depth, d=0, holes=None):
    """the pattern at `depth` with a HOLE MAP: hole name -> the concrete leaf value / sub-tree it stands for."""
    holes = {} if holes is None else holes
    if isinstance(node, ast.AST):
        if d >= depth:
            key = ("sub", ast.dump(node))
            holes.setdefault(key, f"<{len(holes)}:{type(node).__name__}>")
            return holes[key], holes
        parts = []
        for f, v in ast.iter_fields(node):
            if f in ("ctx", "type_comment", "kind"): continue
            if f in LEAF_FIELDS and not isinstance(v, (ast.AST, list)):
                key = ("leaf", repr(v)); holes.setdefault(key, f"_{len(holes)}")
                parts.append(f"{f}={holes[key]}"); continue
            sub, _ = abstract(v, depth, d + 1, holes); parts.append(f"{f}={sub}")
        return f"{type(node).__name__}({','.join(parts)})", holes
    if isinstance(node, list):
        return "[" + ",".join(abstract(x, depth, d, holes)[0] for x in node) + "]", holes
    if node is None: return "None", holes
    key = ("leaf", repr(node)); holes.setdefault(key, f"_{len(holes)}")
    return holes[key], holes


def pattern(stmts, depth):
    holes = {}
    parts = [abstract(s, depth, 0, holes)[0] for s in stmts]
    return "[" + ",".join(parts) + "]", holes


def reproducible(rem, add, depth):
    """Is the after-state determined by the pattern plus the before-state? Every hole (leaf or opaque sub-tree)
    that the AFTER pattern uses must be bound in the BEFORE pattern -- then the operator can be instantiated
    from the before-state alone and yields the gold after-state exactly."""
    holes = {}
    for s in rem: abstract(s, depth, 0, holes)
    before_keys = set(holes)
    holes_after = {}
    for s in add: abstract(s, depth, 0, holes_after)
    return all(k in before_keys for k in holes_after), len(holes_after), sum(1 for k in holes_after if k not in before_keys)


if __name__ == "__main__":
    level = sys.argv[sys.argv.index("--level") + 1] if "--level" in sys.argv else "d2"
    depth = {"d1": 1, "d2": 2, "d3": 3}.get(level, 99)
    minc = int(sys.argv[sys.argv.index("--min-count") + 1]) if "--min-count" in sys.argv else 2
    E = json.load(open(CACHE, encoding="utf-8"))
    st = [e for e in E if e["family"] in STRUCTURAL and "dump_rem" in e]
    head_ts = max(e["ts"] for e in st); cutoff = head_ts - 365 * 86400
    train = [e for e in st if e["ts"] < cutoff]; held = [e for e in st if e["ts"] >= cutoff]
    print(f"SWE-OPS -- restructure as an APPLICABLE primitive at level {level}: train {len(train)}  held-out {len(held)}\n")
    freq = collections.Counter(e[level] if level in e else e["skel"] for e in train)
    ops = {k for k, c in freq.items() if c >= minc}
    print(f"recurring patterns (>= {minc} in train): {len(ops)} of {len(freq)}")
    # applicability of the recurring patterns THEMSELVES on their own training instances
    rep_train = tot_train = 0
    for e in train:
        if (e[level] if level in e else e["skel"]) not in ops: continue
        rem = [undump(d) for d in e["dump_rem"]]; add = [undump(d) for d in e["dump_add"]]
        ok, nh, missing = reproducible(rem, add, depth); tot_train += 1; rep_train += ok
    print(f"training edits under a recurring pattern: {tot_train}; after-state determined by pattern + before-state: {rep_train} ({100*rep_train/max(tot_train,1):.1f}%)")
    # held-out: matched by a recurring pattern AND reproducible from the before-state
    matched = rep = 0; examples = []
    for e in held:
        k = e[level] if level in e else e["skel"]
        if k not in ops: continue
        matched += 1
        rem = [undump(d) for d in e["dump_rem"]]; add = [undump(d) for d in e["dump_add"]]
        ok, nh, missing = reproducible(rem, add, depth); rep += ok
        if len(examples) < 6: examples.append((ok, nh, missing, e["shape"], e["family"], e["sha"][:8]))
    print(f"held-out structural edits: {len(held)}; matched by a recurring pattern: {matched} ({100*matched/max(len(held),1):.1f}%); "
          f"of those REPRODUCED from pattern + before-state: {rep} ({100*rep/max(matched,1):.1f}% of matched, {100*rep/max(len(held),1):.1f}% of all)")
    for ok, nh, missing, shp, fam, sha in examples:
        print(f"    {'REPRODUCED ' if ok else 'needs new material'} holes {nh:3d} unbound {missing:3d}  {fam:22s} {shp}  {sha}")
    print(f"\nSWE-OPS {level}: {rep}/{len(held)} held-out structural fixes are one application of a learned primitive")
