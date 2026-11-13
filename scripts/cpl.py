"""Write the pick-and-place file (run with KiCad's bundled Python). Usage: cpl.py <out.csv>

Same columns as `kicad-cli pcb export pos`, but each part is given at the centre of its body (the F.Fab
outline) rather than at its footprint anchor. The two differ for the JST connectors and the pin headers,
and an assembler reads these columns as the centre of the part.
"""
import csv
import re
import sys
from pathlib import Path

import pcbnew

b = pcbnew.LoadBoard(str(Path(__file__).resolve().parent.parent / "hw" / "fc.kicad_pcb"))
rows = []
for f in b.GetFootprints():
    if f.IsExcludedFromBOM():  # mounting holes
        continue
    box = None
    for g in f.GraphicalItems():
        if g.GetLayer() == pcbnew.F_Fab and g.GetClass() == "PCB_SHAPE":
            r = g.GetBoundingBox()
            if box is None:
                box = pcbnew.BOX2I(r.GetOrigin(), r.GetSize())
            else:
                box.Merge(r)
    c = box.Centre() if box else f.GetPosition()  # no body outline (the IMU): its anchor is its pad centre
    rows.append([f.GetReference(), f.GetValue(), str(f.GetFPID().GetLibItemName()), f"{pcbnew.ToMM(c.x):.4f}",
                 f"{-pcbnew.ToMM(c.y):.4f}", f"{f.GetOrientationDegrees():.1f}", "bottom" if f.IsFlipped() else "top"])
rows.sort(key=lambda r: re.sub(r"\d+", lambda m: m.group().zfill(4), r[0]))
with open(sys.argv[1], "w", newline="") as out:
    w = csv.writer(out, quoting=csv.QUOTE_NONNUMERIC)
    w.writerow(["Ref", "Val", "Package", "PosX", "PosY", "Rot", "Side"])
    w.writerows(rows)
print("CPL:", len(rows), "parts")
