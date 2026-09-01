"""Validate the expressibility checker: the 10 confident reach:token/expr instances SHOULD be
reproduced by the grammar. If they come back 0 too, the checker is broken (not the grammar)."""
import json
import swebench_express as e
rows=json.load(open("swebench_reach.json"))
conf=[r for r in rows if r["reach"].startswith("reach")]
ok=0
for r in conf:
    olc=e.one_line_change(r["patch"])
    if not olc:
        print(f"{r['iid']:34s} {r['reach']:13s} -> multi-line (insertm, skip)"); continue
    yes,why=e.expressible(olc[0],olc[1],e.harvest_names(r["patch"]))
    ok+=yes
    print(f"{r['iid']:34s} {r['reach']:13s} -> {yes}  {why}")
print(f"\nCHECKER SELF-TEST: {ok}/{sum(1 for r in conf if e.one_line_change(r['patch']))} single-line confident instances reproduced by grammar")
