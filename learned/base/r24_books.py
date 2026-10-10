"""R24 run 2: the template learner and the EM pronoun resolver on real prose (the L1 training books), no labels.
Run: python learned/base/r24_books.py [--train 150000] [--held 5000]"""
import os, sys, re, json, math, random, collections, time
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE)); os.chdir(HERE)
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(ROOT, "learned"))
import r24_tlm as T, r24_em as E
import data as D


def arg(name, default):
    return type(default)(sys.argv[sys.argv.index(name) + 1]) if name in sys.argv else default


def paragraphs(bids, n_sent):
    """paragraphs (as 'stories') until n_sent sentences are collected; quotes stripped to plain sentences"""
    out = []; n = 0
    for b in bids:
        for p in D.read(b).split("\n"):
            p = p.replace('"', "").replace("“", "").replace("”", "").replace("’", "'").strip()
            sents = [s for s in T.SENT.split(p) if s.strip()]
            if len(sents) < 2 or len(p) > 1200: continue
            out.append(dict(text=p)); n += len(sents)
            if n >= n_sent: return out
    return out


def main():
    train_b, held_b = D.books(); random.Random(2).shuffle(held_b)
    train = paragraphs(train_b, arg("--train", 150000)); held = paragraphs(held_b, arg("--held", 5000))
    print(f"train {len(train)} paragraphs, held {len(held)} paragraphs", flush=True); T0 = time.time()
    names = T.mid_caps([s["text"] for s in train])
    M = T.TLM(arg("--min-count", 2)); M.learn([s["text"] for s in train], names); print(f"learned {len(M.templates)} templates in {(time.time() - T0) / 60:.1f} min", flush=True)
    bits = n = cov = ns = 0
    for s in held:
        st = T.State()
        for sent in T.SENT.split(s["text"]):
            toks = T.TOK.findall(sent)
            if not toks: continue
            b, k, c, _ = M.score_sentence(toks, names, st); bits += b; n += k; cov += c; ns += 1
    tlm = bits / n; uni = T.ngram_bits([s["text"] for s in train], [s["text"] for s in held], 1); bi = T.ngram_bits([s["text"] for s in train], [s["text"] for s in held], 2)
    print(f"held-out {ns} sentences, {n} tokens")
    print(f"bits/token: template learner {tlm:.2f} | unigram {uni:.2f} | bigram {bi:.2f}   (R24-a2: template <= bigram + 0.5 -> {'PASS' if tlm <= bi + 0.5 else 'MISS'})")
    print(f"template coverage of held-out sentences: {cov}/{ns} = {cov / ns:.3f} (bar >= 0.30 -> {'PASS' if cov / ns >= 0.3 else 'MISS'})")
    for t, c in M.templates.most_common(8): print("   ", c, " ".join(t))
    R = E.EM().fit(E.occurrences([s["text"] for s in train], names))
    pf = {r: round(R.p_form("first", r, "pron"), 2) for r in range(E.TOPK)}
    print(f"R24-b2: learned P(pronoun | rank) at the first slot on books: {pf} -> {'PASS' if pf[0] >= 0.4 and all(pf[r] < 0.1 for r in range(1, E.TOPK)) else 'MISS'}")
    json.dump(dict(bits=tlm, unigram=uni, bigram=bi, coverage=(cov, ns), templates=len(M.templates), p_form_first=pf), open("r24_books_results.json", "w"))


if __name__ == "__main__":
    main()
