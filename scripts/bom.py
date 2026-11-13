"""Write a PCBWay-style assembly BOM (CSV) from design.py. Usage: bom.py <out.csv>"""
import csv
import re
import sys

from design import PARTS

THT = ("PinHeader", "JST_XH")  # footprints soldered through-hole; everything else is SMD


def natural(ref):
    return re.sub(r"\d+", lambda m: m.group().zfill(4), ref)


groups = {}
for ref, p in PARTS.items():
    if p["mpn"]:  # parts without an MPN (mounting holes) are not assembled
        groups.setdefault(p["mpn"], []).append(ref)

rows = sorted(groups.items(), key=lambda kv: natural(min(kv[1], key=natural)))
with open(sys.argv[1], "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["Item #", "Designator", "Qty", "Manufacturer", "Mfg Part #", "Description / Value",
                "Package/Footprint", "Type", "LCSC"])
    for i, (mpn, refs) in enumerate(rows, 1):
        refs = sorted(refs, key=natural)
        p = PARTS[refs[0]]
        value = "/".join(dict.fromkeys(PARTS[r]["value"] for r in refs))  # servo headers: OUT1/.../OUT8
        w.writerow([i, ",".join(refs), len(refs), p["mfr"], mpn, value, p["fp"].split(":")[1],
                    "THT" if any(t in p["fp"] for t in THT) else "SMD", p["lcsc"]])
print("BOM:", len(rows), "lines,", sum(len(r) for r in groups.values()), "parts")
