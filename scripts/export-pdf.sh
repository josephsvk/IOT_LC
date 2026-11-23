#!/usr/bin/env bash
# Generate schematic/PCB PDFs and top/bottom 3D PCB renders, then README previews.
# Uses the project configured in .kicad-automation.conf.
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
source "$ROOT/.kicad-automation.conf"
: "${PROJECT_NAME:?Missing PROJECT_NAME}"
SCH="$ROOT/$PROJECT_NAME.kicad_sch"
PCB="$ROOT/$PROJECT_NAME.kicad_pcb"
PDF_DIR="$ROOT/docs/pdf"
for cmd in kicad-cli pdftoppm pdfinfo python3; do
  command -v "$cmd" >/dev/null || { echo "Missing dependency: $cmd" >&2; exit 1; }
done
python3 -c 'from PIL import Image' >/dev/null || { echo 'Install python3-pil (Pillow)' >&2; exit 1; }
[[ -f "$SCH" && -f "$PCB" ]] || { echo "Missing schematic or PCB for $PROJECT_NAME" >&2; exit 1; }
mkdir -p "$PDF_DIR"
# Do not recursively export all .kicad_sch files: unused draft sheets must not appear.
echo '[1/6] Active hierarchical schematic'
kicad-cli sch export pdf --no-background-color -o "$PDF_DIR/schematic.pdf" "$SCH"
echo '[2/6] PCB front (F.Cu + F.SilkS)'
kicad-cli pcb export pdf --mode-single --layers 'F.Cu,F.SilkS,Edge.Cuts' --check-zones -o "$PDF_DIR/pcb-front.pdf" "$PCB"
echo '[3/6] PCB back (B.Cu + B.SilkS)'
kicad-cli pcb export pdf --mode-single --layers 'B.Cu,B.SilkS,Edge.Cuts' --check-zones -o "$PDF_DIR/pcb-back.pdf" "$PCB"
echo '[4/6] Clean PCB 3D renders (F.SilkS + B.SilkS; green board stackup; no DNP)'
python3 "$ROOT/scripts/render-pcb-3d.py" --no-dnp
rm -f "$PDF_DIR/pcb-layers.pdf"
echo '[6/6] Cropped PNG previews and README'
python3 "$ROOT/scripts/generate-readme.py"
python3 "$ROOT/scripts/check-docs.py"
echo 'Documentation export passed'
