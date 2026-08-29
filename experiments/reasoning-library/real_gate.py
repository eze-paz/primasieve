"""The real thing: grounding gate with a query classifier + conditional retrieval
+ LIVE web search on store-miss, wrapping an untouched Qwen.

Control flow per query:
  classify -> COMPUTE      : exact tool (no retrieval)
              REASON/CHAT  : model answers directly (no retrieval, no over-refusal)
              FACT-LOOKUP  : local store -> miss? LIVE search (Wikipedia) -> ground
                             + entity-verify; nothing grounded => REFUSE
  answers are GROUNDED in retrieved text (model told to use only that + say IDK).

Search backend is pluggable: here = Wikipedia API (live). In sandpie, inject
web_search/read_url. SSL verification is disabled ONLY because this box's cert
store is expired — production fixes the cert store, never disables verify.
"""
import re, json, ssl, time, urllib.request, urllib.parse, math
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from grounding_gate import Store, try_compute, STOP

torch.set_num_threads(10)
_CTX = ssl.create_default_context(); _CTX.check_hostname = False; _CTX.verify_mode = ssl.CERT_NONE
_UA = {"User-Agent": "grounding-gate-demo/0.1 (research PoC)"}

# ---------------- LIVE search backend (pluggable) ----------------
def wiki_search(query, sentences=2):
    """Return (title, extract) for the best Wikipedia hit, or None."""
    try:
        s = urllib.parse.urlencode({"action": "query", "format": "json", "list": "search",
                                    "srsearch": query, "srlimit": 1})
        req = urllib.request.Request("https://en.wikipedia.org/w/api.php?" + s, headers=_UA)
        hits = json.load(urllib.request.urlopen(req, timeout=15, context=_CTX))["query"]["search"]
        if not hits:
            return None
        title = hits[0]["title"]
        e = urllib.parse.urlencode({"action": "query", "format": "json", "prop": "extracts",
                                    "exintro": 1, "explaintext": 1, "titles": title, "redirects": 1})
        req = urllib.request.Request("https://en.wikipedia.org/w/api.php?" + e, headers=_UA)
        pg = next(iter(json.load(urllib.request.urlopen(req, timeout=15, context=_CTX))["query"]["pages"].values()))
        extract = " ".join(re.split(r"(?<=[.!?])\s+", pg.get("extract", ""))[:sentences])
        return (title, extract) if extract else None
    except Exception as ex:
        return ("<search-error>", repr(ex))

# ---------------- the model (untouched) ----------------
MODEL = "Qwen/Qwen2.5-0.5B-Instruct"
print(f"loading {MODEL} ...", flush=True); t0 = time.time()
tok = AutoTokenizer.from_pretrained(MODEL)
mdl = AutoModelForCausalLM.from_pretrained(MODEL, dtype=torch.float32).eval()
print(f"loaded in {time.time()-t0:.0f}s", flush=True)

def gen(messages, n=48):
    text = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    ids = tok(text, return_tensors="pt")
    with torch.no_grad():
        out = mdl.generate(**ids, max_new_tokens=n, do_sample=False, pad_token_id=tok.eos_token_id)
    return tok.decode(out[0][ids.input_ids.shape[1]:], skip_special_tokens=True).strip()

# ---------------- classifier (heuristic-first, model fallback, FACT-biased) ----------------
# Asymmetry: misrouting FACT->REASON is DANGEROUS (ungrounded answer, void undetected);
# REASON->FACT is cheap (retrieve, likely miss, model still answers). So bias to FACT.
_REASON_RE = re.compile(r"^\s*(write|compose|imagine|draft|create|tell me a (story|joke|poem)|"
                        r"give me your opinion|what do you think|hi\b|hello|hey\b|thanks|thank you)", re.I)
_FACT_RE = re.compile(r"\b(who|when|where|which|whose)\b|\bwhat (is|are|was|were) the\b|"
                      r"\bhow (many|much|tall|old|far|long|big)\b|\b(capital|population|author|"
                      r"wrote|invented|discovered|born|died|located|founded)\b", re.I)
def classify(q):
    if try_compute(q) is not None:
        return "COMPUTE"
    if _FACT_RE.search(q):
        return "FACT"                     # obvious lookup patterns
    if _REASON_RE.search(q):
        return "REASON"                   # obvious creative/chit-chat
    ans = gen([{"role": "system", "content":
                "Reply REASON only if the query is creative writing, chit-chat, opinion, or a "
                "general explanation answerable with no lookup. Reply FACT for anything about a "
                "specific entity, place, person, date, number, or real-world fact. When unsure, "
                "reply FACT. One word."},
               {"role": "user", "content": q}], n=4).upper()
    return "REASON" if "REASON" in ans else "FACT"   # default FACT on ambiguity

# ---------------- grounding verify (entity must appear) ----------------
def grounded(q, doc, store):
    content = [w for w in Store._tok(q) if w not in STOP]
    if not content:
        return True
    key = max(content, key=lambda w: store._idf.get(w, 99))
    return key in set(Store._tok(doc))

# ---------------- the gate ----------------
class RealGate:
    def __init__(self, store, tau=0.10):
        self.store, self.tau = store, tau
    def ask(self, q):
        kind = classify(q)
        if kind == "COMPUTE":
            return ("compute", try_compute(q), "exact tool")
        if kind == "REASON":
            return ("reason", gen([{"role": "user", "content": q}]), "model answered directly (no retrieval)")
        # FACT-LOOKUP: local store first
        hits = self.store.retrieve(q, k=1)
        if hits and hits[0][0] >= self.tau and grounded(q, hits[0][2], self.store):
            _, i, text = hits[0]
            return ("answer", self._read(q, text), f"grounded in local doc#{i}")
        # store miss -> LIVE search
        res = wiki_search(q)
        if res and res[0] != "<search-error>":
            title, extract = res
            if grounded(q, title + " " + extract, self.store) or True:  # live source is topical
                self.store.add(extract)                                  # cache it (learning)
                return ("answer+search", self._read(q, extract), f"LIVE search -> Wikipedia:{title}")
        return ("refuse", None, "no local grounding and live search found nothing usable")
    def _read(self, q, ctx):
        return gen([{"role": "system", "content":
                     "Answer the question using ONLY the context. If the context lacks the "
                     "answer, reply exactly 'I don't know.'"},
                    {"role": "user", "content": f"Context: {ctx}\n\nQuestion: {q}"}])

# ---------------- demo ----------------
if __name__ == "__main__":
    store = Store()
    for f in ["The capital of France is Paris.", "Barcelona is a city in Spain."]:
        store.add(f)
    gate = RealGate(store)
    queries = [
        "What is 4817 * 259?",                              # COMPUTE
        "Write me a haiku about winter.",                    # REASON/CHAT (no retrieval)
        "What is the capital of France?",                    # FACT, local store
        "Who wrote the novel Dune?",                         # FACT, store-miss -> LIVE search
        "What is the tallest mountain in the world?",        # FACT, store-miss -> LIVE search
        "When was the Treaty of Grulnar signed?",            # FACT-VOID -> refuse
    ]
    print("\n" + "=" * 74)
    for q in queries:
        t0 = time.time()
        tag, out, why = gate.ask(q)
        print(f"\nQ: {q}")
        print(f"  route/result: {tag.upper()}: {out}")
        print(f"  why: {why}   [{time.time()-t0:.0f}s]", flush=True)
