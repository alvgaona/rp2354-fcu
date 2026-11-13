"""Layout checks that KiCad's DRC cannot make (run by scripts/build.sh with KiCad's Python, which has pcbnew).

DRC passes a board whose ground is a chain of thin tracks, or whose pour hangs together by a hair.
These are the things the rev 0.1.0 review found by hand.
"""
import math
import sys
from pathlib import Path

import pcbnew

MAX_GND_VIA_MM = 2.0  # every SMD ground pad needs a via (or through-hole ground pad) this close
b = pcbnew.LoadBoard(str(Path(__file__).resolve().parent.parent / "hw" / "fc.kicad_pcb"))
mm, MM = pcbnew.FromMM, pcbnew.ToMM
fail = []


def dist(a, c):
    return math.hypot(MM(a.x - c.x), MM(a.y - c.y))


def name(v):
    return f"({MM(v.x) - 100:.1f}, {MM(v.y) - 100:.1f})"


vias = [t for t in b.GetTracks() if t.Type() == pcbnew.PCB_VIA_T]
pads = [(f.GetReference(), p) for f in b.GetFootprints() for p in f.Pads()]

# 1. ground pads sit next to a via into the bottom pour
anchors = [v.GetPosition() for v in vias if v.GetNetname() == "GND"]
anchors += [p.GetPosition() for _, p in pads if p.GetNetname() == "GND" and p.HasHole()]
worst = max(((min(dist(p.GetPosition(), a) for a in anchors), f"{r}.{p.GetNumber()}")
             for r, p in pads if p.GetNetname() == "GND" and not p.HasHole()))
print(f"ground: {sum(v.GetNetname() == 'GND' for v in vias)} vias, farthest pad from one: {worst[1]} at {worst[0]:.2f} mm")
if worst[0] > MAX_GND_VIA_MM:
    fail.append(f"{worst[1]} is {worst[0]:.2f} mm from the nearest ground via")
gnd_len = sum(MM(t.GetLength()) for t in b.GetTracks() if t.Type() != pcbnew.PCB_VIA_T and t.GetNetname() == "GND"
              and MM(t.GetWidth()) < 1)
print(f"ground: {gnd_len:.0f} mm of track in total (stubs to vias; the servo ground bar is not counted)")


# 2. pours: one piece, and how much survives if every neck under `neck` mm is cut
def pour(net, layer, neck):
    z = next(z for z in b.Zones() if z.GetNetname() == net and z.GetAssignedPriority() == 0 and not z.GetIsRuleArea())
    full = z.GetFilledPolysList(layer)
    cut = pcbnew.SHAPE_POLY_SET(full)
    cut.Unfracture()  # KiCad stores holes as zero-width slits to the outline; shrinking would open those up
    cut.Deflate(mm(neck / 2), pcbnew.CORNER_STRATEGY_ROUND_ALL_CORNERS, mm(0.01))
    areas = sorted((pcbnew.SHAPE_POLY_SET(cut.UnitSet(i)).Area() for i in range(cut.OutlineCount())), reverse=True)
    print(f"{net} pour: {full.OutlineCount()} piece(s), {full.Area() / 1e12:.0f} mm2; "
          f"largest solid part ignoring necks under {neck} mm: {areas[0] / 1e12:.0f} mm2")
    return full, cut


def areas_ratio(full, cut):
    return max(pcbnew.SHAPE_POLY_SET(cut.UnitSet(i)).Area() for i in range(cut.OutlineCount())) / full.Area()


full, cut = pour("GND", pcbnew.B_Cu, 0.5)
if full.OutlineCount() != 1:
    fail.append(f"ground pour is in {full.OutlineCount()} pieces")
main = max(range(cut.OutlineCount()), key=lambda i: pcbnew.SHAPE_POLY_SET(cut.UnitSet(i)).Area())
weak = [name(v.GetPosition()) for v in vias if v.GetNetname() == "GND" and not cut.Contains(v.GetPosition(), main)]
print(f"ground vias reaching the main ground area only through a neck under 0.5 mm: {len(weak)} {weak}")
if areas_ratio(full, cut) < 0.8:
    fail.append("less than 80 % of the ground pour is solid once necks under 0.5 mm are cut")
full, _ = pour("+3V3", pcbnew.F_Cu, 0.3)
biggest = max(range(full.OutlineCount()), key=lambda i: pcbnew.SHAPE_POLY_SET(full.UnitSet(i)).Area())
small = [z for z in b.Zones() if z.GetNetname() == "+3V3" and z.GetAssignedPriority() > 0]  # copied with the MCU core
out = sorted(f"{r}.{p.GetNumber()}" for r, p in pads
             if p.GetNetname() == "+3V3" and p.IsOnLayer(pcbnew.F_Cu) and not full.Contains(p.GetPosition(), biggest)
             and not any(z.HitTestFilledArea(pcbnew.F_Cu, p.GetPosition()) for z in small))
print(f"+3V3 pads fed by a track only, not by a pour: {out}")
if out:
    fail.append(f"+3V3 pads outside every 3V3 pour: {out}")

# 3. nothing drilled under the IMU
imu = b.FindFootprintByReference("U3")
box = pcbnew.BOX2I()
for p in imu.Pads():
    box.Merge(p.GetBoundingBox())
under = [f"{v.GetNetname()} {name(v.GetPosition())}" for v in vias if box.Contains(v.GetPosition())]
print(f"vias under the IMU: {len(under)} {under}")
if under:
    fail.append(f"via under the IMU: {under}")

if fail:
    sys.exit("LAYOUT CHECK FAILED: " + "; ".join(fail))
print("layout check: ok")
