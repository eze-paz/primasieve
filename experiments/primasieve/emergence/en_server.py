"""LOCALHOST UI for the English chat -- renders the scene and lets you talk to the engine in a browser.

    python en_server.py            # http://127.0.0.1:8765

Stdlib only. Single-user demo server: the scene and the pending clarification live in module state.
The engine behind it is exactly en_chat.py -- meanings learned by elimination, four responses forced by the
commit rule (COMMIT / ASK / UNKNOWABLE / ABSTAIN). Nothing about the answer logic is special-cased for the UI.
"""
import os, sys, json, random, re, http.server, socketserver
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE)); sys.path.insert(0, HERE)
import en_world as W
import en_chat as C
import wn_acquire as ACQ
import kb_sources as KB
import en_actions as ACT
from core.verdict import Beliefs, ATTRIBUTED, COMMIT, RETRACTED
import en_ops as OPS
import random as _r

PORT = int(os.environ.get("PORT", "8765"))
STATE = {"scene": None, "lex": None, "alex": None, "pending": None, "acquire": None,
         "last_ref": None, "log": [], "teach": None, "provenance": {},
         # E-7 wiring: every attributed word is a BELIEF with a certificate; every reply that relied on one is a
         # DEPENDENT; "wrong" retracts the word and cascades; sources keep confirm/strike counts (never weights).
         "beliefs": Beliefs(), "answers": 0, "answer_text": {}, "last_used": [], "research_log": [], "contested": {}}


def _hold(word, pred, prov):
    """hold `word` -> pred as an ATTRIBUTED belief with certificate pairs (source, span)."""
    STATE["beliefs"].hold(("word", word), pred, ATTRIBUTED, prov)


def load_attributed():
    """(re)load attributed_lexicon.json -- the pre-emptive research output (em_preempt.py) -- into the lexicon as
    ATTRIBUTED beliefs. Words already held, retracted by the user, or world-learned are left alone. Also loads the
    CONTESTED list so an unknown word that research already found contested is asked about, not re-probed."""
    lex, alex = STATE["lex"], STATE["alex"]; B = STATE["beliefs"]
    p = os.path.join(HERE, "attributed_lexicon.json")
    if not os.path.exists(p): return "no attributed lexicon on disk"
    d = json.load(open(p, encoding="utf-8")); n = 0
    for w, v in d.get("words", {}).items():
        if w in lex or w in alex or w in W.NOUNS or w in W.DETS or w in W.FILLER or w in W.QUANT or w in W.GOAL: continue
        if ("word", w) in B.b and B.b[("word", w)]["state"] == RETRACTED: continue   # the user retracted it: stays out
        lex[w] = v["pred"]; n += 1
        chain = " > ".join(v.get("chain", [])) or "direct"
        STATE["provenance"][w] = f"{v.get('how', 'research')}: {v.get('source', 'WORDNET')} via {chain}, unverified"
        _hold(w, v["pred"], [(c[0], c[1]) for c in v.get("cites", [(v.get("source", "WORDNET-adj"), v.get("span", ""))])])
    STATE["contested"] = {w: c for w, c in d.get("contested", {}).items() if w not in lex}
    STATE["single"] = {w: v for w, v in d.get("single", {}).items() if w not in lex}   # one source only: on demand
    total = sum(1 for w in lex if w in STATE["provenance"])
    return (f"loaded {n} new attributed words ({total} total; {len(STATE['contested'])} known-contested; "
            f"{len(STATE['single'])} single-source available on demand) from attributed_lexicon.json")


def _retract_word(word, why):
    """retract an attributed word: drop it from the lexicon, cascade to every answer that relied on it."""
    B = STATE["beliefs"]
    if ("word", word) not in B.b:
        return None
    out = B.retract(("word", word))
    STATE["lex"].pop(word, None); STATE["alex"].pop(word, None); STATE["provenance"].pop(word, None)
    deps = [STATE["answer_text"].get(k, "?") for k in out if k[0] == "answer"]
    return deps


def _jsonable(o):
    if isinstance(o, (set, frozenset)): return sorted(o)
    if isinstance(o, dict): return {("/".join(sorted(k)) if isinstance(k, frozenset) else str(k)): _jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)): return [_jsonable(x) for x in o]
    return o


_LEX_MTIME = [0.0]


def _maybe_reload():
    """the pre-emptive researcher (em_preempt.py --online) writes attributed_lexicon.json incrementally; pick up
    new words whenever the panel refreshes, without a restart."""
    p = os.path.join(HERE, "attributed_lexicon.json")
    try: m = os.path.getmtime(p)
    except OSError: return
    if m > _LEX_MTIME[0]:
        _LEX_MTIME[0] = m; load_attributed()


def _state_json():
    _maybe_reload()
    B = STATE["beliefs"]
    words = []
    for (kind, w), e in B.b.items():
        if kind != "word": continue
        words.append({"word": w, "pred": e["value"], "state": e["state"], "sources": sorted({s for s, _ in e["prov"]}),
                      "provenance": STATE["provenance"].get(w, ""), "dependents": len(e["deps"])})
    words.sort(key=lambda x: (x["state"] != RETRACTED, x["word"]))
    srcs = sorted(set(B.strikes) | set(B.confirms))
    return {"world_words": sorted(w for w in STATE["lex"] if w not in STATE["provenance"]),
            "actions": sorted(STATE["alex"]),
            "attributed": words,
            "sources": {s: {"confirms": B.confirms.get(s, 0), "strikes": B.strikes.get(s, 0)} for s in srcs},
            "answers": STATE["answers"], "research_log": STATE["research_log"][-25:]}

# ---- TEACHING: the user states a meaning ("large means big", "teal is green", "it means big"). ----
# Measured failure (chat, 2026-09-06): "large means big" was answered with the SAME WordNet proposal it was
# correcting, and "no" threw the word away with no way to supply the right meaning. Learning by elimination
# stays the mechanism for the world's words; a meaning the USER states is a different rung -- it is taken on
# the user's word, recorded with provenance "user", never re-labelled as verified, and never allowed to
# overwrite a word the engine learned from the world itself.
TEACH = re.compile(r"^(?:no,?\s+)?(?:(\w+)|it|that|this)\s+(?:means|=|is like|is the same as|is)\s+"
                   r"(?:a |an |the )?(\w+)\s*\.?$")


def _teach(word, target, original):
    lex, alex = STATE["lex"], STATE["alex"]
    STATE["acquire"] = None; STATE["teach"] = None
    how = STATE["provenance"].get(word, "elimination against the world")
    if (word in lex or word in alex) and word not in STATE["provenance"]:
        return {"kind": "ABSTAIN", "msg": f"I already know '{word}' ({how}); I will not overwrite a meaning I "
                                          f"learned from the world with one I am told.", "highlight": []}
    # a word that was itself TAUGHT (or WordNet-confirmed) can be corrected by the same authority that gave it
    if word in lex and word in STATE["provenance"]: del lex[word]
    if word in alex and word in STATE["provenance"]: del alex[word]
    if target in lex:
        lex[word] = lex[target]; STATE["provenance"][word] = "user-taught (unverified)"
        learned = f"'{word}' = {lex[target]}"
        _hold(word, lex[target], [("USER", f"{word} means {target}")])
    elif target in alex:
        alex[word] = alex[target]; STATE["provenance"][word] = "user-taught (unverified)"
        learned = f"'{word}' = action {target}"
        _hold(word, alex[target], [("USER", f"{word} means {target}")])
    else:
        props = ", ".join(sorted(lex)[:10]); acts = ", ".join(sorted(alex))
        return {"kind": "ASK", "msg": f"I do not know '{target}' either. Define '{word}' in terms of a word I "
                                      f"have: {props} ... or an action: {acts}.", "highlight": []}
    msg = f"learned on your word (unverified): {learned}."
    if original:
        r = say(original); r["msg"] = msg + " " + r["msg"]; return r
    return {"kind": "TAUGHT", "msg": msg, "highlight": []}


def new_scene(n=5):
    STATE["scene"] = W.rand_scene(random.Random(random.randrange(10 ** 6)), n)
    STATE["pending"] = None
    STATE["log"] = []


def scene_json():
    sc = STATE["scene"]
    return [{"i": i, "x": o[0][0], "y": o[0][1], "w": o[0][2] - o[0][0], "h": o[0][3] - o[0][1],
             "colour": W.COLOURS[o[1]], "css": W.CSS[W.COLOURS[o[1]]], "props": W.true_unary(o)}
            for i, o in enumerate(sc)]


def say(text):
    """every reply passes through here: if it relied on a word held on someone's WORD rather than learned from
    the world, the reply says so. This is core.verdict's ATTRIBUTED taint made visible (E-7): an answer that
    depends on an attributed premise is attributed, and is never presented as if the world had verified it."""
    r = _say(text)
    used = [w for w in W.tokenize(text) if w in STATE["provenance"]]
    if "attributed" in r:                                    # already tagged by an inner say() (research/teach re-run)
        return r
    if used and r.get("kind") in ("COMMIT", "ASK", "NONE", "UNKNOWABLE"):
        tags = "; ".join(f"'{w}' = {STATE['lex'].get(w, STATE['alex'].get(w))} ({STATE['provenance'][w]})" for w in used)
        r["kind"] = "ATTRIBUTED" if r["kind"] == "COMMIT" else r["kind"]
        r["msg"] += f"  [relies on: {tags}]"
        r["attributed"] = used
        # the reply is a DEPENDENT of the attributed words it used: retracting a word retracts it
        B = STATE["beliefs"]; STATE["answers"] += 1; key = ("answer", STATE["answers"])
        prem = [("word", w) for w in used if ("word", w) in B.b]
        if prem:
            B.derive(key, r["msg"][:90], prem); STATE["answer_text"][key] = f"you> {text}  ->  {r['msg'][:70]}"
        STATE["last_used"] = used
    elif r.get("kind") in ("COMMIT", "ASK", "NONE", "UNKNOWABLE"):
        STATE["last_used"] = []
    return r


def _say(text):
    sc, lex = STATE["scene"], STATE["lex"]
    pend = STATE["pending"]
    acq = STATE["acquire"]
    low = text.strip().lower()
    # ---- FEEDBACK on an attributed answer: "wrong" retracts (and cascades), "correct" counts for the source,
    #      "forget X" / "retract X" retracts a named word. World-learned words cannot be retracted on anyone's word.
    mf = re.match(r"^(?:forget|retract|unlearn)\s+(\w+)\s*\.?$", low)
    if mf:
        w = mf.group(1)
        if w in lex and w not in STATE["provenance"]:
            return {"kind": "ABSTAIN", "msg": f"'{w}' was learned from the world by elimination; I do not retract that on "
                                              f"anyone's word. Show me a scene that contradicts it.", "highlight": []}
        deps = _retract_word(w, "user")
        if deps is None:
            return {"kind": "NONE", "msg": f"I do not hold '{w}'.", "highlight": []}
        return {"kind": "RETRACTED", "msg": f"retracted '{w}' and {len(deps)} answer(s) that relied on it"
                                             + (": " + " | ".join(deps[:4]) if deps else "") + ". Its source was struck.", "highlight": []}
    if low in ("wrong", "that's wrong", "thats wrong", "no that's wrong", "that is wrong", "incorrect"):
        used = [w for w in STATE["last_used"] if ("word", w) in STATE["beliefs"].b]
        if not used:
            return {"kind": "ABSTAIN", "msg": "the last answer relied only on words learned from the world. I cannot retract "
                                              "those on your word -- show me a scene where they fail.", "highlight": []}
        if len(used) > 1:
            return {"kind": "ASK", "msg": f"it relied on {used}. Which one is wrong? Say 'forget <word>'.", "highlight": []}
        deps = _retract_word(used[0], "user"); STATE["last_used"] = []
        return {"kind": "RETRACTED", "msg": f"retracted '{used[0]}' and {len(deps)} answer(s) built on it. Its source was struck. "
                                             f"Tell me what it means ('{used[0]} means ...') or leave it unknown.", "highlight": []}
    if low in ("correct", "right", "that's right", "thats right", "yes that's right"):
        used = [w for w in STATE["last_used"] if ("word", w) in STATE["beliefs"].b]
        if used:
            B = STATE["beliefs"]
            for w in used:
                for s, _ in B.b[("word", w)]["prov"]: B.confirms[s] = B.confirms.get(s, 0) + 1
            return {"kind": "TAUGHT", "msg": f"noted: you confirm {used}. Their sources get a confirmation count; the words stay "
                                             f"attributed (your word, not the world's).", "highlight": []}
    # ---- TEACHING by statement, or answering "which of my words does it mean?" ----
    m = TEACH.match(low)
    if m:
        word = m.group(1)
        pend_word, pend_orig = acq[0] if acq else None, acq[2] if acq else None
        if STATE["teach"]: pend_word, pend_orig = STATE["teach"]
        word = word or pend_word
        # "which is green" / "the red one is tall" must NOT teach: only a word the parser does not know.
        if word and word not in lex and word not in STATE["alex"] and W.parse(word, lex)["unknown"] == [word]:
            return _teach(word, m.group(2), pend_orig)
        if word and (word in lex or word in STATE["alex"]) and m.group(1):
            return _teach(word, m.group(2), None)
    if STATE["teach"]:
        word, original = STATE["teach"]
        if low in ("none", "skip", "no", "n"):
            STATE["teach"] = None
            return {"kind": "ABSTAIN", "msg": f"understood - '{word}' stays unknown.", "highlight": []}
        toks = [t for t in W.tokenize(low) if t not in ("a", "an", "the", "it", "means")]
        if len(toks) == 1:
            return _teach(word, toks[0], original)
        STATE["teach"] = None                                  # anything else: a new sentence, fall through
    # ---- confirming (or rejecting) a WordNet PROPOSAL. Rejected -> ask for the meaning instead of dropping. --
    if acq and low in ("yes", "no", "y", "n"):
        word, pred, original = acq
        STATE["acquire"] = None
        if not low.startswith("y"):
            STATE["teach"] = (word, original)
            props = ", ".join(sorted(lex)[:10])
            return {"kind": "ASK", "msg": f"then which of my words does '{word}' mean? ({props} ...) "
                                          f"Or say 'none' and I will keep refusing it.", "highlight": []}
        STATE["provenance"][word] = "WordNet proposal, confirmed by you"
        _hold(word, pred if not isinstance(pred, tuple) else pred[0], [("WORDNET", f"{word} ~ {pred}"), ("USER", "confirmed")])
        if isinstance(pred, tuple) and pred[0] == "GOAL":
            W.GOAL.add(word)                   # learned on the fly: this verb marks a target state
        elif isinstance(pred, tuple) and pred[0] == "ACTION":
            STATE["alex"][word] = pred[1]
        else:
            lex[word] = pred
        r = say(original)                      # re-run the sentence now that the word is known
        r["msg"] = f"learned: '{word}' = {pred}. " + r["msg"]
        return r
    if pend and text.strip().lower() in ("yes", "no", "y", "n"):
        p, cands = pend
        want = text.strip().lower().startswith("y")
        cands = [i for i in cands if W.unary_holds(p, sc[i]) == want]
        if len(cands) == 1:
            STATE["pending"] = None
            return {"kind": "COMMIT", "msg": f"object #{cands[0]}", "highlight": cands}
        if not cands:
            STATE["pending"] = None
            return {"kind": "NONE", "msg": "then nothing matches.", "highlight": []}
        q = C.best_question(sc, cands)
        if q is None:
            STATE["pending"] = None
            return {"kind": "UNKNOWABLE", "msg": f"still {cands}; nothing separates them.", "highlight": cands}
        STATE["pending"] = (q, cands)
        return {"kind": "ASK", "msg": f"narrowed to {cands}. Next: is it {q}?", "highlight": cands}
    toks = W.tokenize(text)
    alex = STATE["alex"]
    # ---- COMMAND: an action word turns this into a request to CHANGE the world ----
    act = next((t for t in toks if t in alex), None)
    if act:
        rest = " ".join(t for t in toks if t != act)
        if "it" in W.tokenize(rest) and STATE["last_ref"] is not None:
            tgt = [STATE["last_ref"]]
        else:
            qq = W.parse(rest, lex)
            if qq["unknown"]:
                return _diagnose(qq["unknown"], text)
            # "enlarge all" has NO adjectives -- an empty description with a quantifier means EVERY object.
            # The first version returned [] here and answered "I cannot tell which object you mean".
            if qq["left"]:
                tgt = C.referents(sc, qq["left"])
            elif qq["quant"] or qq["plural"]:
                tgt = list(range(len(sc)))
            else:
                tgt = []
        qq2 = W.parse(rest, lex)
        setwise = qq2["quant"] or qq2["plural"]
        if not tgt:
            # EMPTY and AMBIGUOUS are different failures and were reported with the same sentence. If a
            # description was given and matched nothing, say THAT -- "I cannot tell which you mean" is a
            # false statement about an empty match, and it is what made the engine look evasive.
            said = W.parse(rest, lex)["left"]
            if said:
                return {"kind": "NONE", "msg": f"there is nothing {' and '.join(said)} in this scene "
                                               f"right now.", "highlight": []}
            return {"kind": "ASK", "msg": f"'{act}' what? Name a description, or say 'all'.",
                    "highlight": []}
        if len(tgt) != 1 and not setwise:
            p = C.best_question(sc, tgt)
            STATE["pending"] = (p, tgt)
            return {"kind": "ASK", "msg": f"which one? {len(tgt)} match {tgt}. Is it {p}? "
                                          f"(or say 'all' to do every one)", "highlight": tgt}
        # SET-WISE: "remove the red ones" / "enlarge all" -- apply to every match, highest index first so
        # removals do not invalidate the indices still to be processed.
        before_n = len(sc)
        cur = sc
        for i in sorted(tgt, reverse=True):
            cur = ACT.OPS[alex[act]](cur, i)
        STATE["scene"] = cur
        STATE["last_ref"] = None
        which = f"objects {sorted(tgt)}" if len(tgt) > 1 else f"object #{tgt[0]}"
        return {"kind": "COMMIT", "msg": f"done - {act} applied to {which}. "
                                         f"{before_n} -> {len(cur)} objects.",
                "highlight": [], "scene": scene_json()}
    q = W.parse(text, lex)
    # ---- GOAL: "make the green one wider". The property is known; the OPERATION is not stated. So search
    #      the known operations and keep the ones that actually achieve it. Same commit rule, applied to
    #      actions instead of referents: exactly one survivor -> do it; several -> say so; none -> say THAT,
    #      which is a far better answer than claiming not to understand the words.
    if q["kind"] == "goal" and not q["unknown"]:
        if not q["left"] and not q["quant"]:
            return {"kind": "ASK",
                    "msg": f"'{q['goal']}' is the only thing you named, and it could be either the object "
                           f"you mean or the state you want. Do you mean 'make everything {q['goal']}', or "
                           f"did you mean to do something to the {q['goal']} ones? Say 'all', or name the "
                           f"state you want.", "highlight": C.referents(sc, [q["goal"]])}
        tgt = C.referents(sc, q["left"]) if q["left"] else list(range(len(sc)))
        # SET-WISE goals: "make everything wide" is one search per object, not an ambiguity to ask about.
        # The command path already worked this way; the search path did not, and asked "which one?" for a
        # sentence that names all of them.
        if len(tgt) > 1 and (q["quant"] or q["plural"]):
            cur, done, failed = list(sc), [], []
            for i in tgt:
                path = fin = None
                for depth in (2, 4, 6, 8, 12, 20):
                    path, fin = OPS.plan(cur[i], q["goal"], max_depth=depth)
                    if path is not None: break
                if path is None: failed.append(i)
                else: cur[i] = fin; done.append(i)
            if not done:
                return {"kind": "OUT-OF-WORLD", "msg": f"none of {tgt} can be made {q['goal']} within "
                                                       f"20 edits.", "highlight": tgt}
            STATE["scene"] = cur; STATE["last_ref"] = None
            extra = f" ({failed} could not be reached)" if failed else ""
            return {"kind": "COMMIT", "msg": f"done - searched an edit path for each of {done} and made "
                                             f"them {q['goal']}{extra}.",
                    "highlight": done, "scene": scene_json()}
        if len(tgt) != 1:
            if not tgt:
                return {"kind": "NONE", "msg": f"there is nothing {' and '.join(q['left'])} in this scene, "
                                               f"so there is nothing to make {q['goal']}.", "highlight": []}
            p = C.best_question(sc, tgt)
            STATE["pending"] = (p, tgt)
            return {"kind": "ASK", "msg": f"which one? {len(tgt)} match {tgt}. Is it {p}?", "highlight": tgt}
        i = tgt[0]
        goal = q["goal"]
        if W.unary_holds(goal, sc[i]):
            return {"kind": "COMMIT", "msg": f"object #{i} is already {goal}.", "highlight": [i]}
        # SEARCH a GENERATIVE space of edits derived from the object representation, escalating depth,
        # instead of scanning an authored menu of named operations. This is the Phase-1 move: the menu was
        # the thing I kept extending whenever a test failed.
        path = fin = None
        for depth in (2, 4, 6, 8, 12, 20):
            path, fin = OPS.plan(sc[i], goal, max_depth=depth)
            if path is not None: break
        if path is None:
            return {"kind": "OUT-OF-WORLD",
                    "msg": f"I understand '{goal}', but no sequence of my primitive edits "
                           f"({', '.join(sorted(OPS.PRIMS))}) reaches it from object #{i} within 20 steps.",
                    "highlight": [i]}
        new = list(sc); new[i] = fin
        STATE["scene"] = new
        STATE["last_ref"] = None
        return {"kind": "COMMIT", "msg": f"done - worked out a {len(path)}-step edit that makes object #{i} "
                                         f"{goal}: {OPS.describe_path(path)}.",
                "highlight": [i], "scene": scene_json()}
    # ---- UNKNOWN VERB. The refusals the owner hit were almost all LEXICAL, not semantic: "move the red one
    #      rightmost" was refused while the IDENTICAL request under the known marker "make" succeeded. The
    #      engine could already do the thing; it just did not know the word. So do not refuse -- HYPOTHESISE
    #      that the unknown word marks a target state, and let the search decide:
    #
    #          verb + a stated target property -> search for a path; a path EXISTS means the hypothesis is
    #                                             coherent, so ASK to confirm, then learn the word
    #          verb + NO target property       -> the sentence has no truth conditions to verify against, so
    #                                             ASK what should be true afterwards instead of refusing
    #
    #      No verb is named anywhere here. "move", "rotate", "transpose", "change" are all handled by the same
    #      rule, and a verb whose target is unreachable is still refused -- the search is the judge.
    if q["unknown"] and q["kind"] != "goal":
        cand_verb = q["unknown"][0]
        if len(q["left"]) >= 2:
            target, desc = q["left"][-1], q["left"][:-1]
            tgt = C.referents(sc, desc)
            # each of these is a DIFFERENT failure and gets its own answer. Falling through to one generic
            # message is what made every refusal look identical and unhelpful.
            if not tgt:
                return {"kind": "NONE", "msg": f"there is nothing {' and '.join(desc)} in this scene, so I "
                                               f"cannot work out what '{cand_verb}' would do.", "highlight": []}
            if len(tgt) > 1:
                pq = C.best_question(sc, tgt)
                STATE["pending"] = (pq, tgt)
                return {"kind": "ASK", "msg": f"which one? {len(tgt)} match {tgt}. Is it {pq}?",
                        "highlight": tgt}
            path = None
            for depth in (2, 4, 6, 8, 12, 20):
                path, _fin = OPS.plan(sc[tgt[0]], target, max_depth=depth)
                if path is not None: break
            if path is None:
                return {"kind": "OUT-OF-WORLD",
                        "msg": f"I could learn '{cand_verb}' if I could reach '{target}', but no sequence "
                               f"of my primitive edits reaches it from object #{tgt[0]} within 20 steps.",
                        "highlight": tgt}
            if not path:
                # a ZERO-edit path is not evidence. The target is already true, so EVERY verb "succeeds"
                # here and confirming would teach the word from a vacuous example. Ask for a real one.
                return {"kind": "ASK",
                        "msg": f"object #{tgt[0]} is already {target}, so doing nothing would satisfy that "
                               f"sentence and I would learn nothing about '{cand_verb}'. Ask me to "
                               f"'{cand_verb}' something that is NOT {target} yet.", "highlight": tgt}
            STATE["acquire"] = (cand_verb, ("GOAL",), text)
            return {"kind": "ACQUIRE",
                    "msg": f"I have never learned '{cand_verb}', but I CAN reach '{target}' for "
                           f"object #{tgt[0]} in {len(path)} edits. Does '{cand_verb}' mean "
                           f"'make it {target}'?", "highlight": tgt}
        if q["left"] and len(q["unknown"]) == 1:
            tgt = C.referents(sc, q["left"])
            props = ", ".join(sorted(set(lex.values()))[:8])
            return {"kind": "ASK",
                    "msg": f"I do not know '{cand_verb}', and nothing in the sentence says what should be "
                           f"TRUE afterwards, so I have nothing to check a guess against. Tell me the state "
                           f"you want and I will search for it -- e.g. '{cand_verb} the ... wide' or "
                           f"'... tall'. I can aim at: {props} ...", "highlight": tgt}

    # ---- ACQUIRE: an unknown word is not a dead end. WordNet PROPOSES; the engine still has to ask. ----
    if q["unknown"]:
        return _diagnose(q["unknown"], text)
    kind, msg, cands = C.answer(sc, q, lex)
    STATE["pending"] = (C.best_question(sc, cands), cands) if kind == "ASK" else None
    if kind == "COMMIT" and cands: STATE["last_ref"] = cands[0]
    return {"kind": kind, "msg": msg, "highlight": cands or [],
            "parsed": {"adjectives": q["left"], "relation": q["rel"], "second": q["right"],
                       "unknown": q["unknown"]}}


def _diagnose(unknown, original):
    """Three DIFFERENT failures were all reported as one generic refusal. Separate them:
       1. a describable word WordNet can bridge to something known  -> ACQUIRE, ask to confirm
       2. an action word WordNet can bridge to a known operation    -> ACQUIRE, ask to confirm
       3. a word with no possible meaning in this world             -> say so plainly, which is different
          from not knowing the word at all.
    """
    lex, alex = STATE["lex"], STATE["alex"]
    # 0. SPEECH ACT before anything else. A greeting is not a claim about the world, so there is nothing to
    #    verify and nothing to be wrong about -- the commit rule does not apply and refusing was a mistake.
    #    The act TYPE comes from WordNet's gloss, so any word glossed as a greeting works, not a listed set.
    for uw in unknown:
        act = ACQ.speech_act(uw)
        if act:
            kind, gloss = act
            props = ", ".join(sorted(set(lex.values()))[:5])
            acts = ", ".join(sorted(set(alex)))
            reply = {"greeting": f"hello. I can describe things in this scene ({props} ...) and do these "
                                 f"actions ({acts}). Ask me which object matches a description.",
                     "farewell": "goodbye.",
                     "thanks": "you are welcome.",
                     "apology": "no need to apologise."}[kind]
            return {"kind": "SPEECH-ACT", "msg": f"{reply}  [WordNet: '{uw}' = {gloss}]", "highlight": []}
    for uw in unknown:
        # ---- RESEARCH before abstaining (owner's rule): every designated knowledge base, cheapest first. ----
        #      One predicate across sources -> hold it ATTRIBUTED (cited) and answer, tagged; no yes/no dance.
        #      Sources disagree -> ASK with both readings. Nothing anywhere -> only THEN say so, naming the
        #      sources consulted and any that were unreachable.
        anchors = dict(lex)
        # a word the BULK pass found contested is not short-circuited: live research reads with the full anchor set
        # (attributed synonyms included) and may settle it; the bulk verdict is appended only if live also contests.
        bulk_contest = STATE.get("contested", {}).get(uw)
        r = KB.deep_research(uw, anchors)                    # chases the unknowns a definition leads to (budgeted)
        hits = [t for t in r.get("trace", []) if not t.endswith(("-> none", "-> contested")) and "budget" not in t]
        dead = len(r.get("trace", [])) - len(hits)
        chase = (("chased " + "; ".join(t.split(" -> ", 1)[1].replace("chased ", "", 1) for t in hits) + (f" ({dead} probes came back empty)" if dead else "") + ". ")
                 if r.get("trace") else "")
        ex = (f" Example use: \"{r['examples'][0]}\"." if r.get("examples") else "")
        if r["status"] == "attributed":
            pred = next(iter(r["preds"])); cites = next(iter(r["cites"].values()))
            lex[uw] = pred
            srcs = sorted({s for s, _ in cites})
            single = len({KB.family(s) for s in srcs}) < 2                 # one source family only: say so
            STATE["provenance"][uw] = f"research: {', '.join(srcs)} -> {pred}, {'single source, ' if single else 'corroborated, '}unverified"
            rr = say(original)
            via = (" via " + " > ".join(f"{c}={v['pred']}" for c, v in r["chain"].items())) if r.get("chain") else ""
            STATE["provenance"][uw] += via
            _hold(uw, pred, cites)
            STATE["research_log"].append(_jsonable({"word": uw, "status": "attributed", "pred": pred, "cites": cites,
                                                    "trace": r.get("trace", []), "consulted": r["consulted"], "unavailable": r["unavailable"]}))
            rr["msg"] = (f"researched '{uw}': {chase}{'only ' if single else ''}{', '.join(srcs)} read it as '{pred}'{via}"
                         f"{'; no second source corroborates' if single else ''} "
                         f"(e.g. {cites[0][0]}: \"{cites[0][1][:80]}\").{ex} Holding that on their word. " + rr["msg"])
            rr["research"] = {"word": uw, "pred": pred, "cites": cites, "consulted": r["consulted"], "unavailable": r["unavailable"]}
            return rr
        if r["status"] == "contested":
            STATE["teach"] = (uw, original)
            STATE["research_log"].append(_jsonable({"word": uw, "status": "contested", "preds": r["preds"], "cites": r["cites"],
                                                    "trace": r.get("trace", []), "consulted": r["consulted"], "unavailable": r["unavailable"]}))
            sides = "; ".join(f"{'/'.join(sorted(k))} per {', '.join(sorted({s for s, _ in v}))}" for k, v in r["cites"].items())
            if bulk_contest:
                sides += "; earlier bulk pass: " + "; ".join(f"{k} per {', '.join(sorted({s for s, _ in v}))}" for k, v in bulk_contest.items())
            return {"kind": "ASK", "msg": f"researched '{uw}' and the sources disagree: {sides}. Which do you mean? "
                                          f"(say the word, or 'none')", "highlight": [], "research": {"word": uw, "cites": {"/".join(sorted(k)): v for k, v in r["cites"].items()}}}
        if uw in STATE.get("single", {}):                    # live research found nothing; ONE pre-computed source vouches: hold it, cite it, say so
            v = STATE["single"].pop(uw); pred = v["pred"]
            lex[uw] = pred
            STATE["provenance"][uw] = f"{v['how']}: {v['source']}, unverified"
            _hold(uw, pred, [(c[0], c[1]) for c in v.get("cites", [])] or [(v["source"], v["span"])])
            rr = say(original)
            rr["msg"] = (f"'{uw}': only {v['source']} defines it in my terms, as '{pred}' (\"{v['span'][:80]}\"). "
                         f"No second source corroborates. Holding it on that one word. " + rr["msg"])
            return rr
        consulted_note = f" (consulted {', '.join(r['consulted'])}" + (f"; unreachable: {', '.join(r['unavailable'])}" if r["unavailable"] else "") + ")"
        STATE["research_log"].append(_jsonable({"word": uw, "status": "none", "trace": r.get("trace", []),
                                                "consulted": r["consulted"], "unavailable": r["unavailable"]}))
        aprops = ACQ.propose(uw, list(alex), pos_order=("verb",), hops=0)   # an action? STRICT synonymy
        if aprops:
            STATE["acquire"] = (uw, ("ACTION", alex[aprops[0][0]]), original)
            return {"kind": "ACQUIRE", "msg": f"I have never learned '{uw}'. WordNet relates it to "
                                              f"'{aprops[0][0]}', which I know as an action. Is that right?",
                    "highlight": []}
    known_any = [uw for uw in unknown
                 if ACQ.related_words(uw, "noun") or ACQ.related_words(uw, "verb")
                 or ACQ.related_words(uw, "adj")]
    props = ", ".join(sorted(set(lex.values()))[:6])
    acts = ", ".join(sorted(set(alex)))
    if known_any:
        return {"kind": "OUT-OF-WORLD",
                "msg": f"I know {known_any} are real words, but nothing in my world could be their meaning. "
                       f"I can only describe things ({props} ...) and do these actions ({acts})." + consulted_note,
                "highlight": []}
    return {"kind": "ABSTAIN", "msg": f"I have never seen {unknown} anywhere, and no source I can reach defines "
                                      f"them. I will not guess." + consulted_note, "highlight": []}


PAGE = """<!doctype html><meta charset=utf-8><title>primasieve</title>
<style>
 body{font:14px/1.5 system-ui,sans-serif;margin:0;background:#0f1115;color:#e6e6e6}
 .wrap{max-width:900px;margin:0 auto;padding:20px}
 h1{font-size:16px;font-weight:600;margin:0 0 4px} .sub{color:#8b93a7;margin-bottom:16px}
 .row{display:flex;gap:20px;align-items:flex-start;flex-wrap:wrap}
 #grid{background:#171a21;border:1px solid #262b36;border-radius:8px;position:relative;width:360px;height:360px}
 .obj{position:absolute;border-radius:3px;display:flex;align-items:center;justify-content:center;
      font-size:11px;color:#0008;font-weight:700;transition:outline .15s}
 .hl{outline:3px solid #fff;outline-offset:2px}
 #chat{flex:1;min-width:320px}
 #log{height:300px;overflow:auto;background:#171a21;border:1px solid #262b36;border-radius:8px;padding:10px}
 .m{margin:6px 0} .you{color:#9ecbff} .k{font-weight:700;margin-right:6px}
 .COMMIT{color:#4ade80}.ASK{color:#fbbf24}.ABSTAIN{color:#f87171}.UNKNOWABLE{color:#c084fc}.NONE{color:#8b93a7}
 .ACQUIRE{color:#38bdf8}.OUT-OF-WORLD{color:#94a3b8}.SPEECH-ACT{color:#e879f9}
 .ATTRIBUTED{color:#38bdf8}.TAUGHT{color:#a3e635}.RETRACTED{color:#fb7185}
 #kb{margin-top:18px;background:#171a21;border:1px solid #262b36;border-radius:8px;padding:12px;font-size:12px}
 #kb h2{font-size:13px;margin:0 0 6px;color:#c9d1e3} #kb table{border-collapse:collapse;width:100%}
 #kb td,#kb th{padding:2px 6px;text-align:left;border-bottom:1px solid #22262f;vertical-align:top}
 #kb th{color:#8b93a7;font-weight:600} .st-attributed{color:#38bdf8}.st-retracted{color:#fb7185}.st-commit{color:#4ade80}
 .cols{display:flex;gap:16px;flex-wrap:wrap} .cols>div{flex:1;min-width:260px} .mono{font-family:ui-monospace,monospace;font-size:11px;color:#aab2c5}
 details summary{cursor:pointer;color:#8b93a7}
 input{width:100%;padding:9px;margin-top:8px;background:#171a21;color:#e6e6e6;
       border:1px solid #262b36;border-radius:6px;font:inherit}
 button{margin-top:8px;padding:7px 12px;background:#262b36;color:#e6e6e6;border:0;border-radius:6px;cursor:pointer}
 .legend{color:#8b93a7;font-size:12px;margin-top:10px}
 .k{padding:1px 6px;border-radius:4px;background:#ffffff10}
</style>
<div class=wrap>
<h1>primasieve</h1>
<div class=sub>Type real English. It answers only when exactly one thing matches &mdash; otherwise it asks,
reports what is unknowable, or refuses on a word it never learned.</div>
<div class=row>
  <div><div id=grid></div><button onclick="newScene()">new scene</button></div>
  <div id=chat>
    <div id=log></div>
    <input id=inp placeholder="the big red one   /   is the tall blue one above the small green square"
           autofocus onkeydown="if(event.key==='Enter'){event.preventDefault();send()}">
    <button onclick="send()">send</button>
    <div class=legend id=leg></div>
    <div class=legend>feedback: <b>wrong</b> retracts the attributed word the last answer relied on (and every answer built on it);
    <b>correct</b> counts for its source; <b>forget &lt;word&gt;</b>; teach with <b>&lt;word&gt; means &lt;known word&gt;</b>.</div>
  </div>
</div>
<div id=kb>
 <h2>what it knows &mdash; and on whose word</h2>
 <div class=cols>
  <div><h2>attributed words <span class=mono id=kbcount></span></h2>
   <div style="max-height:220px;overflow:auto"><table id=kbwords></table></div></div>
  <div><h2>sources (counts, never weights)</h2><table id=kbsrc></table>
   <h2 style="margin-top:10px">probe a word (research only, learns nothing)</h2>
   <input id=probe placeholder="e.g. turquoise" onkeydown="if(event.key==='Enter'){event.preventDefault();probe()}">
   <button onclick="probe()">deep research</button>
   <pre class=mono id=probeout style="white-space:pre-wrap;max-height:200px;overflow:auto"></pre></div>
 </div>
 <details style="margin-top:8px"><summary>research log (every probe the chat ran)</summary><pre class=mono id=kblog style="white-space:pre-wrap;max-height:240px;overflow:auto"></pre></details>
 <details style="margin-top:6px"><summary>world-learned words (by elimination; cannot be retracted on anyone's word)</summary><div class=mono id=kbworld></div></details>
</div></div>
<script>
async function refreshKB(){const r=await fetch('/api/state');const j=await r.json();
 document.getElementById('kbcount').textContent=`(${j.attributed.length}; ${j.answers} dependent answers so far)`;
 document.getElementById('kbwords').innerHTML='<tr><th>word</th><th>means</th><th>state</th><th>sources</th><th>deps</th></tr>'+
  j.attributed.map(a=>`<tr title="${a.provenance.replace(/"/g,'&quot;')}"><td>${a.word}</td><td>${a.pred}</td><td class="st-${a.state}">${a.state}</td><td>${a.sources.join(', ')}</td><td>${a.dependents}</td></tr>`).join('');
 document.getElementById('kbsrc').innerHTML='<tr><th>source</th><th>confirms</th><th>strikes</th></tr>'+
  Object.entries(j.sources).map(([s,c])=>`<tr><td>${s}</td><td>${c.confirms}</td><td>${c.strikes}</td></tr>`).join('');
 document.getElementById('kblog').textContent=j.research_log.slice().reverse().map(e=>`${e.word}: ${e.status}${e.pred?' -> '+e.pred:''}${e.preds?' -> '+e.preds.join('/'):''}\\n   consulted ${e.consulted.join(', ')}${e.unavailable.length?'; unreachable '+e.unavailable.join(', '):''}${e.trace&&e.trace.length?'\\n   '+e.trace.join('\\n   '):''}`).join('\\n');
 document.getElementById('kbworld').textContent=j.world_words.join(', ')+'   | actions: '+j.actions.join(', ')}
async function probe(){const i=document.getElementById('probe');const w=i.value.trim();if(!w)return;
 document.getElementById('probeout').textContent='researching '+w+' ...';
 const r=await fetch('/api/research',{method:'POST',body:JSON.stringify({word:w})});const j=await r.json();
 document.getElementById('probeout').textContent=JSON.stringify(j,null,1);refreshKB()}
let S=[];
function draw(hl){const g=document.getElementById('grid');g.innerHTML='';
 S.forEach(o=>{const d=document.createElement('div');d.className='obj'+((hl||[]).includes(o.i)?' hl':'');
  d.style.left=(o.x/12*100)+'%';d.style.top=(o.y/12*100)+'%';
  d.style.width=(o.w/12*100)+'%';d.style.height=(o.h/12*100)+'%';d.style.background=o.css;
  d.textContent='#'+o.i;d.title=o.props.join(' ');g.appendChild(d)})}
function add(cls,txt){const l=document.getElementById('log');
 l.innerHTML+=`<div class="m"><span class="k ${cls}">${cls}</span>${txt}</div>`;l.scrollTop=l.scrollHeight}
async function newScene(){const r=await fetch('/api/new',{method:'POST'});const j=await r.json();
 S=j.scene;draw([]);document.getElementById('log').innerHTML='';
 document.getElementById('leg').textContent='words it learned: '+j.words.join(', ')}
async function send(){const i=document.getElementById('inp');const t=i.value.trim();if(!t)return;i.value='';
 document.getElementById('log').innerHTML+=`<div class="m you">you&gt; ${t}</div>`;
 const r=await fetch('/api/say',{method:'POST',body:JSON.stringify({text:t})});const j=await r.json();
 if(j.scene){S=j.scene}
 add(j.kind,j.msg);draw(j.highlight);refreshKB()}
newScene();refreshKB();
</script>"""


class H(http.server.BaseHTTPRequestHandler):
    # HTTP/1.1 + a THREADING server. The first version used single-threaded TCPServer, and one aborted
    # keep-alive connection from the browser wedged it: GET still worked from the already-open socket while
    # every later POST queued forever behind it. The logic was never slow (build 0.2s, say 0.00s) -- it was
    # the transport. Worth recording because "the page loads but nothing responds" reads like an app bug.
    protocol_version = "HTTP/1.1"

    def log_message(self, *a): pass

    def _send(self, code, body, ctype="application/json"):
        b = body.encode() if isinstance(body, str) else body
        self.send_response(code); self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        if self.path in ("/", "/index.html"): self._send(200, PAGE, "text/html; charset=utf-8")
        elif self.path == "/api/state": self._send(200, json.dumps(_state_json()))
        else: self._send(404, "{}")

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n).decode() if n else "{}"
        if self.path == "/api/new":
            new_scene()
            world_words = sorted(w for w in STATE["lex"] if w not in STATE["provenance"])
            n_att = sum(1 for w in STATE["lex"] if w in STATE["provenance"])
            self._send(200, json.dumps({"scene": scene_json(), "words": world_words + ([f"+ {n_att} attributed (WordNet, unverified)"] if n_att else [])}))
        elif self.path == "/api/say":
            self._send(200, json.dumps(say(json.loads(raw).get("text", ""))))
        elif self.path == "/api/research":                      # a manual deep probe; does NOT learn the word
            w = W.tokenize(json.loads(raw).get("word", ""))
            if not w: self._send(200, json.dumps({"error": "no word"})); return
            r = KB.deep_research(w[0], dict(STATE["lex"]))
            self._send(200, json.dumps(_jsonable({k: v for k, v in r.items()})))
        elif self.path == "/api/reload":                        # pick up new pre-emptive research without a restart
            self._send(200, json.dumps({"msg": load_attributed()}))
        elif self.path == "/api/forget":
            w = W.tokenize(json.loads(raw).get("word", ""))
            deps = _retract_word(w[0], "ui") if w else None
            self._send(200, json.dumps({"retracted": w[0] if (w and deps is not None) else None, "dependents": deps or []}))
        else:
            self._send(404, "{}")


if __name__ == "__main__":
    print("learning the English vocabulary by elimination ...")
    _, lex, _ = C.build()
    STATE["lex"] = lex
    alex, _ = ACT.learn_actions(ACT.training(400, _r.Random(4)))
    STATE["alex"] = alex
    print(f"  learned {len(lex)} property words and {len(alex)} action words")
    print(f"  {load_attributed()}")
    new_scene()
    http.server.ThreadingHTTPServer.allow_reuse_address = True
    # Serve on BOTH loopback families. A browser that resolves "localhost" to ::1 gets ERR_CONNECTION_REFUSED
    # from a server bound only to 127.0.0.1 -- which is exactly the error the owner hit.
    import socket, threading
    class H6(http.server.ThreadingHTTPServer):
        address_family = socket.AF_INET6
    srv4 = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), H)
    try:
        srv6 = H6(("::1", PORT), H)
        threading.Thread(target=srv6.serve_forever, daemon=True).start()
        print(f"  serving http://127.0.0.1:{PORT}  and  http://localhost:{PORT} (IPv6 ::1)")
    except OSError as e:
        print(f"  serving http://127.0.0.1:{PORT}  (IPv6 loopback unavailable: {e})")
    srv4.serve_forever()
