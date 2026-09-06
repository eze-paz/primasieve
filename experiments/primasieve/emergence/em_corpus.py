"""EMERGENCE E-8 -- CORPUS ACQUISITION into the ATTRIBUTED lexicon (em_corpus_prereg.md). ZERO LLM, pure stdlib.

Reads every adjective synset in the offline WordNet and attributes unknown lemmas to the engine's predicates when
the synset's lemma list vouches for exactly one of them; chains through attributed words up to depth 3; records
the full provenance chain; writes attributed_lexicon.json for the chat server. Every admission goes through
core.verdict.attribute. Nothing enters the world-learned lexicon.

    python em_corpus.py            # build + audit + write
"""
import os, sys, json, time, random, collections
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE)); sys.path.insert(0, HERE)
import en_world as W
import en_chat as C
import wn_acquire as ACQ
from core.registry import selfcheck
from core.verdict import ATTRIBUTED, attribute

OUT_JSON = os.path.join(HERE, "attributed_lexicon.json")
OUT = os.path.join(HERE, "EMERGENCE.json")
MAX_DEPTH = 3


def acquire(lex, pos="adj", max_depth=MAX_DEPTH, verbose=True, first_sense_only=True):
    """-> (attributed: word -> dict(pred, depth, anchor, span, chain), stats).

    first_sense_only (the V2 rule, adopted AFTER the V1 audit and labelled as such): an anchor vouches only
    through its FIRST-LISTED sense -- WordNet's own frequency order, not mine -- and an attributed word may anchor
    further only if the synset it was admitted from IS its own first sense. V1 (any synset containing the anchor
    lemma) admitted 1001 lemmas of which the author read ~7/40 audited as correct: 'blue' drifted to sad/profane,
    'big' to bad, 'square' to drunk. The certificate held every time (WordNet does list them together); the SENSE
    was uncontrolled. V1 numbers stay in the log as the record."""
    dat = ACQ._data(pos); idx = ACQ._index(pos)
    known = {w: p for w, p in lex.items()}                     # world-learned anchors (COMMIT)
    attributed = {}
    stats = dict(passes=[], refused=0, contested_synsets=0, contested_words=0, synsets=len(dat), rule="first-sense" if first_sense_only else "any-sense")

    def first_sense(w):
        offs = idx.get(w, []); return offs[0] if offs else None

    for depth in range(1, max_depth + 1):
        new = {}
        for off, (lemmas, _ptrs) in dat.items():
            lem = [l.lower() for l in lemmas]
            anchors = [(l, known[l] if l in known else attributed[l]["pred"]) for l in lem
                       if l in known or l in attributed]
            if first_sense_only:                               # the anchor must vouch through its own first sense
                anchors = [(l, p) for l, p in anchors if first_sense(l) == off]
            if not anchors: continue
            preds = {p for _, p in anchors}
            if len(preds) != 1:
                stats["contested_synsets"] += 1; continue
            pred = next(iter(preds)); anchor = anchors[0][0]
            span = " ".join(lem)
            for w in lem:
                if w in known or w in attributed or w in new:
                    if w in new and new[w] is not None and new[w]["pred"] != pred:
                        new[w] = None                          # reached by two chains with different predicates
                    continue
                claim, state, prov = attribute((w, pred), f"WORDNET-{pos}", span, span,
                                               lambda s, a=anchor, p=pred, w=w: (w, p) if a in s.split() else None)
                if state != ATTRIBUTED: stats["refused"] += 1; continue
                chain = ([anchor] if anchor in known else attributed[anchor]["chain"] + [anchor])
                new[w] = dict(pred=pred, depth=depth, anchor=anchor, span=span, chain=chain, source=f"WORDNET-{pos}")
        dropped = [w for w, v in new.items() if v is None]
        stats["contested_words"] += len(dropped)
        for w in dropped: del new[w]
        stats["passes"].append(dict(depth=depth, admitted=len(new)))
        if verbose: print(f"  pass {depth}: admitted {len(new)} (contested so far: synsets {stats['contested_synsets']}, words {stats['contested_words']})", flush=True)
        if not new: break
        attributed.update(new)
    return attributed, stats


if __name__ == "__main__":
    selfcheck(__file__)
    t0 = time.time()
    print("EMERGENCE E-8 -- reading WordNet's adjectives into the ATTRIBUTED lexicon\n", flush=True)
    _, lex, _ = C.build(n=9000, seed=7)
    print(f"anchors: {len(lex)} world-learned words (COMMIT)", flush=True)
    print("V1 (any sense containing the anchor lemma) -- the RECORD; author's audit of 40: ~7 correct, sense drift):", flush=True)
    att1, st1 = acquire(lex, first_sense_only=False)
    print(f"  V1 total {len(att1)}\nV2 (first-listed sense only, chaining only through first-sense-consistent words):", flush=True)
    att, st = acquire(lex, first_sense_only=True)
    single = {w: v for w, v in att.items() if "_" not in w and w.isalpha()}
    by_pred = collections.Counter(v["pred"] for v in att.values())
    print(f"\nattributed {len(att)} lemmas ({len(single)} single-token) over {st['synsets']} synsets; refused {st['refused']}; "
          f"contested synsets {st['contested_synsets']}, contested words {st['contested_words']}", flush=True)
    print(f"by predicate: {dict(by_pred.most_common())}", flush=True)
    print(f"by depth: {dict(collections.Counter(v['depth'] for v in att.values()))}", flush=True)

    rng = random.Random(5); sample = rng.sample(sorted(single), min(40, len(single)))
    print("\nAUDIT (40 random admissions, chain shown; a human should read these):", flush=True)
    for w in sample:
        v = single[w]
        print(f"  {w:18s} -> {v['pred']:9s} via {' -> '.join(v['chain'])}   [synset: {v['span'][:70]}]", flush=True)

    ok = st["refused"] == 0 and not any(w in lex for w in att)
    print(f"\nWORDNET CORPUS ACQUISITION: {'SOUND' if ok else 'NOT SOUND'} -- refused {st['refused']}, laundered into the world lexicon 0"
          if ok else f"\nWORDNET CORPUS ACQUISITION: NOT SOUND", flush=True)
    json.dump({"source": "WordNet 3.1 adjectives (offline, _nldata/dict)", "reading_rule": "synset lemma list vouches for exactly one predicate; chained <= 3",
               "words": single, "n_all": len(att), "stats": st}, open(OUT_JSON, "w"), indent=0)
    d = json.load(open(OUT)) if os.path.exists(OUT) else {}
    d["E8_corpus_acquisition"] = dict(prereg="em_corpus_prereg.md", attributed=len(att), single_token=len(single), stats=st,
                                      v1_record=dict(attributed=len(att1), stats=st1, author_audit="~7/40 correct; sense drift (blue->sad, big->bad, square->drunk)"),
                                      by_pred=dict(by_pred), sound=ok, secs=round(time.time() - t0, 1))
    json.dump(d, open(OUT, "w"), indent=1, sort_keys=True)
    print(f"({time.time()-t0:.0f}s) -> {os.path.basename(OUT_JSON)} ({len(single)} words for the chat), EMERGENCE.json[E8_corpus_acquisition]", flush=True)
