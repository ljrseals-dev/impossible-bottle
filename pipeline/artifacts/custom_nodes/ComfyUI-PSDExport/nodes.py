"""PSD export nodes — raster default, coeyes proxy, template smart objects."""
from __future__ import annotations

import io
import json as _json
import uuid as uuidlib
from pathlib import Path

import numpy as np
import torch
from PIL import Image

try:
    import folder_paths
except ImportError:
    folder_paths = None

from .psd_writer import write_layered_psd
from .smart_object_writer import inject_smart_object_records
from .template_extract import (
    extract_template,
    build_layer_blocks_from_template,
    template_to_token,
    token_to_template,
)


def _tensor_to_pil(t):
    if t.dim() == 4:
        t = t[0]
    arr = (t.clamp(0, 1).cpu().numpy() * 255).astype("uint8")
    return Image.fromarray(arr, "RGBA" if arr.shape[-1] == 4 else "RGB").convert("RGBA")


def _out_dir():
    return Path(folder_paths.get_output_directory()) if folder_paths else Path("outputs")


def _coeyes_available():
    try:
        import importlib
        importlib.import_module("ComfyUI_PSD_Layers")
        return True
    except Exception:
        return False


class PSDAssemble:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "images": ("IMAGE",),
            "layer_names": ("STRING", {"multiline": True,
                "default": "masts_rigging\nship_hull\nsea_resin\nbottle_glass\ntable\nbackground"}),
            "filename_prefix": ("STRING", {"default": "psd/bottle"}),
            "compression": (["rle", "raw"], {"default": "rle"}),
        }}
    RETURN_TYPES = ("STRING", "IMAGE")
    RETURN_NAMES = ("psd_path", "preview")
    FUNCTION = "assemble"
    CATEGORY = "PSD"

    def assemble(self, images, layer_names, filename_prefix, compression):
        d = _out_dir(); d.mkdir(parents=True, exist_ok=True)
        names = [n.strip() for n in layer_names.splitlines() if n.strip()]
        if len(names) != images.shape[0]:
            names = [f"layer_{i:02d}" for i in range(images.shape[0])]
        pil = [_tensor_to_pil(images[i]) for i in range(images.shape[0])]
        p = d / f"{filename_prefix}_00001_.psd"
        write_layered_psd(list(reversed(pil)), list(reversed(names)), p, compression)
        base = Image.new("RGBA", pil[0].size, (0, 0, 0, 0))
        for im in reversed(pil):
            base = Image.alpha_composite(base, im)
        prev = torch.from_numpy((np.array(base).astype("float32") / 255.0)[None, ...])
        return (str(p), prev)


class PSDAssembleSmart:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "base_image": ("IMAGE",),
            "base_mask": ("MASK",),
            "layers": ("IMAGE",),
            "masks": ("MASK",),
            "layer_names": ("STRING", {"multiline": True,
                "default": "masts_rigging\nship_hull\nsea_resin\nbottle_glass\ntable"}),
            "filename_prefix": ("STRING", {"default": "psd/bottle_smart"}),
        }}
    RETURN_TYPES = ("STRING", "IMAGE")
    RETURN_NAMES = ("psd_path", "preview")
    FUNCTION = "assemble"
    CATEGORY = "PSD"

    def assemble(self, base_image, base_mask, layers, masks, layer_names, filename_prefix):
        d = _out_dir(); d.mkdir(parents=True, exist_ok=True)
        names = [n.strip() for n in layer_names.splitlines() if n.strip()]
        if _coeyes_available():
            try:
                from ComfyUI_PSD_Layers.nodes import SeedreamLayersPSD
                node = SeedreamLayersPSD()
                for cand in ("save_psd", "save", "run"):
                    if hasattr(node, cand):
                        return getattr(node, cand)(
                            base_image=base_image, base_mask=base_mask,
                            layers=layers, masks=masks, bboxes=None,
                            filename_prefix=filename_prefix)
                raise RuntimeError("coeyes node has no known save method")
            except Exception as exc:
                print(f"[PSDAssembleSmart] coeyes failed: {exc}; raster fallback")
        all_imgs = torch.cat([layers, base_image], dim=0)
        all_names = names + ["background"]
        if len(all_names) != all_imgs.shape[0]:
            all_names = [f"layer_{i:02d}" for i in range(all_imgs.shape[0])]
        pil = [_tensor_to_pil(all_imgs[i]) for i in range(all_imgs.shape[0])]
        p = d / f"{filename_prefix}_00001_.psd"
        write_layered_psd(list(reversed(pil)), list(reversed(all_names)), p, "rle")
        base = Image.new("RGBA", pil[0].size, (0, 0, 0, 0))
        for im in reversed(pil):
            base = Image.alpha_composite(base, im)
        prev = torch.from_numpy((np.array(base).astype("float32") / 255.0)[None, ...])
        return (str(p), prev)


class PSDTemplateExtract:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"reference_psd": ("STRING", {"default": "input/template.psd"})}}
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("template_token",)
    FUNCTION = "extract"
    CATEGORY = "PSD"

    def extract(self, reference_psd):
        p = Path(reference_psd)
        if not p.is_absolute():
            p = (Path(folder_paths.get_input_directory()) / p) if folder_paths else Path("input") / p
        if not p.exists():
            return (f"ERROR: {p} not found",)
        try:
            return (_json.dumps(template_to_token(extract_template(p))),)
        except Exception as exc:
            return (f"ERROR: {exc}",)


class PSDAssembleSmartTemplate:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "images": ("IMAGE",),
            "layer_names": ("STRING", {"multiline": True,
                "default": "masts_rigging\nship_hull\nsea_resin\nbottle_glass\ntable\nbackground"}),
            "template_token": ("STRING", {"multiline": True, "default": ""}),
            "filename_prefix": ("STRING", {"default": "psd/bottle_tmpl"}),
            "compression": (["rle", "raw"], {"default": "rle"}),
        }}
    RETURN_TYPES = ("STRING", "IMAGE")
    RETURN_NAMES = ("psd_path", "preview")
    FUNCTION = "assemble"
    CATEGORY = "PSD"

    def assemble(self, images, layer_names, template_token, filename_prefix, compression):
        if not template_token.strip():
            raise ValueError("template_token is empty — run PSDTemplateExtract first")
        template = token_to_template(_json.loads(template_token))
        d = _out_dir(); d.mkdir(parents=True, exist_ok=True)
        names = [n.strip() for n in layer_names.splitlines() if n.strip()]
        if len(names) != images.shape[0]:
            names = [f"layer_{i:02d}" for i in range(images.shape[0])]
        pil = [_tensor_to_pil(images[i]) for i in range(images.shape[0])]
        file_layers = list(reversed(pil))
        file_names = list(reversed(names))
        blocks = []
        for im, name in zip(file_layers, file_names):
            uid = uuidlib.uuid4().hex
            buf = io.BytesIO()
            im.save(buf, format="PNG", compress_level=6)
            blocks.append(build_layer_blocks_from_template(template, uid, buf.getvalue()))
        p = d / f"{filename_prefix}_00001_.psd"
        tmp = d / f".{filename_prefix.replace('/', '_')}.tmp.psd"
        write_layered_psd(file_layers, file_names, tmp, compression)
        inject_smart_object_records(tmp, p, blocks)
        tmp.unlink(missing_ok=True)
        base = Image.new("RGBA", pil[0].size, (0, 0, 0, 0))
        for im in reversed(pil):
            base = Image.alpha_composite(base, im)
        prev = torch.from_numpy((np.array(base).astype("float32") / 255.0)[None, ...])
        return (str(p), prev)


class PSDSaveComposite:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "image": ("IMAGE",),
            "filename_prefix": ("STRING", {"default": "psd/composite"}),
        }}
    RETURN_TYPES = ("STRING",)
    FUNCTION = "save"
    CATEGORY = "PSD"
    OUTPUT_NODE = True

    def save(self, image, filename_prefix):
        d = _out_dir(); d.mkdir(parents=True, exist_ok=True)
        p = d / f"{filename_prefix}_00001_.png"
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
        p = Path(psd_path)
        if not p.exists():
            return (f"not found: {p}", 0)
        try:
            psd = PSDImage.open(p)
            names = [layer.name for layer in psd]
        except Exception as exc:
            return (f"read error: {exc}", 0)
        return ("\n".join(names), len(names))


NODE_CLASS_MAPPINGS = {
    "PSDAssemble": PSDAssemble,
    "PSDAssembleSmart": PSDAssembleSmart,
    "PSDAssembleSmartTemplate": PSDAssembleSmartTemplate,
    "PSDTemplateExtract": PSDTemplateExtract,
    "PSDSaveComposite": PSDSaveComposite,
    "PSDLayerInfo": PSDLayerInfo,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "PSDAssemble": "PSD Assemble (raster)",
    "PSDAssembleSmart": "PSD Assemble Smart (coeyes)",
    "PSDAssembleSmartTemplate": "PSD Assemble Smart (template)",
    "PSDTemplateExtract": "PSD Template Extract",
    "PSDSaveComposite": "PSD Save Composite",
    "PSDLayerInfo": "PSD Layer Info",
}
