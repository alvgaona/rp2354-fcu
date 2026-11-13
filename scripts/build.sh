#!/bin/sh
# Full pipeline: schematic -> ERC -> netlist check -> PCB placement -> autoroute -> pours -> DRC -> layout check.
# Usage: scripts/build.sh [path to RPI-RP2350A-MINIMAL_R4-S1.kicad_pcb]  (default: the copy in ref/)
set -e -o pipefail  # a failing step must stop the build even when its output is piped
cd "$(dirname "$0")/.."
REF=${1:-ref/RPI-RP2350A-MINIMAL_R4-S1_public/RPI-RP2350A-MINIMAL_R4-S1.kicad_pcb}
[ -f "$REF" ] || { echo "missing $REF: unzip https://datasheets.raspberrypi.com/rp2350/Minimal-KiCAD.zip into ref/"; exit 1; }
K=/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli
KP=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3
quiet() { grep -v -E "wxApp|stdpbase|swig|Debug|Fontconfig" || true; }
mkdir -p build
python3 scripts/gen_sch.py
$K sch erc --severity-all --exit-code-violations -o build/erc.rpt hw/fc.kicad_sch 2>&1 | quiet
$K sch export netlist --format kicadxml -o build/fc.net.xml hw/fc.kicad_sch 2>&1 | quiet
python3 scripts/check_netlist.py build/fc.net.xml
# Freerouting gives the same result for the same input, and -mp makes no difference here. What does change
# its result is the order of items in the board file, which follows the IDs KiCad hands out: FC_SEED fixes
# those. Try seeds in order and keep the first board that passes DRC and the layout check.
# GND is not routed: build_pcb.py gives every ground pad its own via to the bottom pour.
for seed in 1 2 3 4 5 6 7 8 9 10 11 12; do
  export FC_SEED=$seed
  $KP scripts/build_pcb.py place "$REF" > build/place.log 2>&1 || { quiet < build/place.log; exit 1; }
  (cd hw && pixi run --manifest-path ../pixi.toml java -Djava.awt.headless=true -jar ../freerouting-2.5.0.jar \
      --gui.enabled=false --router.neck_width_um=120 --router.automatic_neckdown=false \
      --router.autorouter.ignore_net_classes=GND --router.scoring.via_costs=300 \
      -de fc.dsn -do fc.ses -mp 100 > ../build/freerouting.log 2>&1)
  $KP scripts/build_pcb.py finish > build/finish.log 2>&1 || { quiet < build/finish.log; exit 1; }
  $K pcb drc --schematic-parity --format json -o build/drc.json hw/fc.kicad_pcb 2>&1 | quiet
  if python3 -c "
import json, sys
d = json.load(open('build/drc.json'))
bad = len(d['unconnected_items']) + len(d['schematic_parity']) + sum(v['severity'] == 'error' for v in d['violations'])
print(f'unconnected {len(d[\"unconnected_items\"])}, errors', [v['type'] for v in d['violations'] if v['severity'] == 'error'])
sys.exit(1 if bad else 0)" && $KP scripts/check_layout.py > build/layout.txt 2>&1; then echo "seed $seed: clean"; break; fi
  echo "seed $seed: not clean, trying the next"
done
python3 scripts/drc_summary.py build/drc.json
$KP scripts/check_layout.py 2>&1 | quiet
