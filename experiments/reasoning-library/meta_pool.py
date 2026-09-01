"""P2 — Mixed task pool + train/holdout class split + held-back assertions. ZERO LLM.

Pool (metaplan P2): 26 QuixBugs + synthesis tasks (synth.py-style) + feature-adds
(unified_loop-style) + multi-edit compose tasks. SPLIT: train-classes vs HELD-OUT
classes. Leakage rules: analogs/corpora must not contain holdout solutions verbatim;
DoF and corpora justified a-priori, never from residuals' answers.

Task classes (a-priori, by the defect's SHAPE — not by program identity):
  stratum0   single-token fixes (op/cmp/const/name swaps)
  stratum1   depth-2 expression closure
  stratum2   structural (statement insert/delete, wraps)
  synthesis  build a novel expression from a value-spec (synth.py)
HOLDOUT: all of stratum2 + one synthesis family — the controller and any learned
guidance NEVER see their solutions during training.

Held-back assertions (metaplan 4.3): every task carries extra assertions never shown
to the search; solved = ALL pass, including held-back. For QuixBugs we hold back a
deterministic subset of the JSON testcases; for synthesis we add independent probes.
"""
import os, sys, json, glob, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reasoner_code import load_tests, run_one, QB

# ---- a-priori class assignment (from the P0/P1 episode logs: max stratum that solved) ----
CLASS = {
 "gcd":"stratum0","rpn_eval":"stratum0","sieve":"stratum0","bitcount":"stratum0",
 "bucketsort":"stratum0","find_first_in_sorted":"stratum0","flatten":"stratum0",
 "get_factors":"stratum0","hanoi":"stratum0","mergesort":"stratum0","next_permutation":"stratum0",
 "quicksort":"stratum0","to_base":"stratum0",
 "find_in_sorted":"stratum1","is_valid_parenthesization":"stratum1","kheapsort":"stratum1",
 "kth":"stratum1","lcs_length":"stratum1","next_palindrome":"stratum1","pascal":"stratum1","sqrt":"stratum1",
 "lis":"stratum2","max_sublist_sum":"stratum2","powerset":"stratum2","shunting_yard":"stratum2","wrap":"stratum2",
}
HOLDOUT_CLASSES = {"stratum2"}          # metaplan P2: hold out a whole class
TRAIN_CLASSES    = {"stratum0","stratum1"}

def split_quixbugs():
    """Returns (train, holdout) name lists, split by CLASS, deterministic."""
    names=sorted(f[:-5] for f in os.listdir(f"{QB}/json_testcases") if f.endswith(".json"))
    train=[n for n in names if CLASS.get(n) in TRAIN_CLASSES]
    holdout=[n for n in names if CLASS.get(n) in HOLDOUT_CLASSES]
    return train,holdout

def held_back_tests(name, frac=0.25, seed=7):
    """Split a task's testcases into search-visible and HELD-BACK (never shown to search).
    Deterministic; the search sees ~75%, the final gate checks 100%."""
    tests=load_tests(name)
    rng=random.Random(seed)
    idx=list(range(len(tests)))
    rng.shuffle(idx)
    nhold=max(1,int(len(tests)*frac))
    hold=set(idx[:nhold])
    visible=[tests[i] for i in sorted(set(range(len(tests)))-hold)]
    held=[tests[i] for i in sorted(hold)]
    return visible,held

def verify_full(name, tree_src, extra_held=None):
    """Final gate: compile + run ALL testcases (visible + held-back [+ extra probes])."""
    code=compile(tree_src,"<gate>","exec")
    tests=load_tests(name)+(extra_held or [])
    return all(run_one(code,name,i,e)[0] for i,e in tests)

# ---- synthesis tasks (synth.py-style value-specs; two families, one held out) ----
def synth_pool():
    """Each task: (name, family, examples, arg_names). Family 'arith' trains,
    family 'list' is HELD OUT (metaplan: hold out one synthesis family)."""
    arith=[
        ("syn_a4b4","arith",[({"a":3,"b":2},65),({"a":2,"b":1},15),({"a":5,"b":4},369)],["a","b"]),  # a^4-b^4
        ("syn_sqdiff","arith",[({"a":4,"b":3},7),({"a":10,"b":6},64),({"a":9,"b":5},56)],["a","b"]), # a^2-b^2
        ("syn_quad","arith",[({"x":3},11),({"x":5},27),({"x":1},3)],["x"]),                          # x^2+x-1
    ]
    lst=[
        ("syn_last","list",[({"xs":[1,2,3]},3),({"xs":[9]},9),({"xs":[4,5]},5)],["xs"]),              # xs[-1]
        ("syn_sum2","list",[({"xs":[1,2,3]},3),({"xs":[5,5]},10),({"xs":[2]},2)],["xs"]),            # sum(xs[:2])
    ]
    return arith,lst

if __name__=="__main__":
    train,holdout=split_quixbugs()
    print(f"QuixBugs split: train={len(train)} holdout={len(holdout)}")
    print("  train  :",train)
    print("  holdout:",holdout)
    arith,lst=synth_pool()
    print(f"synthesis: train={len(arith)} (arith) holdout={len(lst)} (list family)")
    for name,_,ex,an in arith+lst:
        print(f"  {name}: {len(ex)} examples")
    # sanity: held-back split leaves the search enough signal
    for n in ("gcd","lis","wrap"):
        vis,held=held_back_tests(n)
        print(f"  {n}: {len(vis)} visible / {len(held)} held-back")
