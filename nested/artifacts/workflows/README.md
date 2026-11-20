# Workflows

## PSD export paths

| Path | Node | Status |
|------|------|--------|
| Raster (default) | `PSDAssemble` | Verified |
| Smart (coeyes) | `PSDAssembleSmart` | Upstream-maintained |
| Smart (template) | `PSDAssembleSmartTemplate` + `PSDTemplateExtract` | Version-pinned |
| Reference only | `smart_object_writer.py` | Not wired |

## Install

```bash
COMFY_PATH=/path/to/ComfyUI ./install_nodes.sh
# optional coeyes for native smart objects
```

## Template workflow (one-time per Photoshop version)

1. Photoshop: new PSD → 1 layer → Convert to Smart Object → save as `template.psd`
2. Put in ComfyUI `input/`
3. Run `PSDTemplateExtract` → copy `template_token`
4. Paste into `PSDAssembleSmartTemplate`

## Custom node packs

| Pack | Nodes |
|------|--------|
| ComfyUI-LaDe | LaDeLoader, LaDeSampler, LaDeDecodeLayers |
| ComfyUI-OmniPSD | OmniPSDLoader, OmniPSDExtractLayers, OmniPSDSavePSD |
| ComfyUI-PSDExport | PSDAssemble, PSDAssembleSmart, PSDAssembleSmartTemplate, PSDTemplateExtract, PSDSaveComposite, PSDLayerInfo |
