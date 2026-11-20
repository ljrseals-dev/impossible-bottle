"""ComfyUI-PSDExport — assemble an IMAGE batch into a layered PSD."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import torch
from PIL import Image

try:
    import folder_paths
except ImportError:
    folder_paths = None

from .psd_writer import write_layered_psd
try:
    from .smart_object_writer import write_smart_object_psd
except ImportError:
    write_smart_object_psd = None


def _tensor_to_pil(t: torch.Tensor) -> Image.Image:
    if t.dim() == 4:
        t = t[0]
    arr = (t.clamp(0, 1).cpu().numpy() * 255).astype("uint8")
    return Image.fromarray(arr, "RGBA" if arr.shape[-1] == 4 else "RGB").convert("RGBA")


class PSDAssemble:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE",),
                "layer_names": ("STRING", {
                    "multiline": True,
                    "default": "masts_rigging\nship_hull\nsea_resin\nbottle_glass\ntable\nbackground",
                }),
                "filename_prefix": ("STRING", {"default": "psd/bottle"}),
                "compression": (["rle", "raw"], {"default": "rle"}),
                "smart_objects": ("BOOLEAN", {"default": False}),
            }
        }

    RETURN_TYPES = ("STRING", "IMAGE")
    RETURN_NAMES = ("psd_path", "preview")
    FUNCTION = "assemble"
    CATEGORY = "PSD"

    def assemble(self, images, layer_names, filename_prefix, compression, smart_objects=False):
        out_dir = Path(folder_paths.get_output_directory()) if folder_paths else Path("outputs")
        out_dir.mkdir(parents=True, exist_ok=True)
        names = [n.strip() for n in layer_names.splitlines() if n.strip()]
        if len(names) != images.shape[0]:
            names = [f"layer_{i:02d}" for i in range(images.shape[0])]
        pil_layers = [_tensor_to_pil(images[i]) for i in range(images.shape[0])]
        psd_path = out_dir / f"{filename_prefix}_00001_.psd"
        if smart_objects and write_smart_object_psd is not None:
            write_smart_object_psd(pil_layers, names, psd_path, compression=compression)
        else:
            write_layered_psd(list(reversed(pil_layers)), list(reversed(names)), psd_path, compression)
        base = Image.new("RGBA", pil_layers[0].size, (0, 0, 0, 0))
        for im in reversed(pil_layers):
            base = Image.alpha_composite(base, im)
        preview = torch.from_numpy((np.array(base).astype("float32") / 255.0)[None, ...])
        return (str(psd_path), preview)


class PSDSaveComposite:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "filename_prefix": ("STRING", {"default": "psd/composite"}),
            }
        }

    RETURN_TYPES = ("STRING",)
    FUNCTION = "save"
    CATEGORY = "PSD"
    OUTPUT_NODE = True

    def save(self, image, filename_prefix):
        out_dir = Path(folder_paths.get_output_directory()) if folder_paths else Path("outputs")
        out_dir.mkdir(parents=True, exist_ok=True)
        p = out_dir / f"{filename_prefix}_00001_.png"
        _tensor_to_pil(image).save(p)
        return (str(p),)


class PSDLayerInfo:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"psd_path": ("STRING", {"default": ""})}}

    RETURN_TYPES = ("STRING", "INT")
    RETURN_NAMES = ("layer_names", "layer_count")
    FUNCTION = "inspect"
    CATEGORY = "PSD"

    def inspect(self, psd_path):
        try:
            from psd_tools import PSDImage
        except ImportError:
            return ("psd-tools not installed", 0)
        psd = PSDImage.open(psd_path)
        names = [layer.name for layer in psd]
        return ("\n".join(names), len(names))


NODE_CLASS_MAPPINGS = {
    "PSDAssemble": PSDAssemble,
    "PSDSaveComposite": PSDSaveComposite,
    "PSDLayerInfo": PSDLayerInfo,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "PSDAssemble": "PSD Assemble (Layers → PSD)",
    "PSDSaveComposite": "PSD Save Composite PNG",
    "PSDLayerInfo": "PSD Layer Info",
}
