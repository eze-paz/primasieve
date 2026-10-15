"""R27 demo: give a story (a text file or stdin) and questions; prints a retelling and a reply paragraph per question.
The answers come from statement matching + rival check (the comprehension operators); readers are not run here.
Run: py -3.12 r27_demo.py story.txt "Who ...?" "Where ...?" """
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
ARGV0 = list(sys.argv); sys.argv = [sys.argv[0], "--p2d"]
import r27_retell as RT
sys.argv = [ARGV0[0], "--fix2"]
import r26_stmatch as SM
from r27_reply import reply
story = open(ARGV0[1], encoding="utf-8").read() if len(ARGV0) > 1 and os.path.exists(ARGV0[1]) else sys.stdin.read()
print("RETELLING:\n" + RT.realise(story, RT.plan(story)) + "\n")
for q in ARGV0[2:]:
    a = SM.answer(story, q)
    print(f"Q: {q}\nA: {reply(story, q, a)}\n")
