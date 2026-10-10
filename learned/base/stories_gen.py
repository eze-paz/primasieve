"""Training data for the reading skill (subtractive plan, step 2): short stories in the B6 style with who/what/where
questions, generated from skeletons with random names (the L3 name pool), objects, places and verbs. Every story's facts
are new combinations, so nothing in them can be in the pretrained weights: the only way to answer is to read the story.
The B6 test stories (tests/battery/stories.json) are never used; skeletons are written fresh and checked for overlap.
Run: python learned/base/stories_gen.py [n]  -> learned/base/stories_train.json"""
import os, sys, json, random

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
OBJECTS = ["lantern", "fishing rod", "blue bicycle", "wooden flute", "silver watch", "map", "kite", "notebook", "umbrella", "basket of apples",
           "red scarf", "telescope", "pocket knife", "paintbrush", "old radio", "green bottle", "chess set", "leather bag", "copper kettle", "straw hat",
           "ladder", "music box", "compass", "sled", "pair of skates", "camera", "violin", "trumpet", "clay pot", "brass key"]
PLACES = ["the harbour", "the mill", "the old bridge", "the market", "the orchard", "the lighthouse", "the station", "the library", "the river bank",
          "the hilltop", "the bakery", "the village square", "the barn", "the beach", "the schoolhouse", "the forest edge", "the quarry", "the chapel",
          "the well", "the bus stop", "the pier", "the garden gate", "the attic", "the town hall", "the meadow"]
SKILLS = ["the piano", "chess", "to swim", "to bake bread", "the guitar", "to ride a horse", "to sail", "French", "to draw", "the drums", "to skate", "carpentry"]
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
RELS = [("brother", "m"), ("sister", "f"), ("cousin", "o"), ("uncle", "m"), ("aunt", "f"), ("neighbour", "o"), ("friend", "o"), ("grandfather", "m"), ("grandmother", "f")]
TITLES = {"f": ["Mrs", "Miss"], "m": ["Mr", "Dr"]}


def pron(g): return ("she", "her", "her") if g == "f" else ("he", "him", "his")


ANIMALS = ["fox", "hare", "tortoise", "crow", "wolf", "owl", "mouse", "bear", "goat", "heron", "lion", "ant", "frog", "stag", "donkey", "cat", "dog", "sparrow"]
ROLES = [("baker", "o"), ("miller", "m"), ("old woman", "f"), ("old man", "m"), ("captain", "m"), ("innkeeper", "o"), ("shepherd", "m"), ("nurse", "f"),
         ("blacksmith", "m"), ("schoolmaster", "m"), ("widow", "f"), ("merchant", "m"), ("gardener", "o"), ("fisherman", "m"), ("queen", "f"), ("king", "m")]
PROMISES = ["to knock first", "to return it on time", "to be more careful", "to tell her", "to clean it", "to bring it back by noon", "to say sorry", "to share it"]
THANKS = ["a jar of honey", "a basket of pears", "some fresh eggs", "a loaf of bread", "a bunch of flowers", "a bag of walnuts", "a pot of jam", "a warm scarf"]
KEPT = ["on a shelf above the oven", "in a drawer", "under the counter", "on the windowsill", "in a tin box", "behind the flour sacks", "on a nail by the door", "in a basket"]
FOUND = ["in a crate", "under the cart", "in the hayloft", "behind the woodpile", "in a ditch", "on the porch", "under a bush", "in the chapel"]
REASONS = ["to sing", "to answer", "to laugh", "to boast", "to shout", "to thank him"]
NEEDY = ["a child", "an old beggar", "a lost boy", "a little girl", "a tired soldier", "a stray dog"]
FOODS = ["cheese", "clover", "grapes", "a loaf", "honey", "berries", "corn", "a fish", "an apple", "nuts"]


def actor(R, P, kind=None):
    """an actor of a varied kind: a bare name, a titled name, a role ('the baker'), or an animal ('the fox').
    Returns (mention, gold forms, gender)"""
    kind = kind or R.choice(["name", "name", "title", "role", "animal", "animal"])
    if kind == "name":
        x, g = P(None); return x, [x.lower()], g
    if kind == "title":
        g = R.choice("fm"); x, _ = P(g); t = R.choice(TITLES[g]); return f"{t}. {x}", [f"{t.lower()} {x.lower()}", x.lower()], g
    if kind == "role":
        r, g = R.choice(ROLES); return f"the {r}", [f"the {r}", r], (g if g != "o" else R.choice("fm"))
    a = R.choice(ANIMALS); return f"the {a}", [f"the {a}", a], R.choice("fm")


def fables(R, P):
    out = []
    # A: race (tortoise and hare shape, with any two actors)
    a, ga, g1 = actor(R, P); b, gb, g2 = actor(R, P)
    while b == a: b, gb, g2 = actor(R, P)
    place = R.choice(PLACES)
    out.append((f"{a.capitalize()} challenged {b} to a race to {place}. {b.capitalize()} ran ahead and then lay down to sleep under a tree. "
                f"{a.capitalize()} never stopped and reached {place} first. When {b} woke, the race was over.",
                [("Who challenged whom to a race?", ga), ("Who slept during the race?", gb), ("Who never stopped?", ga), ("Who won the race?", ga),
                 ("Where was the race to?", [place.lower(), place.lower().replace("the ", "")]),
                 (f"Where was {a} at the end?", [place.lower(), place.lower().replace("the ", "")]), ("Who reached the end first?", ga)]))   # R20
    # B: flattery and food (fox and crow shape)
    a, ga, _ = actor(R, P); b, gb, _ = actor(R, P); food = R.choice(FOODS); reason = R.choice(REASONS)
    while b == a: b, gb, _ = actor(R, P)
    out.append((f"{b.capitalize()} sat on a branch holding {food}. {a.capitalize()} came by and flattered {b}, praising {b}'s fine voice. "
                f"{b.capitalize()} opened its mouth {reason} and dropped {food}. {a.capitalize()} ate {food} and walked away.",
                [("Who flattered whom?", ga), (f"Who was holding {food}?", gb), (f"Who ate {food}?", ga), (f"What did {a} eat?", [food.replace("a ", "").replace("an ", "")]),
                 (f"Why did {b} drop {food}?", [reason, reason.replace("to ", "")])]))
    # C: keys / lost thing with a time
    a, ga, g1 = actor(R, P); b, gb, g2 = actor(R, P); obj = R.choice(["the keys", "a purse", "a letter", "the ring", "a glove"]); place = R.choice(PLACES)
    where = R.choice(["under a bench", "behind the door", "in a drawer", "under the stairs", "beside the well", "on the roof"]); when = R.choice(["at lunch", "at dawn", "after supper", "at noon", "on Sunday", "before dark"])
    while b == a: b, gb, g2 = actor(R, P)
    out.append((f"{a.capitalize()} could not find {obj}. {b.capitalize()} had seen {obj} {where} near {place}. {b.capitalize()} fetched {obj} and returned {obj} to {a} {when}.",
                [(f"Where were {obj}?" if obj.endswith("s") else f"Where was {obj}?", [where]), (f"Who returned {obj}?", gb), (f"When did {b} return {obj}?", [when]),
                 (f"Who lost {obj}?", ga), (f"Near which place?", [place.lower(), place.lower().replace("the ", "")]),
                 (f"Who had {obj} at the end?", ga), (f"Where {'were' if obj.endswith('s') else 'was'} {obj} before {b} returned {obj}?", [where])]))   # R20
    # D: planting / harvest with a season
    a, ga, _ = actor(R, P); crop = R.choice(["tomatoes", "beans", "potatoes", "pumpkins", "onions", "roses"]); season = R.choice(["in the spring", "in autumn", "in early summer", "in March"])
    helper, gh, _ = actor(R, P); nb = R.choice(["two", "three", "four", "five", "six"])
    while helper == a: helper, gh, _ = actor(R, P)
    out.append((f"{a.capitalize()} planted {crop} {season}. {helper.capitalize()} watered them every evening. By the end of the season the {crop} filled {nb} baskets, "
                f"and {a} gave one basket to {helper}.",
                [(f"What did {a} plant?", [crop]), (f"When were the {crop} planted?", [season, season.replace("in ", "")]), ("Who watered them?", gh),
                 ("How many baskets did they fill?", [nb]), (f"Who received a basket?", gh)]))
    # E: ship / storm
    a, ga, _ = actor(R, P, "title"); b, gb, _ = actor(R, P); thing = R.choice(["a hat", "a lantern", "the map", "a barrel", "a coat"]); place = R.choice(PLACES)
    out.append((f"{a} steered the ship through a storm toward {place}. A wave knocked {thing} belonging to {b} into the sea. {b.capitalize()} was angry, but {a} laughed "
                f"and gave {b} {thing.replace('the ', 'a ')} of {('his' if _ == 'm' else 'her')} own.",
                [("Who steered the ship?", ga), ("What fell into the sea?", [thing.replace("the ", ""), f"{gb[0]}'s {thing.replace('the ', '').replace('a ', '')}"]),
                 (f"Whose {thing.replace('the ', '').replace('a ', '')} fell into the sea?", gb), ("Where was the ship going?", [place.lower(), place.lower().replace("the ", "")]), ("Who was angry?", gb)]))
    # F: buying with a count
    a, ga, _ = actor(R, P); n = R.choice(["two", "three", "four", "five"]); item = R.choice(["loaves of bread", "candles", "eggs", "pears", "ribbons"]); seller, gs, _ = actor(R, P, "role"); place = R.choice(PLACES); coin = R.choice(["a silver coin", "two pennies", "a copper", "a shilling"]); needy = R.choice(NEEDY)
    out.append((f"{a.capitalize()} went to {place} and bought {n} {item} from {seller}. {a.capitalize()} paid with {coin}. On the way home {a} gave one to {needy} who was crying.",
                [(f"What did {a} buy?", [f"{n} {item}", item]), (f"Who sold the {item}?", gs), (f"How did {a} pay?", [coin.replace("a ", "").replace("two ", "")]),
                 (f"Where did {a} buy the {item}?", [place.lower(), place.lower().replace("the ", "")]), ("Who was crying?", [needy, needy.split()[-1]])]))
    return out


def skeletons(R, P):
    """P(gender) -> a fresh name. Each skeleton returns (text, [(question, [gold forms])])."""
    out = []
    # 1 ownership / borrowing / promise
    a, ga = P(None); rel, gr = R.choice(RELS); b, gb = P(gr); obj = R.choice(OBJECTS); place = R.choice(PLACES); promise = R.choice(PROMISES)
    s, o, p = pron(ga); s2, o2, p2 = pron(gb)
    out.append((f"{a} had a {obj}. One afternoon {p} {rel} {b} borrowed the {obj} without asking. {s2.capitalize()} took it to {place}. "
                f"When {s2} came back, {a} was waiting at the door. {s.capitalize()} made {o2} promise {promise} next time.",
                [(f"Who owned the {obj}?", [a.lower()]), (f"Who borrowed the {obj}?", [b.lower(), f"{p} {rel}"]),
                 (f"Where did {b} take the {obj}?", [place.lower(), place.lower().replace("the ", "")]),
                 (f"Where was the {obj} at the end?", [place.lower(), place.lower().replace("the ", "")]),           # R20: state questions the generator knows
                 (f"Who had the {obj} at the end?", [b.lower()]), (f"Who had the {obj} first?", [a.lower()]),
                 (f"Who was waiting at the door?", [a.lower()]), (f"What did {b} promise?", [promise, promise.replace("to ", "")])]))
    # 2 learning / teacher
    a, ga = P(None); tg = R.choice("fm"); t, _ = P(tg); title = R.choice(TITLES[tg]); skill = R.choice(SKILLS); day = R.choice(WEEKDAYS); place = R.choice(PLACES)
    s, o, p = pron(ga); rel, gr = R.choice(RELS)
    out.append((f"{a} wanted to learn {skill}. {p.capitalize()} teacher, {title}. {t}, gave {o} a lesson every {day}. After a year, {a} performed at {place}. "
                f"{p.capitalize()} {rel} came to watch.",
                [(f"What did {a} want to learn?", [skill.lower().replace("to ", ""), skill.lower()]), (f"Who was {p} teacher?", [f"{title.lower()} {t.lower()}", t.lower()]),
                 (f"On which day was the lesson?", [day.lower()]), (f"Where did {a} perform?", [place.lower(), place.lower().replace("the ", "")]),
                 (f"Who came to watch?", [f"{p} {rel}", rel])]))
    # 3 lost and found
    a, ga = P(None); b, gb = P(None); obj = R.choice(OBJECTS); p1 = R.choice(PLACES); p2 = R.choice(PLACES)
    while p2 == p1: p2 = R.choice(PLACES)
    thanks = R.choice(THANKS)
    s, o, p = pron(ga); s2, o2, pp2 = pron(gb)
    out.append((f"{a} lost {p} {obj} near {p1}. {s.capitalize()} searched all morning. In the evening {b} found the {obj} at {p2} and brought it to {a}. "
                f"{a} gave {b} {thanks} to say thank you.",
                [(f"What did {a} lose?", [obj.lower()]), (f"Where did {a} lose the {obj}?", [p1.lower(), p1.lower().replace("the ", "")]),
                 (f"Who found the {obj}?", [b.lower()]), (f"Where was the {obj} found?", [p2.lower(), p2.lower().replace("the ", "")]),
                 (f"Who had the {obj} at the end?", [a.lower()]), (f"Who had the {obj} after {a}?", [b.lower()]),     # R20
                 (f"What did {a} give {b}?", [thanks.replace("a ", "").replace("some ", ""), thanks.split()[-1]])]))
    # 4 gift / trip
    a, ga = P(None); rel, gr = R.choice(RELS); b, gb = P(gr); obj = R.choice(OBJECTS); place = R.choice(PLACES); day = R.choice(WEEKDAYS)
    s, o, p = pron(ga)
    out.append((f"On {day}, {a} travelled to {place} to visit {p} {rel} {b}. {s.capitalize()} brought a {obj} as a gift. {b} was delighted and hung it by the window. "
                f"They ate supper together and {a} went home after dark.",
                [(f"Who did {a} visit?", [b.lower(), f"{p} {rel}", rel]), (f"Where did {a} travel?", [place.lower(), place.lower().replace("the ", "")]),
                 (f"What did {a} bring as a gift?", [obj.lower()]), (f"When did {a} travel?", [day.lower()]), (f"Who hung the {obj} by the window?", [b.lower()]),
                 (f"Where was {a} at the end?", ["home"]), (f"Where did {a} travel?", [place.lower(), place.lower().replace("the ", "")]), (f"Who had the {obj} at the end?", [b.lower()])]))   # R20
    # 5 job / making
    a, ga = P(None); b, gb = P(None); obj = R.choice(OBJECTS); place = R.choice(PLACES); n = R.choice(["three", "four", "five", "six", "seven"]); kept = R.choice(KEPT)
    s, o, p = pron(ga); s2, o2, p2 = pron(gb)
    out.append((f"{a} worked at {place}. Every morning {s} made {n} loaves of bread. {b}, who lived next door, bought one loaf each day and once paid with a {obj}. "
                f"{a} kept the {obj} {kept}.",
                [(f"Where did {a} work?", [place.lower(), place.lower().replace("the ", "")]), (f"How many loaves did {a} make?", [n]),
                 (f"Who bought a loaf each day?", [b.lower()]), (f"What did {b} once pay with?", [obj.lower()]), (f"Where did {a} keep the {obj}?", [kept.replace("on a ", "").replace("in a ", "").replace("under the ", ""), kept])]))
    # 6 race / contest
    a, ga = P(None); b, gb = P(None); c, gc = P(None); place = R.choice(PLACES); obj = R.choice(OBJECTS)
    out.append((f"{a}, {b} and {c} raced from the fountain to {place}. {b} tripped on a root and {c} stopped to help. {a} reached {place} first and won a {obj}. "
                f"{a} shared the prize with {c} for being kind.",
                [(f"Who won the race?", [a.lower()]), (f"Who tripped on a root?", [b.lower()]), (f"Who stopped to help?", [c.lower()]),
                 (f"What was the prize?", [obj.lower()]), (f"Who did {a} share the prize with?", [c.lower()])]))
    # 7 letter / message
    a, ga = P(None); b, gb = P(None); place = R.choice(PLACES); day = R.choice(WEEKDAYS); obj = R.choice(OBJECTS)
    s, o, p = pron(ga); s2, o2, p2 = pron(gb)
    out.append((f"{a} wrote a letter to {b} asking to meet at {place} on {day}. {b} read the letter twice and wrote back yes. "
                f"On {day} {b} arrived early carrying a {obj}, and they walked together until sunset.",
                [(f"Who wrote the letter?", [a.lower()]), (f"Who was the letter to?", [b.lower()]), (f"Where did they agree to meet?", [place.lower(), place.lower().replace("the ", "")]),
                 (f"On which day did they meet?", [day.lower()]), (f"What was {b} carrying?", [obj.lower()])]))
    # 8 animal / pet
    a, ga = P(None); animal = R.choice(["dog", "cat", "goat", "parrot", "pony", "rabbit", "goose", "donkey"]); pet, _ = P(None); place = R.choice(PLACES); b, gb = P(None); found = R.choice(FOUND)
    s, o, p = pron(ga)
    out.append((f"{a} kept a {animal} named {pet}. One night {pet} ran off toward {place}. {a} looked everywhere until {b} heard a noise behind the shed. "
                f"{pet} was found asleep {found}, and {a} carried {pet} home.",
                [(f"What animal did {a} keep?", [animal]), (f"What was the {animal} called?", [pet.lower()]), (f"Where did {pet} run toward?", [place.lower(), place.lower().replace("the ", "")]),
                 (f"Who heard a noise behind the shed?", [b.lower()]), (f"Where was {pet} found?", [found.split()[-1], found]),
                 (f"Where was {pet} at the end?", ["home"]), (f"Who had {pet} at the end?", [a.lower()])]))   # R20
    return out


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else 6000
    names = json.load(open(os.path.join(ROOT, "learned", "cache", "names.json"), encoding="utf-8"))["pool"]
    first = {g: [x for x in names[g] if x.isalpha() and 3 <= len(x) <= 9] for g in "fm"}
    R = random.Random(2026); data = []
    test = json.load(open(os.path.join(ROOT, "tests", "battery", "stories.json"), encoding="utf-8"))["stories"]
    test_names = {w.strip(".,") for s in test for w in s["text"].split() if w[:1].isupper()}
    while len(data) < n:
        used = set()
        def P(g):
            g = g if g in ("f", "m") else R.choice("fm")
            while True:
                x = R.choice(first[g])
                if x not in used and x not in test_names: used.add(x); return x, g
        for text, qs in skeletons(R, P) + (fables(R, P) if "--v2" in sys.argv else []):
            data.append(dict(text=text, qs=qs))
    R.shuffle(data); data = data[:n]
    assert not any(d["text"] == s["text"] for d in data for s in test)
    json.dump(data, open(os.path.join(HERE, "stories_train_v2.json" if "--v2" in sys.argv else "stories_train.json"), "w", encoding="utf-8"), indent=0)
    print(len(data), "stories,", sum(len(d["qs"]) for d in data), "questions"); print(data[0]["text"]); print(data[0]["qs"][:2])


if __name__ == "__main__":
    main()
