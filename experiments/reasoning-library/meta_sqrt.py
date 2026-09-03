import os
from meta_reason import solve_ucb, load_tests
name = "sqrt"; tests = load_tests(name)
src = open(os.path.expanduser(f"~/quixbugs/python_programs/{name}.py")).read()
ep = []; ok, en, _ = solve_ucb(name, src, tests, ep)
print(f"sqrt: solved={ok} energy={en}")
print("forms:", [(e['form'], e['before'], e['after']) for e in ep])
