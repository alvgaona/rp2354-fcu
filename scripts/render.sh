#!/bin/sh
# render.sh <out.png> [layers]  - plot hw/fc.kicad_pcb board area to a PNG (board at 100..140 mm on the page)
set -e
OUT=$1; LAYERS=${2:-F.Cu,B.Cu,F.Silkscreen,F.Courtyard,F.Fab,Edge.Cuts}
K=/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli
cd "$(dirname "$0")/.."
$K pcb export pdf --mode-single --layers "$LAYERS" -o "$OUT.pdf" hw/fc.kicad_pcb >/dev/null 2>&1
sips -s format png -Z 6000 "$OUT.pdf" --out "$OUT.full.png" >/dev/null
# A4 landscape 297 mm -> 6000 px; crop 96..144 mm
PX=$(python3 -c "print(6000/297)")
python3 - "$OUT.full.png" "$OUT" "$PX" <<'PY'
import subprocess, sys
src, out, px = sys.argv[1], sys.argv[2], float(sys.argv[3])
x0 = int(96*px); y0 = int(96*px); w = int(48*px)
subprocess.run(["sips", "-c", str(w), str(w), "--cropOffset", str(y0), str(x0), src, "--out", out], check=True, capture_output=True)
PY
rm -f "$OUT.pdf" "$OUT.full.png"
echo "$OUT"
