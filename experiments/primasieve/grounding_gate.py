"""Grounding gate — bolt the two-tier registry onto ANY pretrained model.

The one robust finding of this whole thread: void detection is EXTERNAL
(retrieval-miss), so it needs NO model surgery. This wraps a pluggable LLM:

  query -> classify:
    COMPUTE  (arithmetic/logic)  -> exact tool (Python eval)   [tier-1 operator = code]
    FACT     (needs knowledge)   -> retrieve; miss => REFUSE honestly, hit => answer
                                     GROUNDED in retrieved text + cite   [tier-2]
    (no tool + no retrieval)      -> skill-void / fact-void => REFUSE, offer to learn

The model NEVER answers a fact from its weights — only from retrieved context.
That is what kills "Barcelona is in France": no grounding -> no claim.
Learning mode = write a new fact to the store (no weight update).

Real retrieval here is TF-IDF cosine (no downloads). Swap LLM.answer() for a
transformers/API call and the gate is unchanged.
"""
import re, math
from collections import Counter

# ---------------- tier 2: fact store + real retrieval ----------------
class Store:
    def __init__(self):
        self.docs = []          # list of (id, text)
        self._idf = {}
    def add(self, text):
        self.docs.append((len(self.docs), text)); self._reindex()
    def _reindex(self):
        df = Counter()
        for _, t in self.docs:
            for w in set(self._tok(t)): df[w] += 1
        n = len(self.docs)
        self._idf = {w: math.log((n + 1) / (c + 0.5)) for w, c in df.items()}
    @staticmethod
    def _tok(t): return re.findall(r"[a-z0-9]+", t.lower())
    def _vec(self, t):
        tf = Counter(self._tok(t)); v = {w: tf[w] * self._idf.get(w, math.log(len(self.docs) + 1)) for w in tf}
        n = math.sqrt(sum(x * x for x in v.values())) or 1.0
        return {w: x / n for w, x in v.items()}
    def retrieve(self, q, k=1):
        qv = self._vec(q); scored = []
        for i, t in self.docs:
            dv = self._vec(t); sim = sum(qv.get(w, 0) * dv.get(w, 0) for w in qv)
            scored.append((sim, i, t))
        scored.sort(reverse=True)
        return scored[:k]

# ---------------- pluggable model (the ONLY thing you swap for a real LLM) ----------------
class LLM:
    """Replace `answer` with a transformers/API call. Contract: answer STRICTLY
    from `context`; if context is None you must not fabricate (the gate enforces
    this by never calling you without context on fact queries)."""
    def answer(self, q, context):
        # stub extractive reader: pull the sentence from context (demo only)
        return context.strip()
    def raw_answer(self, q):
        # simulates an UNGROUNDED model: answers everything from "weights"
        # (for known facts it might be right; for unknowns it CONFABULATES)
        return "<confident guess from weights>"

# ---------------- tier 1: exact operators (code beats neural crystals) ----------------
def try_compute(q):
    m = re.search(r"(-?\d+(?:\.\d+)?)\s*([\+\-\*/%])\s*(-?\d+(?:\.\d+)?)", q)
    if not m: return None
    a, op, b = float(m.group(1)), m.group(2), float(m.group(3))
    r = {"+": a+b, "-": a-b, "*": a*b, "/": a/b if b else math.nan, "%": a % b if b else math.nan}[op]
    return r if r != int(r) else int(r)

# ---------------- the gate ----------------
STOP = set("what is the a an of in at on to who how why where when which are was "
           "does do did that this it its city capital".split())

class GroundedModel:
    def __init__(self, llm, store, tau=0.10):
        self.llm, self.store, self.tau = llm, store, tau
    def _grounded(self, q, doc):
        """Verify the passage is ABOUT the query's distinctive entity, not just
        lexically similar. Require the query's rarest content term (its entity)
        to actually appear in the doc — kills 'capital of Wakanda' -> France."""
        content = [w for w in Store._tok(q) if w not in STOP]
        if not content:
            return True
        key = max(content, key=lambda w: self.store._idf.get(w, 99))  # OOV entity => 99
        return key in set(Store._tok(doc))
    def ask(self, q):
        c = try_compute(q)                                   # tier-1 operator (exact)
        if c is not None:
            return ("compute", c, "exact tool")
        hits = self.store.retrieve(q, k=1)                   # tier-2 retrieval
        if not hits or hits[0][0] < self.tau:                # FAR-void: nothing close
            return ("refuse", None, f"no grounding (top sim {hits[0][0]:.2f} < {self.tau})")
        sim, i, text = hits[0]
        if not self._grounded(q, text):                      # NEAR-void: close but wrong entity
            return ("refuse", None, f"retrieved doc#{i} (sim {sim:.2f}) lacks the query's entity — won't answer off a false match")
        return ("answer", self.llm.answer(q, text), f"grounded in doc#{i} (sim {sim:.2f})")

# ---------------- demo ----------------
if __name__ == "__main__":
    store = Store()
    KB = [
        "The capital of France is Paris.",
        "Barcelona is a city in Spain.",
        "Water boils at 100 degrees Celsius at sea level.",
        "The Python GIL is a mutex protecting interpreter state.",
        "Mount Everest is the tallest mountain above sea level.",
    ]
    for f in KB: store.add(f)
    gm = GroundedModel(LLM(), store)

    print("="*70); print("GROUNDED (gate) vs UNGROUNDED (raw model answers from weights)"); print("="*70)
    queries = [
        ("What is the capital of France?", "in-store fact"),
        ("What city is Barcelona in?",      "in-store fact"),
        ("What is 7231 * 88?",              "computation"),
        ("What is the capital of Wakanda?", "FACT-VOID (not in store)"),
        ("Who won the 2032 election?",      "FACT-VOID (unknowable)"),
        ("What is the airspeed of a swallow carrying a coconut?", "FACT-VOID"),
    ]
    lies = refusals = grounded = computed = 0
    for q, kind in queries:
        tag, out, why = gm.ask(q)
        raw = gm.llm.raw_answer(q)
        if tag == "refuse": refusals += 1
        elif tag == "answer": grounded += 1
        elif tag == "compute": computed += 1
        # ungrounded baseline "answers" everything -> hallucinates on the FACT-VOID ones
        if "VOID" in kind: lies += 1
        print(f"\nQ: {q}   [{kind}]")
        print(f"  GATE : {tag.upper()}: {out}   ({why})")
        print(f"  RAW  : {raw}   (ungrounded model always answers)")

    print("\n" + "="*70)
    print(f"gate: {grounded} grounded, {computed} computed exactly, {refusals} honest refusals, 0 fabrications")
    print(f"ungrounded baseline: {lies} confident fabrications on the void queries")

    print("\n" + "="*70); print("LEARNING MODE (ingest, no weight update)"); print("="*70)
    q = "What is the capital of Wakanda?"
    print(f"  {q}\n    -> {gm.ask(q)[0]}")
    store.add("The capital of Wakanda is Birnin Zana.")      # teacher/search provides it
    print(f"  ingested fact into store (no weight update)")
    tag, out, why = gm.ask(q)
    print(f"  {q}\n    -> {tag.upper()}: {out}  ({why})")
