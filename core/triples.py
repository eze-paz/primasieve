"""TRIPLES -- a quoted source over a JSON file {entity: {property: [values]}} with the interface KGWorld expects
(entities / properties / claims / claims_text / label / consulted). A format adapter, like JSON -> Records; it
holds no fact of its own and no name of any language. Ids are the file's own strings; certificates are checked
verbatim against the entity's serialized claims (core.kg.edge_certificate), exactly as for Wikidata."""
import json


class Triples:
    def __init__(self, path, name):
        self.data = json.load(open(path, encoding="utf-8")); self.name = name; self.log = []
        self.props = sorted({p for e in self.data.values() for p in e})
        self.text = {e: json.dumps(cl, sort_keys=True) for e, cl in self.data.items()}

    def entities(self, label):
        self.log.append((self.name, "item", label))
        return [(label, label, "")] if label in self.data else []

    def properties(self, label):
        self.log.append((self.name, "property", label))
        return [(label, label)] if label in self.props else []

    def claims(self, e): return {p: list(v) for p, v in self.data.get(e, {}).items()}

    def claims_text(self, e): return self.text.get(e, "")

    def label(self, x): return x

    def labelled(self, x): return isinstance(x, str) and bool(x)      # its values ARE labels (research_prereg.md: a fetched value feeds the next hop)

    def consulted(self): return list(self.log)
