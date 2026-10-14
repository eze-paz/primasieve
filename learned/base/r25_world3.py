"""R25-cz-t: the R25-ct-t world state with the hand verb lists for give / take / release replaced by the rules the next-word
game learned on the generator stories (R24-f, r24_hold_results.json). Run: py -3.12 r25_world3.py"""
import os, sys, json, inspect
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE))
import worldstate as WS, r25_world2 as W2, r24_dict as Dct
RULE = {}
for k, v in json.load(open(os.path.join(HERE, "r24_hold_results.json")))["rules"].items():
    b = Dct.verb_base(k)
    if b and v != "none": RULE.setdefault(b, v)
src = W2.src
for old, new in (('elif v in ("give", "hand", "pass", "lend"):', 'elif RULE.get(v) == "give":'),
                 ('elif v in ("take", "steal", "find", "pick", "catch", "grab", "buy", "receive", "get"):', 'elif RULE.get(v) == "hold":'),
                 ('elif v in ("leave", "put", "set", "drop", "hang", "lay", "place"):', 'elif RULE.get(v) == "release":')):
    assert old in src, old; src = src.replace(old, new)
ns = dict(vars(WS)); ns["RULE"] = RULE; exec(compile("\n".join(l[4:] for l in src.splitlines()), "r25_world3_read", "exec"), ns)
class World3(W2.World2):
    read = ns["read"]
if __name__ == "__main__":
    import shutil
    print("R25-cz-t emerged rules used:", RULE, flush=True)
    if not os.path.exists(os.path.join(HERE, "r25_world2_answers_w1.json")): shutil.copy(os.path.join(HERE, "r25_world2_answers.json"), os.path.join(HERE, "r25_world2_answers_w1.json"))
    W2.World2 = World3                                                    # answers(): column 0 = R19 (W0), column 1 = World3
    W2.answers(); shutil.copy(os.path.join(HERE, "r25_world2_answers.json"), os.path.join(HERE, "r25_world3_answers.json"))
    print("--- columns: W0 (R19) and W3 (emerged rules) ---", flush=True); W2.report()
    shutil.copy(os.path.join(HERE, "r25_world2_answers_w1.json"), os.path.join(HERE, "r25_world2_answers.json"))
    print("--- columns: W0 (R19) and W1 (hand rules, R25-ct-t) ---", flush=True); W2.report()
