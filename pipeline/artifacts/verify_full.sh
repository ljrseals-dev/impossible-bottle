#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
fail=0

echo "=== 1. Python compile ==="
for f in main.py \
         custom_nodes/ComfyUI-LaDe/nodes.py \
         custom_nodes/ComfyUI-LaDe/stub_repo.py \
         custom_nodes/ComfyUI-OmniPSD/nodes.py \
         custom_nodes/ComfyUI-PSDExport/nodes.py \
         custom_nodes/ComfyUI-PSDExport/psd_writer.py \
         custom_nodes/ComfyUI-PSDExport/smart_object_writer.py \
         custom_nodes/ComfyUI-PSDExport/template_extract.py; do
  python3 -m py_compile "$f" && echo "  ok $f" || fail=$((fail+1))
done

echo "=== 2. Workflow JSON ==="
for f in workflows/*.json; do
  python3 -c "import json;json.load(open('$f'))" && echo "  ok $f" || fail=$((fail+1))
done

echo "=== 3. Raster PSD ==="
python3 - <<'PY'
import sys; sys.path.insert(0, "custom_nodes/ComfyUI-PSDExport")
from pathlib import Path
from PIL import Image
from psd_writer import write_layered_psd
out = Path("outputs/verify_raster.psd"); out.parent.mkdir(exist_ok=True)
write_layered_psd([Image.new("RGBA",(256,256),(i*40,100,200,255)) for i in range(4)], ["a","b","c","d"], out)
assert out.read_bytes()[:4]==b"8BPS"
print(f"  PASS raster: {out.stat().st_size} B")
PY

echo "=== 4. Smart-object SoLd/lnk2 ==="
python3 - <<'PY'
import sys; sys.path.insert(0, "custom_nodes/ComfyUI-PSDExport")
from pathlib import Path
from PIL import Image
from smart_object_writer import write_smart_object_psd
out = Path("outputs/verify_smart.psd")
write_smart_object_psd([Image.new("RGBA",(128,128),(i*60,80,200,255)) for i in range(3)], ["a","b","c"], out)
raw = out.read_bytes()
assert raw.count(b"8BIMSoLd")==3, raw.count(b"8BIMSoLd")
assert raw.count(b"8BIMlnk2")==3
print(f"  PASS smart: 3 SoLd, 3 lnk2, {out.stat().st_size} B")
PY

echo "=== 5. Template extractor ==="
python3 - <<'PY'
import sys; sys.path.insert(0, "custom_nodes/ComfyUI-PSDExport")
from pathlib import Path
from PIL import Image
from smart_object_writer import write_smart_object_psd
from template_extract import extract_template, template_to_token, token_to_template
ref = Path("outputs/verify_ref.psd")
write_smart_object_psd([Image.new("RGBA",(128,128))], ["layer"], ref)
t = extract_template(ref)
assert t["sold_uuid_off"] >= 0 and t["lnk2_size_off"] > 0
assert token_to_template(template_to_token(t))["sold_template"] == t["sold_template"]
print(f"  PASS extractor: uuid={t['sold_uuid_off']} size={t['lnk2_size_off']}")
PY

echo "=== 6. LaDe stub ==="
python3 - <<'PY'
import sys; sys.path.insert(0, "custom_nodes/ComfyUI-LaDe")
from stub_repo import generate
out = generate("test", ["a","b","c"], 64, 64, seed=1)
assert len(out)==3 and all(v.size==(64,64) for v in out.values())
print(f"  PASS stub: {len(out)} layers")
PY

echo "=== 7. OmniPSD stub script ==="
python3 - <<'PY'
import sys, subprocess, tempfile
from pathlib import Path
from PIL import Image
stub = Path("custom_nodes/ComfyUI-OmniPSD/stub_repo/inference/infer_psd_flux.py")
with tempfile.TemporaryDirectory() as td:
    inp = Path(td)/"in"; out = Path(td)/"out"; inp.mkdir(); out.mkdir()
    Image.new("RGBA",(64,64),(128,128,128,255)).save(inp/"test.png")
    src = stub.read_text()
    src = src.replace('INPUT_TXT_DIR = "REPLACE_ME"', f'INPUT_TXT_DIR = "{inp}"')
    src = src.replace('OUTPUT_ROOT = "REPLACE_ME"', f'OUTPUT_ROOT = "{out}"')
    run = Path(td)/"run.py"; run.write_text(src)
    r = subprocess.run([sys.executable, str(run)], capture_output=True, text=True)
    assert r.returncode==0, r.stderr
    assert len(list(out.glob("*.png")))==6
    print("  PASS stub script: 6 output PNGs")
PY

echo "=== 8. Node registration ==="
python3 -c "
from pathlib import Path; import re
src = Path(\"custom_nodes/ComfyUI-PSDExport/nodes.py\").read_text()
block = re.search(r\"NODE_CLASS_MAPPINGS\\s*=\\s*\\{([^}]+)\\}\", src, re.S)
assert block; keys = set(re.findall(r'\"([A-Za-z]+)\"', block.group(1)))
expected = {\"PSDAssemble\",\"PSDAssembleSmart\",\"PSDAssembleSmartTemplate\",\"PSDTemplateExtract\",\"PSDSaveComposite\",\"PSDLayerInfo\"}
assert expected <= keys; print(f\"  PASS: {len(keys)} nodes\")
"
echo ""
echo "=== All checks passed ==="
