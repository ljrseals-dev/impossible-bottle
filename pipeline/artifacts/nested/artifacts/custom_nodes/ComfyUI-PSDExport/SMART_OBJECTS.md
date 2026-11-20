# Smart Objects Status

## What works (verified)

- **Raster layered PSD** via `psd_writer.write_layered_psd` — RLE, RGBA, psd-tools + Photoshop readable.
- `PSDAssemble` with `smart_objects=False` (default).

## Experimental

- `smart_object_writer.py` emits `8BIM/SoLd` + `8BIM/lnk2` blocks (count matches layer count).
- Descriptor OSType layout is still rejected by psd-tools (`b'\x00\x00lo' is not a valid OSType`).
- Do **not** rely on this for production until a Photoshop-saved template is used.

## Recommended path for real smart objects

```bash
./install_psd_tools.sh /path/to/ComfyUI
# uses coeyes/ComfyUI-PSD-Layers → Save Seedream Layers PSD
```

Or extract a SoLd template from a one-layer Photoshop smart-object PSD and splice it (see earlier template-extraction notes).
