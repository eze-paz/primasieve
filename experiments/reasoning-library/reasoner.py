"""Generic reasoning loop: make a SMALL model punch above its weight by
externalizing everything it lacks and reducing what's left to local choices.

Principle (the through-line of the whole session):
  - knowledge  -> external retrieval / live search  (model needn't contain facts)
  - compute    -> exact tool                         (model needn't calculate)
  - know-what-you-dont-know -> the ANSWER is GROUNDING-GATED: the model may only
                   state facts that appear in what it gathered; ungrounded answers
                   are REJECTED and it must go research  (structural, not introspective)
  - planning   -> never plan the whole task; each step the model makes ONE local
                   choice: SEARCH / CALC / ANSWER. Decomposition EMERGES from the loop.

The model's only job: pick the next action given the state. Everything hard is
scaffolded or externalized. Runs on real Qwen2.5-0.5B.
"""
import re, json, ssl, time, urllib.request, urllib.parse
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

torch.set_num_threads(10)
_CTX = ssl.create_default_context(); _CTX.check_hostname = False; _CTX.verify_mode = ssl.CERT_NONE
_UA = {"User-Agent": "reasoner-demo/0.1 (research PoC)"}

def wiki(query):
    try:
        s = urllib.parse.urlencode({"action": "query", "format": "json", "list": "search",
                                    "srsearch": query, "srlimit": 1})
        req = urllib.request.Request("https://en.wikipedia.org/w/api.php?" + s, headers=_UA)
        hits = json.load(urllib.request.urlopen(req, timeout=15, context=_CTX))["query"]["search"]
        if not hits: return None
        title = hits[0]["title"]
        e = urllib.parse.urlencode({"action": "query", "format": "json", "prop": "extracts",
                                    "exintro": 1, "explaintext": 1, "titles": title, "redirects": 1})
        req = urllib.request.Request("https://en.wikipedia.org/w/api.php?" + e, headers=_UA)
        pg = next(iter(json.load(urllib.request.urlopen(req, timeout=15, context=_CTX))["query"]["pages"].values()))
        txt = " ".join(re.split(r"(?<=[.!?])\s+", pg.get("extract", ""))[:3])
        return f"{title}: {txt}" if txt else None
    except Exception as ex:
        return f"<search-error {ex}>"

def calc(expr):
    expr = expr.replace(",", "").strip()
    if not re.fullmatch(r"[-+*/(). \d]+", expr): return None
    try:
        v = eval(expr, {"__builtins__": {}}, {})
        return v if v != int(v) else int(v)
    except Exception:
        return None

MODEL = "Qwen/Qwen2.5-0.5B-Instruct"
print(f"loading {MODEL} ...", flush=True); t0 = time.time()
tok = AutoTokenizer.from_pretrained(MODEL)
mdl = AutoModelForCausalLM.from_pretrained(MODEL, dtype=torch.float32).eval()
print(f"loaded in {time.time()-t0:.0f}s", flush=True)

def gen(prompt, n=60):
    ids = tok(prompt, return_tensors="pt")
    with torch.no_grad():
        out = mdl.generate(**ids, max_new_tokens=n, do_sample=False, pad_token_id=tok.eos_token_id)
    return tok.decode(out[0][ids.input_ids.shape[1]:], skip_special_tokens=True).strip()

SYS = (
    "You solve a task step by step using tools. Each step output EXACTLY two lines:\n"
    "THINK: <one short sentence>\n"
    "ACTION: SEARCH <query>   OR   CALC <arithmetic>   OR   ANSWER <final answer>\n"
    "Rules: never state a number or fact you did not get from a SEARCH observation. "
    "Use CALC for any arithmetic. Only ANSWER when every needed fact is in the observations.\n\n"
    "Example:\n"
    "Task: What is the population of the capital of Japan, times 2?\n"
    "THINK: I need the capital of Japan.\n"
    "ACTION: SEARCH capital of Japan\n"
    "OBSERVATION: Tokyo is the capital of Japan.\n"
    "THINK: Now I need Tokyo's population.\n"
    "ACTION: SEARCH population of Tokyo\n"
    "OBSERVATION: Tokyo has a population of 14000000.\n"
    "THINK: Multiply by 2 with a tool.\n"
    "ACTION: CALC 14000000 * 2\n"
    "OBSERVATION: 28000000\n"
    "THINK: I have the result.\n"
    "ACTION: ANSWER 28000000\n"
)

def grounded_answer(ans, observations):
    """know-what-you-dont-know: every number in the answer must appear in what we
    gathered (or be a CALC result). Blocks ungrounded/hallucinated answers."""
    nums = re.findall(r"\d[\d,]*", ans)
    obs_blob = " ".join(observations).replace(",", "")
    for nraw in nums:
        if nraw.replace(",", "") not in obs_blob:
            return False
    return True

def solve(task, max_steps=6):
    print(f"\n{'='*72}\nTASK: {task}\n{'='*72}", flush=True)
    trace, observations = [], []
    for step in range(max_steps):
        prompt = SYS + f"\nTask: {task}\n" + "\n".join(trace) + ("\n" if trace else "")
        out = gen(prompt, n=60)
        # take the first THINK/ACTION pair the model emits
        think = (re.search(r"THINK:\s*(.+)", out) or [None, ""])[1].split("\n")[0].strip()
        m = re.search(r"ACTION:\s*(SEARCH|CALC|ANSWER)\s*(.+)", out, re.I)
        if not m:
            print(f"  step {step}: [unparseable] {out[:80]!r}"); break
        act, arg = m.group(1).upper(), m.group(2).split("\n")[0].strip()
        trace.append(f"THINK: {think}"); trace.append(f"ACTION: {act} {arg}")
        print(f"  step {step}: THINK: {think}\n            ACTION: {act} {arg}", flush=True)
        if act == "SEARCH":
            obs = wiki(arg) or "(nothing found)"
            observations.append(obs); trace.append(f"OBSERVATION: {obs[:200]}")
            print(f"            OBS: {obs[:120]}", flush=True)
        elif act == "CALC":
            r = calc(arg)
            obs = str(r) if r is not None else "(invalid expression)"
            observations.append(obs); trace.append(f"OBSERVATION: {obs}")
            print(f"            OBS: {obs}", flush=True)
        elif act == "ANSWER":
            if grounded_answer(arg, observations):
                print(f"  --> ANSWER (grounded): {arg}", flush=True); return arg
            print(f"  --> REJECTED ungrounded answer '{arg}' (not in observations) — keep researching", flush=True)
            trace.append("OBSERVATION: (that answer was not grounded in observations; gather the fact first)")
    print("  --> gave up (budget/void)", flush=True); return None

if __name__ == "__main__":
    # multi-hop tasks: require decompose + research + exact compute. A bare small
    # model would hallucinate the numbers and/or botch the arithmetic.
    for task in [
        "What is the population of the capital of France, divided by 1000?",
        "Who wrote the novel Dune, and in what year was it published?",
    ]:
        solve(task)
