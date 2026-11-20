#!/usr/bin/env bash
# Install PSD-related ComfyUI custom nodes (smart-object path)
# Usage: ./install_psd_tools.sh /path/to/ComfyUI
set -euo pipefail

COMFY="${1:-${COMFY_PATH:-$HOME/ComfyUI}}"
NODES="$COMFY/custom_nodes"

if [ ! -d "$NODES" ]; then
  echo "ComfyUI custom_nodes not found at $NODES"
  echo "Usage: $0 /path/to/ComfyUI"
  exit 1
fi

echo "Installing PSD toolchain into $NODES"

install_pack() {
  local name="$1" url="$2"
  local dst="$NODES/$name"
  if [ -d "$dst" ]; then
    echo "  $name already exists — pulling latest"
    git -C "$dst" pull --ff-only || true
    return
  fi
  git clone "$url" "$dst"
  echo "  installed $name"
  if [ -f "$dst/requirements.txt" ]; then
    python -m pip install -r "$dst/requirements.txt" || true
  fi
}

install_pack "ComfyUI-PSD-Layers" \
  "https://github.com/coeyes/ComfyUI-PSD-Layers"

install_pack "Comfyui-HAIGC-PSD" \
  "https://github.com/HAIGC/Comfyui-HAIGC-PSD"

echo ""
echo "Done. Restart ComfyUI."
echo "Smart-object writer: Save Seedream Layers PSD (coeyes)"
echo "Raster assembler:    HAIGC_SavePSD / PSDAssemble (bundled)"
