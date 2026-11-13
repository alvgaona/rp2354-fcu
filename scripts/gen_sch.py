"""Generate hw/fc.kicad_sch from design.py. Every pin gets a net label or a no-connect flag."""
import math
import sys
import uuid
from datetime import date

from design import PARTS, POWER_FLAGS, REV, TITLE
from sexpr import ROOT, Sym, dump, find, first, get_symbol, pins

PROJECT = "fc"
NS = uuid.UUID("6b1f0c1e-4a7e-4a53-9a43-2b9f1f4c0d01")
ROOT_UUID = str(uuid.uuid5(NS, "root"))
G = 1.27  # schematic grid
CHAR = 1.25  # approx global-label width per char incl. flag (mm)
PAGE_W, PAGE_H = 420, 297  # A3
GROUP_TITLES = {"mcu": "MCU RP2354A + core regulator + crystal", "usb": "USB-C", "ctl": "Buttons / SWD / LED",
                "pwr": "Power: 2S LiPo / USB -> 3.3 V", "imu": "IMU ICM-42688-P (SPI0)",
                "ext": "GPS + servo/ESC outputs", "flags": "Power flags"}


def uid(*k):
    return str(uuid.uuid5(NS, "/".join(map(str, k))))


def snap(v):
    return round(v / G) * G


def rot(x, y, a):
    r = math.radians(a)
    return x * math.cos(r) - y * math.sin(r), x * math.sin(r) + y * math.cos(r)


def placed_pins(symdef, a):
    """Pins in schematic orientation relative to symbol origin (y down), with outward label angle."""
    out = {}
    for num, (name, x, y, pa, _) in pins(symdef).items():
        rx, ry = rot(x, y, a)
        # pin angle points from connection point into the body; label goes the other way
        out[num] = (round(rx, 3), round(-ry, 3), (pa + a + 180) % 360)
    return out


def font(size=1.27):
    return [Sym("effects"), [Sym("font"), [Sym("size"), size, size]]]


def label_just(angle):
    return Sym("left") if angle in (0, 90) else Sym("right")


def build():
    symdefs, items = {}, []
    # ---- layout: flow parts into columns, grouped ----
    groups = {}
    for ref, p in PARTS.items():
        groups.setdefault(p["group"], []).append(ref)
    groups["flags"] = [f"#FLG{i + 1}" for i in range(len(POWER_FLAGS))]
    flag_net = {f"#FLG{i + 1}": n for i, n in enumerate(POWER_FLAGS)}

    def info(ref):
        sym = "power:PWR_FLAG" if ref.startswith("#FLG") else PARTS[ref]["sym"]
        if sym not in symdefs:
            symdefs[sym] = get_symbol(sym)
        pp = pins(symdefs[sym])
        a = 90 if pp and len(pp) == 2 and all(abs(v[1]) < 1e-6 for v in pp.values()) else 0
        pl = placed_pins(symdefs[sym], a)
        netof = {"1": flag_net[ref]} if ref.startswith("#FLG") else PARTS[ref]["pins"]
        xs = [v[0] for v in pl.values()] or [0]
        ys = [v[1] for v in pl.values()] or [0]
        ext = {0: 0, 90: 0, 180: 0, 270: 0}
        for num, (x, y, la) in pl.items():
            n = netof.get(num)
            ext[la] = max(ext[la], (len(n) * CHAR + 2) if n else 1.5)
        box = (min(xs) - ext[180], max(xs) + ext[0], min(ys) - ext[90] - 4, max(ys) + ext[270] + 4)
        return sym, a, pl, netof, box

    x0, y0, colw = 15.0, 25.0, 0.0
    x, y = x0, y0
    layout = []
    for gname in ["mcu", "usb", "ctl", "pwr", "imu", "ext", "flags"]:
        refs = sorted(groups[gname], key=lambda r: (not r.startswith(("U", "J", "X", "SW")), r[0], int("".join(c for c in r if c.isdigit()) or 0)))
        # group title
        if y > y0 + 1 and y + 30 > PAGE_H - 20:
            x, y, colw = x + colw + 10, y0, 0.0
        layout.append(("title", gname, x, y))
        colw = max(colw, len(GROUP_TITLES[gname]) * 1.9)
        y += 6
        for ref in refs:
            sym, a, pl, netof, box = info(ref)
            w, h = box[1] - box[0], box[3] - box[2]
            if y + h > PAGE_H - 20:
                x, y, colw = x + colw + 10, y0, 0.0
            sx, sy = snap(x - box[0]), snap(y - box[2])
            layout.append(("part", ref, sx, sy, sym, a, pl, netof, box))
            colw = max(colw, w)
            y += h + 3
        y += 6
    if x + colw > PAGE_W - 10:
        sys.exit(f"schematic layout overflows page width ({x + colw:.0f} mm)")

    # ---- emit ----
    for entry in layout:
        if entry[0] == "title":
            _, g, tx, ty = entry
            items.append([Sym("text"), GROUP_TITLES[g], [Sym("exclude_from_sim"), Sym("no")],
                          [Sym("at"), snap(tx), snap(ty), 0],
                          [Sym("effects"), [Sym("font"), [Sym("size"), 2, 2], [Sym("bold"), Sym("yes")]],
                           [Sym("justify"), Sym("left"), Sym("bottom")]], [Sym("uuid"), uid("title", g)]])
            continue
        _, ref, sx, sy, sym, a, pl, netof, box = entry
        is_flag = ref.startswith("#FLG")
        p = None if is_flag else PARTS[ref]
        props = [("Reference", ref, sx, sy + box[2] + 3, False),
                 ("Value", "PWR_FLAG" if is_flag else p["value"], sx, sy + box[3] - 2, False),
                 ("Footprint", "" if is_flag else p["fp"], sx, sy, True),
                 ("Datasheet", "~", sx, sy, True),
                 ("Description", "", sx, sy, True)]
        if not is_flag:
            props += [("MPN", p["mpn"], sx, sy, True), ("Manufacturer", p["mfr"], sx, sy, True), ("LCSC", p["lcsc"], sx, sy, True)]
        node = [Sym("symbol"), [Sym("lib_id"), sym], [Sym("at"), sx, sy, a], [Sym("unit"), 1],
                [Sym("exclude_from_sim"), Sym("no")], [Sym("in_bom"), Sym("no") if is_flag or not p["mpn"] else Sym("yes")],
                [Sym("on_board"), Sym("no") if is_flag else Sym("yes")], [Sym("dnp"), Sym("no")],
                [Sym("uuid"), uid("sym", ref)]]
        for k, v, px, py, hide in props:
            eff = font() + ([[Sym("hide"), Sym("yes")]] if hide else [])
            node.append([Sym("property"), k, v, [Sym("at"), snap(px), snap(py), a], eff])
        for num in pl:
            node.append([Sym("pin"), num, [Sym("uuid"), uid("pin", ref, num)]])
        node.append([Sym("instances"), [Sym("project"), PROJECT, [Sym("path"), "/" + ROOT_UUID,
                                                                   [Sym("reference"), ref], [Sym("unit"), 1]]]])
        items.append(node)
        # labels / no-connects, one per connection point (stacked pins share a point)
        seen = {}
        for num, (px, py, la) in pl.items():
            pt = (round(sx + px, 2), round(sy + py, 2))
            net = netof.get(num)
            if pt in seen:
                if seen[pt] != net:
                    sys.exit(f"{ref}: stacked pins at {pt} on different nets {seen[pt]} / {net}")
                continue
            seen[pt] = net
            if net:
                # global labels: net names match the PCB exactly (local labels would add a "/" prefix)
                items.append([Sym("global_label"), net, [Sym("shape"), Sym("passive")], [Sym("at"), pt[0], pt[1], la],
                              [Sym("fields_autoplaced"), Sym("yes")],
                              [Sym("effects"), [Sym("font"), [Sym("size"), 1.27, 1.27]], [Sym("justify"), label_just(la)]],
                              [Sym("uuid"), uid("label", ref, num)],
                              [Sym("property"), "Intersheetrefs", "${INTERSHEET_REFS}", [Sym("at"), pt[0], pt[1], 0],
                               [Sym("effects"), [Sym("font"), [Sym("size"), 1.27, 1.27]], [Sym("hide"), Sym("yes")]]]])
            else:
                items.append([Sym("no_connect"), [Sym("at"), pt[0], pt[1]], [Sym("uuid"), uid("nc", ref, num)]])

    sch = [Sym("kicad_sch"), [Sym("version"), 20231120], [Sym("generator"), "eeschema"],
           [Sym("generator_version"), "8.0"], [Sym("uuid"), ROOT_UUID], [Sym("paper"), "A3"],
           [Sym("title_block"), [Sym("title"), TITLE], [Sym("date"), date.today().isoformat()], [Sym("rev"), REV],
            [Sym("comment"), 1, "Generated by scripts/gen_sch.py from scripts/design.py - edit design.py, not this file"]],
           [Sym("lib_symbols")] + list(symdefs.values())] + items + \
          [[Sym("sheet_instances"), [Sym("path"), "/", [Sym("page"), "1"]]]]
    out = ROOT / "hw" / f"{PROJECT}.kicad_sch"
    out.write_text(dump(sch) + "\n")
    print("wrote", out, len(layout), "entries")


if __name__ == "__main__":
    build()
