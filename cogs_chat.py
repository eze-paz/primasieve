"""CHAT -- talk to the primasieve engine over the English fragment it has learned.

The engine is not an open-domain chatbot; it is a COMPREHENSION + REALIZATION engine. So a turn is honest by
construction: it parses your sentence to a MEANING (a logical form) -- proving it understood -- and paraphrases
that meaning back in its own words. Where it cannot parse (an unknown word, an unlearned construction) it says
so and ABSTAINS rather than guess. "Fluent" here means: within its learned grammar and vocabulary, it
understands what you said and says it back naturally, and it is honest about the edge.

Run interactively:  python cogs_chat.py            (a REPL)
Batch a script:     python cogs_chat.py <file>     (one sentence per line)
"""
import os, sys, time, functools

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cogs_gram import induce, generate, strip_term
from cogs_gen import Realizer, generate_text
from cogs_lf import parse_lf, norm_lf

D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_nldata", "slog", "data", "cogs_LF")


@functools.lru_cache(maxsize=1)
def _model():
    def rd(f):
        return [tuple(l.rstrip("\n").split("\t")[:3])
                for l in open(os.path.join(D, f), encoding="utf-8") if l.strip()]
    train = rd("train.tsv")
    t = time.time()
    m = induce(train)
    return m, Realizer(m, train), time.time() - t


def _gloss(lf):
    """A plain-language gloss of the meaning: the event(s) and their role fillers."""
    p = parse_lf(lf)
    if p is None or p[0] == "LAMBDA":
        return "(no structured meaning)"
    ent = {}
    for noun, idx in p[0]:                        # DEFINITE nouns (`* cat ( x )`) name their filler too
        ent[idx] = "the " + noun
    for pred, args in p[1]:
        segs = [x.strip() for x in pred.split(" . ")]
        if len(segs) == 1 and len(args) == 1:
            ent.setdefault(args[0][1], "a " + segs[0])
    def name(a):
        return a[1] if a[0] == "c" else ent.get(a[1], f"x{a[1]}")
    events = {}
    for pred, args in p[1]:
        segs = [x.strip() for x in pred.split(" . ")]
        if len(segs) == 2 and len(args) == 2 and segs[1] != "nmod":
            events.setdefault(segs[0] + "@" + str(args[0][1]), []).append((segs[1], name(args[1])))
    parts = []
    for ev, roles in events.items():
        verb = ev.split("@")[0]
        parts.append(verb + "(" + ", ".join(f"{r}={f}" for r, f in roles) + ")")
    return "  ".join(parts) if parts else "(entities only)"


def respond(s, m, R):
    lex = m[0]
    toks = strip_term(lex, s)
    oov = [w for w in toks if w not in lex.cls and not (lex.open_vocab and True)]
    lf = generate(m, s)
    if lf is None:
        unknown = [w for w in toks if w not in lex.cls]
        if unknown:
            return f"  [abstain] I don't know the word(s): {', '.join(unknown)}"
        return "  [abstain] I couldn't parse that -- an unlearned construction."
    gloss = _gloss(lf)
    para = generate_text(R, lf)
    out = [f"  understood: {gloss}"]
    if para and para != " ".join(toks):
        out.append(f"  paraphrase: {para}")
    elif para:
        out.append(f"  (I'd say it the same way)")
    else:
        out.append(f"  (understood, but I can't rephrase it)")
    return "\n".join(out)


PROBES = [
    "The cat ran .",
    "A dog helped a rose .",
    "Emma rolled a teacher .",
    "A rose was helped by a dog .",
    "The boy wanted to run .",
    "Liam hoped that the dog preferred to run .",
    "The cake was given to Emma by a boy .",
    "The mouse admired a butterfly that Sophia rolled .",
    "Who did a bird love ?",
    "The girl ate the cake in the house .",
    "A cat sneezed loudly .",                     # adverb -- not in grammar
    "The happy dog ran .",                        # adjective -- not in COGS/SLOG
    "The cat and the dog ran .",                  # coordination -- not in SLOG
]


if __name__ == "__main__":
    (m, R, dt) = _model()
    lex = m[0]
    print(f"primasieve chat -- grammar induced from SLOG in {dt:.0f}s "
          f"({len(lex.cls)} words, terminators {sorted(lex.terminators)}).")
    print("Type an English sentence; I'll show what I understood and say it back. Ctrl-D to quit.\n")
    if len(sys.argv) > 1 and sys.argv[1] == "--probe":
        lines = PROBES                                   # the built-in probe conversation
    elif len(sys.argv) > 1 and os.path.exists(sys.argv[1]):
        lines = [l.strip() for l in open(sys.argv[1], encoding="utf-8") if l.strip()]
    else:
        lines = None                                     # interactive REPL
    if lines is None:
        while True:
            try:
                s = input("you> ").strip()
            except EOFError:
                break
            if s:
                print(respond(s, m, R))
    else:
        for s in lines:
            print(f"you> {s}")
            print(respond(s, m, R))
            print()
