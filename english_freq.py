"""ENGLISH FREQUENCIES -- a DIAGNOSTIC for ENGLISH_MAP.md (not engine code; nothing in core/ imports it).

Estimates, per phenomenon of the English map, the share of sentences showing a SURFACE CUE for it, over training
Gutenberg books (training = not kb_events.held_book). English cue words are written here on purpose: this script only
measures, it never reads for the engine. Every rate is APPROXIMATE -- a cue both misses instances (recall) and fires on
look-alikes (precision); the cue used is printed beside each rate so the number can be judged.

    python english_freq.py [--books 60] [--sentences 50000]      -> english_freq.json + a table on stdout
"""
import os, re, sys, json, hashlib, collections

HERE = os.path.dirname(os.path.abspath(__file__))
GUT = os.path.join(HERE, "_nldata", "gutenberg")
OUT = os.path.join(HERE, "english_freq.json")


def held_book(bid): return int(hashlib.sha256(f"book:{bid}".encode()).hexdigest(), 16) % 10 == 0   # = kb_events.held_book


def training_books(n):
    allb = sorted(f[:-4] for f in os.listdir(GUT) if f.endswith(".txt") and not held_book(f[:-4]))
    step = max(1, len(allb) // n)
    return allb[::step][:n]                      # spread over the sorted list (not only the first ids)


SPLIT = re.compile(r'(?<=[.!?])["”’\']?\s+(?=["“‘\']?[A-Z])')
ABBR = re.compile(r"\b(Mr|Mrs|Dr|St|Mt|Messrs|Capt|Col|Gen|Rev|Prof|Sr|Jr|vs|etc|No)\.$")


def sentences(text):
    """paragraphs (blank-line separated) joined, then split after . ! ? before a capital; an abbreviation does not end
    a sentence (counted separately as an orthography hazard)"""
    out = []
    for para in re.split(r"\n\s*\n", text):
        p = " ".join(para.split())
        if len(p) < 2 or p.isupper() or p.startswith("[Illustration"): continue
        parts = SPLIT.split(p); buf = ""
        for s in parts:
            buf = (buf + " " + s).strip() if buf else s
            if ABBR.search(buf): continue
            out.append(buf); buf = ""
        if buf: out.append(buf)
    return out


W = r"[A-Za-z]+"
BE = r"(?:is|was|are|were|be|been|being|am|'s|'re)"
HAVE = r"(?:have|has|had|having|'ve|'d)"
IRR_PART = ("gone taken given seen done made known found told brought thought left kept held heard felt said built "
            "sent spent lost won written spoken broken chosen driven eaten fallen forgotten frozen hidden ridden risen "
            "shaken stolen sworn torn worn woken begun drunk rung sung sunk swum run come become caught taught bought "
            "fought sought struck stuck hung led fed bred met paid laid shut put set cut hit hurt let read spread").split()
IRR_PAST = ("went came saw took gave made said found knew thought told got left felt brought began ran stood heard held "
            "kept sat spoke wrote rose fell drew drove ate grew threw wore broke chose forgot hid rode shook stole swore "
            "tore woke drank rang sang sank swam became caught taught bought fought sought struck stuck hung led fed met "
            "paid laid lay meant sent spent lost won understood").split()
PART = r"(?:\w+ed|" + "|".join(IRR_PART) + r")"
PAST = r"(?:\w{2,}ed|" + "|".join(IRR_PAST) + r")"
WH = ("what", "who", "whom", "whose", "which", "where", "when", "why", "how")
AUX = r"(?:is|are|was|were|am|do|does|did|have|has|had|can|could|will|would|shall|should|may|might|must|isn't|aren't|wasn't|weren't|don't|doesn't|didn't|haven't|hasn't|hadn't|can't|couldn't|won't|wouldn't|shan't|shouldn't|mustn't)"
PRON_OBJ = r"(?:him|her|them|me|us|you|it)"
NAME_OR_OBJ = r"(?:him|her|them|me|us|you|it|[A-Z][a-z]+)"


def cue(rx, flags=re.I): return re.compile(rx, flags)


# (phenomenon id in ENGLISH_MAP.md, cue description, test(sentence, lower tokens) -> bool)
CUES = [
    # ---------------- morphology
    ("morph.plural", "determiner/numeral + word ending -s", cue(rf"\b(?:the|these|those|many|few|several|two|three|four|some|all|both|my|his|her|their|our)\s+(?:{W}\s+)?{W}[^s's]s\b")),
    ("morph.past_regular", "word ending -ed (5+ letters)", cue(r"\b[a-z]{3,}ed\b", 0)),
    ("morph.irregular", "one of ~60 common irregular past forms", cue(r"\b(?:" + "|".join(IRR_PAST) + r")\b")),
    ("morph.third_sg", "he/she/it + word ending -s", cue(r"\b(?:he|she|it)\s+(?!is\b|was\b|has\b|has\b|does\b)[a-z]{2,}[^s's]s\b")),
    ("morph.contraction_neg", "n't", cue(r"n't\b")),
    ("morph.contraction_other", "pronoun + 'll/'re/'ve/'d/'m/'s", cue(r"\b(?:i|you|he|she|it|we|they|that|there|what|who)'(?:ll|re|ve|d|m|s)\b")),
    ("morph.possessive_s", "word's + word (not it's/that's/there's/he's/let's...)", cue(r"\b(?!(?:it|that|there|he|she|what|who|let|here|where)'s)[A-Za-z]+'s\s+[a-z]+")),
    ("morph.derivation", "word with -ness/-ment/-tion/-able/-ful/-less/-ity or un-/re- prefix", cue(r"\b(?:[a-z]{3,}(?:ness|ment|tion|able|ible|ful|less|ity|ize|ise)|un[a-z]{4,})\b", 0)),
    ("morph.adverb_ly", "word ending -ly (5+ letters, not only/family/early...)", cue(r"\b(?!only|family|early|daily|holy|ugly|likely|lovely|lonely|silly|jolly|fly|reply|supply)[a-z]{3,}ly\b", 0)),
    # ---------------- noun phrase
    ("np.article", "the/a/an", cue(r"\b(?:the|a|an)\b")),
    ("np.adjective", "a/the + word ending -ful/-ous/-ive/-al/-ic/-y/-ish + word", cue(rf"\b(?:the|a|an)\s+[a-z]+(?:ful|ous|ive|al|ic|ish|ent|ant|y)\s+[a-z]+", 0)),
    ("np.compound", "two lowercase nouns after the/a ending -er/-ing/-ion + noun? (no reliable cue: the/a + 2 words + verb proxy)", cue(r"\b(?:the|a)\s+(?:[a-z]+(?:house|room|door|water|man|men|light|book|paper|work|day|time))\b", 0)),
    ("np.of_phrase", "word + of + (the|a|an|his|her|their|my|its|word)", cue(r"\b[a-z]+\s+of\s+[a-z]+", 0)),
    ("np.appositive", "Capitalised name , the/a/an/my/his/her ... ,", cue(r"\b[A-Z][a-z]+,\s+(?:the|a|an|my|his|her|our|their)\s+[a-z]+(?:\s+[a-z]+){0,3},", 0)),
    ("np.possessive_det", "my/your/his/her/its/our/their", cue(r"\b(?:my|your|his|its|our|their)\b|\bher\s+[a-z]+\b")),
    ("np.quantifier", "all/every/each/some/any/many/few/several/most/both/no/much + word", cue(r"\b(?:all|every|each|some|any|many|few|several|most|both|no|much|little)\s+[a-z]+")),
    ("np.numeral", "a digit or one..twelve/twenty/hundred/thousand", cue(r"\b(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|twenty|hundred|thousand)\b")),
    ("np.proper_name", "capitalised non-initial word (not I, not after a quote or colon)", cue(r"(?<=[a-z,;] )[A-Z][a-z]+", 0)),
    ("np.multiword_name", "two or more consecutive capitalised words, not sentence-initial (Mary Ann Evans, New York)", cue(r"(?<=[a-z,;] )[A-Z][a-z]+\s+[A-Z][a-z]+", 0)),
    ("np.world_name", "a name that one of the engine's worlds also holds (the 11 records employees, the fixture's cities/countries/works)", cue(r"\b(?:Alice|Bob|Carol|Dave|Erin|Frank|Grace|Heidi|Ivan|Judy|Ken|Paris|Rome|Berlin|Madrid|Lisbon|France|Japan|Italy|Spain|Germany|Egypt|Brazil|Tokyo|Kyoto|Athens|Napoleon|Hamlet|Shakespeare|Einstein|Nepal|Portugal)\b", 0)),
    ("np.coordinated_np", "Name and Name | the/a/his/her X and the/a/his/her Y", cue(r"\b[A-Z][a-z]+ and [A-Z][a-z]+\b|\b(?:the|a|an|his|her|their|my) [a-z]+ and (?:the|a|an|his|her|their|my) [a-z]+", 0)),
    ("np.title", "Mr/Mrs/Dr/Miss/Sir/Lady/Lord/Captain/Colonel/Madame + Name", cue(r"\b(?:Mr|Mrs|Dr|Miss|Sir|Lady|Lord|Captain|Capt|Colonel|Madame|Monsieur|Professor|Uncle|Aunt|King|Queen|Prince)\.?\s+[A-Z]", 0)),
    ("np.frequent_noun", "the/a/his/her/their + one of the very frequent nouns man/men/people/time/day/city/town/family/water/world/life/work/place/village/group/part/way/name/house? (man..name: words in the engine's 200 commonest)", cue(r"\b(?:the|a|an|his|her|their|my|this|that|every|one|old|little)\s+(?:man|men|people|time|day|city|town|family|water|world|life|work|place|village|group|part|area|way|name|language|number|state|community)\b")),
    ("np.demonstrative", "this/that/these/those + word", cue(r"\b(?:this|these|those)\b|\bthat\s+[a-z]+\s+(?:was|is|had|has)\b")),
    # ---------------- verb and argument structure
    ("verb.transitive", "pronoun/name + past verb + the/a/his/her (proxy for V + object NP)", cue(rf"\b(?:he|she|they|i|we|[A-Z][a-z]+)\s+{PAST}\s+(?:the|a|an|his|her|their|my|its)\b")),
    ("verb.ditransitive", "give/tell/show/send/bring/offer/hand/lend (any form) + object pronoun/name + the/a/his/her/some", cue(rf"\b(?:gave|give|gives|giving|told|tell|tells|showed|show|shown|sent|send|brought|bring|offered|offer|handed|hand|lent|lend|bought|promised|asked|taught|owed)\s+{NAME_OR_OBJ}\s+(?:the|a|an|his|her|their|my|some|no|all|that)\b", 0)),
    ("verb.dative_to", "give/send/hand/bring/show/offer/lend/sell/pass ... to + pronoun/name/the", cue(r"\b(?:gave|give|sent|send|handed|brought|showed|offered|lent|sold|passed|threw|wrote|read)\b[^.;]{1,40}?\bto\s+(?:him|her|them|me|us|you|the|[A-Z][a-z]+)\b")),
    ("verb.particle", "common verb + up/down/out/off/away/back/over/on", cue(r"\b(?:pick|picked|take|took|taken|put|give|gave|look|looked|come|came|go|went|get|got|set|turn|turned|make|made|run|ran|bring|brought|carry|carried|sit|sat|stand|stood|throw|threw|hold|held|keep|kept|break|broke|call|called|find|found|put)\s+(?:up|down|out|off|away|back|over|on)\b")),
    ("verb.top200_forms", "a form of the commonest verbs (made/said/found/called/used/given/take/get/make/see/use/do/set/work): all inside the engine's 200-word closed class", cue(r"\b(?:made|said|found|called|used|given|take|get|make|see|use|do|set|work|act)\b")),
    ("verb.light", "take/make/have/give + a + walk/look/bath/step/turn/decision/rest/try/glance/promise/start", cue(r"\b(?:take|took|taken|make|made|have|had|give|gave|given)\s+(?:a|an|another)\s+(?:walk|look|bath|step|turn|decision|rest|try|glance|promise|start|stroll|nap|swim|ride|run|drink|bite|break|leap|jump|sigh|shout|speech|visit)\b")),
    ("verb.copula", "be-form + a/an/the/not/very/so/too/adjective-like word (not a participle, not -ing)", cue(rf"\b(?:is|was|are|were|am|be|been)\s+(?:a|an|the|not|very|so|too|quite|rather|[a-z]+(?:ful|ous|ive|al|ic|y|ent|ant|ble|ish|less))\b")),
    ("verb.existential", "there + be-form", cue(r"\bthere\s+(?:is|was|are|were|be|been|'s|seemed to be|must be|will be|would be)\b")),
    ("verb.control", "want/try/begin/decide/hope/wish/refuse/promise/agree/mean/like/manage/forget/seem/seem/continue/attempt/long + to", cue(r"\b(?:want|wanted|wants|try|tried|tries|began|begin|decided|decide|hoped|hope|wished|wish|refused|refuse|promised|promise|agreed|agree|meant|mean|liked|like|managed|forgot|longed|ceased|continued|seemed|seem|seems|appeared|attempted|intended|expected|ought|used|wanted)\s+to\s+[a-z]+")),
    ("verb.raising_object", "want/expect/ask/tell/order/allow/beg/persuade + object + to", cue(rf"\b(?:wanted|want|expected|expect|asked|ask|told|tell|ordered|allowed|begged|persuaded|forced|advised|urged|warned|invited|taught|caused|got)\s+{NAME_OR_OBJ}\s+to\s+[a-z]+", 0)),
    ("verb.causative", "make/let/have/help/bid (any form) + object + bare word (not to/-ing/-ed)", cue(rf"\b(?:made|make|makes|let|lets|had|have|help|helped|bade|bid|watched|saw|heard|felt)\s+(?:him|her|them|me|us|it)\s+(?!to\b|the\b|a\b|and\b|in\b|on\b|at\b|of\b|for\b|with\b|up\b|down\b|out\b|go\b)[a-z]+(?<!ing)(?<!ed)\b", 0)),
    # ---------------- voice
    ("voice.passive", "be-form + (adverb) + participle (-ed or irregular)", cue(rf"\b(?:is|was|are|were|be|been|being)\s+(?:\w+ly\s+|not\s+)?{PART}\b")),
    ("voice.passive_by", "passive cue + by within 6 words", cue(rf"\b(?:is|was|are|were|be|been|being)\s+(?:\w+ly\s+|not\s+)?{PART}\b(?:\s+\w+){{0,5}}\s+by\b")),
    ("voice.get_passive", "get/got/gets/getting/gotten + participle", cue(rf"\b(?:get|got|gets|getting|gotten)\s+{PART}\b")),
    # ---------------- tense, aspect, mood
    ("tam.progressive", "be-form + word ending -ing", cue(r"\b(?:is|was|are|were|am|be|been|'s|'re|'m)\s+(?:\w+ly\s+|not\s+)?[a-z]{2,}ing\b")),
    ("tam.perfect", "have-form + (adverb) + participle", cue(rf"\b(?:have|has|had|having|'ve|'d)\s+(?:\w+ly\s+|not\s+|never\s+|just\s+|already\s+)?(?:been|{PART})\b")),
    ("tam.modal", "will/would/can/could/may/might/shall/should/must/'ll", cue(r"\b(?:will|would|can|could|may|might|shall|should|must|cannot|won't|can't|couldn't|wouldn't|shouldn't)\b|'ll\b")),
    ("tam.will_future", "will/shall/'ll/going to + word", cue(r"\b(?:will|shall|won't|shan't)\s+[a-z]+|'ll\b|\bgoing\s+to\s+[a-z]+")),
    ("tam.epistemic", "may/might/must/could/should + have/be (epistemic or perfect modal)", cue(r"\b(?:may|might|must|could|should|would)\s+(?:not\s+)?(?:have|be)\b")),
    ("tam.future_going_to", "going to + word (not a place: the/a)", cue(r"\bgoing\s+to\s+(?!the\b|a\b|an\b|his\b|her\b|my\b|their\b|bed\b|church\b|school\b|town\b)[a-z]+")),
    ("tam.conditional", "if/unless/were I/had I/should you", cue(r"\b(?:if|unless)\b|(?:^|[,;] )(?:were|had|should)\s+(?:i|he|she|they|we|you|it)\b")),
    ("tam.imperative", "sentence (or quotation) opening with a common base verb", cue(r"(?:^|[\"“‘] ?)(?:Come|Go|Let|Look|Take|Tell|Give|Do|Don't|Be|Get|See|Stop|Wait|Listen|Bring|Sit|Stand|Keep|Leave|Put|Say|Make|Help|Try|Remember|Forgive|Hold|Run|Never|Please|Call|Show|Send|Follow|Hear|Mind|Fetch|Pray|Kill|Hurry)\b", 0)),
    ("tam.subjunctive", "if I/he/she/it were | lest | God save/bless | be it | so be it | would that", cue(r"\b(?:if|as if|as though|wish)\s+(?:i|he|she|it)\s+were\b|\blest\b|\bgod\s+(?:save|bless|grant|forbid)\b|\bbe it\b|\bwould that\b")),
    ("tam.habitual_used_to", "used to + word / would (habitual) proxy: used to", cue(r"\bused\s+to\s+[a-z]+")),
    ("tam.archaic", "thou/thee/thy/thine/hath/doth/art/shalt/wilt/'tis/ye", cue(r"\b(?:thou|thee|thy|thine|hath|doth|dost|shalt|wilt|'tis|ye|hast|didst)\b")),
    # ---------------- negation
    ("neg.not", "not / n't", cue(r"\bnot\b|n't\b")),
    ("neg.never", "never", cue(r"\bnever\b")),
    ("neg.no_det", "no + word / nothing / nobody / none / no one / nowhere", cue(r"\bno\s+[a-z]+|\b(?:nothing|nobody|none|nowhere|no one|neither|nor)\b")),
    ("neg.scope", "not all / not every / not only / not much / not a single / never all", cue(r"\bnot\s+(?:all|every|only|much|many|a single|quite|always|even)\b")),
    # ---------------- questions (rates over ALL sentences; shares among questions printed separately)
    ("q.any", "sentence ending ? (inside or outside a quotation)", cue(r"\?[\"”’']?\s*$")),
    ("q.yes_no", "? and first word (after an opening quote) an auxiliary", cue(rf"^[\"“‘']?\s*{AUX}\b.*\?[\"”’']?\s*$")),
    ("q.wh_what", "? and opening word what", cue(r"^[\"“‘']?\s*what\b.*\?")),
    ("q.wh_who", "? and opening who", cue(r"^[\"“‘']?\s*who\b.*\?")),
    ("q.wh_whom", "? and whom anywhere", cue(r"\bwhom\b.*\?")),
    ("q.wh_whose", "? and opening whose", cue(r"^[\"“‘']?\s*whose\b.*\?")),
    ("q.wh_which", "? and opening which", cue(r"^[\"“‘']?\s*which\b.*\?")),
    ("q.wh_where", "? and opening where", cue(r"^[\"“‘']?\s*where\b.*\?")),
    ("q.wh_when", "? and opening when", cue(r"^[\"“‘']?\s*when\b.*\?")),
    ("q.wh_why", "? and opening why", cue(r"^[\"“‘']?\s*why\b.*\?")),
    ("q.wh_how", "? and opening how (not how many/much)", cue(r"^[\"“‘']?\s*how\b(?!\s+(?:many|much)).*\?")),
    ("q.wh_how_many", "? and opening how many/how much", cue(r"^[\"“‘']?\s*how\s+(?:many|much)\b.*\?")),
    ("q.subject_wh", "? opening who/what + past or -s verb (subject question)", cue(rf"^[\"“‘']?\s*(?:who|what)\s+(?:{PAST}|[a-z]+s)\b(?<!\bis)(?<!\bwas)(?<!\bdoes)(?<!\bhas).*\?")),
    ("q.object_wh", "? opening what/who/whom + do/did/does/will/would/can/shall", cue(r"^[\"“‘']?\s*(?:what|who|whom|where|when|why|how)\s+(?:do|did|does|will|would|can|could|shall|should)\b.*\?")),
    ("q.alternative", "? with ' or ' inside the question", cue(r"\bor\b[^?]*\?[\"”’']?\s*$")),
    ("q.tag", ", aux(n't) + pronoun ?", cue(rf",\s*{AUX}\s+(?:it|he|she|you|they|we|there|i|not)\??\s*[\"”’']?\s*\?")),
    ("q.embedded", "know/wonder/ask/tell/see/understand + wh-word/whether/if, not ending ?", cue(r"\b(?:know|knew|wonder|wondered|ask|asked|tell|told|see|saw|understand|understood|guess|remember|forget|forgot|find out|learn|learned)\s+(?:\w+\s+)?(?:what|who|whom|whose|which|where|when|why|how|whether)\b(?!.*\?\s*$)")),
    ("q.elliptical", "question of 1-3 words (echo / fragment: 'Why?', 'And you?')", cue(r"^[\"“‘']?\s*(?:[A-Za-z']+[\s,]*){1,3}\?[\"”’']?\s*$")),
    ("q.declarative", "? with no auxiliary or wh-word in the first two words (rising declarative 'You saw him?')", cue(rf"^[\"“‘']?\s*(?!{AUX}\b|what\b|who\b|whom\b|whose\b|which\b|where\b|when\b|why\b|how\b)\w+\s+(?!{AUX}\b)\w+\b[^?]*\?[\"”’']?\s*$")),
    # ---------------- clause linkage
    ("clause.coordination", ", and / , but / ; and / and + pronoun subject", cue(r"[,;]\s+(?:and|but|or|yet|so)\b|\band\s+(?:he|she|they|i|we|it)\s+[a-z]+")),
    ("clause.coord_vp", "and/but/or + (adverb) + past verb (a second verb sharing the subject)", cue(rf"\b(?:and|but|or|then)\s+(?:\w+ly\s+)?{PAST}\b")),
    ("clause.coord_clauses", ", and/but/so + pronoun/name/the (a second clause with its own subject)", cue(r",\s+(?:and|but|so|or)\s+(?:he|she|they|i|we|it|the|his|her|[A-Z][a-z]+)\b")),
    ("clause.subordination", "because/when/after/before/until/while/since/although/though/as soon as/till/whenever", cue(r"\b(?:because|when|after|before|until|till|while|since|although|though|whenever|as soon as|once)\b")),
    ("clause.open_class_connective", "until/till/since/unless/although/though/whereas/across/near/toward(s)/against/among/along/beyond/behind/beside/during/within/beneath", cue(r"\b(?:until|till|since|unless|although|though|whereas|across|near|toward|towards|against|among|along|beyond|behind|beside|during|within|beneath)\b")),
    ("quant.arithmetic_words", "twice/thrice/double/half/plus/minus/divided/times as", cue(r"\b(?:twice|thrice|double|half|plus|minus|divided|times as)\b")),
    ("clause.relative_wh", "noun-like word + who/whom/whose/which (not after a comma-less verb)", cue(r"\b[a-z]{3,}[,]?\s+(?:who|whom|whose|which)\s+[a-z]+", 0)),
    ("clause.relative_that", "the/a + word + that + word (relative OR complement 'that': ambiguous)", cue(r"\b(?:the|a|an|every|any|all)\s+[a-z]+\s+that\s+[a-z]+")),
    ("clause.relative_reduced", "noun + -ed/-ing participle + by/in/on/with/from (reduced relative proxy)", cue(r"\b(?:the|a|an)\s+[a-z]+\s+(?:[a-z]+ed|[a-z]+ing)\s+(?:by|in|on|with|from|at|near)\b", 0)),
    ("clause.complement_that", "say/think/know/believe/feel/see/find/hope/fear/tell + (obj) + that", cue(r"\b(?:said|says|say|thought|think|knew|know|believed|believe|felt|feel|saw|see|found|find|hoped|hope|feared|fear|told\s+\w+|tells\s+\w+|declared|answered|replied|suppose|supposed|heard|seemed|seems|perceived|realized|knows)\s+that\b")),
    ("clause.infinitive_purpose", "(in order) to + verb after a comma or an object (proxy: in order to | , to)", cue(r"\bin order to\b|\bso as to\b|,\s+to\s+[a-z]+")),
    ("clause.participial_adjunct", "sentence-initial or post-comma -ing/-ed clause", cue(r"(?:^|,\s+)(?:[A-Z]?[a-z]+ing)\s+(?:the|a|his|her|their|to|in|at|on|up|down|out|over|him|her|them)\b", 0)),
    ("clause.direct_speech", "a quotation mark", cue(r"[\"“”]|(?:^|\s)'[A-Z]")),
    ("clause.reported_speech", "said/told/asked/answered + (him/her/them) + that/if/whether/to", cue(r"\b(?:said|told|asked|answered|replied|explained|declared|promised|warned)\s+(?:\w+\s+)?(?:that|if|whether|to)\b")),
    # ---------------- reference
    ("ref.personal_pronoun", "he/she/they/it/we/i/you/him/her/them/me/us", cue(r"\b(?:he|she|they|it|we|i|you|him|her|them|me|us)\b")),
    ("ref.third_person_pronoun", "he/she/they/him/her/them (third-person, needing an antecedent)", cue(r"\b(?:he|she|they|him|her|them)\b")),
    ("ref.object_pronoun", "him/them/me/us, or it after a verb-like word", cue(r"\b(?:him|them|me|us)\b|\b[a-z]+(?:ed|s)\s+it\b")),
    ("ref.first_second_person", "I/me/my/we/us/our/you/your", cue(r"\b(?:i|me|my|we|us|our|you|your)\b")),
    ("ref.reflexive", "himself/herself/themselves/itself/myself/yourself/ourselves", cue(r"\b(?:himself|herself|themselves|itself|myself|yourself|yourselves|ourselves|oneself)\b")),
    ("ref.possessive_pronoun", "mine/yours/hers/ours/theirs", cue(r"\b(?:mine|yours|hers|ours|theirs)\b")),
    ("ref.demonstrative_pron", "this/that + verb or punctuation", cue(r"\b(?:this|that)\s+(?:is|was|will|would|must|may|can|could|had|has|made|seemed)\b|\b(?:this|that)[.,;!?]")),
    ("ref.definite_desc", "the + word", cue(r"\bthe\s+[a-z]+")),
    ("ref.one_anaphora", "a/the/an + adjective + one(s) | the other one | that one", cue(r"\b(?:a|an|the|this|that|which)\s+(?:[a-z]+\s+)?ones?\b(?!\s+(?:of|another|day|hand|man|woman|thing|side|night|morning|time))")),
    ("ref.vp_ellipsis", "aux (+not) right before punctuation | so did/do I | did too | do so", cue(rf"\b(?:did|does|do|could|would|will|can|should|had|has|have|was|is|were|are|must|might|shall)(?:\s+not|n't)?\s*[.,;!?]|\bso\s+(?:did|do|does|could|would|was|had)\s+\w+|\bdo\s+so\b|\bdid\s+too\b")),
    ("ref.gapping", "no reliable cue: ', and X Y' with verb missing -- proxy: , and + Name/pronoun + the/a + word + punctuation", cue(r",\s+(?:and|or)\s+(?:[A-Z][a-z]+|he|she|they|I)\s+(?:the|a|an|his|her)\s+[a-z]+[.;,]", 0)),
    ("ref.cataphora_sentence_initial_pronoun", "sentence opening with a third-person pronoun (antecedent outside the sentence)", cue(r"^[\"“]?\s*(?:He|She|They|It|His|Her|Their)\b", 0)),
    # ---------------- quantification and comparison
    ("quant.comparative", "more/less/fewer ... than | -er than | as ... as", cue(r"\b(?:more|less|fewer|[a-z]{2,}er)\s+(?:\w+\s+)?than\b|\bas\s+[a-z]+\s+as\b")),
    ("quant.superlative", "the most/least + word | the -est", cue(r"\bthe\s+(?:most|least|best|worst|[a-z]{2,}est)\b")),
    ("quant.only_focus", "only/just/even/also (focus particles)", cue(r"\b(?:only|just|even|also|alone)\b")),
    ("quant.universal", "every/each/all/everyone/everything/everybody", cue(r"\b(?:every|each|all|everyone|everything|everybody)\b")),
    ("quant.counting", "how many / the number of / count / numeral + plural noun", cue(r"\bhow many\b|\bnumber of\b|\b(?:two|three|four|five|six|seven|eight|nine|ten|\d+)\s+[a-z]+s\b")),
    # ---------------- discourse and dialogue
    ("disc.quote", "a quotation mark (= clause.direct_speech)", cue(r"[\"“”]|(?:^|\s)'[A-Z]")),
    ("disc.speaker_attribution", "said/asked/replied/cried/answered/exclaimed/whispered + Name/pronoun, or the reverse, next to a quote", cue(r"[\"”,]\s*(?:said|asked|replied|cried|answered|exclaimed|whispered|shouted|returned|continued|added)\s+[A-Za-z]+|[\"”,]\s*(?:[A-Z][a-z]+|he|she|they|I)\s+(?:said|asked|replied|cried|answered|exclaimed|whispered|shouted|returned|continued|added)\b")),
    ("disc.vocative_courtesy", "please/thank/thanks/sorry/pardon/sir/madam/ma'am/hello/good morning/goodbye", cue(r"\b(?:please|thank|thanks|sorry|pardon|sir|madam|ma'am|hello|good morning|good night|goodbye|good-bye|excuse me)\b")),
    ("disc.hedge", "perhaps/maybe/probably/possibly/I think/I suppose/I believe/seems/it may be/I fancy", cue(r"\b(?:perhaps|maybe|probably|possibly|i think|i suppose|i believe|i fancy|i dare say|i daresay|seems|seemed|apparently|i guess)\b")),
    ("disc.marker", "sentence opening with Well/Now/So/Oh/However/Indeed/Then/Yet/Still/Besides/Why/Ah/Of course + comma", cue(r"^[\"“]?\s*(?:Well|Now|So|Oh|However|Indeed|Then|Yet|Still|Besides|Why|Ah|Of course|Anyway|Still|Surely|Certainly|Alas|Look|Come)\s*,", 0)),
    ("disc.exclamative", "sentence ending !", cue(r"![\"”’']?\s*$")),
    ("disc.interjection", "oh/ah/alas/hush/hurrah/pooh/ha/hm/bah", cue(r"\b(?:oh|ah|alas|hush|hurrah|pooh|ha|hm|bah|o|aye|nay|yes|no)\s*[,!]")),
    # ---------------- lexical semantics (surface proxies only)
    ("lex.converse_pairs", "a member of give/receive, buy/sell, lend/borrow, teach/learn, win/lose, before/after, parent/child", cue(r"\b(?:gave|give|received|receive|bought|buy|sold|sell|lent|lend|borrowed|borrow|taught|teach|learned|learnt|won|lost|parent|parents|child|children|husband|wife|employer|servant|master)\b")),
    ("lex.idiom", "one of ~30 fixed phrases (of course, at once, at last, by and by, make up his mind, take place, give up, in fact, after all, all at once, as well, kind of, sort of, for good, on the other hand)", cue(r"\b(?:of course|at once|at last|by and by|made up (?:his|her|my|their) mind|make up (?:his|her|my|their) mind|take place|took place|give up|gave up|in fact|after all|all at once|as well|kind of|sort of|for good|on the other hand|by the way|at all|in spite of|for the sake of|out of the question|at least|at any rate|all the same|no doubt|in vain|at hand|by no means)\b")),
    ("lex.phrasal_meaning", "particle verb with non-compositional meaning (give up/make out/put up with/turn out/come across/take after/find out/carry on/look after/go on)", cue(r"\b(?:give up|gave up|make out|made out|put up with|turn(?:ed)? out|came across|come across|take after|took after|find out|found out|carry on|carried on|look(?:ed)? after|go(?:es)? on|went on|set out|set off|broke down|break down|brought up|bring up|made off)\b")),
    # ---------------- inference (cue words that signal the relation the reader must infer or carry)
    ("inf.cause", "because/so/therefore/thus/hence/for this reason/as a result/so that", cue(r"\b(?:because|therefore|thus|hence|consequently|so that|as a result|for this reason|on account of)\b|,\s+so\s+[a-z]+")),
    ("inf.temporal", "then/afterwards/later/next/at last/finally/soon/presently/meanwhile/at length", cue(r"\b(?:then|afterwards|afterward|later|next|at last|finally|soon|presently|meanwhile|at length|immediately|suddenly)\b")),
    ("inf.manner", "by + -ing | with + a/an/the/his/her + noun at clause end | -ly adverb", cue(r"\bby\s+[a-z]+ing\b|\b[a-z]{4,}ly\b")),
    # ---------------- orthography and noise
    ("orth.abbreviation", "Mr./Mrs./Dr./St./etc. (a period that does not end the sentence)", cue(r"\b(?:Mr|Mrs|Dr|St|Mt|Capt|Col|Gen|Rev|Prof|etc|i\.e|e\.g)\.", 0)),
    ("orth.hyphen_dash", "a hyphenated word or a dash (--, —)", cue(r"[a-z]-[a-z]|--|—")),
    ("orth.semicolon_colon", "; or :", cue(r"[;:]")),
    ("orth.allcaps", "an all-caps word of 2+ letters (not I, not roman numerals)", cue(r"\b(?!I\b|II\b|III\b|IV\b|VI\b|VII\b|VIII\b|IX\b|XI\b|XII\b)[A-Z]{2,}\b", 0)),
    ("orth.long_sentence", "more than 40 words", None),
    ("orth.nonascii", "a non-ASCII character", cue(r"[^\x00-\x7f]", 0)),
    ("orth.parenthesis", "( or [", cue(r"[(\[]")),
]


def main():
    nb = int(sys.argv[sys.argv.index("--books") + 1]) if "--books" in sys.argv else 60
    ns = int(sys.argv[sys.argv.index("--sentences") + 1]) if "--sentences" in sys.argv else 50000
    bks = training_books(nb); per = max(1, ns // len(bks))
    sents = []; nwords = 0
    for b in bks:
        # the corpus files end lines with CR CR LF: read raw and drop every CR, or each line becomes a paragraph
        text = open(os.path.join(GUT, b + ".txt"), encoding="utf-8", errors="replace", newline="").read().replace(chr(13), "")
        ss = [s for s in sentences(text) if 3 <= len(s.split()) <= 120]
        mid = max(0, len(ss) // 2 - per // 2)           # a block from the middle (skips front matter and back matter)
        sents += ss[mid:mid + per]
    sents = sents[:ns]
    counts = collections.Counter()
    for s in sents:
        nwords += len(s.split())
        for pid, desc, rx in CUES:
            if rx is None:
                if pid == "orth.long_sentence" and len(s.split()) > 40: counts[pid] += 1
                continue
            if rx.search(s): counts[pid] += 1
    n = len(sents); nq = counts["q.any"] or 1
    res = dict(note="APPROXIMATE surface-cue rates: share of sentences where the cue fires (cue recall and precision both "
                    "imperfect). Question types also as a share of question sentences ('of_questions').",
               books=len(bks), book_ids=bks, sentences=n, words=nwords, rates={})
    for pid, desc, rx in CUES:
        r = dict(rate=round(counts[pid] / n, 4), count=counts[pid], cue=desc)
        if pid.startswith("q.") and pid != "q.any": r["of_questions"] = round(counts[pid] / nq, 4)
        res["rates"][pid] = r
    json.dump(res, open(OUT, "w", encoding="utf-8"), indent=1)
    print(f"ENGLISH FREQUENCIES over {len(bks)} training books, {n} sentences, {nwords} words  (approximate surface cues)")
    print(f"{'phenomenon':38s} {'rate':>7s} {'of q':>6s}  cue")
    for pid, desc, rx in CUES:
        r = res["rates"][pid]
        oq = f"{r['of_questions']:.3f}" if "of_questions" in r else ""
        print(f"{pid:38s} {r['rate']:7.3f} {oq:>6s}  {desc[:90]}")
    print(f"\nwritten {OUT}")


if __name__ == "__main__":
    main()
