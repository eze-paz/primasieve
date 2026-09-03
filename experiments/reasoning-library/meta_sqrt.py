import os, ast, json
from meta_reason import solve_ucb, solve_iterdeep, load_tests
import reasoner_code as rc
name = "sqrt"
tests = load_tests(name)
src = open(os.path.expanduser(f"~/quixbugs/python_programs/{name}.py")).read()
print("=== buggy sqrt ==="); print(src)
# what does the PROVEN engine do?
dom = rc.CodeDomain(name, src, tests)
from reasoner_core import reason
st, score, meta = reason(dom, budget=40000)
fix = next((d for d,a,b in meta["trace"] if b==0), None)
print(f"proven reasoner_code: score={score} tried={meta['tried']} fix={fix}")
# what does the meta-controller do? (trace the forms)
ep = []; ok, en, _ = solve_ucb(name, src, tests, ep)
print(f"\nmeta solve_ucb: solved={ok} energy={en}")
print("form trace:", [(e['form'], e['before'], e['after']) for e in ep])
# iterdeep?
iok, ien, _ = solve_iterdeep(name, src, tests)
print(f"iterdeep: solved={iok} energy={ien}")
