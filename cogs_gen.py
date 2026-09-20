"""STAGE 4d -- GENERATION: meaning -> English, by inverting the synchronous grammar.

The Stage 3/4 grammar is synchronous (every rule pairs a string shape with a logical-form shape), so the
inverse derivation exists and uses the SAME induced facts the parser uses: the frame -> role table gives, for
an event's ordered role tuple, the frame that realizes it (pre-marker, slot markers, slot kinds); the lexicon
gives lemma -> surface forms; the determiner table gives definiteness -> determiner. Nothing here is a second
grammar written for generation.

Two facts have to be INDUCED for the inverse that the parser never needed:
  VERB FORM BY CONTEXT   one lemma has several surface forms (eat / ate / eaten). Which one appears depends on
                         the verb's position: after the passive pre-marker (`was`) the participle, after the
                         control marker (`to`) the base form, otherwise the finite form. Learned from training as
                         (context, lemma) -> surface form; unseen (context, lemma) -> the generator ABSTAINS.
  DETERMINER BY POSITION `The` sentence-initially, `the` elsewhere: both are determiners with the same
                         definiteness realization; which one appears is a function of position, learned.

Verdict discipline unchanged: where several sentences realize one logical form (two frames with the same role
tuple), the generator returns the SET, and commits only on a singleton."""
import os, sys, collections, itertools

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cogs_lf import parse_lf
from cogs_gram import (parse_sentence, strip_term, clause_nodes, frame_key, ENTITY, EVENT, NAME, FUNC)


class Realizer:
    def __init__(self, model, train):
        self.lex, self.sch, self.mid, self.roles, self.vc = model
        # role tuple -> frames, BOTH frame-level entries and verb-keyed ones. A contested frame (the
        # unaccusative / unergative split) exists only under (frame, verb) keys, and indexing frame-level
        # entries alone left `The box changed` with the agentless passive as its only realization -- a
        # confabulation, not an ambiguity, and the whole of D1's first failure.
        self.by_roles = collections.defaultdict(set)         # roles -> {frame key}
        self.by_roles_verb = collections.defaultdict(set)    # (roles, verb) -> {frame key}
        for k, rs in self.roles.items():
            if isinstance(k, tuple) and len(k) == 3 and isinstance(k[1], tuple):
                self.by_roles[tuple(rs)].add(k)
            elif isinstance(k, tuple) and len(k) == 2 and isinstance(k[0], tuple) and len(k[0]) == 3:
                self.by_roles_verb[(tuple(rs), k[1])].add(k[0])
        self.attested = self.roles.get("__attested__", frozenset())
        self._induce_surface(train)

    def _induce_surface(self, train):
        """(context, lemma) -> surface verb form; (position class, realization) -> determiner."""
        lex = self.lex
        vform = collections.defaultdict(collections.Counter)
        dform = collections.defaultdict(collections.Counter)
        for s, lf, cat in train:
            if cat == "primitive" or lf.startswith("LAMBDA"):
                continue
            toks = strip_term(lex, s)
            for i, w in enumerate(toks):
                c = lex.cls.get(w)
                if c == EVENT:
                    prev = toks[i - 1] if i else None
                    ctx = prev if (prev is not None and lex.cls.get(prev) == FUNC and prev not in lex.det) else ""
                    vform[(ctx, lex.lemma.get(w, w))][w] += 1
                elif w in lex.det:
                    dform[("initial" if i == 0 else "medial", lex.det[w])][w] += 1
        self.vform = {k: cc.most_common(1)[0][0] for k, cc in vform.items()}
        self.dform = {k: cc.most_common(1)[0][0] for k, cc in dform.items()}
        self.term = lex.terminator

    # ---------------------------------------------------------------- realization
    def realize(self, lf):
        """-> set of sentences realizing this logical form (empty = abstain; >1 = genuine ambiguity)."""
        p = parse_lf(lf)
        if p is None or p[0] == "LAMBDA":
            return set()
        defs, conj = p
        self.defs = {i: lem for lem, i in defs}
        self.noun = {}                # variable -> lemma (indefinite)
        self.mods = collections.defaultdict(list)   # variable -> [(rel, variable)]
        self.rcs = collections.defaultdict(list)    # variable -> [event]
        self.events = collections.OrderedDict()     # event var -> [(role, arg)] in gold order
        rc_role = self.lex.rc_mid[0] if self.lex.rc_mid else None
        for pred, args in conj:
            segs = [x.strip() for x in pred.split(" . ")]
            if len(segs) == 1 and len(args) == 1:
                self.noun[args[0][1]] = segs[0]
            elif len(segs) >= 3 and len(args) == 2:
                self.mods[args[0][1]].append((segs[-1], args[1]))
            elif len(segs) == 2 and len(args) == 2:
                if segs[1] == rc_role and args[1][0] == "v":
                    self.rcs[args[0][1]].append(args[1][1])
                else:
                    self.events.setdefault(args[0][1], (segs[0], []))[1].append((segs[1], args[1]))
        if not self.events:
            return set()
        # the ROOT event is the one that is nobody's argument
        argd = {a[1] for _, (lem, rs) in self.events.items() for _, a in rs if a[0] == "v"}
        roots = [e for e in self.events if e not in argd and not any(e in v for v in self.rcs.values())]
        if len(roots) != 1:
            return set()
        outs = set()
        for toks in self._clause(roots[0], gap=None, vctx="", initial=True):
            if self.vc == "position" and not self._positions_agree(toks):
                continue
            outs.add(" ".join(toks + ([self.term] if self.term else [])))
        return outs

    def _positions_agree(self, toks):
        """Under COGS's convention a variable IS a token position, so the input logical form states where each
        event and entity word stands. `grow . theme ( x _ 4 , x _ 1 )` puts `grew` at token 4 -- which rules
        out `was grown` (verb at 5). This is a CONSISTENCY CHECK of a candidate against the input, the same kind
        the parser's sound gate performs, not a preference; under first-appearance numbering it is unavailable
        and the SET stands. It resolves the unaccusative / agentless-passive pairs and the D2 shifted-index
        confabulations at once."""
        lex = self.lex
        for e, (lemma, rs) in self.events.items():
            if e >= len(toks) or lex.lemma_of(toks[e], EVENT) != lemma:
                return False
        for v, lem in list(self.defs.items()) + list(self.noun.items()):
            if v >= len(toks) or lex.lemma_of(toks[v], ENTITY) != lem:
                return False
        return True

    def _frames_for(self, lemma, full_roles):
        """Candidate frames for an event: frame-level and verb-keyed entries with this role tuple. Several
        candidates are narrowed by SUBCATEGORIZATION -- keep those attested with this verb -- as a tie-break
        only, mirroring the parser: a single candidate is never rejected for being unattested."""
        cands = set(self.by_roles.get(full_roles, ())) | set(self.by_roles_verb.get((full_roles, lemma), ()))
        if len(cands) > 1:
            att = {fk for fk in cands if (fk, lemma) in self.attested}
            if att:
                cands = att
        return cands

    def _clause(self, e, gap, vctx, initial):
        """All realizations of event e. gap: the ARGUMENT left out (filled from outside: a relative clause's
        head, a control clause's subject); vctx: the verb-form context (the marker that precedes the verb)."""
        lemma, rs = self.events[e]
        full_roles = tuple(r for r, a in rs)          # a gap keeps its position in the frame as a GAP slot
        for fk in sorted(self._frames_for(lemma, full_roles), key=repr):
            pre, slots, front = fk
            if front is not None or len(slots) != len(rs):
                continue
            kinds = [k for m, k in slots]
            if (gap is None) != ("GAP" not in kinds) or kinds.count("GAP") > 1:
                continue
            # every slot yields a LIST of alternative realizations; the clause is their product (capped).
            # An embedded clause with two realizations must multiply into the parent's SET, not kill it --
            # requiring a singleton here was cp_recursion's 0.357 abstention.
            alts = []
            ok = True
            subj = None
            for (m, k), (r, a) in zip(slots, rs):
                if k == "GAP":
                    if a != gap:
                        ok = False
                        break
                    if subj is None:
                        subj = a
                    continue
                if k == "NP":
                    reals = self._np(a, initial and not alts and subj is None)
                    if not reals:
                        ok = False
                        break
                    alts.append([([m] if m else []) + list(t) for t in sorted(reals)])
                    if subj is None:
                        subj = a
                elif k in ("CL", "VP"):
                    if a[0] != "v":
                        ok = False
                        break
                    # a control clause's gap is THIS clause's subject and its verb directly follows the marker,
                    # so the marker (`to`) is its verb-form context; a finite complement (`that`) has its own
                    # subject between marker and verb, so its context is empty.
                    subs = list(self._clause(a[1], subj if k == "VP" else None, (m or "") if k == "VP" else "",
                                             False))
                    if not subs:
                        ok = False
                        break
                    alts.append([([m] if m else []) + t for t in subs[:8]])
            if not ok:
                continue
            key = (pre if pre else vctx, lemma)
            if key not in self.vform:
                continue                                  # unseen (context, lemma): abstain, do not invent
            verb = ([pre] if pre else []) + [self.vform[key]]
            n_out = 0
            for combo in itertools.product(*alts) if alts else [()]:
                pieces = list(combo)
                if self.sch.verb_pos == "medial":
                    if slots and slots[0][1] == "NP":
                        toks = pieces[0] + verb + [t for pc in pieces[1:] for t in pc]
                    else:
                        toks = verb + [t for pc in pieces for t in pc]
                else:
                    toks = [t for pc in pieces for t in pc] + verb
                yield toks
                n_out += 1
                if n_out >= 16:
                    break

    def _np(self, a, initial):
        """All realizations of an argument: a name, or [det] noun [modifiers] [relative clause]."""
        if a[0] == "c":
            return {(a[1],)}
        v = a[1]
        if v in self.defs:
            lem, realization = self.defs[v], "prefix"
        elif v in self.noun:
            lem, realization = self.noun[v], "plain"
        else:
            return set()
        det = self.dform.get(("initial" if initial else "medial", realization))
        if det is None:
            det = self.dform.get(("medial", realization))
        if det is None:
            return set()
        toks = [det, self._surface_noun(lem)]
        for rel, dep in self.mods.get(v, []):
            inner = self._np(dep, False)
            if not inner:
                return set()
            toks += [rel] + list(next(iter(inner)))
        for e in self.rcs.get(v, []):
            marker = next(iter(self.lex.rc_markers), None)
            if marker is None:
                return set()
            subs = list(self._clause(e, ("v", v), "", False))
            if len(subs) != 1:
                return set()
            toks += [marker] + subs[0]
        return {tuple(toks)}

    def _surface_noun(self, lem):
        for w, l in self.lex.lemma.items():
            if l == lem and self.lex.cls.get(w) == ENTITY:
                return w
        return lem


def generate_text(realizer, lf):
    """-> a sentence, or None (no realization, or several -- the SET is the honest answer, not a pick)."""
    outs = realizer.realize(lf)
    return next(iter(outs)) if len(outs) == 1 else None
