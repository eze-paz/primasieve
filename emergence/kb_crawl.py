"""WIKIDATA CRAWL -- a larger, compact, offline store of entities for the gloss-reading experiments (gloss_scale_prereg.md).
Never imported by core/. Same public interface as kb_wikidata.Wikidata so core.kg's KGWorld can run over it.

Why a second store: the main cache (`_nldata/wikidata_cache.json`) is one JSON file loaded whole by every gate; it holds
the raw API text of ~5,600 entities at ~190 MB. The crawl keeps only what the readers need -- English label, item-valued
claims, and (new) time- and quantity-valued claims -- in sqlite, so 50,000+ entities cost ~150 MB and load nothing up
front. Values: "Q123" (item), "T:1949" (time, year), "N:67" (quantity, amount). The claims text stored per entity is the
compact JSON, which is what core.verdict.attribute checks a certificate span against.

    python emergence/kb_crawl.py --crawl [--minutes 75]     # ring 1: full entries for every id the main cache mentions;
                                                           # ring 2: labels for the objects those entries mention
"""
import os, sys, json, time, sqlite3, collections, urllib.request, urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from kb_wikidata import Wikidata, CACHE_PATH, API, UA

DB = os.path.join(HERE, "..", "_nldata", "wikidata_crawl.sqlite")


def say(s=""): print(str(s).encode("ascii", "replace").decode(), flush=True)


def _compact(ent):
    """raw API entity -> (label, {pid: [value]}) keeping items, times (year) and quantities (amount)"""
    lab = ent.get("labels", {}).get("en", {}).get("value")
    out = {}
    for pid, sts in ent.get("claims", {}).items():
        pref = [st for st in sts if st.get("rank") == "preferred"]
        use = pref or [st for st in sts if st.get("rank") != "deprecated"]
        vals = []
        for st in use:
            dv = st.get("mainsnak", {}).get("datavalue", {})
            t = dv.get("type"); v = dv.get("value")
            if t == "wikibase-entityid": vals.append(v["id"])
            elif t == "time":
                try: vals.append("T:" + str(int(v["time"][:5].replace("+", ""))))
                except Exception: pass
            elif t == "quantity":
                try:
                    a = float(v["amount"]); vals.append("N:" + (str(int(a)) if a == int(a) else str(a)))
                except Exception: pass
        if vals: out[pid] = vals
    return lab, out


class Crawl:
    def __init__(self, path=DB):
        self.path = path; self.db = sqlite3.connect(path)
        self.db.execute("create table if not exists ent (q text primary key, label text, claims text)")
        self.db.execute("create table if not exists lab (q text primary key, label text)")
        self.db.execute("create index if not exists lab_l on lab (lower(label))")
        self.db.execute("create index if not exists ent_l on ent (lower(label))")
        self.log = []; self._memo = {}; self.ctx = Wikidata(offline=True).ctx

    # ---- the source interface (core.kg) --------------------------------------------------------------------------
    def entities(self, label):
        rows = self.db.execute("select q, label from ent where lower(label)=? limit 8", (label.lower(),)).fetchall()
        self.log.append(("item", label))
        return [(q, l, "") for q, l in rows]

    def properties(self, label):
        rows = self.db.execute("select q, label from lab where lower(label)=? and q like 'P%' limit 8", (label.lower(),)).fetchall()
        self.log.append(("property", label))
        return [(q, l) for q, l in rows]

    def claims(self, q):
        """item-valued claims only, as core.kg expects"""
        if q not in self._memo:
            row = self.db.execute("select claims from ent where q=?", (q,)).fetchone()
            d = json.loads(row[0]) if row else {}
            self._memo[q] = {p: [v for v in vs if v.startswith("Q")] for p, vs in d.items() if any(v.startswith("Q") for v in vs)}
        return {p: list(v) for p, v in self._memo[q].items()}

    def allclaims(self, q):
        """every stored value: items, T:year, N:amount (the readers' extension)"""
        row = self.db.execute("select claims from ent where q=?", (q,)).fetchone()
        return json.loads(row[0]) if row else {}

    def claims_text(self, q):
        row = self.db.execute("select claims from ent where q=?", (q,)).fetchone()
        return row[0] if row else ""

    def label(self, x):
        row = self.db.execute("select label from lab where q=?", (x,)).fetchone()
        if row and row[0]: return row[0]
        row = self.db.execute("select label from ent where q=?", (x,)).fetchone()
        return row[0] if row and row[0] else x

    def has(self, q): return self.db.execute("select 1 from ent where q=?", (q,)).fetchone() is not None

    def consulted(self): return list(self.log)

    def count(self): return self.db.execute("select count(*) from ent").fetchone()[0], self.db.execute("select count(*) from lab").fetchone()[0]

    # ---- fetching -----------------------------------------------------------------------------------------------
    def _get(self, params):
        url = API + urllib.parse.urlencode(dict(params, format="json"))
        return json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60, context=self.ctx).read().decode("utf-8"))

    def fetch_entities(self, ids, pace=0.5, deadline=None, batch=50):
        n = 0
        for i in range(0, len(ids), batch):
            if deadline and time.time() > deadline: say("    (time cap reached)"); break
            chunk = ids[i:i + batch]
            try: d = self._get(dict(action="wbgetentities", ids="|".join(chunk), props="claims|labels", languages="en"))
            except Exception as e:
                say(f"    batch failed: {e!r}"); time.sleep(3); continue
            rows = []
            for q, ent in d.get("entities", {}).items():
                if "missing" in ent: continue
                lab, cl = _compact(ent); rows.append((q, lab, json.dumps(cl, separators=(",", ":"))))
            self.db.executemany("insert or replace into ent values (?,?,?)", rows)
            self.db.executemany("insert or replace into lab values (?,?)", [(q, l) for q, l, _ in rows if l])
            n += len(rows)
            if (i // batch) % 100 == 0: self.db.commit(); say(f"    ... {i + len(chunk)}/{len(ids)} entities ({n} stored)")
            time.sleep(pace)
        self.db.commit(); return n

    def fetch_labels(self, ids, pace=0.3, deadline=None, batch=50):
        n = 0
        for i in range(0, len(ids), batch):
            if deadline and time.time() > deadline: say("    (time cap reached)"); break
            chunk = ids[i:i + batch]
            try: d = self._get(dict(action="wbgetentities", ids="|".join(chunk), props="labels", languages="en"))
            except Exception as e:
                say(f"    batch failed: {e!r}"); time.sleep(3); continue
            rows = [(q, ent.get("labels", {}).get("en", {}).get("value")) for q, ent in d.get("entities", {}).items() if "missing" not in ent]
            self.db.executemany("insert or replace into lab values (?,?)", [(q, l) for q, l in rows if l]); n += len(rows)
            if (i // batch) % 200 == 0: self.db.commit(); say(f"    ... {i + len(chunk)}/{len(ids)} labels")
            time.sleep(pace)
        self.db.commit(); return n


def crawl(minutes=75):
    t0 = time.time(); deadline = t0 + minutes * 60
    C = Crawl(); cache = json.load(open(CACHE_PATH, encoding="utf-8"))
    # seed labels from the main cache (entities and properties alike)
    C.db.executemany("insert or ignore into lab values (?,?)", [(k.split(":", 1)[1], v) for k, v in cache.items() if k.startswith("label:") and v and v != k.split(":", 1)[1]])
    ring1 = set()
    for k, txt in cache.items():
        if not k.startswith("entity:"): continue
        q = k.split(":", 1)[1]; ring1.add(q)
        try: ent = json.loads(txt)["entities"][q]
        except Exception: continue
        for pid, sts in ent.get("claims", {}).items():
            ring1.add(pid)
            for st in sts:
                dv = st.get("mainsnak", {}).get("datavalue", {})
                if dv.get("type") == "wikibase-entityid": ring1.add(dv["value"]["id"])
    todo = sorted(q for q in ring1 if not C.has(q))
    say(f"  ring 1: {len(ring1)} ids, {len(todo)} to fetch as full entries"); n1 = C.fetch_entities(todo, deadline=t0 + minutes * 60 * 0.7)
    # ring 2: labels for what ring 1 mentions, most mentioned first
    cnt = collections.Counter()
    for (cl,) in C.db.execute("select claims from ent"):
        for p, vs in json.loads(cl).items():
            cnt[p] += 1
            for v in vs:
                if v.startswith("Q"): cnt[v] += 1
    have = {q for (q,) in C.db.execute("select q from lab")}
    todo2 = [q for q, _ in cnt.most_common() if q not in have]
    say(f"  ring 2: {len(cnt)} mentioned ids, {len(todo2)} without a label; fetching most-mentioned first"); n2 = C.fetch_labels(todo2, deadline=deadline)
    e, l = C.count(); say(f"  crawl done in {time.time() - t0:.0f} s: {e} entities, {l} labels (ring 1 stored {n1}, ring 2 labels {n2})")


if __name__ == "__main__":
    a = sys.argv
    if "--crawl" in a:
        crawl(int(a[a.index("--minutes") + 1]) if "--minutes" in a else 75)
    else:
        C = Crawl(); say(f"crawl store: {C.count()} (entities, labels)")
