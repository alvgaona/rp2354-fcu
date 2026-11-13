#!/bin/sh
# Fabrication package for PCBWay from hw/fc.kicad_pcb (run scripts/build.sh first).
# Output: build/fab/ with gerbers zip, BOM, pick-and-place and schematic PDF.
set -e
cd "$(dirname "$0")/.."
K=/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli
quiet() { grep -v -E "wxApp|stdpbase|swig|Debug|Fontconfig" || true; }
REV=$(python3 -c "import sys; sys.path.insert(0, 'scripts'); from design import REV; print(REV)")
OUT=build/fab
rm -rf $OUT && mkdir -p $OUT/gerbers
$K pcb export gerbers -o $OUT/gerbers --check-zones \
  -l F.Cu,B.Cu,F.Paste,B.Paste,F.Silkscreen,B.Silkscreen,F.Mask,B.Mask,Edge.Cuts hw/fc.kicad_pcb 2>&1 | quiet
$K pcb export drill -o $OUT/gerbers/ --excellon-separate-th --generate-map --map-format gerberx2 hw/fc.kicad_pcb 2>&1 | quiet
(cd $OUT/gerbers && zip -q ../fc-gerbers-rev$REV.zip *)
$K pcb export pos --format csv --units mm --side both --exclude-dnp -o $OUT/fc-cpl-rev$REV.csv hw/fc.kicad_pcb 2>&1 | quiet
python3 scripts/bom.py $OUT/fc-bom-rev$REV.csv
$K sch export pdf -o $OUT/fc-schematic-rev$REV.pdf hw/fc.kicad_sch 2>&1 | quiet
ls -1 $OUT
