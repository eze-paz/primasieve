"""Validate the QuixBugs verifier (model-free): run each buggy vs correct program against
its JSON testcases. Buggy should fail some, correct should pass all. Confirms harness +
which bugs manifest in the JSON IO tests (the ones we can score)."""
import os, json, subprocess, tempfile, sys
QB=os.path.expanduser("~/quixbugs")
PY=sys.executable
NAMES=sorted(f[:-5] for f in os.listdir(f"{QB}/json_testcases") if f.endswith(".json"))

def load_tests(name):
    T=[]
    for line in open(f"{QB}/json_testcases/{name}.json"):
        line=line.strip()
        if not line: continue
        obj=json.loads(line)
        # format: [input_args, expected]; input_args may be a single value or list of args
        inp, exp = obj[0], obj[1]
        if not isinstance(inp, list): inp=[inp]
        T.append((inp, exp))
    return T

def verify(src, name, tests, timeout=10):
    runner = src + f"""
import json, copy, types
_tests = {json.dumps(tests)}
_res=[]
for inp, exp in _tests:
    try:
        r = {name}(*copy.deepcopy(inp))
        if isinstance(r, types.GeneratorType): r=list(r)
        if {name!r}=='sqrt': ok = abs(r-exp) < 1e-4
        else: ok = (r == exp)
        _res.append(bool(ok))
    except Exception as e:
        _res.append('ERR:'+type(e).__name__)
print('__R__'+json.dumps(_res))
"""
    with tempfile.NamedTemporaryFile('w', suffix='.py', delete=False, encoding='utf-8') as f:
        f.write(runner); path=f.name
    try:
        p=subprocess.run([PY, path], capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        os.unlink(path); return 0, len(tests)
    os.unlink(path)
    line=next((l for l in p.stdout.splitlines() if l.startswith("__R__")), None)
    if not line: return 0, len(tests)
    res=json.loads(line[5:])
    return sum(1 for x in res if x is True), len(res)

if __name__=="__main__":
    ok_manifest=0; ok_correct=0; bad=[]
    for name in NAMES:
        tests=load_tests(name)
        bsrc=open(f"{QB}/python_programs/{name}.py").read()
        csrc=open(f"{QB}/correct_python_programs/{name}.py").read()
        bp,bt=verify(bsrc,name,tests); cp,ct=verify(csrc,name,tests)
        manifests = bp<bt          # bug shows up in tests
        correct_ok = cp==ct        # correct passes all
        ok_manifest+=manifests; ok_correct+=correct_ok
        flag="" if (manifests and correct_ok) else "  <-- CHECK"
        if not (manifests and correct_ok): bad.append(name)
        print(f"{name:28s} buggy {bp}/{bt}   correct {cp}/{ct}{flag}")
    print(f"\n{ok_manifest}/{len(NAMES)} bugs manifest in tests; {ok_correct}/{len(NAMES)} correct-versions pass all")
    if bad: print("exclude/check:", bad)
