#!/bin/sh
# zoom.sh <out.png> <cx> <cy> <size_mm> [layers] - zoomed plot around board-relative (cx,cy)
set -e
OUT=$1; CX=$2; CY=$3; SZ=$4; LAYERS=${5:-F.Cu,B.Cu,F.Fab,Edge.Cuts}
cd "$(dirname "$0")/.."
/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli pcb export pdf --mode-single --layers "$LAYERS" -o "$OUT.pdf" hw/fc.kicad_pcb >/dev/null 2>&1
sips -s format png -Z 14000 "$OUT.pdf" --out "$OUT.full.png" >/dev/null
python3 - "$OUT" "$CX" "$CY" "$SZ" <<'PY'
import subprocess, sys
out, cx, cy, sz = sys.argv[1], *map(float, sys.argv[2:5])
px = 14000 / 297
x0, y0, w = int((100 + cx - sz / 2) * px), int((100 + cy - sz / 2) * px), int(sz * px)
subprocess.run(["sips", "-c", str(w), str(w), "--cropOffset", str(y0), str(x0), out + ".full.png", "--out", out], check=True, capture_output=True)
subprocess.run(["sips", "-Z", "900", out], check=True, capture_output=True)
PY
rm -f "$OUT.pdf" "$OUT.full.png"
