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


def skeletons(R, P):
    """P(gender) -> a fresh name. Each skeleton returns (text, [(question, [gold forms])])."""
    out = []
    # 1 ownership / borrowing / promise
    a, ga = P(None); rel, gr = R.choice(RELS); b, gb = P(gr); obj = R.choice(OBJECTS); place = R.choice(PLACES)
    s, o, p = pron(ga); s2, o2, p2 = pron(gb)
    out.append((f"{a} had a {obj}. One afternoon {p} {rel} {b} borrowed the {obj} without asking. {s2.capitalize()} took it to {place}. "
                f"When {s2} came back, {a} was waiting at the door. {s.capitalize()} made {o2} promise to return it on time next time.",
                [(f"Who owned the {obj}?", [a.lower()]), (f"Who borrowed the {obj}?", [b.lower(), f"{p} {rel}"]),
                 (f"Where did {b} take the {obj}?", [place.lower(), place.lower().replace("the ", "")]),
                 (f"Who was waiting at the door?", [a.lower()]), (f"What did {b} promise?", ["return it on time", "to return it"])]))
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
    s, o, p = pron(ga); s2, o2, pp2 = pron(gb)
    out.append((f"{a} lost {p} {obj} near {p1}. {s.capitalize()} searched all morning. In the evening {b} found the {obj} at {p2} and brought it to {a}. "
                f"{a} gave {b} a jar of honey to say thank you.",
                [(f"What did {a} lose?", [obj.lower()]), (f"Where did {a} lose the {obj}?", [p1.lower(), p1.lower().replace("the ", "")]),
                 (f"Who found the {obj}?", [b.lower()]), (f"Where was the {obj} found?", [p2.lower(), p2.lower().replace("the ", "")]),
                 (f"What did {a} give {b}?", ["jar of honey", "honey"])]))
    # 4 gift / trip
    a, ga = P(None); rel, gr = R.choice(RELS); b, gb = P(gr); obj = R.choice(OBJECTS); place = R.choice(PLACES); day = R.choice(WEEKDAYS)
    s, o, p = pron(ga)
    out.append((f"On {day}, {a} travelled to {place} to visit {p} {rel} {b}. {s.capitalize()} brought a {obj} as a gift. {b} was delighted and hung it by the window. "
                f"They ate supper together and {a} went home after dark.",
                [(f"Who did {a} visit?", [b.lower(), f"{p} {rel}", rel]), (f"Where did {a} travel?", [place.lower(), place.lower().replace("the ", "")]),
                 (f"What did {a} bring as a gift?", [obj.lower()]), (f"When did {a} travel?", [day.lower()]), (f"Who hung the {obj} by the window?", [b.lower()])]))
    # 5 job / making
    a, ga = P(None); b, gb = P(None); obj = R.choice(OBJECTS); place = R.choice(PLACES); n = R.choice(["three", "four", "five", "six", "seven"])
    s, o, p = pron(ga); s2, o2, p2 = pron(gb)
    out.append((f"{a} worked at {place}. Every morning {s} made {n} loaves of bread. {b}, who lived next door, bought one loaf each day and once paid with a {obj}. "
                f"{a} kept the {obj} on a shelf above the oven.",
                [(f"Where did {a} work?", [place.lower(), place.lower().replace("the ", "")]), (f"How many loaves did {a} make?", [n]),
                 (f"Who bought a loaf each day?", [b.lower()]), (f"What did {b} once pay with?", [obj.lower()]), (f"Where did {a} keep the {obj}?", ["shelf", "above the oven"])]))
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
    a, ga = P(None); animal = R.choice(["dog", "cat", "goat", "parrot", "pony", "rabbit", "goose", "donkey"]); pet, _ = P(None); place = R.choice(PLACES); b, gb = P(None)
    s, o, p = pron(ga)
    out.append((f"{a} kept a {animal} named {pet}. One night {pet} ran off toward {place}. {a} looked everywhere until {b} heard a noise behind the shed. "
                f"{pet} was found asleep in a crate, and {a} carried {pet} home.",
                [(f"What animal did {a} keep?", [animal]), (f"What was the {animal} called?", [pet.lower()]), (f"Where did {pet} run toward?", [place.lower(), place.lower().replace("the ", "")]),
                 (f"Who heard a noise behind the shed?", [b.lower()]), (f"Where was {pet} found?", ["crate", "in a crate"])]))
    return out


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 6000
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
        for text, qs in skeletons(R, P):
            data.append(dict(text=text, qs=qs))
    R.shuffle(data); data = data[:n]
    assert not any(d["text"] == s["text"] for d in data for s in test)
    json.dump(data, open(os.path.join(HERE, "stories_train.json"), "w", encoding="utf-8"), indent=0)
    print(len(data), "stories,", sum(len(d["qs"]) for d in data), "questions"); print(data[0]["text"]); print(data[0]["qs"][:2])


if __name__ == "__main__":
    main()
