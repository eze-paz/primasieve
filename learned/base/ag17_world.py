"""AG17 (AG_prereg.md): World3 (R19 world state, emerged verb rules) reads the AG4 canonical text with the AG15 slot
lines as its events; answers the state questions the slot matcher leaves silent. Untouched dev block, scored once.
Run: py -3.12 ag17_world.py"""
import os, sys, json, collections
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE))
sys.argv = [sys.argv[0], "--score", "--grammar"]
import ag10_slots as G
import ag1_translator as A
import r25_world3 as W3
from b6_rwkv import hit
from ag3_canon import STOP
os.chdir(HERE)


class SlotReader:
    """events of a clause = the slot lines written from it"""
    def __init__(self, lines): self.by = collections.defaultdict(list); self.last_agent = None; self.last_patient = None
    def load(self, lines):
        self.by.clear()
        for l in lines: self.by[(l.get("sent") or "").strip().rstrip(".").lower()].append(l)
    def read(self, s):
        out = []
        for l in self.by.get(s.strip().rstrip(".").lower(), []):
            did = [w for w in (l.get("DID") or "").lower().split() if w not in STOP]
            if not l.get("WHO") or not did: continue
            out.append(dict(agent=l["WHO"], verb=A.lemma(did[0]), patient=l.get("WHAT"), place=l.get("WHERE")))
        return out


def main():
    D = json.load(open("ag15_lines.json", encoding="utf-8")); D.pop("_stats", None)
    C = json.load(open("ag4_canon.json", encoding="utf-8"))
    R = SlotReader([]); res = collections.Counter(); byk = collections.Counter(); rows = []
    for sid, rec in D.items():
        R.load(rec["lines"]); W = W3.World3(R)
        try: W.read(C[sid]["canon"])
        except Exception as e: print("read error", sid, e)
        for qq in rec["qs"]:
            qd = G.grammar(qq["q"], qq["qline"]); a = G.answer(rec["lines"], qd) if qd else None; src = "slots"
            if a is None:
                try: a = W.ask(qq["q"]); src = "world"
                except Exception: a = None
            if a is None: res["silent"] += 1
            elif hit(a, qq["gold"]): res["right"] += 1; byk[src, "right"] += 1
            else: res["wrong"] += 1; byk[src, "wrong"] += 1
            rows.append(dict(q=qq["q"], gold=qq["gold"], answer=a, src=src if a else None))
    r, w, s = res["right"], res["wrong"], res["silent"]
    print(f"AG17 untouched val_fresh2, slots then world: {r} right / {w} wrong / {s} silent / fitness {r - 3 * w} / precision {r / max(1, r + w):.3f}")
    print("AG17 by source:", dict(byk))
    for x in rows:
        if x["src"] == "world": print("  world:", x["q"], "->", x["answer"], "| gold", x["gold"][0])
    json.dump(rows, open("ag17_rows.json", "w", encoding="utf-8"), indent=1)


if __name__ == "__main__":
    main()
