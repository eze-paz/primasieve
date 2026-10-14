"""R25-da-t: the world state reads its events from the learned role reader (r25_soft.roles_of) -- W4 alone, W5 added to the
hand reader where it found nothing in a sentence. Rules as R25-cz-t (emerged verb rules + three literature rules).
Run: py -3.12 r25_world4.py"""
import os, sys, json, random, time, collections
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE))
sys.argv = [sys.argv[0]]
import r25_soft as S                                                     # chdir to HERE, imports the learned reader stack
T, E, R, B, D0, D, QR = S.T, S.E, S.R, S.B, S.D0, S.D, S.QR
import r25_world3 as W3, r25_world2 as W2
from b6_rwkv import hit
t0 = time.time()
data = json.load(open("stories_train_v2.json", encoding="utf-8")); random.Random(24).shuffle(data); names = T.mid_caps([s["text"] for s in data[:7000]])
train_b, _ = D0.books(); E.induce_verbish([p["text"] for p in B.paragraphs(train_b, 150000)], k=200)
D.ON = True; T.SPAN_STOP.update(D.verb_forms() - E.NOUNISH); QR.ARGV = ["x", "--pron-ref"]
print(f"R25-da-t reader stack ready ({time.time() - t0:.0f} s)", flush=True)


class RoleReader:
    """read(sentence) -> events from the learned role reader"""
    def __init__(self, base=None): self.base = base; self.last_agent = None; self.last_patient = None
    def roles(self, s):
        try:
            cs, cf = R.construction(s, names); rows = S.roles_of([(cs, cf, list(R.LAST_RAWS))])
        except Exception: return []
        out = []
        for r in rows:
            v = D.verb_base(r["verb"]) or r["verb"]
            if r["subj"]: out.append(dict(agent=str(r["subj"]), verb=v, patient=str(r["obj"]) if r["obj"] else None))
        return out
    def read(self, s):
        if self.base is None: return self.roles(s)
        try: ev = [e for e in self.base.read(s) if e.get("agent") and e.get("verb")]
        except Exception: ev = []
        return ev if ev else self.roles(s)


def main():
    import battery
    hand = battery.door().events.reader
    stories = json.load(open("val_all13.json", encoding="utf-8"))["stories"]
    out = []
    for k, s in enumerate(stories):
        ws = []
        for rd in (RoleReader(None), RoleReader(hand)):
            W = W3.World3(rd)
            try: W.read(s["text"])
            except Exception as e: print("read error", s.get("id"), e, flush=True)
            ws.append(W)
        for q, g in s["qs"]:
            row = []
            for W in ws:
                try: row.append(W.ask(q))
                except Exception: row.append(None)
            out.append(row)
        if k % 100 == 0: print(f"  {k} stories ({time.time() - t0:.0f} s)", flush=True)
    json.dump(out, open("r25_world4_answers.json", "w", encoding="utf-8"))
    gold = [g for s in stories for _, g in s["qs"]]; W3a = json.load(open("r25_world3_answers.json", encoding="utf-8"))
    PR = list(range(0, 310)) + list(range(510, 910)); UN = list(range(310, 510)) + list(range(910, 2510))
    def st(idx, col):
        r = w = 0
        for i in idx:
            a = col(i)
            if a is not None: r += bool(hit(a, gold[i])); w += not hit(a, gold[i])
        return r, w, r - 3 * w
    for nm, col in (("W3 hand reader (R25-cz-t)", lambda i: W3a[i][1]), ("W4 role reader", lambda i: out[i][0]), ("W5 both", lambda i: out[i][1])):
        print(f"R25-da-t {nm}: practice {st(PR, col)}, untouched {st(UN, col)}  (right, wrong, fitness)", flush=True)


if __name__ == "__main__":
    main()
