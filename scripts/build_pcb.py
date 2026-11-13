"""Build hw/fc.kicad_pcb (run with KiCad's bundled Python).

  place  : footprints, nets, transplanted RP2350 layout, outline, rules -> fc.kicad_pcb + fc.dsn
  finish : import Freerouting session, GND pours, silkscreen -> fc.kicad_pcb
"""
import math
import os
import sys
from pathlib import Path

import pcbnew

sys.path.insert(0, str(Path(__file__).parent))
from design import PARTS, REV  # noqa: E402
from gen_sch import uid  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
HW = ROOT / "hw"
PCB = HW / "fc.kicad_pcb"
PLACED = ROOT / "build" / "placed.kicad_pcb"  # pre-route snapshot so routing can be retried
REF = Path(sys.argv[2]) if len(sys.argv) > 2 else None  # Raspberry Pi minimal design .kicad_pcb
KSHARE = Path("/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints")
IO = pcbnew.PCB_IO_KICAD_SEXPR()

OX, OY, W, H = 100.0, 100.0, 40.0, 40.0  # board origin and size (mm)
U1_AT = (20.0, 17.0)  # RP2354A centre, board-relative

# Parts copied with the reference layout (relative to U1, same orientation).
CLUSTER = ["U1", "L1", "C6", "C7", "C9", "R3", "C8", "C10", "C11", "C12", "C13", "C14", "C15", "C16", "C17",
           "C18", "C3", "C4", "R2", "X1", "R7", "R8"]
# Reference nets whose cluster-internal copper we keep -> our net names.
REF_NETS = {"+1V1": "+1V1", "+3V3": "+3V3", "GND": "GND", "/VREG_AVDD": "VREG_AVDD", "/VREG_LX": "VREG_LX",
            "/XIN": "XIN", "/XOUT": "XOUT", "Net-(C4-Pad1)": "XTAL_OUT",
            "Net-(U1-USB_DM)": "USB_DM_MCU", "Net-(U1-USB_DP)": "USB_DP_MCU"}
KEEP_BOX = (-9.5, 9.5, -9.0, 14.5)  # dx0, dx1, dy0, dy1 around U1 for copied tracks
REF_DROP = [(17.9, 8.4)]  # reference copper not copied (board coords): C12's ground via, which is under J1's pads here

# Board-relative placement (x, y, rotation deg) for everything else.
PLACE = {
    # top edge: USB-C, VBUS diode, buttons
    # J1's data pads sit right above the series resistors R7/R8 (usb_copper); CC resistors beside their pads
    "J1": (19.1, 3.4, 180), "R5": (15.9, 9.6, 270), "R1": (25.6, 8.4, 0), "D2": (25.8, 5.0, 90),
    "SW1": (29.0, 3.0, 90), "R6": (29.0, 6.6, 0),
    # right side: battery in, power, battery sense, LED, IMU
    # Buck: power flows east -> west. C1 sits right across U2's VIN/GND pins, the inductor and output
    # caps sit next to the MCU's 3V3 pads. The critical copper is pre-routed in power_copper().
    "J6": (36.6, 12.0, 270), "D1": (31.0, 11.8, 90), "C1": (34.2, 18.5, 180),
    "U2": (34.2, 21.2, 180), "C2": (31.6, 21.675, 90),  # C2 pads line up with the SW/BST pins
    "L2": (29.25, 21.2, 180),
    "C5": (30.6, 17.9, 0), "C19": (29.9, 24.1, 0),  # output caps: one each side of the inductor's 3V3 pad
    "R9": (29.2, 10.8, 90), "R10": (29.2, 13.4, 90), "C20": (29.2, 15.8, 90),
    "D3": (30.4, 8.4, 0), "R19": (27.6, 8.4, 0),
    # IMU sits north-east of the SWD tracks (swd_copper), so its SPI lines reach it without crossing them
    # and 2.5 mm clear of C16: three of its lines must hop to the bottom layer there and need room for vias
    "U3": (25.8, 24.7, 0), "C21": (27.5, 26.7, 180), "C22": (29.4, 26.7, 0), "C23": (24.6, 27.15, 270),
    # left side: GPS, PWM series resistors (SWD sits bottom-right, away from the PWM fan-out)
    "J5": (3.0, 13.3, 270), "J4": (35.8, 28.3, 90),
    # MCU-side pad faces the MCU; outputs leave west (pwm_copper). 6-8 step east: one via column each.
    **{f"R{10 + i}": (8.9 if i < 6 else 9.5 + 0.6 * (i - 6), 16.5 + 1.5 * (i - 1), 180) for i in range(1, 9)},
    # bottom: 8x servo/ESC headers (signal row nearest the MCU, GND row at the edge)
    **{f"J{6 + i}": (20.0 + (i - 4.5) * 2.54, 32.92, 0) for i in range(1, 9)},
    "H1": (4.75, 4.75, 0), "H2": (35.25, 4.75, 0), "H3": (4.75, 35.25, 0), "H4": (35.25, 35.25, 0),
}
HOLES = [PLACE[h][:2] for h in ("H1", "H2", "H3", "H4")]
HOLE_KEEPOUT = 3.2  # mm radius without copper: an M3 screw head is 5.5-6 mm across
VIA_D = 0.6


def mm(v):
    return pcbnew.FromMM(v)


def pt(x, y):
    return pcbnew.VECTOR2I(mm(OX + x), mm(OY + y))


def load_fp(fpid):
    lib, name = fpid.split(":")
    path = HW / "lib" / f"{lib}.pretty" if lib in ("rpi", "easyeda", "fc") else KSHARE / f"{lib}.pretty"
    fp = IO.FootprintLoad(str(path), name)
    if fp is None:
        sys.exit(f"footprint not found: {fpid}")
    fp.SetFPID(pcbnew.LIB_ID(lib, name))
    return fp


def rules(b):
    ds = b.GetDesignSettings()
    ds.SetCopperLayerCount(2)
    ds.m_TrackMinWidth = mm(0.1)  # PCBWay 2-layer min; router necks down to 0.12 mm at QFN pins
    ds.m_MinClearance = mm(0.1)  # reference layout relies on 0.125 mm pad overrides
    ds.m_ViasMinSize = mm(0.6)
    ds.m_MinThroughDrill = mm(0.25)  # reference vias are 0.6/0.25; PCBWay standard min drill is 0.2
    ds.m_HoleToHoleMin = mm(0.25)
    ds.m_CopperEdgeClearance = mm(0.3)
    ds.m_ViasMinAnnularWidth = mm(0.13)
    nc = ds.m_NetSettings.GetDefaultNetclass()
    nc.SetClearance(mm(0.15))
    nc.SetTrackWidth(mm(0.15))  # same as the Raspberry Pi reference; needed to escape the 0.4 mm QFN
    nc.SetViaDiameter(mm(0.6))
    nc.SetViaDrill(mm(0.3))
    pwr = pcbnew.NETCLASS("Power")
    pwr.SetClearance(mm(0.15))
    pwr.SetTrackWidth(mm(0.4))
    pwr.SetViaDiameter(mm(0.6))
    pwr.SetViaDrill(mm(0.3))  # one via size for all nets: Freerouting mixed up padstacks
    ds.m_NetSettings.SetNetclass("Power", pwr)
    for n in ("VBAT", "VIN", "SW_BUCK"):
        ds.m_NetSettings.SetNetclassPatternAssignment(n, "Power")
    # USB-C CC pins sit between 0.3 mm pads at 0.5 mm pitch; without a 0.1/0.1 class the router leaves one net open
    fine = pcbnew.NETCLASS("Fine")
    fine.SetClearance(mm(0.1))
    fine.SetTrackWidth(mm(0.1))
    fine.SetViaDiameter(mm(0.6))
    fine.SetViaDrill(mm(0.3))
    ds.m_NetSettings.SetNetclass("Fine", fine)
    for n in ("CC1", "CC2"):
        ds.m_NetSettings.SetNetclassPatternAssignment(n, "Fine")
    # GND gets its own class only so the router can skip it (-inc GND): gnd_vias() ties every pad to the pour
    gnd = pcbnew.NETCLASS("GND")
    gnd.SetClearance(mm(0.15))
    gnd.SetTrackWidth(mm(0.15))
    gnd.SetViaDiameter(mm(0.6))
    gnd.SetViaDrill(mm(0.3))
    ds.m_NetSettings.SetNetclass("GND", gnd)
    ds.m_NetSettings.SetNetclassPatternAssignment("GND", "GND")


def xy(v):
    return pcbnew.ToMM(v.x) - OX, pcbnew.ToMM(v.y) - OY


def track(b, net, pts, w, layer=pcbnew.F_Cu):
    for a, c in zip(pts, pts[1:]):
        t = pcbnew.PCB_TRACK(b)
        t.SetStart(pt(*a))
        t.SetEnd(pt(*c))
        t.SetWidth(mm(w))
        t.SetLayer(layer)
        t.SetNet(b.FindNet(net))
        t.SetLocked(True)
        b.Add(t)


def via(b, net, x, y):
    v = pcbnew.PCB_VIA(b)
    v.SetPosition(pt(x, y))
    v.SetWidth(mm(VIA_D))
    v.SetDrill(mm(0.3))
    v.SetNet(b.FindNet(net))
    v.SetLocked(True)
    b.Add(v)


def power_copper(b):
    """Hand-routed buck converter copper (locked): short, wide and on one layer."""
    def p(refdes, num):
        return xy(next(q for q in b.FindFootprintByReference(refdes).Pads() if q.GetNumber() == num).GetPosition())

    vin, gnd, sw, bst, out, fb = p("U2", "3"), p("U2", "4"), p("U2", "5"), p("U2", "6"), p("L2", "2"), p("U2", "1")
    track(b, "VIN", [p("C1", "1"), vin, p("U2", "2")], 0.5)  # input cap -> VIN -> EN
    track(b, "GND", [p("C1", "2"), gnd], 0.5)
    via(b, "GND", (p("C1", "2")[0] + gnd[0]) / 2, (p("C1", "2")[1] + gnd[1]) / 2 + 0.2)  # in the hot loop
    track(b, "GND", [p("C1", "2"), (p("C1", "2")[0] - 1.1, p("C1", "2")[1])], 0.5)
    via(b, "GND", p("C1", "2")[0] - 1.1, p("C1", "2")[1])
    track(b, "SW_BUCK", [sw, p("C2", "2"), p("L2", "1")], 0.5)
    track(b, "BST", [bst, p("C2", "1")], 0.3)
    c5, c19, yn = p("C5", "1"), p("C19", "1"), out[1] - 1.9
    track(b, "+3V3", [out, c19], 0.5)
    track(b, "+3V3", [out, (out[0], yn), (c5[0], yn), c5], 0.5)
    mcu = p("C14", "1")  # trunk to the MCU's 3V3 pads, so the supply does not depend on how the pour fills
    track(b, "+3V3", [(out[0], yn), (mcu[0], yn), mcu], 0.4)
    y = (p("L2", "1")[1] + 1.35 + p("C19", "2")[1] - 0.725) / 2  # midway between the SW pad and C19's GND pad
    track(b, "+3V3", [fb, (fb[0], y - 0.36), (fb[0] - 0.36, y), (c19[0] + 0.3, y), c19], 0.2)  # output sense


def pwm_copper(b):
    """Servo outputs, nested so they never cross: west out of the series resistors, down the board edge
    and along the header row. 1-5 run on the top layer. 6-8 cannot get past the crystal on top, so they
    drop to the bottom as one tight bundle. Left to the autorouter the outputs spread over the bottom
    layer and cut ground vias off from the pour."""
    def p(refdes, num):
        return xy(next(q for q in b.FindFootprintByReference(refdes).Pads() if q.GetNumber() == num).GetPosition())

    for i in range(1, 6):
        (rx, ry), (hx, hy) = p(f"R{10 + i}", "2"), p(f"J{6 + i}", "1")
        col, row = 6.0 + 0.4 * (i - 1), 32.1 - 0.4 * (i - 1)
        pts = [(rx, ry), (col + 0.4, ry), (col, ry + 0.4), (col, row - 0.4), (col + 0.4, row)]
        if i == 5:  # step down to clear the crystal pads once output 4 has dropped to its pin
            pts += [(17.0, row), (17.7, row + 0.7)]
            row += 0.7
        track(b, f"PWM{i}", pts + [(hx - (hy - row), row), (hx, hy)], 0.2)
    for i in range(6, 9):
        (rx, ry), (hx, hy) = p(f"R{10 + i}", "2"), p(f"J{6 + i}", "1")
        vx, row = rx - 0.72, 31.7 - 0.4 * (i - 6)
        track(b, f"PWM{i}", [(rx, ry), (vx, ry)], 0.2)
        via(b, f"PWM{i}", vx, ry)
        track(b, f"PWM{i}", [(vx, ry), (vx, row - 0.4), (vx + 0.4, row), (hx - (hy - row), row), (hx, hy)], 0.2, pcbnew.B_Cu)


def usb_copper(b):
    """USB data pair on the top layer, about 2 mm per line and no vias. Each signal has two pads (the plug
    fits either way round): both D+ pads drop onto R7, and the D- pads are joined behind the pad row."""
    def p(refdes, num):
        return xy(next(q for q in b.FindFootprintByReference(refdes).Pads() if q.GetNumber() == num).GetPosition())

    a6, b6, a7, b7, r7, r8 = p("J1", "A6"), p("J1", "B6"), p("J1", "A7"), p("J1", "B7"), p("R7", "1"), p("R8", "1")
    for pad in (a6, b6):
        track(b, "USB_D+", [pad, (pad[0], 8.4), r7], 0.15)
    track(b, "USB_D-", [b7, (b7[0], 8.4), r8], 0.15)
    track(b, "USB_D-", [a7, (a7[0], 6.35), (b7[0], 6.35), b7], 0.15)


def imu_copper(b):
    """IMU supply links: VDDIO and VDD to their capacitors, and on to the regulator's output capacitor.
    The autorouter squeezed these past the IMU's ground via a few microns under the clearance."""
    def p(refdes, num):
        return xy(next(q for q in b.FindFootprintByReference(refdes).Pads() if q.GetNumber() == num).GetPosition())

    vddio, vdd, c23, c21, c22, c19 = p("U3", "5"), p("U3", "8"), p("C23", "1"), p("C21", "1"), p("C22", "1"), p("C19", "1")
    y = c23[1] + 0.38  # passes below the ground via of pins 6/7, then dips under C21's ground pad
    track(b, "+3V3", [vddio, (vddio[0], vddio[1] + 0.4), c23, (c23[0] + 0.38, y), (c21[0] - 1.68, y),
                      (c21[0] - 1.43, y + 0.25), (c21[0] - 0.28, y + 0.25), c21], 0.15)
    track(b, "+3V3", [vdd, (vdd[0] + 0.44, vdd[1]), (c21[0], vdd[1] + 0.48), c21], 0.15)
    track(b, "+3V3", [c21, c22, c19], 0.3)


def swd_copper(b):
    """SWD on the top layer, first leg as in the Raspberry Pi layout. Left to the autorouter the two
    lines went to the bottom, split around the IMU and cut its ground off from the rest of the pour."""
    def p(num):
        return xy(next(q for q in b.FindFootprintByReference("U1").Pads() if q.GetNumber() == num).GetPosition())

    (cx, cy), (dx, dy) = p("24"), p("25")
    # the pair stays west of x = 23.1 beside the IMU (room for its INT1 track), then jogs east past C4's via
    track(b, "SWDIO", [(dx, dy), (dx, 21.7), (23.0, 23.9), (23.0, 24.75), (23.65, 25.4), (23.65, 27.8), (24.45, 28.6),
                       (31.0, 28.6)], 0.15)
    track(b, "SWCLK", [(cx, cy), (cx, 21.9), (22.7, 24.2), (22.7, 24.9), (23.35, 25.55), (23.35, 27.97), (24.38, 29.0),
                       (31.0, 29.0)], 0.15)


def gnd_vias(b):
    """Tie every SMD GND pad that the copied MCU core does not already connect to the bottom pour with
    its own via (or a neighbouring one) and a short stub. The autorouter does not know about the pour:
    left alone it chains ground pads together on long thin tracks."""
    R, GAP = VIA_D / 2, 0.2
    pads, segs, vias = [], [], []  # obstacles: (rect, net), (a, c, half width, net), (centre, net)
    def rect(q):
        bb = q.GetBoundingBox()
        return xy(bb.GetOrigin())[0], xy(bb.GetEnd())[0], xy(bb.GetOrigin())[1], xy(bb.GetEnd())[1]

    for f in b.GetFootprints():
        for q in f.Pads():
            pads.append((rect(q), q.GetNetname(), q))
    for t in b.GetTracks():
        if t.Type() == pcbnew.PCB_VIA_T:
            vias.append((xy(t.GetPosition()), t.GetNetname()))
        else:
            segs.append((xy(t.GetStart()), xy(t.GetEnd()), pcbnew.ToMM(t.GetWidth()) / 2, t.GetNetname()))
    zones = []
    for z in b.Zones():
        if z.GetNetname() != "GND" and not z.GetIsRuleArea():
            bb = z.GetBoundingBox()
            zones.append((*xy(bb.GetOrigin()), *xy(bb.GetEnd())))
    zones = [(x0, x1, y0, y1) for x0, y0, x1, y1 in zones]
    imu = b.FindFootprintByReference("U3").GetBoundingBox(False)
    imu = (xy(imu.GetOrigin())[0], xy(imu.GetEnd())[0], xy(imu.GetOrigin())[1], xy(imu.GetEnd())[1])

    def rect_d(pnt, r):
        dx = max(r[0] - pnt[0], 0, pnt[0] - r[1])
        dy = max(r[2] - pnt[1], 0, pnt[1] - r[3])
        return math.hypot(dx, dy)

    def seg_d(pnt, a, c):
        vx, vy = c[0] - a[0], c[1] - a[1]
        k = max(0, min(1, ((pnt[0] - a[0]) * vx + (pnt[1] - a[1]) * vy) / ((vx * vx + vy * vy) or 1)))
        return math.hypot(pnt[0] - a[0] - k * vx, pnt[1] - a[1] - k * vy)

    def clear(pnt, r):  # a disc of radius r at pnt keeps GAP to all copper on other nets
        return (all(n == "GND" or rect_d(pnt, rc) >= r + GAP for rc, n, _ in pads)
                and all(n == "GND" or seg_d(pnt, a, c) >= r + hw + GAP for a, c, hw, n in segs)
                and all(n == "GND" or math.dist(pnt, c) >= r + R + GAP for c, n in vias))

    def stub_ok(a, c, w):
        n = max(2, int(math.dist(a, c) / 0.05))
        return all(clear((a[0] + (c[0] - a[0]) * i / n, a[1] + (c[1] - a[1]) * i / n), w / 2) for i in range(n + 1))

    def via_ok(pnt):
        return (0.7 <= pnt[0] <= W - 0.7 and 0.7 <= pnt[1] <= H - 0.7 and clear(pnt, R)
                and all(rect_d(pnt, rc) >= R + 0.05 for rc, _, _ in pads)  # never in a pad: solder would wick away
                and all(math.dist(pnt, c) >= VIA_D + 0.25 for c, _ in vias)
                and all(rect_d(pnt, z) >= R + 0.3 for z in zones) and rect_d(pnt, imu) >= R
                and all(math.dist(pnt, (hx, hy)) >= HOLE_KEEPOUT + R + 0.2 for hx, hy in HOLES))

    anchors = [c for c, n in vias if n == "GND"] + [xy(q.GetPosition()) for _, n, q in pads if n == "GND" and q.HasHole()]
    failed, made = [], 0
    gz = [z for z in b.Zones() if z.GetNetname() == "GND"]
    for f in sorted(b.GetFootprints(), key=lambda f: f.GetReference()):
        fc = xy(f.GetPosition())
        for q in f.Pads():
            if q.GetNetname() != "GND" or q.HasHole():
                continue
            c = xy(q.GetPosition())
            rc = rect(q)
            if (any(n == "GND" and (rect_d(a, rc) == 0 or rect_d(e, rc) == 0) for a, e, _, n in segs)
                    or any(n == "GND" and rect_d(v, rc) == 0 for v, n in vias)
                    or any(z.HitTestFilledArea(z.GetLayer(), q.GetPosition()) for z in gz)):
                continue  # already tied down by copied reference copper or power_copper()
            w = min(0.4, pcbnew.ToMM(min(q.GetSize(pcbnew.F_Cu).x, q.GetSize(pcbnew.F_Cu).y)))
            near = sorted((a for a in anchors if math.dist(a, c) <= 1.6 and stub_ok(c, a, w)), key=lambda a: math.dist(a, c))
            if not near:
                out = math.atan2(c[1] - fc[1], c[0] - fc[0])  # prefer a via on the outside of the part
                cands = [(r, abs(math.remainder(k * math.pi / 8 - out, 2 * math.pi)),
                          (c[0] + r * math.cos(k * math.pi / 8), c[1] + r * math.sin(k * math.pi / 8)))
                         for r in [0.5 + 0.1 * i for i in range(21)] for k in range(16)]
                near = [v for _, _, v in sorted(cands) if via_ok(v) and stub_ok(c, v, w)][:1]
                if not near:
                    failed.append(f"{f.GetReference()}.{q.GetNumber()}")
                    continue
                via(b, "GND", *near[0])
                vias.append((near[0], "GND"))
                anchors.append(near[0])
                made += 1
            track(b, "GND", [c, near[0]], w)
            segs.append((c, near[0], w / 2, "GND"))
    if failed:
        sys.exit(f"no room for a GND via at {failed}")
    print("GND vias added:", made)


def place():
    if not REF:
        sys.exit("usage: build_pcb.py place <reference .kicad_pcb>")
    b = pcbnew.NewBoard(str(PCB))
    rules(b)
    # net names come from KiCad's own netlist export, so the board matches the schematic exactly
    # (including the per-pin "unconnected-(...)" nets KiCad gives no-connect pins)
    import xml.etree.ElementTree as ET
    pinnet, netinfo = {}, {}
    for n in ET.parse(ROOT / "build" / "fc.net.xml").getroot().find("nets"):
        name = n.get("name")
        if name.startswith("unconnected-("):
            name = name.replace("/", "{slash}")  # KiCad escapes '/' in pin names inside net names
        netinfo[name] = pcbnew.NETINFO_ITEM(b, name)
        b.Add(netinfo[name])
        for node in n:
            pinnet[(node.get("ref"), node.get("pin"))] = name

    if not REF.is_file():
        sys.exit(f"reference board not found: {REF}")
    ref = pcbnew.LoadBoard(str(REF.resolve()))
    ru = ref.FindFootprintByReference("U1").GetPosition()

    def add(refdes, x, y, rot):
        p = PARTS[refdes]
        fp = load_fp(p["fp"])
        fp.SetReference(refdes)
        fp.SetValue(p["value"])
        fp.SetPath(pcbnew.KIID_PATH("/" + uid("sym", refdes)))
        for k, f in (("MPN", "mpn"), ("Manufacturer", "mfr"), ("LCSC", "lcsc")):
            fp.SetField(k, p[f])
        for fld in fp.GetFields():
            if fld.GetName() not in ("Reference", "Value"):
                fld.SetVisible(False)
        b.Add(fp)
        fp.SetPosition(pt(x, y))
        fp.SetOrientationDegrees(rot)
        fp.SetField("Datasheet", "")  # drop the reference design's local file paths
        fp.SetField("Description", "")
        fp.SetExcludedFromBOM(not p["mpn"])
        for pad in fp.Pads():
            n = pinnet.get((refdes, pad.GetNumber()))
            if n:
                pad.SetNet(netinfo[n])
        fp.Reference().SetVisible(False)
        fp.Value().SetVisible(False)
        return fp

    for r in CLUSTER:
        rf = ref.FindFootprintByReference(r)
        d = rf.GetPosition() - ru
        add(r, U1_AT[0] + pcbnew.ToMM(d.x), U1_AT[1] + pcbnew.ToMM(d.y), rf.GetOrientationDegrees())
    missing = set(PARTS) - set(CLUSTER) - set(PLACE)
    if missing:
        sys.exit(f"no placement for {sorted(missing)}")

    # transplant reference copper inside the cluster box
    shift = pt(*U1_AT) - ru

    def inside(p):
        dx, dy = pcbnew.ToMM(p.x - ru.x), pcbnew.ToMM(p.y - ru.y)
        return KEEP_BOX[0] < dx < KEEP_BOX[1] and KEEP_BOX[2] < dy < KEEP_BOX[3]

    copied = 0
    for t in ref.GetTracks():
        net = REF_NETS.get(t.GetNetname())
        if not net or not inside(t.GetStart()) or not inside(t.GetEnd()):
            continue
        if any(math.dist(xy(e + shift), d) < 0.05 for e in (t.GetStart(), t.GetEnd()) for d in REF_DROP):
            continue
        if t.Type() == pcbnew.PCB_VIA_T:
            v = pcbnew.PCB_VIA(b)
            v.SetPosition(t.GetPosition() + shift)
            v.SetWidth(t.GetWidth(pcbnew.F_Cu))
            v.SetDrill(t.GetDrillValue())
        elif t.Type() == pcbnew.PCB_ARC_T:
            v = pcbnew.PCB_ARC(b)
            v.SetStart(t.GetStart() + shift)
            v.SetMid(pcbnew.Cast_to_PCB_ARC(t).GetMid() + shift)
            v.SetEnd(t.GetEnd() + shift)
            v.SetWidth(t.GetWidth())
            v.SetLayer(t.GetLayer())
        else:
            v = pcbnew.PCB_TRACK(b)
            v.SetStart(t.GetStart() + shift)
            v.SetEnd(t.GetEnd() + shift)
            v.SetWidth(t.GetWidth())
            v.SetLayer(t.GetLayer())
        v.SetNet(netinfo[net])
        v.SetLocked(True)
        b.Add(v)
        copied += 1
    zones = 0
    for z in ref.Zones():
        net = REF_NETS.get(z.GetNetname())
        bb = z.GetBoundingBox()
        if not net or not (inside(bb.GetOrigin()) and inside(bb.GetEnd())):
            continue
        nz = pcbnew.Cast_to_ZONE(z.Duplicate(False))
        nz.Move(shift)
        nz.SetNet(netinfo[net])
        b.Add(nz)
        zones += 1
    # drop copied stubs that led to parts we did not keep (fill first: some copper connects via zones)
    pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    b.BuildConnectivity()
    conn = b.GetConnectivity()
    removed = 1
    while removed:
        removed = 0
        for tr in list(b.GetTracks()):
            if tr.Type() in (pcbnew.PCB_TRACE_T, pcbnew.PCB_ARC_T) and conn.TestTrackEndpointDangling(tr, False):
                b.Remove(tr)
                removed += 1
                copied -= 1
        ends = [e for tr in b.GetTracks() if tr.Type() != pcbnew.PCB_VIA_T for e in (tr.GetStart(), tr.GetEnd())]
        for v in [x for x in b.GetTracks() if x.Type() == pcbnew.PCB_VIA_T]:  # vias left with nothing on them
            pos = v.GetPosition()
            if not (any(v.HitTest(e) for e in ends) or any(q.HitTest(pos) for f in b.GetFootprints() for q in f.Pads())
                    or any(z.HitTestFilledArea(z.GetLayer(), pos) for z in b.Zones())):
                b.Remove(v)
                removed += 1
                copied -= 1
        b.BuildConnectivity()
        conn = b.GetConnectivity()
    print(f"transplanted {copied} tracks/vias, {zones} zones")
    # our own parts go in only now, so leftover reference copper cannot latch onto them
    for r, (x, y, rot) in PLACE.items():
        add(r, x, y, rot)

    # servo rail and GND row: heavy straight bars along the header rows (both layers)
    xs = [20.0 + (i - 4.5) * 2.54 for i in range(1, 9)]
    for net, y in (("SERVO_V", 32.92 + 2.54), ("GND", 32.92 + 5.08)):
        for layer, (xa, xb) in ((lay, seg) for lay in (pcbnew.F_Cu, pcbnew.B_Cu) for seg in zip(xs, xs[1:])):
            t = pcbnew.PCB_TRACK(b)
            t.SetStart(pt(xa, y))
            t.SetEnd(pt(xb, y))
            t.SetWidth(mm(1.5))
            t.SetLayer(layer)
            t.SetNet(netinfo[net])
            t.SetLocked(True)
            b.Add(t)

    power_copper(b)
    usb_copper(b)
    imu_copper(b)
    swd_copper(b)
    pwm_copper(b)
    gnd_vias(b)

    # no copper under the M3 screw heads / standoffs (the top pour is +3V3)
    for hx, hy in HOLES:
        k = pcbnew.ZONE(b)
        k.SetIsRuleArea(True)
        k.SetDoNotAllowZoneFills(True)
        k.SetDoNotAllowTracks(True)
        k.SetDoNotAllowVias(True)
        k.SetDoNotAllowPads(False)
        k.SetDoNotAllowFootprints(False)
        k.SetLayerSet(pcbnew.LSET.AllCuMask())
        k.Outline().NewOutline()
        for i in range(24):
            k.Outline().Append(mm(OX + hx + HOLE_KEEPOUT * math.cos(i * math.pi / 12)),
                               mm(OY + hy + HOLE_KEEPOUT * math.sin(i * math.pi / 12)))
        b.Add(k)

    # nothing under the IMU: copper or a via below a MEMS package stresses it unevenly
    ux, uy = xy(b.FindFootprintByReference("U3").GetPosition())
    k = pcbnew.ZONE(b)
    k.SetIsRuleArea(True)
    k.SetDoNotAllowZoneFills(True)
    k.SetDoNotAllowTracks(True)
    k.SetDoNotAllowVias(True)
    k.SetDoNotAllowPads(False)
    k.SetDoNotAllowFootprints(False)
    k.SetLayer(pcbnew.F_Cu)
    k.Outline().NewOutline()
    for dx, dy in ((-0.8, -0.55), (0.8, -0.55), (0.8, 0.55), (-0.8, 0.55)):  # inside the pad ring
        k.Outline().Append(mm(OX + ux + dx), mm(OY + uy + dy))
    b.Add(k)
    k = pcbnew.ZONE(b)  # and no vias anywhere under the 3 x 2.5 mm body
    k.SetIsRuleArea(True)
    k.SetDoNotAllowVias(True)
    k.SetDoNotAllowTracks(False)
    k.SetDoNotAllowZoneFills(False)
    k.SetDoNotAllowPads(False)
    k.SetDoNotAllowFootprints(False)
    k.SetLayer(pcbnew.F_Cu)
    k.Outline().NewOutline()
    for dx, dy in ((-1.6, -1.35), (1.6, -1.35), (1.6, 1.35), (-1.6, 1.35)):
        k.Outline().Append(mm(OX + ux + dx), mm(OY + uy + dy))
    b.Add(k)

    # outline with 1 mm corner radius
    r = 1.0
    segs = [((r, 0), (W - r, 0)), ((W, r), (W, H - r)), ((W - r, H), (r, H)), ((0, H - r), (0, r))]
    for a, c in segs:
        s = pcbnew.PCB_SHAPE(b)
        s.SetShape(pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(pt(*a))
        s.SetEnd(pt(*c))
        s.SetLayer(pcbnew.Edge_Cuts)
        s.SetWidth(mm(0.1))
        b.Add(s)
    for cx, cy, sx, sy in ((r, r, 0, r), (W - r, r, W - r, 0), (W - r, H - r, W, H - r), (r, H - r, r, H)):
        s = pcbnew.PCB_SHAPE(b)
        s.SetShape(pcbnew.SHAPE_T_ARC)
        s.SetCenter(pt(cx, cy))
        s.SetStart(pt(sx, sy))
        s.SetArcAngleAndEnd(pcbnew.EDA_ANGLE(90, pcbnew.DEGREES_T), True)
        s.SetLayer(pcbnew.Edge_Cuts)
        s.SetWidth(mm(0.1))
        b.Add(s)

    b.BuildConnectivity()
    pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    pcbnew.SaveBoard(str(PCB), b)
    pcbnew.SaveBoard(str(PLACED), b)
    export_dsn(PCB)
    print("saved", PCB, "and fc.dsn")


def export_dsn(src, drop_pours=False):
    """Freerouting ignores arcs and zones: export a copy with arcs flattened to chords (so it sees them as
    connected) and router-only keepouts over the reference's copper zones."""
    s = pcbnew.LoadBoard(str(src))
    for z in list(s.Zones()):
        if z.GetIsRuleArea():
            continue  # mounting-hole keepouts export as they are
        if drop_pours and z.GetAssignedPriority() == 0:
            s.Remove(z)
            continue
        k = pcbnew.ZONE(s)
        k.SetIsRuleArea(True)
        k.SetDoNotAllowTracks(True)
        k.SetDoNotAllowVias(True)
        k.SetDoNotAllowPads(False)
        k.SetDoNotAllowZoneFills(False)
        k.SetDoNotAllowFootprints(False)
        k.SetLayer(z.GetLayer())
        k.Outline().Append(z.Outline())
        s.Add(k)
    for a in [x for x in s.GetTracks() if x.Type() == pcbnew.PCB_ARC_T]:
        a = pcbnew.Cast_to_PCB_ARC(a)
        c, r = a.GetCenter(), a.GetRadius()
        a0 = math.atan2(a.GetStart().y - c.y, a.GetStart().x - c.x)
        sweep = a.GetAngle().AsRadians()
        n = 6
        prev = a.GetStart()
        for k in range(1, n + 1):
            ang = a0 + sweep * k / n
            nxt = a.GetEnd() if k == n else pcbnew.VECTOR2I(int(c.x + r * math.cos(ang)), int(c.y + r * math.sin(ang)))
            seg = pcbnew.PCB_TRACK(s)
            seg.SetStart(prev)
            seg.SetEnd(nxt)
            seg.SetWidth(a.GetWidth())
            seg.SetLayer(a.GetLayer())
            seg.SetNet(a.GetNet())
            seg.SetLocked(True)
            s.Add(seg)
            prev = nxt
        s.Remove(a)
    if not pcbnew.ExportSpecctraDSN(s, str(HW / "fc.dsn")):
        sys.exit("DSN export failed")


def reroute():
    """Second routing round: hand the routed board back to Freerouting (router copper stays movable)."""
    export_dsn(PCB, drop_pours=True)
    print("exported routed board to fc.dsn")


def zone(b, net, layer, prio, clearance, min_width):
    z = pcbnew.ZONE(b)
    z.SetLayer(layer)
    z.SetNet(b.FindNet(net))
    z.SetAssignedPriority(prio)
    z.SetLocalClearance(mm(clearance))
    z.SetMinThickness(mm(min_width))
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_THT_THERMAL)  # solid to SMD pads, reliefs on THT
    z.SetThermalReliefGap(mm(0.3))
    z.SetThermalReliefSpokeWidth(mm(0.3))
    ol = z.Outline()
    ol.NewOutline()
    for x, y in ((0, 0), (W, 0), (W, H), (0, H)):
        ol.Append(mm(OX + x), mm(OY + y))
    b.Add(z)


def silk(b, text, x, y, size=0.8, rot=0, layer=pcbnew.F_SilkS):
    t = pcbnew.PCB_TEXT(b)
    t.SetText(text)
    t.SetPosition(pt(x, y))
    t.SetTextSize(pcbnew.VECTOR2I(mm(size), mm(size)))
    t.SetTextThickness(mm(size * 0.15))
    t.SetTextAngleDegrees(rot)
    t.SetLayer(layer)
    b.Add(t)


def finish():
    ses = sys.argv[2] if len(sys.argv) > 2 else str(HW / "fc.ses")
    b = pcbnew.LoadBoard(str(PLACED))
    s = pcbnew.LoadBoard(str(PLACED))
    if not pcbnew.ImportSpecctraSES(s, ses):
        sys.exit("SES import failed")
    # keep our locked copper (incl. true arcs); take only what the router added
    have = {(t.GetStart().x, t.GetStart().y, t.GetEnd().x, t.GetEnd().y, t.GetLayer()) for t in b.GetTracks()}
    added = 0
    for t in s.GetTracks():
        if t.IsLocked() or (t.GetStart().x, t.GetStart().y, t.GetEnd().x, t.GetEnd().y, t.GetLayer()) in have:
            continue
        n = pcbnew.PCB_VIA(b) if t.Type() == pcbnew.PCB_VIA_T else pcbnew.PCB_TRACK(b)
        if t.Type() == pcbnew.PCB_VIA_T:
            n.SetPosition(t.GetPosition())
            n.SetWidth(t.GetWidth(pcbnew.F_Cu))
            n.SetDrill(t.GetDrillValue())
        else:
            n.SetStart(t.GetStart())
            n.SetEnd(t.GetEnd())
            # Freerouting necks to 0.09 mm at the USB-C CC pads despite --router.neck_width_um; DRC checks the clearance
            n.SetWidth(max(t.GetWidth(), mm(0.1)))
            n.SetLayer(t.GetLayer())
        n.SetNet(b.FindNet(t.GetNetname()))
        b.Add(n)
        added += 1
    # with GND left out of routing Freerouting skips its clean-up pass and leaves vias that lead nowhere
    ends = {(e.x, e.y, t.GetLayer()) for t in b.GetTracks() if t.Type() != pcbnew.PCB_VIA_T for e in (t.GetStart(), t.GetEnd())}
    for v in [x for x in b.GetTracks() if x.Type() == pcbnew.PCB_VIA_T and not x.IsLocked()]:
        pos = v.GetPosition()
        if not all((pos.x, pos.y, lay) in ends for lay in (pcbnew.F_Cu, pcbnew.B_Cu)):
            b.Remove(v)
            added -= 1
    print("router added", added, "tracks/vias")
    # same scheme as the Raspberry Pi reference: 3V3 pour on top, solid GND on the bottom
    zone(b, "+3V3", pcbnew.F_Cu, 0, 0.15, 0.15)  # settings copied from the reference pours
    zone(b, "GND", pcbnew.B_Cu, 0, 0.2, 0.2)
    for i in range(1, 9):  # channel numbers on the back: the crystal sits above the header block on top
        silk(b, str(i), 20.0 + (i - 4.5) * 2.54, 30.9, layer=pcbnew.B_SilkS)
    silk(b, "S", 8.6, 32.92), silk(b, "+", 8.6, 35.46), silk(b, "-", 8.6, 38.0)
    silk(b, "OUT", 31.6, 32.9, 0.8)
    silk(b, "2S", 36.6, 8.2, 0.8), silk(b, "+", 32.5, 12.0), silk(b, "-", 32.5, 14.5)
    silk(b, "GPS", 7.8, 10.4, 0.8), silk(b, "SWD", 31.2, 30.6, 0.8)
    silk(b, f"RP2354A FC rev {REV}", 20.0, 22.0, 1.0, layer=pcbnew.B_SilkS)
    for t in b.GetDrawings():
        if t.GetLayer() == pcbnew.B_SilkS and isinstance(t, pcbnew.PCB_TEXT):
            t.SetMirrored(True)
    filler = pcbnew.ZONE_FILLER(b)
    filler.Fill(b.Zones())
    pcbnew.SaveBoard(str(PCB), b)
    # DRC cannot see a pour that tracks have cut into pieces if a thin track still joins them: report it
    for z in b.Zones():
        if z.GetAssignedPriority() == 0 and not z.GetIsRuleArea():
            print(f"pour {z.GetNetname()}: {z.GetFilledPolysList(z.GetLayer()).OutlineCount()} piece(s)")
    print("finished", PCB)


if __name__ == "__main__":
    # KiCad gives new items random IDs and writes files sorted by ID, so the autorouter would see a different
    # item order (and route differently) on every build. A fixed seed makes the build reproducible.
    pcbnew.KIID.SeedGenerator(int(os.environ.get("FC_SEED", "1")))
    {"place": place, "finish": finish, "reroute": reroute}[sys.argv[1]]()
