#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

echo "=== Python syntax ==="
for f in main.py \
         custom_nodes/ComfyUI-LaDe/nodes.py \
         custom_nodes/ComfyUI-OmniPSD/nodes.py \
         custom_nodes/ComfyUI-PSDExport/nodes.py \
         custom_nodes/ComfyUI-PSDExport/psd_writer.py \
         custom_nodes/ComfyUI-PSDExport/smart_object_writer.py \
         custom_nodes/ComfyUI-PSDExport/template_extract.py; do
  [ -f "$f" ] && python3 -m py_compile "$f" && echo "  ok $f"
done

echo "=== Workflow JSON ==="
for f in workflows/*.json; do
  python3 -c "import json; json.load(open('$f'))" && echo "  ok $f"
done

echo "=== Node class_types ==="
grep -h 'NODE_CLASS_MAPPINGS' -A 15 custom_nodes/*/nodes.py | grep -oE '"[A-Za-z]+"' | sort -u

echo "=== PSD raster round-trip ==="
mkdir -p outputs
PYTHONPATH="${PYTHONPATH:-}:custom_nodes/ComfyUI-PSDExport" python3 - <<'PY'
import sys
sys.path.insert(0, "custom_nodes/ComfyUI-PSDExport")
from pathlib import Path
from PIL import Image
from psd_writer import write_layered_psd
out = Path("outputs/smoke.psd")
imgs = [Image.new("RGBA", (256, 256), (i * 40, 100, 200, 255)) for i in range(4)]
write_layered_psd(imgs, ["a", "b", "c", "d"], out)
assert out.read_bytes()[:4] == b"8BPS"
print(f"  wrote {out} ({out.stat().st_size} bytes)")
try:
    from psd_tools import PSDImage
    psd = PSDImage.open(out)
    print(f"  readback: {len(list(psd))} layers, {psd.width}x{psd.height}")
except ImportError:
    print("  install psd-tools to verify readback")
PY

echo "=== All checks complete ==="
