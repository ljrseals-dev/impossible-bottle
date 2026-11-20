"""ComfyUI-LaDe — wrapper for LaDe (Adobe Research CVPRW 2026)."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import numpy as np
import torch
from PIL import Image

try:
    import folder_paths
except ImportError:
    folder_paths = None


def _pil_to_tensor(im: Image.Image) -> torch.Tensor:
    if im.mode != "RGBA":
        im = im.convert("RGBA")
    arr = np.array(im).astype(np.float32) / 255.0
    return torch.from_numpy(arr)[None, ...]


class LaDeLoader:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "flux_checkpoint": ("STRING", {"default": "flux1-dev.safetensors"}),
                "rgba_vae": ("STRING", {"default": "flux1-dev-alpha.safetensors"}),
                "precision": (["fp16", "bf16", "fp32"], {"default": "bf16"}),
            }
        }

    RETURN_TYPES = ("LADE_MODEL",)
    RETURN_NAMES = ("lade_model",)
    FUNCTION = "load"
    CATEGORY = "LaDe"

    def load(self, flux_checkpoint: str, rgba_vae: str, precision: str):
        ckpt_dir = Path(folder_paths.models_dir) / "checkpoints" if folder_paths else Path(".")
        vae_dir = Path(folder_paths.models_dir) / "vae" if folder_paths else Path(".")
        dtype = {"fp16": torch.float16, "bf16": torch.bfloat16, "fp32": torch.float32}[precision]
        model_obj: dict[str, Any] = {
            "flux_path": str(ckpt_dir / flux_checkpoint),
            "vae_path": str(vae_dir / rgba_vae),
            "dtype": dtype,
            "lade_repo": None,
            "loaded": False,
        }
        for candidate in [
            Path(__file__).parent.parent.parent / "LaDe",
            Path(folder_paths.base_path) / "LaDe" if folder_paths else None,
            Path(os.environ["LADE_REPO"]) if os.environ.get("LADE_REPO") else None,
        ]:
            if candidate and candidate.exists() and (candidate / "inference.py").exists():
                sys.path.insert(0, str(candidate))
                model_obj["lade_repo"] = str(candidate)
                break
        if model_obj["lade_repo"]:
            try:
                import importlib
                model_obj["lade_api"] = importlib.import_module("inference")
                model_obj["loaded"] = True
                print(f"[LaDe] loaded repo at {model_obj['lade_repo']}")
            except Exception as e:
                print(f"[LaDe] repo found but import failed: {e}")
        else:
            print("[LaDe] no LaDe repo found — sampler will use Flux fallback")
        return (model_obj,)


class LaDeSampler:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "lade_model": ("LADE_MODEL",),
                "prompt": ("STRING", {"multiline": True, "default": ""}),
                "layer_names": ("STRING", {
                    "multiline": True,
                    "default": "table\nbottle_glass\nship_hull\nmasts_rigging\nsea_resin",
                }),
                "width": ("INT", {"default": 1216, "min": 256, "max": 4096, "step": 64}),
                "height": ("INT", {"default": 832, "min": 256, "max": 4096, "step": 64}),
                "steps": ("INT", {"default": 28, "min": 1, "max": 100}),
                "cfg": ("FLOAT", {"default": 3.5, "min": 0.0, "max": 20.0, "step": 0.1}),
                "seed": ("INT", {"default": 42, "min": 0, "max": 0xFFFFFFFF}),
            }
        }

    RETURN_TYPES = ("LADE_LATENTS",)
    RETURN_NAMES = ("layer_latents",)
    FUNCTION = "sample"
    CATEGORY = "LaDe"

    def sample(self, lade_model, prompt, layer_names, width, height, steps, cfg, seed):
        names = [n.strip() for n in layer_names.splitlines() if n.strip()]
        if lade_model.get("loaded") and "lade_api" in lade_model:
            return (self._run_lade(lade_model, prompt, names, width, height, steps, seed),)
        print("[LaDe] using Flux fallback — producing placeholder latents")
        latents = {}
        for i, name in enumerate(names):
            latents[name] = {
                "width": width, "height": height, "seed": seed + i,
                "prompt": f"{prompt}\n\nLayer: {name}", "placeholder": True,
            }
        return (latents,)

    def _run_lade(self, lade_model, prompt, names, width, height, steps, seed):
        api = lade_model["lade_api"]
        try:
            return api.generate(
                prompt=prompt, layer_names=names, width=width, height=height,
                num_inference_steps=steps, seed=seed,
                flux_path=lade_model["flux_path"], vae_path=lade_model["vae_path"],
            )
        except Exception as e:
            print(f"[LaDe] sampler error: {e}")
            return {name: {"error": str(e)} for name in names}


class LaDeDecodeLayers:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"layer_latents": ("LADE_LATENTS",)}}

    RETURN_TYPES = ("IMAGE", "STRING", "MASK")
    RETURN_NAMES = ("layers", "layer_names", "layer_masks")
    FUNCTION = "decode"
    CATEGORY = "LaDe"

    def decode(self, layer_latents):
        if isinstance(layer_latents, dict) and all(
            isinstance(v, dict) and v.get("placeholder") for v in layer_latents.values()
        ):
            return self._placeholder_decode(layer_latents)
        images, masks, names = [], [], []
        for name, layer in layer_latents.items():
            names.append(name)
            if isinstance(layer, torch.Tensor):
                t = layer if layer.dim() == 4 else layer[None, ...]
                images.append(t)
                masks.append(t[..., 3] if t.shape[-1] == 4 else torch.ones_like(t[..., 0]))
            elif isinstance(layer, Image.Image):
                t = _pil_to_tensor(layer)
                images.append(t)
                masks.append(t[..., 3])
            else:
                raise ValueError(f"unknown layer type for {name}: {type(layer)}")
        return (torch.cat(images, dim=0), ",".join(names), torch.stack(masks, dim=0))

    def _placeholder_decode(self, latents):
        images, names = [], []
        for name, spec in latents.items():
            w, h = spec["width"], spec["height"]
            arr = np.zeros((h, w, 4), dtype=np.float32)
            arr[..., :3] = 0.2
            arr[..., 3] = 1.0
            images.append(torch.from_numpy(arr)[None, ...])
            names.append(name)
        batch = torch.cat(images, dim=0)
        return (batch, ",".join(names), batch[..., 3])


NODE_CLASS_MAPPINGS = {
    "LaDeLoader": LaDeLoader,
    "LaDeSampler": LaDeSampler,
    "LaDeDecodeLayers": LaDeDecodeLayers,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "LaDeLoader": "LaDe Loader",
    "LaDeSampler": "LaDe Sampler (Text → Layers)",
    "LaDeDecodeLayers": "LaDe Decode Layers (RGBA)",
}
