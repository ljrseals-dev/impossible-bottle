#!/usr/bin/env bash
set -euo pipefail

COMFY="${COMFY_PATH:-$HOME/ComfyUI}"
NODES="$COMFY/custom_nodes"
ROOT="$(cd "$(dirname "$0")" && pwd)"

if [ ! -d "$NODES" ]; then
  echo "ComfyUI custom_nodes not found at $NODES"
  echo "Set COMFY_PATH=/path/to/ComfyUI and rerun"
  exit 1
fi

echo "Installing into $NODES"
for pack in ComfyUI-LaDe ComfyUI-OmniPSD ComfyUI-PSDExport; do
  src="$ROOT/custom_nodes/$pack"
  dst="$NODES/$pack"
  if [ -d "$dst" ]; then
    echo "  $pack already exists — skipping (rm -rf to reinstall)"
    continue
  fi
  cp -r "$src" "$dst"
  echo "  installed $pack"
  if [ -f "$dst/requirements.txt" ]; then
    python -m pip install -r "$dst/requirements.txt" || true
  fi
done

if [ ! -f "$NODES/ComfyUI-PSDExport/psd_writer.py" ]; then
  cp "$NODES/ComfyUI-OmniPSD/psd_writer.py" "$NODES/ComfyUI-PSDExport/psd_writer.py"
fi

echo "Done. Restart ComfyUI."
