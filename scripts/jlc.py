"""Turn KiCad's BOM and placement exports into the two files JLCPCB's assembly order takes.

    python3 scripts/jlc.py <bom.csv> <pos.csv> <out dir>

  <bom.csv>  every part, from `kicad-cli sch export bom` (columns already named as JLCPCB wants)
  <pos.csv>  the SMD parts only, from `kicad-cli pcb export pos --smd-only`

It writes:
  fc-cpl.csv  where each SMD part goes: KiCad's columns, renamed to JLCPCB's
  fc-bom.csv  what to buy for those parts: the BOM minus the through-hole parts (the servo headers
              and the battery connector), which are soldered by hand
"""
import csv
import sys


def read_placements(pos_csv):
    """KiCad's placement rows, one per SMD part."""
    with open(pos_csv, newline="") as f:
        return list(csv.DictReader(f))


def write_cpl(placements, out_csv):
    """The placement file, with JLCPCB's column names and 'Top' for KiCad's 'top'."""
    with open(out_csv, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        for p in placements:
            w.writerow([p["Ref"], p["PosX"], p["PosY"], p["Side"].capitalize(), p["Rot"]])


def write_smd_bom(bom_csv, smd_refs, out_csv):
    """The BOM, keeping only the references JLCPCB places. Returns the placed parts with no LCSC number."""
    no_lcsc = []
    with open(bom_csv, newline="") as f, open(out_csv, "w", newline="") as g:
        bom, w = csv.DictReader(f), csv.writer(g)
        w.writerow(bom.fieldnames)
        for line in bom:  # one line per group of identical parts, e.g. Designator "C2,C3,C8"
            refs = [r for r in line["Designator"].split(",") if r in smd_refs]
            if not refs:
                continue  # all through-hole
            line["Designator"] = ",".join(refs)
            w.writerow(line.values())
            if not line["LCSC Part #"]:
                no_lcsc += refs
    return no_lcsc


def main():
    bom_csv, pos_csv, out = sys.argv[1:]
    placements = read_placements(pos_csv)
    write_cpl(placements, f"{out}/fc-cpl.csv")
    no_lcsc = write_smd_bom(bom_csv, {p["Ref"] for p in placements}, f"{out}/fc-bom.csv")

    print(f"JLCPCB files: {len(placements)} SMD parts")
    if no_lcsc:
        print(f"  No LCSC number, so pick one or place by hand: {', '.join(no_lcsc)}")


main()
