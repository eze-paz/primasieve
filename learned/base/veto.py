"""R14: vetoes on the learned model's proposal, offline on saved replies. The merged policy (reader first) is applied,
then, for answers that came from the model, three checks on the hits: support (every content word in one hit), role
(if the reader finds events with the question's verb, the proposal must fill the asked role), entity (the hit holding
the proposal contains the question's named entity). A vetoed proposal becomes "unknown".
Run: python learned/base/veto.py   (validation; then the tests once if R14-a passes)"""
import os, sys, re, json
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
os.chdir(ROOT); sys.argv = [sys.argv[0], "--v3"]
sys.path.insert(0, ROOT); sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(ROOT, "learned"))
import reader_check as rc
from guard import guarded, hits_of, norm
from store import entity_of
SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'])")


def role_veto(question, reply, hits):
    """True = veto. Only when the question asks a role and the reader finds events with that verb in the hits."""
    p = rc.parse_q(question)
    if p is None or p[0] not in ("agent", "patient") or p[1] is None: return False
    role, verb, other = p; lem = rc.R.verbs.get(verb.lower(), verb.lower())
    evs = rc.resolve_names(rc.events_in(hits))
    same_verb = [e for e in evs if e.get("verb") == lem or verb.lower().startswith(e.get("verb", "")[:4])]
    if not same_verb: return False
    if any(rc.match(reply, e[role]) for e in same_verb): return False                         # fills the asked role somewhere
    other_role = "patient" if role == "agent" else "agent"
    return any(rc.match(reply, e[other_role]) for e in same_verb)                            # it is the OTHER role of such an event: veto


def entity_veto(question, reply, hits):
    ent = entity_of(question)
    if not ent: return False
    r = norm(reply)
    holding = [h for h in hits if r and r in norm(h)]                                        # the hits that contain the proposal
    if not holding: return False
    return not any(ent.lower() in h.lower() for h in holding)                                 # none of them names the question's entity: veto


def vetoed(question, reply, prompt):
    hits = hits_of(prompt)
    if guarded(reply, prompt) == "unknown": return "support"
    if role_veto(question, reply, hits): return "role"
    if entity_veto(question, reply, hits): return "entity"
    return None


def run_items(items, label):
    """items: dicts with q, gold, prompt, reply (the model's), found(optional). Returns (right, wrong) before and after."""
    b_right = b_wrong = a_right = a_wrong = 0; reasons = {}
    for it in items:
        committed, ra = rc.check(it)
        ans = ra if ra is not None else it["reply"]; src = "reader" if ra is not None else "model"
        ok = rc.hit(ans, it["gold"]); b_right += ok; b_wrong += (not ok) and "unknown" not in ans.lower()
        if src == "model":
            v = vetoed(it["q"], ans, it["prompt"])
            if v: reasons[v] = reasons.get(v, 0) + 1; ans = "unknown"
        ok = rc.hit(ans, it["gold"]); a_right += ok; a_wrong += (not ok) and "unknown" not in ans.lower()
    print(f"{label}: merged right {b_right} wrong {b_wrong} -> with vetoes right {a_right} wrong {a_wrong}  (vetoes {reasons})", flush=True)
    return b_right, b_wrong, a_right, a_wrong


def story_items(stories_file, replies_file):
    stories = json.load(open(stories_file, encoding="utf-8"))["stories"]; rep = json.load(open(replies_file, encoding="utf-8"))["items"]; i = 0; out = []
    for s in stories:
        sents = [x.strip() for x in SENT.split(s["text"]) if x.strip()]; wins = [" ".join(sents[max(0, k - 1):k + 1]) for k in range(len(sents))]
        prompt = "Hits:\n" + "\n".join(f"[{k}] {w}" for k, w in enumerate(wins)) + "\nAnswer:"
        for q, gold in s["qs"]:
            x = rep[i]; i += 1; out.append(dict(q=q, gold=gold, prompt=prompt, reply=x["reply"]))
    return out


def trace_items(test_file, replies_file):
    test = json.load(open(test_file, encoding="utf-8")); rep = {x["q"]: x for x in json.load(open(replies_file, encoding="utf-8"))["items"]}
    return [dict(t, reply=rep[t["q"]]["reply"]) for t in test]


if __name__ == "__main__":
    B = HERE
    val = (story_items(os.path.join(B, "val_stories.json"), os.path.join(B, "b6_rwkv_val_ckpt_read1b.json"))
           + story_items(os.path.join(B, "val_fables.json"), os.path.join(B, "b6_rwkv_valfables_ckpt_read1b.json"))
           + trace_items(os.path.join(B, "r3_val_v3.json"), os.path.join(B, "r3_val_v3_ckpt_read5_s400.json")))
    br, bw, ar, aw = run_items(val, "validation (130)")
    res = dict(validation=(br, bw, ar, aw))
    if bw and (bw - aw) / bw >= 0.40 and (br - ar) / max(1, br) <= 0.10:
        print("R14-a PASS -> tests once:")
        res["test_real"] = run_items(trace_items(os.path.join(B, "r3_b6real_v3.json"), os.path.join(B, "r3_b6real_v3_ckpt_read5_s400.json")), "TEST real-text (R5 replies)")
        res["test_b6"] = run_items(story_items(os.path.join(ROOT, "tests", "battery", "stories.json"), os.path.join(B, "b6_rwkv_ckpt_read1b.json")), "TEST B6 (0.4B replies)")
    else: print("R14-a MISS -> tests not run")
    json.dump(res, open(os.path.join(B, "r14_results.json"), "w"), indent=1)
