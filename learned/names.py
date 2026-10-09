"""L3_prereg.md: name permutation. Proper names are detected per training book from the text's own statistics, each
book's names are replaced consistently by names drawn from other books (within an honorific class), and K permuted copies
of the training corpus are tokenised. Facts about individuals ("Elizabeth ... Bennet") then differ across copies and
cannot be learned; the mechanics of names (a capitalised word that recurs and takes "Mr", "said", "'s") stay learnable.
Also extracts the closed-book probe set: training-book sentences cut right before a surname that follows a first name.
Run: python learned/names.py  -> learned/cache/{names.json, train_perm{0..K-1}.bin, name_probes.json}"""
import os, re, sys, json, random, array, collections, time
from data import books, read, BPE, CACHE

K = 4                                                   # permuted copies of the corpus
HONOR_F = {"Mrs", "Miss", "Madame", "Mme", "Lady", "Mademoiselle", "Mlle", "Dame", "Senora", "Signora"}
HONOR_M = {"Mr", "Monsieur", "M", "Sir", "Lord", "Dr", "Captain", "Colonel", "Major", "General", "Herr", "Signor", "Senor", "Count", "Baron", "Duke"}
STOP = HONOR_F | HONOR_M | {"I", "O", "Oh", "God", "Lord", "Christ", "Jesus", "Heaven", "Ah", "Yes", "No", "Chapter", "CHAPTER", "Book", "Part",
        "January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December",
        "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday", "Sir", "Madam", "Monsieur", "Mister",
        "English", "French", "German", "American", "Indian", "Italian", "Spanish", "Russian", "Greek", "Roman", "Latin", "British",
        "Irish", "Scotch", "Scottish", "Welsh", "Dutch", "Chinese", "Japanese", "Turkish", "Jewish", "Christian", "Christians", "Jews"}
WORD = re.compile(r"[A-Za-z]+")


def detect(text, lower_corpus):
    """names in one book: capitalised words seen >= 3 times not at a sentence start, whose lowercase form is rare in the
    whole corpus relative to the capitalised one. Returns {name: class} with class in {f, m, o}."""
    cap = collections.Counter(); after = collections.defaultdict(collections.Counter); prev = None
    for m in WORD.finditer(text):
        w = m.group(); start = m.start()
        # sentence-initial: preceded (ignoring quotes/spaces) by . ! ? or the paragraph start
        j = start - 1
        while j >= 0 and text[j] in " \"'“‘(": j -= 1
        initial = j < 0 or text[j] in ".!?\n"
        if w[0].isupper() and not w.isupper() and len(w) >= 2 and w not in STOP and not initial:
            cap[w] += 1
            if prev in HONOR_F: after[w]["f"] += 1
            elif prev in HONOR_M: after[w]["m"] += 1
        prev = w
    names = {}
    for w, c in cap.items():
        if c < 3: continue
        if lower_corpus.get(w.lower(), 0) > 0.02 * (lower_corpus.get(w, 0) + c): continue
        cls = "f" if after[w]["f"] > after[w]["m"] else "m" if after[w]["m"] > 0 else "o"
        names[w] = cls
    return names


def permute(text, mapping):
    return WORD.sub(lambda m: mapping.get(m.group(), m.group()), text)


def main():
    T0 = time.time(); train, _ = books(); tok = BPE.load()
    texts = {b: read(b) for b in train}
    corpus = collections.Counter()
    for t in texts.values(): corpus.update(WORD.findall(t))
    lower_corpus = collections.Counter()
    for w, c in corpus.items(): lower_corpus[w] += c                       # exact-case counts; .lower() lookups use the lowercase key
    names = {b: detect(t, lower_corpus) for b, t in texts.items()}
    pool = {c: sorted({n for d in names.values() for n, cc in d.items() if cc == c}) for c in "fmo"}
    print(f"{len(train)} books: {sum(map(len, names.values()))} name tokens, pool f {len(pool['f'])} m {len(pool['m'])} o {len(pool['o'])} ({time.time() - T0:.0f} s)", flush=True)
    json.dump(dict(names=names, pool=pool), open(os.path.join(CACHE, "names.json"), "w", encoding="utf-8"))
    # ---- K permuted corpora: per copy and book, a fresh consistent mapping, names drawn from the class pool minus the book's own
    for k in range(K if "--probes-only" not in sys.argv else 0):
        R = random.Random(1000 + k); arr = array.array("H")
        for b in train:
            own = names[b]; mapping = {}
            for c in "fmo":
                src = [n for n, cc in own.items() if cc == c]
                if not src: continue
                cand = [n for n in pool[c] if n not in own] or pool[c]
                tgt = R.sample(cand, len(src)) if len(cand) >= len(src) else [R.choice(cand) for _ in src]
                mapping.update(zip(src, tgt))
            arr.extend(tok.encode(permute(texts[b], mapping)))
        arr.tofile(open(os.path.join(CACHE, f"train_perm{k}.bin"), "wb"))
        print(f"train_perm{k}: {len(arr) / 1e6:.1f} M tokens ({time.time() - T0:.0f} s)", flush=True)
    # ---- closed-book probes: "First Last" pairs (both detected names) seen >= 5 times in a training book; cut before Last
    R = random.Random(7); probes = []
    for b in train:
        own = names[b]; t = texts[b]
        pairs = collections.Counter(m.group(1, 2) for m in re.finditer(r"\b([A-Z][a-z]+) ([A-Z][a-z]+)\b", t)
                                    if m.group(1) in own and m.group(2) in own and m.group(1) not in STOP)
        top = [(p, c) for p, c in pairs.most_common(3) if c >= 5]
        for (first, last), c in top:
            occ = [m.start(1) for m in re.finditer(rf"\b{first} ({last})\b", t)]
            cut = R.choice(occ[1:]) if len(occ) > 1 else occ[0]
            ctx = t[max(0, cut - 600):cut]
            ctx = ctx[ctx.find(" ") + 1:] if cut > 600 else ctx                    # start at a word boundary
            distract = R.sample([n for n in pool[own[last]] if n != last and n not in own], 10)
            probes.append(dict(book=b, first=first, last=last, count=c, context=ctx, distractors=distract))
    R.shuffle(probes); probes = probes[:200]
    json.dump(probes, open(os.path.join(CACHE, "name_probes.json"), "w", encoding="utf-8"), indent=1)
    print(f"{len(probes)} surname probes from {len({p['book'] for p in probes})} books ({time.time() - T0:.0f} s)")


if __name__ == "__main__":
    main()
