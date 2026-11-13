"""Summarise a kicad-cli DRC JSON report."""
import collections
import json
import sys

d = json.load(open(sys.argv[1]))
print("DRC:", dict(collections.Counter(f'{v["severity"]}:{v["type"]}' for v in d["violations"])))
for v in d["violations"]:
    print("  ", v["severity"], v["type"], [i["description"] for i in v["items"]])
for u in d["unconnected_items"]:
    print("  UNCONNECTED", [i["description"] for i in u["items"]])
for p in d.get("schematic_parity", []):
    print("  PARITY", p["type"], [i["description"] for i in p["items"]])
print(f'{len(d["violations"])} violations, {len(d["unconnected_items"])} unconnected, {len(d.get("schematic_parity", []))} parity issues')
