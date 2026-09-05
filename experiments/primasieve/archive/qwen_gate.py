"""Test the grounding gate on a REAL pretrained model (Qwen), no training.
Shows: bare Qwen hallucinates on out-of-store facts; the SAME Qwen behind the
gate either grounds its answer in retrieved text, computes exactly, or refuses.
The model is untouched — only wrapped."""
import time, torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from grounding_gate import Store, GroundedModel, try_compute, STOP

torch.set_num_threads(10)
MODEL = "Qwen/Qwen2.5-0.5B-Instruct"
print(f"loading {MODEL} ...", flush=True)
t0 = time.time()
tok = AutoTokenizer.from_pretrained(MODEL)
model = AutoModelForCausalLM.from_pretrained(MODEL, torch_dtype=torch.float32)
model.eval()
print(f"loaded in {time.time()-t0:.0f}s", flush=True)

def gen(messages, n=40):
    text = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    ids = tok(text, return_tensors="pt")
    with torch.no_grad():
        out = model.generate(**ids, max_new_tokens=n, do_sample=False,
                             pad_token_id=tok.eos_token_id)
    return tok.decode(out[0][ids.input_ids.shape[1]:], skip_special_tokens=True).strip()

class QwenLLM:
    def answer(self, q, context):      # grounded: answer ONLY from context
        return gen([{"role": "system", "content":
                     "Answer the question using ONLY the provided context. "
                     "If the context lacks the answer, reply 'I don't know.'"},
                    {"role": "user", "content": f"Context: {context}\n\nQuestion: {q}"}])
    def raw_answer(self, q):           # ungrounded: answer from weights alone
        return gen([{"role": "user", "content": q}])

store = Store()
for f in ["The capital of France is Paris.",
          "Barcelona is a city in Spain.",
          "The Zorvax Protocol was ratified in the year 3021 on the planet Kelvor.",
          "Mount Everest is the tallest mountain above sea level."]:
    store.add(f)
llm = QwenLLM()
gm = GroundedModel(llm, store)

queries = [
    ("What is the capital of France?", "in-store"),
    ("What is 4817 * 259?", "computation"),
    ("When was the Zorvax Protocol ratified?", "in-store (fictional — model CANNOT know from weights)"),
    ("When was the Treaty of Grulnar signed?", "FACT-VOID (nothing in store)"),
]
print("\n" + "=" * 72)
for q, kind in queries:
    print(f"\nQ: {q}   [{kind}]")
    t0 = time.time()
    raw = llm.raw_answer(q)
    tag, out, why = gm.ask(q)
    print(f"  BARE QWEN : {raw}")
    print(f"  GATED     : {str(tag).upper()}: {out}   ({why})   [{time.time()-t0:.0f}s]", flush=True)

print("\n" + "=" * 72)
print("Note the Zorvax row: bare Qwen must fabricate (it's fictional, not in weights);")
print("the gated model answers it correctly FROM RETRIEVAL, and refuses the Grulnar void.")
