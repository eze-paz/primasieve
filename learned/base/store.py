"""The store and its grep (subtractive plan, step 5 / R3): a text split into sentences, searched by a BM25-style word
overlap. The engine never holds the text; it asks for hits and reads them. Nothing here is learned."""
import re, math, collections

STOP = set("the a an of to in on at and or but for with by from as is was were be been are it its he she they them his her their this that these those "
           "who what where when which how did do does was were had has have not no".split())
SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'])")
WORD = re.compile(r"[A-Za-z0-9]+")


def words(s): return [w.lower() for w in WORD.findall(s)]


class Store:
    def __init__(self, text):
        self.sents = [s.strip() for s in SENT.split(text.replace("\n", " ")) if s.strip()]
        self.docs = [collections.Counter(words(s)) for s in self.sents]
        self.df = collections.Counter(w for d in self.docs for w in d); self.N = len(self.sents)
        self.avg = sum(sum(d.values()) for d in self.docs) / max(1, self.N)

    def grep(self, query, k=3, window=0, entity=None):
        """top-k sentences by BM25; with window=1 each hit is the sentence with its predecessor (a human reads around a match).
        entity (R6): a name the question asks about -- hits are restricted to sentences (with their window) containing it,
        falling back to the plain hits when none do"""
        hits = self._grep(query, k if not entity else 12)
        if entity:
            keep = [(i, s) for i, s in hits if re.search(rf"\b{re.escape(entity)}\b", " ".join(self.sents[max(0, i - window):i + 1]))]
            hits = keep[:k] if keep else hits[:k]
        if not window: return hits
        return [(i, " ".join(self.sents[max(0, i - window):i + 1])) for i, _ in hits]

    def _grep(self, query, k=3):
        q = [w for w in words(query) if w not in STOP] or words(query)
        scored = []
        for i, d in enumerate(self.docs):
            s = 0.0; dl = sum(d.values())
            for w in q:
                if w in d:
                    idf = math.log(1 + (self.N - self.df[w] + 0.5) / (self.df[w] + 0.5))
                    s += idf * d[w] * 2.2 / (d[w] + 1.2 * (0.25 + 0.75 * dl / self.avg))
            if s > 0: scored.append((s, i))
        scored.sort(key=lambda x: (-x[0], x[1]))
        return [(i, self.sents[i]) for _, i in scored[:k]]


def render(question, query, hits):
    """the engine's prompt: the question, the query it sent, the hits it got back; the model writes the answer"""
    h = "\n".join(f"[{i}] {s}" for i, s in hits) if hits else "(no hits)"
    return f"Question: {question}\nSearch: {query}\nHits:\n{h}\nAnswer:"


def entity_of(question):
    """R6: the first capitalised word of the question that is not its opening word (question words are capitalised there)"""
    m = re.findall(r"\b([A-Z][a-z]+)\b", question)
    return next((w for w in m[1:] if w not in ("I",)), None) if len(m) > 1 else None


def query_for(question):
    """the fixed search policy of R3: the question's content words (a learned policy is a later step)"""
    return " ".join(w for w in WORD.findall(question) if w.lower() not in STOP)
