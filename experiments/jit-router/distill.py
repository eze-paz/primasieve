"""Transplant-channel bandwidth experiment: context distillation vs text SFT.

Question: how much MORE efficiently does knowledge move from a big model to a
small one when we transplant LOGITS (the teacher's full belief) instead of
TEXT (one sample from it)?

Setup (lexmap task: fixed arbitrary 12-entry word->word table):
  teacher = Qwen2.5-1.5B-Instruct WITH the table in its prompt   (competent)
  student = Qwen2.5-0.5B-Instruct with a BARE prompt (no table)  (fails)
  Same tokenizer -> full-logit cross-scale distillation, no vocab mapping.

Arms (same LoRA config, same steps, same inputs):
  a_text : CE on teacher's greedy answers            (standard distillation)
  b_kl   : KL vs teacher's top-k logits per answer position (context distill)
  c_gold : CE on ground-truth answers                (data-quality ceiling)

The teacher sees the skill in context; the student never does. If b_kl >>
a_text at equal steps, the fat pipe is real: same wall, more bits per example.

Usage:
  py -3.12 distill.py gen                # precompute teacher answers + logits
  py -3.12 distill.py train --arm b_kl --steps 30
"""
from __future__ import annotations
import argparse, time, os, json
import numpy as np
import torch

import regimeB as R

TEACHER_ID = "Qwen/Qwen2.5-1.5B-Instruct"
STUDENT_ID = "Qwen/Qwen2.5-0.5B-Instruct"
TOPK = 64
DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "distill_data")

INSTR = R.TASKS["lexmap"][0]

def skill_text():
    tbl = R._lexmap_table()
    return "Mapping table:\n" + "\n".join("%s -> %s" % (k, v) for k, v in tbl.items())

def make_data(n_pool=24, n_test=8, seed=7):
    data = R.gen_lexmap(n_pool + n_test, seed)
    return data[:n_pool], data[n_pool:]


# ------------------------------- gen (teacher) --------------------------------
def gen():
    os.makedirs(DATA, exist_ok=True)
    from transformers import AutoTokenizer, AutoModelForCausalLM
    tok = AutoTokenizer.from_pretrained(TEACHER_ID)
    teacher = AutoModelForCausalLM.from_pretrained(TEACHER_ID, dtype=torch.float32).eval()
    pool, test = make_data()
    t_instr = INSTR + "\n" + skill_text()

    records = []
    t0 = time.perf_counter()
    for i, (x, y) in enumerate(pool):
        tp = R.build_prompt(tok, t_instr, [], x)
        ids = tok(tp, return_tensors="pt")
        with torch.no_grad():
            out = teacher.generate(**ids, max_new_tokens=12, do_sample=False,
                                   pad_token_id=tok.eos_token_id)
        ans_ids = out[0, ids["input_ids"].shape[1]:]
        # trim at eos
        eos_pos = (ans_ids == tok.eos_token_id).nonzero()
        if len(eos_pos):
            ans_ids = ans_ids[:eos_pos[0, 0] + 1]
        elif ans_ids[-1] != tok.eos_token_id:
            ans_ids = torch.cat([ans_ids, torch.tensor([tok.eos_token_id])])
        ans_text = tok.decode(ans_ids, skip_special_tokens=True)
        # teacher logits at each answer position: forward on prompt+answer
        full = torch.cat([ids["input_ids"][0], ans_ids]).unsqueeze(0)
        with torch.no_grad():
            logits = teacher(full).logits[0]
        plen = ids["input_ids"].shape[1]
        # logits predicting answer token t are at position plen-1+t
        pos_logits = logits[plen - 1: plen - 1 + len(ans_ids)]  # (A, V)
        vals, idxs = pos_logits.topk(TOPK, dim=-1)
        records.append({
            "x": x, "gold": y, "teacher_text": R._norm(ans_text),
            "ans_ids": ans_ids.tolist(),
            "topk_vals": vals.numpy().astype(np.float32),
            "topk_idxs": idxs.numpy().astype(np.int64),
        })
        print("[%d/%d] %r -> %r (gold %r) %.1fs" %
              (i + 1, len(pool), x, R._norm(ans_text), y,
               time.perf_counter() - t0), flush=True)

    np.savez(os.path.join(DATA, "teacher.npz"),
             ans_ids=np.array([r["ans_ids"] for r in records], dtype=object),
             topk_vals=np.array([r["topk_vals"] for r in records], dtype=object),
             topk_idxs=np.array([r["topk_idxs"] for r in records], dtype=object),
             allow_pickle=True)
    meta = {"pool": [(r["x"], r["gold"], r["teacher_text"]) for r in records],
            "test": test,
            "teacher_acc_on_pool": float(np.mean(
                [r["teacher_text"] == R._norm(r["gold"]) for r in records]))}
    with open(os.path.join(DATA, "meta.json"), "w") as f:
        json.dump(meta, f, indent=1)
    print("teacher acc on pool: %.2f" % meta["teacher_acc_on_pool"])


# ------------------------------- train (student) ------------------------------
def make_lora(base):
    from peft import LoraConfig, get_peft_model
    cfg = LoraConfig(r=8, lora_alpha=16, target_modules=["q_proj", "v_proj"],
                     lora_dropout=0.0, task_type="CAUSAL_LM")
    return get_peft_model(base, cfg)

def train(arm, steps, lr=1e-3, seed=0):
    torch.manual_seed(seed)
    from transformers import AutoTokenizer, AutoModelForCausalLM
    tok = AutoTokenizer.from_pretrained(STUDENT_ID)
    base = AutoModelForCausalLM.from_pretrained(STUDENT_ID, dtype=torch.float32).eval()
    with open(os.path.join(DATA, "meta.json")) as f:
        meta = json.load(f)
    npz = np.load(os.path.join(DATA, "teacher.npz"), allow_pickle=True)

    # build training items on the BARE student prompt
    items = []
    for i, (x, gold, ttext) in enumerate(meta["pool"]):
        sp = R.build_prompt(tok, INSTR, [], x)
        pids = tok(sp, return_tensors="pt")["input_ids"][0]
        if arm == "c_gold":
            tids = tok(" " + gold, return_tensors="pt")["input_ids"][0]
            tids = torch.cat([tids, torch.tensor([tok.eos_token_id])])
            items.append(("ce", pids, tids, None, None))
        else:
            tids = torch.tensor(list(npz["ans_ids"][i]))
            if arm == "a_text":
                items.append(("ce", pids, tids, None, None))
            else:  # b_kl
                items.append(("kl", pids, tids,
                              torch.tensor(npz["topk_vals"][i]),
                              torch.tensor(npz["topk_idxs"][i])))

    model = make_lora(base); model.train()
    opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=lr)
    rng = np.random.default_rng(seed)
    t0 = time.perf_counter()
    for step in range(steps):
        kind, pids, tids, tv, ti = items[int(rng.integers(len(items)))]
        ids = torch.cat([pids, tids]).unsqueeze(0)
        logits = model(input_ids=ids).logits[0]
        plen = len(pids)
        sl = logits[plen - 1: plen - 1 + len(tids)]           # (A, V)
        if kind == "ce":
            loss = torch.nn.functional.cross_entropy(sl, tids)
        else:
            logp = torch.log_softmax(sl, dim=-1)               # (A, V)
            tp = torch.softmax(tv, dim=-1)                     # (A, K) renorm topk
            loss = -(tp * logp.gather(1, ti)).sum(1).mean()
        loss.backward(); opt.step(); opt.zero_grad()
        if (step + 1) % 10 == 0:
            print("step %d loss %.3f (%.0fs)" % (step + 1, loss.item(),
                                                 time.perf_counter() - t0), flush=True)
    train_s = time.perf_counter() - t0
    model.eval()

    # eval: bare prompt, no skill, held-out test + pool
    test = [tuple(t) for t in meta["test"]]
    pool_xy = [(x, g) for x, g, _ in meta["pool"]]
    acc_test = R.score(tok, model, INSTR, [], test)
    acc_pool = R.score(tok, model, INSTR, [], pool_xy[:8])
    print("ARM=%s steps=%d train=%.0fs  acc_test=%.2f  acc_pool=%.2f"
          % (arm, steps, train_s, acc_test, acc_pool))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["gen", "train"])
    ap.add_argument("--arm", default="b_kl", choices=["a_text", "b_kl", "c_gold"])
    ap.add_argument("--steps", type=int, default=30)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    if a.cmd == "gen":
        gen()
    else:
        train(a.arm, a.steps, seed=a.seed)
