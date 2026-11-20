#!/usr/bin/env bash
set -euo pipefail
COMFY="${COMFY_PATH:-$HOME/ComfyUI}"
NODES="$COMFY/custom_nodes"
[ -d "$NODES" ] || { echo "Set COMFY_PATH=/path/to/ComfyUI"; exit 1; }

for pack in ComfyUI-LaDe ComfyUI-OmniPSD ComfyUI-PSDExport; do
  src="$(pwd)/custom_nodes/$pack"; dst="$NODES/$pack"
  if [ -d "$dst" ]; then echo "skip $pack (exists)"; continue; fi
  cp -r "$src" "$dst"; echo "installed $pack"
  [ -f "$dst/requirements.txt" ] && python -m pip install -r "$dst/requirements.txt" || true
done

if [ ! -d "$NODES/ComfyUI-PSD-Layers" ]; then
  echo ""
  echo "Optional: install coeyes/ComfyUI-PSD-Layers for native smart objects?"
  read -p "  [y/N] " -n 1 -r; echo
  if [[ ${REPLY:-} =~ ^[Yy]$ ]]; then
    git clone https://github.com/coeyes/ComfyUI-PSD-Layers "$NODES/ComfyUI-PSD-Layers"
    [ -f "$NODES/ComfyUI-PSD-Layers/requirements.txt" ] && \
      python -m pip install -r "$NODES/ComfyUI-PSD-Layers/requirements.txt" || true
  fi
fi

echo "Done. Restart ComfyUI."
