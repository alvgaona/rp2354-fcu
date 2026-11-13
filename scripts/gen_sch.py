"""Draw hw/fc.kicad_sch: hand-placed blocks, wired inside each block, net labels only between blocks.

Same approach as balancio-board/scripts/draw_sch.py. Coordinates are schematic mm (y down) on the 1.27 mm
grid, local to each block; arrange() then moves the blocks into a grid of frames on the page. Wires must end
on pins or on other wires; junction dots and no-connect flags are added automatically, and a pin that
design.py connects but the drawing leaves open stops the build. check_netlist.py then proves the drawing
connects exactly what design.py says.

Every net of design.py carries its name: a power port for the supply rails, a label on the wire otherwise.
"""
import math
import sys
import uuid
from datetime import date

from design import PARTS, REV, TITLE
from sexpr import ROOT, Sym, dump, find, first, get_symbol, pins

PROJECT = "fc"
NS = uuid.UUID("6b1f0c1e-4a7e-4a53-9a43-2b9f1f4c0d01")
ROOT_UUID = str(uuid.uuid5(NS, "root"))
P = 2.54
POWER_LIB = {"GND": "power:GND", "+3V3": "power:+3V3", "+1V1": "power:+1V1", "VBUS": "power:VBUS",
             "FLAG": "power:PWR_FLAG"}
AREA = (12.7, 12.7, 406.4, 251.46)  # A3 inside the border, above the title block


def uid(*k):
    return str(uuid.uuid5(NS, "/".join(map(str, k))))


def r2(v):
    return round(v + 0.0, 2)


def eff(size=1.27, just=None, hide=False, bold=False):
    f = [Sym("font"), [Sym("size"), size, size]] + ([[Sym("bold"), Sym("yes")]] if bold else [])
    return [Sym("effects"), f] + ([[Sym("justify"), *map(Sym, just.split())]] if just else []) + \
        ([[Sym("hide"), Sym("yes")]] if hide else [])


class Placed:
    def __init__(self, ref, lib, x, y, a, mirror):
        self.ref, self.lib, self.x, self.y, self.a, self.mirror = ref, lib, x, y, a, mirror
        self.fields = {}

    def T(self, px, py):
        """Library point (y up) -> schematic point (y down)."""
        if self.mirror == "y":
            px = -px
        r = math.radians(self.a)
        rx, ry = px * math.cos(r) - py * math.sin(r), px * math.sin(r) + py * math.cos(r)
        return r2(self.x + rx), r2(self.y - ry)

    def __getitem__(self, num):
        return self.pins[num][0]


class Sheet:
    def __init__(self):
        self.symdefs, self.parts, self.wires, self.labels, self.extra = {}, [], [], [], []
        self.n = {"#PWR": 0, "#FLG": 0}
        self.blocks = []

    # ---- placing ----
    def place(self, ref, x, y, a=0, mirror=None, lib=None, ref_at=None, val_at=None, hide_val=False):
        """ref_at / val_at: (x, y, justify) to override where the reference and value texts go."""
        assert not (mirror and a), "mirror only with rotation 0"
        lib = lib or PARTS[ref]["sym"]
        if lib not in self.symdefs:
            self.symdefs[lib] = get_symbol(lib)
        d = self.symdefs[lib]
        s = Placed(ref, lib, x, y, a, mirror)
        s.pins = {num: (s.T(px, py), name, typ) for num, (name, px, py, _, typ) in pins(d).items()}
        val = PARTS[ref]["value"] if ref in PARTS else lib.split(":")[1]
        if ref.startswith("#"):  # power port / flag: keep the library's field placement
            props = {p[1]: first(p, "at") for p in find(d, "property")}
            s.fields = {"Reference": (ref, *s.T(float(props["Reference"][1]), float(props["Reference"][2])), None, True),
                        "Value": (val, *s.T(float(props["Value"][1]), float(props["Value"][2])), None, hide_val)}
        else:
            box = self._box(s, d)
            ends = [pt for pt, _, _ in s.pins.values()]
            if lib.startswith("Device:") and len(ends) == 2 and ends[0][0] == ends[1][0]:  # upright two-pin part
                dr, dv = (x + P, y - 1.27, "left"), (x + P, y + 1.27, "left")
            elif lib.startswith("Device:") and len(ends) == 2:
                dr, dv = (x, y - P, None), (x, y + P, None)
            else:
                dr, dv = (box[0], box[1] - 1.27, "left"), (box[0], box[3] + 1.27, "left")
            rx, ry, rj = ref_at or dr
            vx, vy, vj = val_at or dv
            s.fields = {"Reference": (ref, rx, ry, rj, False), "Value": (val, vx, vy, vj, hide_val)}
        self.parts.append(s)
        return s

    def _box(self, s, d):
        pts = []
        for sub in find(d, "symbol"):
            for r in find(sub, "rectangle"):
                pts += [s.T(float(first(r, "start")[1]), float(first(r, "start")[2])),
                        s.T(float(first(r, "end")[1]), float(first(r, "end")[2]))]
        pts = pts or [p[0] for p in s.pins.values()] or [(s.x, s.y)]
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        return min(xs), min(ys), max(xs), max(ys)

    def power(self, name, pt, a=0):
        kind = "#FLG" if name == "FLAG" else "#PWR"
        self.n[kind] += 1
        return self.place(f"{kind}{self.n[kind]:02d}", pt[0], pt[1], a, lib=POWER_LIB[name],
                          hide_val=name in ("GND", "FLAG"))

    # ---- connecting ----
    def w(self, *pts):
        for a, b in zip(pts, pts[1:]):
            a, b = (r2(a[0]), r2(a[1])), (r2(b[0]), r2(b[1]))
            assert a[0] == b[0] or a[1] == b[1], f"wire not orthogonal: {a} {b}"
            if a != b:
                self.wires.append((a, b))

    def label(self, name, pt, a=0):
        """Net label on a wire: the text runs right from pt (a=0) or ends at pt (a=180)."""
        self.labels.append((name, (r2(pt[0]), r2(pt[1])), a))

    # ---- annotation ----
    def text(self, s, x, y, size=1.27, bold=False):
        self.extra.append([Sym("text"), s, [Sym("exclude_from_sim"), Sym("no")], [Sym("at"), x, y, 0],
                           eff(size, "left bottom", bold=bold), [Sym("uuid"), uid("text", s, x, y)]])

    def frame(self, x1, y1, x2, y2, title):
        self.extra.append([Sym("rectangle"), [Sym("start"), x1, y1], [Sym("end"), x2, y2],
                           [Sym("stroke"), [Sym("width"), 0.254], [Sym("type"), Sym("dash")]],
                           [Sym("fill"), [Sym("type"), Sym("none")]], [Sym("uuid"), uid("frame", title)]])
        self.text(title, x1 + 2.54, y1 + 5.08, 2, bold=True)

    def block(self, title, col, row, draw):
        """Draw a block anywhere; arrange() later moves it into its cell of the page grid."""
        mark = len(self.parts), len(self.wires), len(self.labels), len(self.extra)
        draw(self)
        stop = len(self.parts), len(self.wires), len(self.labels), len(self.extra)
        pts = []
        for s in self.parts[mark[0]:]:
            b = self._box(s, self.symdefs[s.lib])
            pts += [(b[0], b[1]), (b[2], b[3])] + [pt for pt, _, _ in s.pins.values()]
            pts += [(x + d * len(v) * 0.55, y) for v, x, y, _, h in s.fields.values() if not h for d in (-1, 1)]
        pts += [p for seg in self.wires[mark[1]:] for p in seg]
        for name, (x, y), a in self.labels[mark[2]:]:
            pts += [(x, y), (x + (len(name) * 1.1 + 1) * (1 if a == 0 else -1), y - 1.5)]
        for t in self.extra[mark[3]:]:
            x, y = float(first(t, "at")[1]), float(first(t, "at")[2])
            pts += [(x, y - 1.27), (x + len(t[1]) * 1.05, y)]
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        self.blocks.append(dict(title=title, col=col, row=row, mark=mark, stop=stop,
                                box=(min(xs), min(ys), max(xs), max(ys))))

    def arrange(self, margin=7.62, gap=5.08, title=7.62):
        """Aligned grid of frames sized to their contents, centred on the page above the title block."""
        snap = lambda v: round(v / P) * P
        cols, rows = {}, {}
        for b in self.blocks:
            x1, y1, x2, y2 = b["box"]
            cols[b["col"]] = max(cols.get(b["col"], 0), x2 - x1 + 2 * margin)
            rows[b["row"]] = max(rows.get(b["row"], 0), y2 - y1 + 2 * margin + title)
        W = sum(cols.values()) + gap * (len(cols) - 1)
        H = sum(rows.values()) + gap * (len(rows) - 1)
        assert W <= AREA[2] - AREA[0] and H <= AREA[3] - AREA[1], f"blocks need {W:.0f} x {H:.0f} mm: too big for the page"
        x0 = snap(AREA[0] + (AREA[2] - AREA[0] - W) / 2)
        y0 = snap(AREA[1] + (AREA[3] - AREA[1] - H) / 2)
        for b in self.blocks:
            cx1 = x0 + sum(cols[c] for c in cols if c < b["col"]) + gap * b["col"]
            cy1 = y0 + sum(rows[r] for r in rows if r < b["row"]) + gap * b["row"]
            cx2, cy2 = cx1 + cols[b["col"]], cy1 + rows[b["row"]]
            x1, y1, x2, y2 = b["box"]
            dx = snap((cx1 + cx2) / 2 - (x1 + x2) / 2)
            dy = snap((cy1 + title + cy2) / 2 - (y1 + y2) / 2)
            mv = lambda pt: (r2(pt[0] + dx), r2(pt[1] + dy))
            (p0, w0, l0, e0), (p1, w1, l1, e1) = b["mark"], b["stop"]
            for s in self.parts[p0:p1]:
                s.x, s.y = mv((s.x, s.y))
                s.pins = {n: (mv(pt), name, typ) for n, (pt, name, typ) in s.pins.items()}
                s.fields = {k: (v, *mv((x, y)), j, h) for k, (v, x, y, j, h) in s.fields.items()}
            self.wires[w0:w1] = [(mv(a), mv(c)) for a, c in self.wires[w0:w1]]
            self.labels[l0:l1] = [(n, mv(pt), a) for n, pt, a in self.labels[l0:l1]]
            for t in self.extra[e0:e1]:
                at = first(t, "at")
                at[1], at[2] = mv((float(at[1]), float(at[2])))
            self.frame(r2(cx1), r2(cy1), r2(cx2), r2(cy2), b["title"])

    # ---- output ----
    def finish(self):
        pin_pts = {}
        for s in self.parts:
            for num, (pt, _, _) in s.pins.items():
                pin_pts.setdefault(pt, []).append((s.ref, num))

        def inside(p, seg):
            (x1, y1), (x2, y2) = seg
            return (x1 == x2 == p[0] and min(y1, y2) < p[1] < max(y1, y2)) or \
                   (y1 == y2 == p[1] and min(x1, x2) < p[0] < max(x1, x2))

        # split wires wherever another wire ends, or a pin or label sits, on them (KiCad connects those points)
        changed = True
        while changed:
            changed = False
            ends = {p for seg in self.wires for p in seg} | set(pin_pts) | {p for _, p, _ in self.labels}
            for seg in list(self.wires):
                for p in ends:
                    if inside(p, seg):
                        self.wires.remove(seg)
                        self.wires += [(seg[0], p), (p, seg[1])]
                        changed = True
                        break
                if changed:
                    break
        ends = {}
        for seg in self.wires:
            for p in seg:
                ends[p] = ends.get(p, 0) + 1
        juncs = [p for p, k in ends.items() if k >= 3 or (k == 2 and pin_pts.get(p))]
        for name, p, _ in self.labels:
            if p not in ends:
                sys.exit(f"label {name} at {p} is not on a wire")

        items = []
        for s in self.parts:
            items.append(self._symbol(s))
            if s.ref.startswith("#"):
                continue
            want = PARTS[s.ref]["pins"]
            for num, (pt, name, typ) in s.pins.items():
                shared = len(pin_pts[pt]) > 1
                if num in want and pt not in ends and not shared:
                    sys.exit(f"{s.ref} pin {num} ({name}) should be on net {want[num]} but nothing touches it")
                if num not in want and typ != "no_connect":
                    if pt in ends or shared:
                        sys.exit(f"{s.ref} pin {num} ({name}) has no net in design.py but is wired")
                    items.append([Sym("no_connect"), [Sym("at"), *pt], [Sym("uuid"), uid("nc", s.ref, num)]])
        for a, b in self.wires:
            items.append([Sym("wire"), [Sym("pts"), [Sym("xy"), *a], [Sym("xy"), *b]],
                          [Sym("stroke"), [Sym("width"), 0], [Sym("type"), Sym("default")]], [Sym("uuid"), uid("w", a, b)]])
        for p in juncs:
            items.append([Sym("junction"), [Sym("at"), *p], [Sym("diameter"), 0], [Sym("color"), 0, 0, 0, 0],
                          [Sym("uuid"), uid("j", p)]])
        for name, p, a in self.labels:
            items.append([Sym("label"), name, [Sym("at"), *p, a], [Sym("fields_autoplaced"), Sym("yes")],
                          eff(1.27, "left bottom" if a == 0 else "right bottom"), [Sym("uuid"), uid("l", name, p)]])
        sch = [Sym("kicad_sch"), [Sym("version"), 20231120], [Sym("generator"), "eeschema"],
               [Sym("generator_version"), "8.0"], [Sym("uuid"), ROOT_UUID], [Sym("paper"), "A3"],
               [Sym("title_block"), [Sym("title"), TITLE], [Sym("date"), date.today().isoformat()], [Sym("rev"), REV],
                [Sym("comment"), 1, "Drawn by scripts/gen_sch.py; netlist checked against scripts/design.py by scripts/build.sh"]],
               [Sym("lib_symbols")] + list(self.symdefs.values())] + items + self.extra + \
              [[Sym("sheet_instances"), [Sym("path"), "/", [Sym("page"), "1"]]]]
        out = ROOT / "hw" / f"{PROJECT}.kicad_sch"
        out.write_text(dump(sch) + "\n")
        print("wrote", out, len(self.parts), "symbols,", len(self.wires), "wires,", len(juncs), "junctions,",
              len(self.labels), "labels")

    def _symbol(self, s):
        virtual = s.ref.startswith("#")
        p = None if virtual else PARTS[s.ref]
        node = [Sym("symbol"), [Sym("lib_id"), s.lib], [Sym("at"), s.x, s.y, s.a]]
        if s.mirror:
            node.append([Sym("mirror"), Sym(s.mirror)])
        node += [[Sym("unit"), 1], [Sym("exclude_from_sim"), Sym("no")],
                 [Sym("in_bom"), Sym("yes" if p and p["mpn"] else "no")],
                 [Sym("on_board"), Sym("no" if virtual else "yes")], [Sym("dnp"), Sym("no")], [Sym("uuid"), uid("sym", s.ref)]]
        flip = {"left": "right", "right": "left"} if s.a == 180 or s.mirror == "y" else {}
        for k, (v, x, y, just, hide) in s.fields.items():
            node.append([Sym("property"), k, v, [Sym("at"), x, y, s.a % 180], eff(1.27, flip.get(just, just), hide)])
        hidden = [("Footprint", p["fp"] if p else ""), ("Datasheet", "~"), ("Description", "")]
        if p:
            hidden += [("MPN", p["mpn"]), ("Manufacturer", p["mfr"]), ("LCSC", p["lcsc"])]
        for k, v in hidden:
            node.append([Sym("property"), k, v, [Sym("at"), s.x, s.y, 0], eff(hide=True)])
        for num in s.pins:
            node.append([Sym("pin"), num, [Sym("uuid"), uid("pin", s.ref, num)]])
        node.append([Sym("instances"), [Sym("project"), PROJECT, [Sym("path"), "/" + ROOT_UUID,
                                                                 [Sym("reference"), s.ref], [Sym("unit"), 1]]]])
        return node


def power_block(s):
    # battery and USB, each through a Schottky diode, joined into VIN
    j6 = s.place("J6", 10.16, 30.48, mirror="y", ref_at=(7.62, 30.48, "right"), val_at=(7.62, 33.02, "right"))
    d1 = s.place("D1", 44.45, 30.48, a=180)
    d2 = s.place("D2", 44.45, 20.32, a=180)
    u2 = s.place("U2", 88.9, 33.02, ref_at=(81.28, 26.67, "left"), val_at=(86.36, 26.67, "left"))
    s.w(j6["1"], d1["2"])
    s.label("VBAT", (17.78, 30.48))
    s.w(j6["2"], (22.86, 33.02))
    s.power("GND", (17.78, 33.02))
    s.power("FLAG", (22.86, 33.02), a=180)
    s.w(d2["2"], (35.56, 20.32))
    s.power("VBUS", (35.56, 20.32))
    s.w(d2["1"], (53.34, 20.32), (53.34, 30.48))
    s.w(d1["1"], u2["3"])
    s.label("VIN", (55.88, 30.48))
    s.power("FLAG", (62.23, 30.48))
    c1 = s.place("C1", 68.58, 34.29)
    s.power("GND", c1["2"])
    s.w(u2["2"], (76.2, 35.56), (76.2, 30.48))
    s.power("GND", u2["4"])
    s.text("Either input powers the board and both may be plugged in. A reversed battery is blocked.", 30.48, 12.7)

    # battery voltage divider for ADC0
    r9 = s.place("R9", 27.94, 39.37)
    r10 = s.place("R10", 27.94, 50.8)
    c20 = s.place("C20", 38.1, 50.8)
    s.w((27.94, 30.48), r9["1"])
    s.w(r9["2"], r10["1"])
    s.w((27.94, 45.72), (38.1, 45.72), c20["1"])
    s.w((38.1, 45.72), (45.72, 45.72))
    s.label("VBAT_SENSE", (45.72, 45.72))
    s.power("GND", r10["2"])
    s.power("GND", c20["2"])
    s.text("VBAT_SENSE = VBAT / 4.03 (8.4 V reads as 2.08 V)", 15.24, 62.23)

    # buck converter: switch node up to the inductor, bootstrap capacitor across BST and SW, feedback from the output
    l2 = s.place("L2", 121.92, 25.4, a=90)
    c2 = s.place("C2", 111.76, 29.21, a=180)
    s.w(u2["5"], (101.6, 30.48), (101.6, 25.4), l2["1"])
    s.label("SW_BUCK", (102.87, 25.4))
    s.w(u2["6"], c2["1"])
    s.label("BST", (102.87, 33.02))
    s.w(l2["2"], (152.4, 25.4))
    s.w(u2["1"], (129.54, 35.56), (129.54, 25.4))
    for ref, x in (("C5", 134.62), ("C19", 144.78)):
        s.power("GND", s.place(ref, x, 29.21)["2"])
    s.power("FLAG", (139.7, 25.4))
    s.power("+3V3", (152.4, 25.4))


def usb_block(s):
    j1 = s.place("J1", 20.32, 40.64, ref_at=(10.16, 21.59, "left"), val_at=(15.24, 21.59, "left"))
    s.w(j1["A4"], (45.72, 25.4))
    s.power("VBUS", (40.64, 25.4))
    s.power("FLAG", (45.72, 25.4))
    r1 = s.place("R1", 66.04, 34.29)
    r5 = s.place("R5", 55.88, 36.83)
    s.w(j1["A5"], r1["1"])
    s.label("CC1", (38.1, 30.48))
    s.w(j1["B5"], r5["1"])
    s.label("CC2", (38.1, 33.02))
    s.w(r1["2"], (66.04, 40.64))
    s.power("GND", (66.04, 40.64))
    s.power("GND", r5["2"])
    # the connector has two pins per data line, one for each way the plug can go in
    for a, b, y, name in (("A7", "B7", 38.1, "USB_D-"), ("A6", "B6", 45.72, "USB_D+")):
        s.w(j1[a], (38.1, j1[a][1]), (38.1, j1[b][1]), j1[b])
        s.w((38.1, y), (43.18, y))
        s.label(name, (43.18, y))
    s.w(j1["SH"], (12.7, 66.04), (20.32, 66.04), j1["A1"])
    s.power("GND", (20.32, 66.04))
    s.text("5.1 k on CC: USB device", 40.64, 53.34)


def imu_block(s):
    u3 = s.place("U3", 60.96, 45.72, val_at=(67.31, 31.75, "left"))
    for pin, name, a in (("13", "IMU_SCK", 180), ("14", "IMU_MOSI", 180), ("1", "IMU_MISO", 180), ("12", "IMU_CS", 180),
                         ("4", "IMU_INT1", 0)):
        end = (u3[pin][0] + (5.08 if a == 0 else -5.08), u3[pin][1])
        s.w(u3[pin], end)
        s.label(name, end, a)
    # one 3.3 V rail above the part: the VDDIO capacitor on its side, the two VDD capacitors on theirs
    s.w(u3["5"], (u3["5"][0], 25.4))
    s.w(u3["8"], (u3["8"][0], 25.4))
    s.w((30.48, 25.4), (99.06, 25.4))
    s.power("+3V3", (60.96, 25.4))
    for ref, x in (("C23", 30.48), ("C21", 88.9), ("C22", 99.06)):
        s.power("GND", s.place(ref, x, 29.21)["2"])
    # ground under the part: its own pin, the three reserved pins the datasheet wants grounded, and the unused FSYNC
    for p in ("6", "7", "10", "11"):
        s.w(u3[p], (u3[p][0], 63.5))
    s.w((u3["6"][0], 63.5), (81.28, 63.5), (81.28, u3["9"][1]), u3["9"])
    s.power("GND", (71.12, 63.5))
    s.text("Reserved pins 7, 10, 11 and the unused FSYNC go to GND.", 30.48, 72.39)
    s.text("Reserved pins 2 and 3 stay open.", 30.48, 74.93)


def mcu_block(s):
    u1 = s.place("U1", 101.6, 101.6, ref_at=(116.84, 58.42, "left"))
    pin = lambda net: u1[next(n for n, v in PARTS["U1"]["pins"].items() if v == net)]

    # top: supplies. VREG_AVDD is 3.3 V through an RC filter; the core regulator makes 1.1 V through L1.
    r3 = s.place("R3", 64.77, 50.8, a=90)
    c9 = s.place("C9", 73.66, 54.61)
    s.w(u1["46"], (83.82, 50.8), r3["2"])
    s.label("VREG_AVDD", (74.93, 50.8))
    s.power("FLAG", (71.12, 50.8))
    s.w(r3["1"], (58.42, 50.8), (58.42, 48.26))
    s.power("+3V3", (58.42, 48.26))
    s.power("GND", c9["2"])
    for p in ("53", "44", "54", "1", "49"):
        s.w(u1[p], (u1[p][0], 45.72))
    s.w((88.9, 45.72), (104.14, 45.72))
    s.power("+3V3", (93.98, 45.72))
    l1 = s.place("L1", 120.65, 38.1, a=270)
    c7 = s.place("C7", 134.62, 41.91)
    s.w(u1["48"], (106.68, 38.1), l1["2"])
    s.label("VREG_LX", (107.95, 38.1))
    s.w(l1["1"], (139.7, 38.1))
    s.w((127, 38.1), (127, 48.26), (109.22, 48.26), u1["50"])
    s.w(u1["6"], (114.3, 48.26))
    s.power("FLAG", (130.81, 38.1))
    s.power("+1V1", (139.7, 38.1))
    s.power("GND", c7["2"])
    s.w(u1["47"], (99.06, 149.86), (101.6, 149.86), u1["61"])
    s.power("GND", (101.6, 149.86))

    # left: USB series resistors, BOOTSEL button, crystal, SWD connector
    r8 = s.place("R8", 55.88, 86.36, a=90, ref_at=(53.34, 83.82, None), val_at=(58.42, 83.82, None))
    r7 = s.place("R7", 43.18, 88.9, a=90, ref_at=(40.64, 91.44, None), val_at=(45.72, 91.44, None))
    for r, mcu, usb in ((r8, "USB_DM_MCU", "USB_D-"), (r7, "USB_DP_MCU", "USB_D+")):
        s.w(pin(mcu), r["2"])
        s.label(mcu, (59.69, r["2"][1]))
        s.w(r["1"], (33.02, r["1"][1]))
        s.label(usb, (33.02, r["1"][1]), 180)
    r6 = s.place("R6", 60.96, 96.52, a=270)
    sw = s.place("SW1", 40.64, 96.52, ref_at=(36.83, 100.33, "left"), val_at=(41.91, 100.33, "left"))
    s.w(u1["60"], r6["1"])
    s.label("QSPI_SS", (66.04, 96.52))
    s.w(r6["2"], sw["3"])
    s.label("USB_BOOT", (46.99, 96.52))
    s.w(sw["1"], (33.02, 96.52), (33.02, 99.06))
    s.power("GND", (33.02, 99.06))

    x1 = s.place("X1", 60.96, 121.92, a=270, ref_at=(68.58, 120.65, None), val_at=(69.85, 123.19, None))
    c3 = s.place("C3", 44.45, 116.84, a=270, ref_at=(41.91, 113.03, None), val_at=(46.99, 113.03, None))
    c4 = s.place("C4", 44.45, 127, a=270, ref_at=(41.91, 130.81, None), val_at=(46.99, 130.81, None))
    r2_ = s.place("R2", 67.31, 127, a=270, ref_at=(64.77, 129.54, None), val_at=(69.85, 129.54, None))
    s.w(u1["21"], c3["1"])
    s.w((60.96, 116.84), x1["1"])
    s.label("XIN", (66.04, 116.84))
    s.w(u1["22"], r2_["1"])
    s.label("XOUT", (71.12, 127))
    s.w(r2_["2"], c4["1"])
    s.w((60.96, 127), x1["3"])
    s.label("XTAL_OUT", (49.53, 127))
    s.w(c3["2"], c4["2"])
    s.w(x1["2"], (40.64, 121.92))
    s.power("GND", c4["2"])

    j4 = s.place("J4", 40.64, 137.16, mirror="y", ref_at=(36.83, 135.89, "right"), val_at=(36.83, 138.43, "right"))
    s.w(j4["1"], u1["24"])
    s.label("SWCLK", (55.88, 134.62))
    # SWDIO drops below the ground pin's symbol before it runs to the MCU
    s.w(j4["3"], (48.26, 139.7), (48.26, 144.78), (71.12, 144.78), (71.12, 137.16), u1["25"])
    s.label("SWDIO", (55.88, 144.78))
    s.w(j4["2"], (53.34, 137.16))
    s.power("GND", (53.34, 137.16))
    s.power("GND", j4["MP"])

    # right: GPS connector straight across from UART0, signals that leave the block, status LED
    j5 = s.place("J5", 172.72, 63.5, ref_at=(176.53, 63.5, "left"), val_at=(176.53, 66.04, "left"))
    s.w(u1["2"], j5["2"])
    s.label("GPS_TX", (129.54, 63.5))
    s.w(u1["3"], j5["3"])
    s.label("GPS_RX", (129.54, 66.04))
    s.w(j5["1"], (162.56, 60.96))
    s.power("+3V3", (162.56, 60.96))
    s.w(j5["4"], (162.56, 68.58))
    s.power("GND", (162.56, 68.58))
    s.power("GND", j5["MP"])
    s.text("Pins 1-4: 3V3, MCU TX, MCU RX, GND", 147.32, 80.01)
    for name in [f"PWM{i}_MCU" for i in range(1, 9)] + ["IMU_MISO", "IMU_CS", "IMU_SCK", "IMU_MOSI", "IMU_INT1",
                                                         "VBAT_SENSE"]:
        end = (132.08, pin(name)[1])
        s.w(pin(name), end)
        s.label(name, end)
    r19 = s.place("R19", 142.24, 127, a=90, ref_at=(139.7, 124.46, None), val_at=(144.78, 124.46, None))
    d3 = s.place("D3", 161.29, 127, a=180)
    s.w(u1["37"], r19["1"])
    s.label("LED", (129.54, 127))
    s.w(r19["2"], d3["2"])
    s.label("LED_A", (147.32, 127))
    s.w(d3["1"], (167.64, 127), (167.64, 129.54))
    s.power("GND", (167.64, 129.54))


def outputs_block(s):
    last = 0
    for i in range(1, 9):
        y = 20.32 + 12.7 * (i - 1)
        r = s.place(f"R{10 + i}", 24.13, y, a=90, ref_at=(21.59, y - 2.54, None), val_at=(26.67, y - 2.54, None))
        j = s.place(f"J{6 + i}", 43.18, y + 2.54, ref_at=(46.99, y + 1.27, "left"), val_at=(46.99, y + 3.81, "left"))
        s.w(r["1"], (17.78, y))
        s.label(f"PWM{i}_MCU", (17.78, y), 180)
        s.w(r["2"], j["1"])
        s.label(f"PWM{i}", (29.21, y))
        s.w(j["2"], (5.08, j["2"][1]))
        s.w(j["3"], (35.56, j["3"][1]))
        s.power("GND", (35.56, j["3"][1]))
        last = j["2"][1]
    s.w((7.62, 12.7), (5.08, 12.7), (5.08, last))
    s.label("SERVO_V", (7.62, 12.7))
    s.text("SERVO_V comes from the ESC's BEC through any", 5.08, 5.08)
    s.text("header. The board supply does not feed it.", 5.08, 7.62)


def decoupling_block(s):
    rows = ((20.32, "+3V3", ["C6"] + [f"C{n}" for n in range(12, 19)], "C6: core regulator input. 100 nF: at the 3.3 V supply pins."),
            (48.26, "+1V1", ["C8", "C10", "C11"], "At the DVDD (core) pins."))
    for y, rail, refs, note in rows:
        xs = [20.32 + 10.16 * i for i in range(len(refs))]
        for ref, x in zip(refs, xs):
            s.place(ref, x, y + 3.81)
        s.w((12.7, y), (xs[-1], y))
        s.power(rail, (12.7, y))
        s.w((12.7, y + 7.62), (xs[-1], y + 7.62))
        s.power("GND", (12.7, y + 7.62))
        s.text(note, 20.32, y - 5.08)
    for i in range(4):
        x = 20.32 + 15.24 * i
        s.place(f"H{i + 1}", x, 76.2, ref_at=(x, 72.39, None), val_at=(x, 80.01, None))
    s.text("Mounting holes, 30.5 mm pattern, not connected.", 20.32, 68.58)


if __name__ == "__main__":
    sheet = Sheet()
    sheet.block("Power: 2S LiPo or USB to 3.3 V", 0, 0, power_block)
    sheet.block("MCU RP2354A, GPS, SWD, status LED", 0, 1, mcu_block)
    sheet.block("USB-C", 1, 0, usb_block)
    sheet.block("Servo / ESC outputs", 1, 1, outputs_block)
    sheet.block("IMU ICM-42688-P (SPI0)", 2, 0, imu_block)
    sheet.block("MCU decoupling, mounting holes", 2, 1, decoupling_block)
    sheet.arrange()
    sheet.finish()
