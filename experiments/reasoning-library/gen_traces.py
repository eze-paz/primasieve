"""Synthetic trace generator for the controller. Produces gold (state -> next-action)
decision points from templated tasks whose correct decomposition we KNOW. No teacher
API needed — the structure is defined by construction.

Action types the controller must choose among:
  SEARCH  - look up an external fact
  CALC    - do arithmetic with a tool
  ANSWER  - all facts gathered, produce the grounded answer
  REASON  - creative/opinion/chit-chat: answer directly, no tools
  DEFER   - unanswerable / nothing found: honestly refuse

A task unrolls into decision points: at each step, (goal, steps-so-far) -> next action.
"""
import json, random

ENT = ["France", "Japan", "Brazil", "Egypt", "Canada", "Peru", "Norway", "Kenya"]
CAP = {"France": "Paris", "Japan": "Tokyo", "Brazil": "Brasilia", "Egypt": "Cairo",
       "Canada": "Ottawa", "Peru": "Lima", "Norway": "Oslo", "Kenya": "Nairobi"}
ATTR = ["population", "area", "elevation", "founding year"]
FICT = ["Wakanda", "Grulnar", "the Zorvax Protocol", "Genovia", "the Treaty of Xanth"]

def rf(rng, lo, hi): return rng.randint(lo, hi)

def task_factual(rng):
    e, a = rng.choice(ENT), rng.choice(ATTR)
    goal = f"What is the {a} of {e}?"
    return goal, [("SEARCH", f"{a} of {e}", f"found: {e} {a} is {rf(rng,1,99)} million"),
                  ("ANSWER", None, None)]

def task_multihop(rng):
    e, a = rng.choice(ENT), rng.choice(["population", "area", "elevation"])
    cap = CAP[e]
    goal = f"What is the {a} of the capital of {e}?"
    return goal, [("SEARCH", f"capital of {e}", f"found: the capital of {e} is {cap}"),
                  ("SEARCH", f"{a} of {cap}", f"found: {cap} {a} is {rf(rng,1,20)} million"),
                  ("ANSWER", None, None)]

def task_arith(rng):
    a, b = rf(rng, 10, 9999), rf(rng, 2, 500)
    goal = f"What is {a} times {b}?"
    return goal, [("CALC", f"{a} * {b}", f"{a*b}"), ("ANSWER", None, None)]

def task_mixed(rng):
    e = rng.choice(ENT)
    goal = f"What is the population of the capital of {e}, divided by 1000?"
    cap = CAP[e]; pop = rf(rng, 1, 20) * 1000000
    return goal, [("SEARCH", f"capital of {e}", f"found: the capital of {e} is {cap}"),
                  ("SEARCH", f"population of {cap}", f"found: {cap} population is {pop}"),
                  ("CALC", f"{pop} / 1000", f"{pop//1000}"),
                  ("ANSWER", None, None)]

def task_reason(rng):
    g = rng.choice(["Write a haiku about winter.", "Tell me a short joke.",
                    "What do you think makes a good leader?", "Compose a two-line poem about the sea.",
                    "Give me your opinion on remote work."])
    return g, [("REASON", None, None)]

def task_defer(rng):
    f = rng.choice(FICT)
    g = rng.choice([f"When was {f} signed?", f"What is the population of {f}?",
                    f"Who is the leader of {f}?"])
    return g, [("SEARCH", g, "found: (nothing found)"), ("DEFER", None, None)]

TASKS = [task_factual, task_multihop, task_arith, task_mixed, task_reason, task_defer]

def unroll(goal, steps):
    """Turn a gold trace into (state_text, next_action_label) decision points."""
    points, sofar = [], []
    for (act, arg, obs) in steps:
        state = f"GOAL: {goal}\nSTEPS SO FAR:\n" + ("\n".join(sofar) if sofar else "(none)")
        points.append({"state": state, "label": act})
        if arg is not None:
            sofar.append(f"- did {act} {arg} -> {obs}")
    return points

def generate(n, seed=0):
    rng = random.Random(seed)
    data = []
    for _ in range(n):
        goal, steps = rng.choice(TASKS)(rng)
        data.extend(unroll(goal, steps))
    return data

if __name__ == "__main__":
    tr = generate(1000, seed=0)
    te = generate(250, seed=999)
    json.dump({"train": tr, "test": te}, open("traces.json", "w"))
    from collections import Counter
    print(f"train decision points: {len(tr)}  test: {len(te)}")
    print("train label dist:", dict(Counter(d["label"] for d in tr)))
    print("\nexample decision points:")
    for d in tr[:4]:
        print("  ", repr(d["state"][:70]), "->", d["label"])
