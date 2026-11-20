# Workflows

ComfyUI graph definitions for the Impossible Bottle pipeline. Each file
is a `class_type` graph that the FastAPI bridge (`main.py` / `server.py`) injects
prompts into and queues against ComfyUI.

## Files

| File | Stage | Purpose | Custom nodes required |
|---|---|---|---|
| `lade.json` | 1 | Multi-layer RGBA generation | LaDe (standalone or wrapper) |
| `snellcaster.json` | 2 | Snell's Law refraction pass | `YueYin27/snellcaster` |
| `hbo.json` | 3 | Cinematic grade | Flux + optional LoRA |
| `transparent.json` | 4 | Native RGBA plates | `ComfyUI-GGUF`, `ImageAlphaCrop` |
| `sprite.json` | 5 | Motion frames | sprite-gen CLI |
| `omni.json` | 6 | Image-to-PSD decomposition | OmniPSD wrapper |

## Install paths

All custom nodes go into `ComfyUI/custom_nodes/`:

```bash
cd /path/to/ComfyUI/custom_nodes

# Snellcaster (refraction)
git clone https://github.com/YueYin27/snellcaster
cd snellcaster && pip install -r requirements.txt && cd ..

# Qwen GGUF loader (use leejet fork for Qwen 2.1)
git clone https://github.com/leejet/ComfyUI-GGUF

# RGBA save node (alpha survives to disk)
git clone https://github.com/swan7-py/ComfyUI-ImageAlphaCrop
```

Restart ComfyUI after installing. Nodes appear under their respective
categories; if a graph fails to load with "unknown class_type", the
corresponding pack is missing or outdated.

## Model files

Place these in the standard ComfyUI model directories:

| Model | Directory | Notes |
|---|---|---|
| `flux1-dev.safetensors` | `models/checkpoints/` | LaDe, Snellcaster, HBO grade |
| `qwen_image_2.1-Q8_0.gguf` | `models/diffusion_models/` | Qwen RGBA (GGUF) |
| `qwen_2.1_text_encoder.safetensors` | `models/text_encoders/` | CLIPLoader type `qwen_image` |
| `qwen_image_2.1_vae_bf16.safetensors` | `models/vae/` | 64-channel RGBA VAE |

## Node class reference

These are the exact `class_type` strings the graphs expect. If ComfyUI
reports a different name after you install a pack, update the JSON.

| Graph | class_type | Registered by |
|---|---|---|
| snellcaster.json | SnellcasterRefraction | YueYin27/snellcaster |
| snellcaster.json | SnellcasterPanorama | YueYin27/snellcaster |
| snellcaster.json | SnellcasterBlend | YueYin27/snellcaster |
| transparent.json | UnetLoaderGGUF | ComfyUI-GGUF |
| transparent.json | SaveImageRGBA | ComfyUI-ImageAlphaCrop |
| omni.json | OmniPSDLoader | OmniPSD wrapper (custom) |
| omni.json | OmniPSDExtractLayers | OmniPSD wrapper (custom) |
| omni.json | OmniPSDSavePSD | OmniPSD wrapper (custom) |

## LaDe

LaDe is an Adobe Research latent diffusion framework that generates a
flexible number of semantically meaningful RGBA layers from a text prompt.
It combines an LLM-based prompt expander, a Latent Diffusion Transformer
with 4D RoPE positional encoding, and an RGBA VAE with full alpha-channel
support.

As of this writing, LaDe does not ship an official ComfyUI node. Two options:

1. Run LaDe standalone, then feed the output PNG into ComfyUI via LoadImage
   for downstream stages.
2. Wrap it as a custom node — the inference script is a single Python entry
   point, so a thin `class_type` wrapper that calls it and returns an IMAGE
   tensor is ~40 lines.

Until then, `lade.json` uses a Flux placeholder that approximates the
layered output with a single high-resolution pass.

## OmniPSD

OmniPSD is a unified diffusion-transformer framework for bidirectional
conversion between raster images and editable PSD files. It uses a shared
RGBA-VAE and Flux-Kontext for iterative in-context editing: extract text
layer → erase it → rebuild background → segment foreground layers.

Like LaDe, it ships as a standalone repo (showlab/OmniPSD) without an
official ComfyUI node. The graph in `omni.json` assumes a thin wrapper
exposing `OmniPSDLoader`, `OmniPSDExtractLayers`, and `OmniPSDSavePSD`.
If you do not wrap it, run OmniPSD directly from its repo and skip stage 6.

## Troubleshooting

**"unknown class_type" on load**  
The custom node pack for that `class_type` is not installed, or ComfyUI
was not restarted after installation. Check `custom_nodes/` and restart.

**"Given normalized_shape=[8192]"**  
Your ComfyUI-GGUF node is outdated. Update via ComfyUI Manager or
`git pull` inside `custom_nodes/ComfyUI-GGUF`. Use the leejet fork.

**Transparent PNG comes out opaque**  
You are using stock `SaveImage`, which flattens alpha. Switch the terminal
node to `SaveImageRGBA` from ComfyUI-ImageAlphaCrop.

**Snellcaster node fails with "moge not found"**  
The MoGe patch was not applied. Run the patch command from the
Snellcaster README after installing its requirements.

**Qwen GGUF loads but produces noise**  
The text encoder must be a `.safetensors` file, not a GGUF. ComfyUI
does not yet support GGUF as the Qwen-Image-2.1 text encoder.

**ComfyUI reports `comfy: false` in `/api/health`**  
The FastAPI bridge cannot reach ComfyUI. Verify `COMFY_URL` and that
ComfyUI is listening on that port (`curl $COMFY_URL/system_stats`).
