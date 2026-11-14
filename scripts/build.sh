#!/usr/bin/env bash
# Check the KiCad design and export everything needed to order and view the board, into build/.
#
#   pixi run build      (or scripts/build.sh, with any Python 3 on PATH)
#
# Runs on macOS and Linux. Tools are found on PATH or in their usual macOS install places;
# set KICAD_CLI, KICAD_PYTHON or PYTHON to point at one explicitly.
# hw/ is the source: edit it in KiCad. Any ERC, DRC or layout error stops the build before anything is exported.
set -e -o pipefail
cd "$(dirname "$0")/.."

BOARD=fc
SCH=hw/$BOARD.kicad_sch
PCB=hw/$BOARD.kicad_pcb
OUT=build

# Print the first tool that exists: a bare name is looked up on PATH, a path must be executable.
find_tool() {
  for t in "$@"; do
    case $t in
      */*) if [ -x "$t" ]; then echo "$t"; return 0; fi ;;
      *) if command -v "$t" 2>/dev/null; then return 0; fi ;;
    esac
  done
  return 1
}

KICAD_APP=/Applications/KiCad/KiCad.app/Contents
KICAD_CLI=${KICAD_CLI:-$(find_tool kicad-cli $KICAD_APP/MacOS/kicad-cli || true)}
PYTHON=${PYTHON:-$(find_tool python3 || true)}
# The Python that has KiCad's pcbnew module: KiCad's own on macOS, the system one on Linux (pixi's has none).
KICAD_PYTHON=${KICAD_PYTHON:-$(find_tool $KICAD_APP/Frameworks/Python.framework/Versions/Current/bin/python3 /usr/bin/python3 python3 || true)}
[ -n "$KICAD_CLI" ] || { echo "kicad-cli not found: install KiCad or set KICAD_CLI"; exit 1; }
[ -n "$PYTHON" ] || { echo "Python 3 not found: install it or set PYTHON"; exit 1; }

# Drop kicad-cli's progress chatter; reports and real errors still show.
quiet() {
  grep -v -E "wxApp|stdpbase|swig|Debug|Fontconfig|Plotted to|Created file|^Done|Loading|Writing|NSCocoaErrorDomain|file .* created|Export time|Wrote position data|^$" || true
}

# kicad-cli, quietly. A kicad-cli failure still stops the build (pipefail).
kicad() {
  "$KICAD_CLI" "$@" 2>&1 | quiet
}

# Electrical rules check of the schematic. It has no known warnings.
check_erc() {
  kicad sch erc --severity-all -o "$OUT/erc.rpt" "$SCH"
  if grep -q '; error' "$OUT/erc.rpt"; then
    cat "$OUT/erc.rpt"
    exit 1
  fi
}

# Design rules check of the board, including that it matches the schematic (schematic parity).
# Known warnings: the line width of the back text (4), and J1's silkscreen at the board edge (2), where the
# USB-C connector overhangs. Errors, unconnected pads or parity issues fail.
check_drc() {
  kicad pcb drc --schematic-parity --severity-all -o "$OUT/drc.rpt" "$PCB"
  if ! grep -q 'Found 0 unconnected pads' "$OUT/drc.rpt" || ! grep -q 'Found 0 Footprint errors' "$OUT/drc.rpt" \
      || grep -q '; error' "$OUT/drc.rpt"; then
    grep -E -A3 '; error|^\*\* Found' "$OUT/drc.rpt"
    exit 1
  fi
}

# What DRC cannot check: a ground via at every ground pad, the ground pour in one solid piece,
# no pad fed only by a thin 3.3 V track, and nothing drilled under the IMU.
check_layout() {
  "$KICAD_PYTHON" scripts/check_layout.py "$PCB" 2>&1 | quiet
}

# The schematic as a PDF.
export_schematic() {
  kicad sch export pdf -o "$OUT/$BOARD-schematic.pdf" "$SCH"
}

# Gerbers and drill files (plated and unplated holes apart), zipped for the PCB order.
export_gerbers() {
  rm -rf "$OUT/gerbers" && mkdir "$OUT/gerbers"
  kicad pcb export gerbers --check-zones --layers F.Cu,B.Cu,F.Paste,B.Paste,F.Silkscreen,B.Silkscreen,F.Mask,B.Mask,Edge.Cuts \
    -o "$OUT/gerbers/" "$PCB"
  kicad pcb export drill --excellon-separate-th -o "$OUT/gerbers/" "$PCB"
  rm -f "$OUT/$BOARD-gerbers.zip"
  (cd "$OUT/gerbers" && "$PYTHON" -m zipfile -c "../$BOARD-gerbers.zip" "$BOARD"*)
}

# The assembled board in 3D, every part's model in one GLB, for Blender or descent.
export_3d() {
  kicad pcb export glb -f --subst-models --include-tracks --include-pads --include-zones --include-silkscreen \
    --include-soldermask -o "$OUT/$BOARD.glb" "$PCB"
}

# JLCPCB assembly files for the SMD parts, BOM and pick-and-place (CPL), to upload with the Gerber zip.
# Through-hole parts are soldered by hand.
export_jlcpcb() {
  kicad sch export bom --fields "Value,Reference,Footprint,LCSC" --labels "Comment,Designator,Footprint,LCSC Part #" \
    --group-by "Value,LCSC" --ref-range-delimiter "" -o "$OUT/bom-all.csv" "$SCH"
  kicad pcb export pos --format csv --units mm --side front --smd-only -o "$OUT/pos-smd.csv" "$PCB"
  "$PYTHON" scripts/jlc.py "$OUT/bom-all.csv" "$OUT/pos-smd.csv" "$OUT"
}

# Everything above plus the KiCad sources, in one zip that descent (the board viewer) opens.
package() {
  "$PYTHON" scripts/package.py "$BOARD" "$OUT"
}

main() {
  mkdir -p "$OUT"
  check_erc
  check_drc
  check_layout
  export_schematic
  export_gerbers
  export_3d
  export_jlcpcb
  package
}

main "$@"
