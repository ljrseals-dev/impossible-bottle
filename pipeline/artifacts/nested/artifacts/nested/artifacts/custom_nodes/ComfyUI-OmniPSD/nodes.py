"""ComfyUI-OmniPSD — wrapper for OmniPSD (Show Lab)."""
from __future__ import annotations

import importlib
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

from .psd_writer import write_layered_psd


def _tensor_to_pil(t: torch.Tensor) -> Image.Image:
    if t.dim() == 4:
        t = t[0]
    arr = (t.clamp(0, 1).cpu().numpy() * 255).astype(np.uint8)
    return Image.fromarray(arr, "RGBA" if arr.shape[-1] == 4 else "RGB")


class OmniPSDLoader:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "flux_checkpoint": ("STRING", {"default": "flux1-dev.safetensors"}),
                "kontext_checkpoint": ("STRING", {"default": "flux1-kontext-dev.safetensors"}),
                "rgba_vae": ("STRING", {"default": "flux1-dev-alpha.safetensors"}),
                "content_front_lora": ("STRING", {"default": "omni_content_front.safetensors"}),
                "content_back_lora": ("STRING", {"default": "omni_content_back.safetensors"}),
                "text_front_lora": ("STRING", {"default": "omni_text_front.safetensors"}),
                "text_back_lora": ("STRING", {"default": "omni_text_back.safetensors"}),
            }
        }

    RETURN_TYPES = ("OMNIPSD_MODEL",)
    FUNCTION = "load"
    CATEGORY = "OmniPSD"

    def load(self, flux_checkpoint, kontext_checkpoint, rgba_vae,
             content_front_lora, content_back_lora, text_front_lora, text_back_lora):
        ckpt_dir = Path(folder_paths.models_dir) / "checkpoints" if folder_paths else Path(".")
        lora_dir = Path(folder_paths.models_dir) / "loras" if folder_paths else Path(".")
        vae_dir = Path(folder_paths.models_dir) / "vae" if folder_paths else Path(".")
        obj: dict[str, Any] = {
            "flux": str(ckpt_dir / flux_checkpoint),
            "kontext": str(ckpt_dir / kontext_checkpoint),
            "vae": str(vae_dir / rgba_vae),
            "loras": {
                "content_front": str(lora_dir / content_front_lora),
                "content_back": str(lora_dir / content_back_lora),
                "text_front": str(lora_dir / text_front_lora),
                "text_back": str(lora_dir / text_back_lora),
            },
            "omni_repo": None,
            "loaded": False,
        }
        for candidate in [
            Path(__file__).parent.parent.parent / "OmniPSD",
            Path(folder_paths.base_path) / "OmniPSD" if folder_paths else None,
            Path(os.environ["OMNIPSD_REPO"]) if os.environ.get("OMNIPSD_REPO") else None,
        ]:
            if candidate and candidate.exists() and (candidate / "inference").exists():
                sys.path.insert(0, str(candidate))
                obj["omni_repo"] = str(candidate)
                break
        if obj["omni_repo"]:
            try:
                obj["api"] = importlib.import_module("inference.infer_psd_flux")
                obj["loaded"] = True
                print(f"[OmniPSD] loaded repo at {obj['omni_repo']}")
            except Exception as e:
                print(f"[OmniPSD] repo found but import failed: {e}")
        else:
            print("[OmniPSD] no repo found — extract node will use segmentation fallback")
        return (obj,)


class OmniPSDExtractLayers:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "omnipsd_model": ("OMNIPSD_MODEL",),
                "image": ("IMAGE",),
                "layer_names": ("STRING", {
                    "multiline": True,
                    "default": "masts_rigging\nship_hull\nsea_resin\nbottle_glass\ntable\nbackground",
                }),
                "iterations": ("INT", {"default": 3, "min": 1, "max": 8}),
                "fallback_mode": (["luminance", "chroma"], {"default": "luminance"}),
            }
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("layers", "masks", "layer_names")
    FUNCTION = "extract"
    CATEGORY = "OmniPSD"

    def extract(self, omnipsd_model, image, layer_names, iterations, fallback_mode):
        names = [n.strip() for n in layer_names.splitlines() if n.strip()]
        if omnipsd_model.get("loaded") and "api" in omnipsd_model:
            return self._run_omni(omnipsd_model, image, names, iterations)
        print("[OmniPSD] using fallback decomposition")
        return self._fallback(image, names, fallback_mode)

    def _run_omni(self, model, image, names, iterations):
        api = model["api"]
        pil = _tensor_to_pil(image)
        try:
            layers = api.decompose(
                image=pil, layer_names=names, iterations=iterations,
                flux_path=model["flux"], kontext_path=model["kontext"],
                vae_path=model["vae"], loras=model["loras"],
            )
            tensors, masks = [], []
            for name in names:
                layer = layers.get(name)
                if layer is None:
                    continue
                arr = np.array(layer.convert("RGBA")).astype(np.float32) / 255.0
                t = torch.from_numpy(arr)[None, ...]
                tensors.append(t)
                masks.append(t[..., 3])
            return (torch.cat(tensors, dim=0), torch.stack(masks, dim=0), ",".join(names))
        except Exception as e:
            print(f"[OmniPSD] extract error: {e}")
            return self._fallback(image, names, "luminance")

    def _fallback(self, image, names, mode):
        pil = _tensor_to_pil(image).convert("RGBA")
        arr = np.array(pil).astype(np.float32) / 255.0
        lum = 0.2126 * arr[..., 0] + 0.7152 * arr[..., 1] + 0.0722 * arr[..., 2]
        thresholds = np.linspace(0.0, 1.0, len(names) + 1)
        tensors, masks = [], []
        for i in range(len(names)):
            lo, hi = thresholds[i], thresholds[i + 1]
            alpha = ((lum >= lo) & (lum < hi)).astype(np.float32)
            layer = arr.copy()
            layer[..., 3] = alpha
            t = torch.from_numpy(layer)[None, ...]
            tensors.append(t)
            masks.append(t[..., 3])
        return (torch.cat(tensors, dim=0), torch.stack(masks, dim=0), ",".join(names))


class OmniPSDSavePSD:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE",),
                "layer_names": ("STRING", {"default": ""}),
                "filename_prefix": ("STRING", {"default": "omni/bottle_layers"}),
                "compression": (["rle", "raw"], {"default": "rle"}),
                "embed_smart_objects": ("BOOLEAN", {"default": False}),
            }
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("psd_path",)
    FUNCTION = "save"
    CATEGORY = "OmniPSD"
    OUTPUT_NODE = True

    def save(self, images, layer_names, filename_prefix, compression, embed_smart_objects):
        out_dir = Path(folder_paths.get_output_directory()) if folder_paths else Path("outputs")
        out_dir.mkdir(parents=True, exist_ok=True)
        names = [n.strip() for n in layer_names.split(",") if n.strip()]
        if len(names) != images.shape[0]:
            names = [f"layer_{i:02d}" for i in range(images.shape[0])]
        pil_layers = [_tensor_to_pil(images[i]) for i in range(images.shape[0])]
        psd_path = out_dir / f"{filename_prefix}_00001_.psd"
        write_layered_psd(layers=pil_layers, names=names, output_path=psd_path, compression=compression)
        print(f"[OmniPSD] wrote {psd_path}")
        return (str(psd_path),)


NODE_CLASS_MAPPINGS = {
    "OmniPSDLoader": OmniPSDLoader,
    "OmniPSDExtractLayers": OmniPSDExtractLayers,
    "OmniPSDSavePSD": OmniPSDSavePSD,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "OmniPSDLoader": "OmniPSD Loader",
    "OmniPSDExtractLayers": "OmniPSD Extract Layers",
    "OmniPSDSavePSD": "OmniPSD Save PSD",
}
