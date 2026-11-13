#!/bin/sh
# Fabrication package for PCBWay from hw/fc.kicad_pcb (run scripts/build.sh first).
# Output: build/fab/ with gerbers zip, BOM, pick-and-place, assembly drawing and schematic PDF.
set -e
cd "$(dirname "$0")/.."
K=/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli
KP=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3
quiet() { grep -v -E "wxApp|stdpbase|swig|Debug|Fontconfig" || true; }
REV=$(python3 -c "import sys; sys.path.insert(0, 'scripts'); from design import REV; print(REV)")
OUT=build/fab
rm -rf $OUT && mkdir -p $OUT/gerbers
$K pcb export gerbers -o $OUT/gerbers --check-zones \
  -l F.Cu,B.Cu,F.Paste,B.Paste,F.Silkscreen,B.Silkscreen,F.Mask,B.Mask,Edge.Cuts hw/fc.kicad_pcb 2>&1 | quiet
$K pcb export drill -o $OUT/gerbers/ --excellon-separate-th --generate-map --map-format gerberx2 hw/fc.kicad_pcb 2>&1 | quiet
(cd $OUT/gerbers && zip -q ../fc-gerbers-rev$REV.zip *)
$KP scripts/cpl.py $OUT/fc-cpl-rev$REV.csv 2>&1 | quiet
# the silkscreen has no reference designators: this drawing is what tells the assembler which part is which
$K pcb export pdf --mode-single --layers F.Fab,F.Silkscreen,Edge.Cuts -o $OUT/fc-assembly-rev$REV.pdf hw/fc.kicad_pcb 2>&1 | quiet
python3 scripts/bom.py $OUT/fc-bom-rev$REV.csv
$K sch export pdf -o $OUT/fc-schematic-rev$REV.pdf hw/fc.kicad_sch 2>&1 | quiet
if command -v pdftoppm >/dev/null; then pdftoppm -png -r 200 -singlefile $OUT/fc-schematic-rev$REV.pdf $OUT/fc-schematic-rev$REV; fi
ls -1 $OUT
