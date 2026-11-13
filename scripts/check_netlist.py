"""Fail if KiCad's exported netlist differs from design.py (catches label placement mistakes)."""
import sys
import xml.etree.ElementTree as ET

from design import nets

got = {}
for n in ET.parse(sys.argv[1]).getroot().find("nets"):
    conns = {(x.get("ref"), x.get("pin")) for x in n}
    if not n.get("name").startswith("unconnected"):
        got[n.get("name").lstrip("/")] = conns
want = {k: set(v) for k, v in nets().items()}
bad = [k for k in set(got) | set(want) if got.get(k) != want.get(k)]
for k in sorted(bad):
    print("MISMATCH", k, sorted(got.get(k, [])), sorted(want.get(k, [])))
print(f"netlist check: {len(want)} nets, {len(bad)} mismatches")
sys.exit(1 if bad else 0)
