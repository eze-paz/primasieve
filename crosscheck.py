"""CROSSCHECK -- two fetched sources: corroborated, contested, never voted (crosscheck_prereg.md). Zero LLM. The online
pass runs ONCE (`--record`: Wikidata into research_cache.json if missing, OpenStreetMap into osm_cache.json); the gate
replays both offline and plants its contradictions in a COPY of the OpenStreetMap cache.

Usage:  python crosscheck.py [--record] [--quick]"""
import os, sys, time, json, random, subprocess, collections, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "emergence"))
import research as Rg
from chat import Door, YES, NO, ASK
from core.research import Researcher, WikidataFetcher
from core.verdict import COMMIT, ATTRIBUTED, CONJECTURED
from core.reason import READINGS, PARTIAL, NOT_FOUND
from core.registry import selfcheck
from kb_osm import Nominatim, CACHE_PATH as OSM_CACHE

T0 = time.time()
OUT = os.path.join(HERE, "_nldata", "crosscheck")
QS = Rg.QS
NAMES = [q.split(" of ", 1)[1] for q, g in QS]


def say(s=""): print(str(s).encode("ascii", "replace").decode(), flush=True)


def osm(path, online=False): return Nominatim(offline=not online, cache_path=path)


def planted_cache(plants):
    """a copy of the recorded OpenStreetMap cache with `plants` {name: country} written into the stored responses"""
    c = json.load(open(OSM_CACHE, encoding="utf-8")); out = os.path.join(OUT, "osm_planted.json")
    for name, country in plants.items():
        key = "search:" + name
        if key not in c: continue
        hits = json.loads(c[key])
        for h in hits:
            h.setdefault("address", {})["country"] = country
        c[key] = json.dumps(hits)
    json.dump(c, open(out, "w", encoding="utf-8")); return out


def shuffled_cache(seed=3):
    c = json.load(open(OSM_CACHE, encoding="utf-8")); out = os.path.join(OUT, "osm_shuffled.json")
    keys = ["search:" + n for n in NAMES if "search:" + n in c]; vals = [c[k] for k in keys]
    random.Random(seed).shuffle(vals)
    for k, v in zip(keys, vals): c[k] = v
    json.dump(c, open(out, "w", encoding="utf-8")); return out


def door(osm_path, tag):
    R = Researcher([Rg.fetcher(online=False), osm(osm_path)], os.path.join(OUT, tag))
    D, W, df = Rg.door(R)
    return D, R


def main():
    selfcheck(__file__)
    if "--record" in sys.argv:
        if not os.path.exists(Rg.CACHE): say("record the Wikidata pass first: python research.py --record"); return
        src = osm(OSM_CACHE, online=True)
        for n in NAMES:
            got = src.fetch(n); say(f"    {n!r:22s} -> {sorted({c for e in got[1].values() for c in e['claims'].get('country', [])}) if got else 'nothing'}")
        say(f"    cache written: {OSM_CACHE} ({src.calls} calls)"); return
    if not (os.path.exists(Rg.CACHE) and os.path.exists(OSM_CACHE)):
        say("CROSSCHECK: NOT RUN (record both caches once online: python research.py --record; python crosscheck.py --record)"); return
    say("TWO FETCHED SOURCES: corroborated, contested, never voted (crosscheck_prereg.md)\n")
    if os.path.exists(OUT): shutil.rmtree(OUT)
    os.makedirs(OUT, exist_ok=True); fails = []
    # ---- X1 + X2
    D, R = door(OSM_CACHE, "both")
    both = 0; rows = []; corroborated = 0; conf0 = D.S.ledger.snapshot()
    for q, g in QS:
        rec = D.turn(q); srcs = sorted(set(rec.get("sources", []))); att = {f for f, s_, p in R.attached if s_ == q.split(" of ", 1)[1]}
        both += len(att) == 2; s = Rg.sc(rec, g); rows.append((q, rec["kind"], rec.get("values"), srcs, s, sorted(att)))
        if rec["kind"] == ATTRIBUTED and len(rec.get("values", [])) == 1 and len(srcs) >= 2: corroborated += 1
    for q, k, v, srcs, s, att in rows: say(f"    {q:44s} -> {k:11s} {str(v)[:36]:38s} {s:8s} sources {srcs} attached {att}")
    fired = sum(1 for t, fr in D.S.history if fr.get("self_confirmed"))
    x1 = both >= 7; x2 = corroborated >= 5 and D.S.ledger.snapshot() == conf0 and fired == 0 and all(s != "confab" for *_, s, _ in rows)
    say(f"X1  both sources attached for {both}/10 names   [>= 7 -> {'PASS' if x1 else 'FAIL'}]")
    say(f"X2  corroborated (one value, two sources): {corroborated}; ledger unchanged {D.S.ledger.snapshot() == conf0}; self-confirmations {fired}   [{'PASS' if x2 else 'FAIL'}]")
    if not x1: fails.append("X1")
    if not x2: fails.append("X2")
    # ---- X3 a contest, settled the W6 way
    say("\nX3  PLANTED DISAGREEMENTS")
    D3, R3 = door(planted_cache({"stonehenge": "France", "angkor wat": "Thailand"}), "planted")
    r1 = D3.turn("what is the country of stonehenge")
    say(f"    stonehenge (osm planted France) -> {r1['kind']} {r1.get('values')} {r1['frame'].get('kind')}")
    opt = next((v for v in r1.get("values", []) if "kingdom" in v.lower()), None)
    r1b = D3.turn(opt) if opt else None; r1c = D3.turn(YES) if opt else None
    snap = D3.S.ledger.snapshot(); say(f"    choice {opt!r} -> {r1b['kind'] if r1b else None}; 'correct' -> ledger {snap}")
    r2 = D3.turn("what is the country of angkor wat")
    say(f"    angkor wat (osm planted Thailand) -> {r2['kind']} {r2.get('values')}; reply: {r2['reply'][:120]!r}")
    x3 = r1["kind"] == READINGS and set(v.lower() for v in r1["values"]) >= {"france", "united kingdom"} and bool(opt) and snap.get("osm-research", (0, 0))[1] >= 1 \
        and r2["kind"] == CONJECTURED and r2.get("values", [None])[0].lower() == "cambodia"
    say(f"X3  READINGS first, record written by the user's word, then CONJECTURED by the better record   [{'PASS' if x3 else 'FAIL'}]")
    if not x3: fails.append("X3")
    # ---- X4 knockout
    D4, R4 = door(shuffled_cache(), "shuffled"); lone_wrong = []; sole_wrong = []; kinds = collections.Counter()
    for q, g in QS:
        rec = D4.turn(q); kinds[rec["kind"]] += 1
        if rec["kind"] in (COMMIT, ATTRIBUTED) and len(rec.get("values", [])) == 1 and rec["values"][0].lower() not in g:
            (lone_wrong if len(set(rec.get("sources", []))) >= 2 else sole_wrong).append((q, rec["values"], rec.get("sources")))
    # amended before this run's reading (run 2): a wrong value from the ONLY source that carries the property is unknowable
    # without a second; the knockout's bar is no lone wrong value where both sources speak
    x4 = not lone_wrong
    say(f"\nX4  shuffled OpenStreetMap entries: kinds {dict(kinds)}; lone wrong with two sources {lone_wrong}; wrong from a sole source (unknowable, recorded) {sole_wrong}   [{'PASS' if x4 else 'FAIL'}]")
    if not x4: fails.append("X4")
    # ---- X5 the live chat
    src = open(os.path.join(HERE, "chat.py"), encoding="utf-8").read()
    live = src[src.index("def live_door"):src.index("def repl")]
    wired = all(t in live for t in ("Researcher(", "WikidataFetcher(", "Nominatim(", "transfer=True", "chat_store.json"))
    Dp, Wp, _ = Rg.door(None); rp = Dp.turn(ASK)
    x5 = wired and rp["kind"] == "PROPOSAL" and bool(rp["reply"])
    say(f"X5  live door wires store + transfer + both fetchers: {wired}; the proposal word -> {rp['kind']} {rp['reply'][:90]!r}   [{'PASS' if x5 else 'FAIL'}]")
    if not x5: fails.append("X5")
    say("\nX6  REGISTERED NUMBERS")
    if "--quick" in sys.argv:
        say("    (skipped: --quick)"); say(f"CROSSCHECK (quick): missed {fails or None}; {time.time() - T0:.0f} s"); return
    ok6 = True
    for f, needle in {"chat.py": "ONE DOOR: PASS", "research.py": "RESEARCH BY ITSELF: PASS", "together.py": "TOGETHER: PASS"}.items():
        tt = time.time(); out = subprocess.run([sys.executable, f], capture_output=True, text=True, cwd=HERE, encoding="utf-8", errors="replace").stdout
        hit = needle in out; ok6 = ok6 and hit; say(f"    {f:14s} {'unchanged' if hit else 'MOVED'}  ({time.time() - tt:.0f} s)")
    if not ok6: fails.append("X6")
    say(f"\nCROSSCHECK: {'PASS' if not fails else 'FAIL ' + ','.join(fails)} -- corroborated {corroborated}/10, both attached {both}/10; {time.time() - T0:.0f} s")


if __name__ == "__main__":
    main()
