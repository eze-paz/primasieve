"""Dump the tight-subset instances (s0/s1:line-mod + clean s2:insert) with the fields the
end-to-end reasoner needs, and pick 5 across distinct repos. No Docker."""
import json, re, ast
from swebench_census import parse_patch, classify

def load():
    import datasets
    d=datasets.load_dataset("princeton-nlp/SWE-bench_Lite", split="test")
    return d

def target_file(files):
    src=[f for f in files if f[0].endswith(".py") and "/test" not in f[0]
         and not f[0].endswith("_test.py") and not f[0].startswith("test")]
    return src[0][0] if len(src)==1 else None

if __name__=="__main__":
    d=load(); rows=[]
    for r in d:
        files=parse_patch(r["patch"]); b=classify(files)
        if b in ("s0/s1:line-mod","s2:insert"):
            tf=target_file(files)
            if not tf: continue
            try: f2p=json.loads(r["FAIL_TO_PASS"]); p2p=json.loads(r["PASS_TO_PASS"])
            except Exception: f2p=r["FAIL_TO_PASS"]; p2p=r["PASS_TO_PASS"]
            rows.append({"iid":r["instance_id"],"repo":r["repo"],"base":r["base_commit"],
                         "bucket":b,"file":tf,"f2p":f2p,"p2p_n":len(p2p),
                         "patch_lines":r["patch"].count("\n")})
    json.dump(rows, open("swebench_tight.json","w"), indent=0)
    print(f"tight subset: {len(rows)} instances")
    byrepo={}
    for x in rows: byrepo.setdefault(x["repo"],[]).append(x)
    # pick 5 across distinct repos, smallest patch first within repo
    pick=[]
    for repo in sorted(byrepo, key=lambda r:len(byrepo[r])):
        cand=sorted(byrepo[repo], key=lambda x:(len(x["f2p"]), x["patch_lines"]))
        pick.append(cand[0])
    pick=sorted(pick, key=lambda x:x["patch_lines"])[:5]
    print("\nrepos present:", {k:len(v) for k,v in byrepo.items()})
    print("\n=== 5 picked (distinct repos, smallest) ===")
    for x in pick:
        print(f"  {x['iid']:34s} {x['bucket']:14s} f2p={len(x['f2p'])} p2p={x['p2p_n']:4d} {x['file']}")
    json.dump(pick, open("swebench_pick5.json","w"), indent=1)
