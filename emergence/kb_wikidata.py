"""WIKIDATA SOURCE for core.kg -- live public API, paced, cached on disk. The core never imports this; a runner
injects an instance. Every claim it returns carries the verbatim JSON text of the entity's claims as source_text,
so core.verdict.attribute can check a certificate span against it.

Interface (what core.kg expects of a source):
    entities(label)   -> [(id, label, description)]  exact label/alias matches, case-insensitive, <= 5
    properties(label) -> [(id, label)]                exact label/alias matches
    claims(qid)       -> {pid: [value_qid, ...]}      item-valued claims only (this experiment reasons over items)
    label(id)         -> str
    claims_text(qid)  -> str                          the fetched claims JSON, verbatim (certificate source text)
    consulted()       -> list of (kind, key) looked up so far (for the NOT FOUND report)"""
import json, os, ssl, time, urllib.request, urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE_PATH = os.path.join(HERE, "..", "_nldata", "wikidata_cache.json")
UA = {"User-Agent": "primasieve-kg/0.1 (rejection-first research engine; local experiment; contact pagustina@gasn2.com)"}
PACE = 0.15
API = "https://www.wikidata.org/w/api.php?"


class Wikidata:
    def __init__(self, offline=False, cache_path=None):
        """cache_path: where LIVE results are saved. The default is the shared offline fixture the gates read; a live
        chat passes its own file (chat.py --online) so that what a user happens to ask -- and what the graph is asked
        about the dictionary text in that session's context -- never changes the fixture the registered claims rest on
        (2026-10-02: an online session wrote the alias of P31 for the span "is a" into the fixture and W5-c moved)."""
        self.path = cache_path or CACHE_PATH
        base = json.load(open(CACHE_PATH, encoding="utf-8")) if os.path.exists(CACHE_PATH) else {}
        if cache_path and os.path.exists(cache_path):
            base.update(json.load(open(cache_path, encoding="utf-8")))
        self.cache = base
        self.offline = offline
        self.last = 0.0
        self.log = []
        try:
            import certifi; self.ctx = ssl.create_default_context(cafile=certifi.where())
        except Exception:
            self.ctx = ssl.create_default_context()
        self.calls = 0

    def _get(self, key, params):
        if key in self.cache: return self.cache[key]
        if self.offline: return None
        wait = PACE - (time.time() - self.last)
        if wait > 0: time.sleep(wait)
        self.last = time.time(); self.calls += 1
        url = API + urllib.parse.urlencode(dict(params, format="json"))
        try:
            txt = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20, context=self.ctx).read().decode("utf-8")
        except Exception as e:
            return None
        self.cache[key] = txt
        if self.calls % 10 == 0: self.save()
        return txt

    def save(self):
        try: json.dump(self.cache, open(self.path, "w", encoding="utf-8"))
        except Exception: pass

    def _search(self, label, typ):
        key = f"search:{typ}:{label.lower()}"
        txt = self._get(key, dict(action="wbsearchentities", search=label, language="en", type=typ, limit=20))
        self.log.append((typ, label))
        if txt is None: return []
        out = []
        for x in json.loads(txt).get("search", []):
            names = [x.get("label", "")] + list(x.get("aliases", []) or [])
            if any(n.lower() == label.lower() for n in names):
                out.append((x["id"], x.get("label", ""), x.get("description", "")))
        return out[:8]

    def entities(self, label): return self._search(label, "item")

    def properties(self, label): return self._search(label, "property")

    def _entity(self, qid):
        key = f"entity:{qid}"
        txt = self._get(key, dict(action="wbgetentities", ids=qid, props="claims|labels|descriptions", languages="en"))
        return txt

    def claims_text(self, qid):
        return self._entity(qid) or ""

    def claims(self, qid):
        """parsed once per entity: the profile of worlds_general.py showed 163k re-parses of the same cached JSON
        (304 of 424 s) under the two-hop path search; the memo is exact (the cache text never changes in a run)."""
        memo = self.__dict__.setdefault("_claims", {})
        if qid in memo: return {p: list(v) for p, v in memo[qid].items()}
        out = self._claims_parse(qid); memo[qid] = out
        return {p: list(v) for p, v in out.items()}

    def _claims_parse(self, qid):
        txt = self._entity(qid)
        if txt is None: return {}
        ent = json.loads(txt).get("entities", {}).get(qid, {})
        out = {}
        for pid, sts in ent.get("claims", {}).items():
            pref = [st for st in sts if st.get("rank") == "preferred"]       # A10: statement rank is a field, not a word
            use = pref or [st for st in sts if st.get("rank") != "deprecated"]
            vals = []
            for st in use:
                dv = st.get("mainsnak", {}).get("datavalue", {})
                if dv.get("type") == "wikibase-entityid":
                    vals.append(dv["value"]["id"])
            if vals: out[pid] = vals
        return out

    def label(self, xid):
        key = f"label:{xid}"
        if key in self.cache: return self.cache[key]
        txt = self._get(f"labels:{xid}", dict(action="wbgetentities", ids=xid, props="labels", languages="en"))
        if txt is None: return xid
        lab = json.loads(txt).get("entities", {}).get(xid, {}).get("labels", {}).get("en", {}).get("value", xid)
        self.cache[key] = lab
        return lab

    def description(self, qid):
        txt = self._entity(qid)
        if txt is None: return ""
        return json.loads(txt).get("entities", {}).get(qid, {}).get("descriptions", {}).get("en", {}).get("value", "")

    def consulted(self): return list(self.log)
