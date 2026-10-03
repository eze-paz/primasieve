"""OpenStreetMap Nominatim as a FETCHER for core/research.py (crosscheck_prereg.md): a place name -> the top matches with
their address fields as claims (country, state, county, city, type). A second, independent structured source beside
Wikidata, so that fetched claims can be CORROBORATED or CONTESTED (W6, critical_prereg.md) -- never voted. Paced at one
request per second (the service's policy), identified by a user agent, cached in its own file so that a recorded pass can
be replayed offline (offline=True never calls the network)."""
import json, os, ssl, time, urllib.request, urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE_PATH = os.path.join(HERE, "..", "_nldata", "osm_cache.json")
UA = {"User-Agent": "primasieve-research/0.1 (rejection-first research engine; local experiment; contact pagustina@gasn2.com)"}
API = "https://nominatim.openstreetmap.org/search?"
PACE = 1.1
FIELDS = ("country", "state", "county", "city", "town", "village", "region", "island", "continent")


class Nominatim:
    quotes = True
    name = "osm-research"

    def __init__(self, offline=False, cache_path=None, limit=1):      # its own ranking: the top match (the second and third were namesakes)
        self.path = cache_path or CACHE_PATH
        self.cache = json.load(open(self.path, encoding="utf-8")) if os.path.exists(self.path) else {}
        self.offline, self.limit, self.last, self.calls = offline, limit, 0.0, 0
        try:
            import certifi; self.ctx = ssl.create_default_context(cafile=certifi.where())
        except Exception:
            self.ctx = ssl.create_default_context()

    def _get(self, q):
        key = "search:" + q.lower()
        if key in self.cache: return self.cache[key]
        if self.offline: return None
        wait = PACE - (time.time() - self.last)
        if wait > 0: time.sleep(wait)
        self.last = time.time(); self.calls += 1
        url = API + urllib.parse.urlencode(dict(q=q, format="jsonv2", addressdetails=1, limit=self.limit, **{"accept-language": "en"}))
        try:
            txt = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20, context=self.ctx).read().decode("utf-8")
        except Exception:
            return None
        self.cache[key] = txt
        try: json.dump(self.cache, open(self.path, "w", encoding="utf-8"))
        except Exception: pass
        return txt

    def fetch(self, symbol):
        """-> ("graph", {id: {label, aliases, desc, claims}}) or None. Claims are the address fields the match carries."""
        txt = self._get(symbol)
        if not txt: return None
        try: hits = json.loads(txt)
        except Exception: return None
        data = {}
        for h in hits[: self.limit]:
            addr = h.get("address", {}) or {}
            claims = {f: [str(addr[f])] for f in FIELDS if addr.get(f)}
            if h.get("type"): claims["type"] = [str(h["type"])]
            if not claims: continue
            label = str(h.get("name") or h.get("display_name", "").split(",")[0] or symbol)
            data[f"osm:{h.get('osm_type', '')}:{h.get('osm_id', '')}"] = dict(label=label, aliases=[symbol], desc=str(h.get("display_name", "")), claims=claims)
        return ("graph", data) if data else None


if __name__ == "__main__":
    src = Nominatim(offline=False, cache_path=os.path.join(HERE, "..", "_nldata", "osm_probe.json"))
    print(str(src.fetch("uluru")).encode("ascii", "replace").decode())
