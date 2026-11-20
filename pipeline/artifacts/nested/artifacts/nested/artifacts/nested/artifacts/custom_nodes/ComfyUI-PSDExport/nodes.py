"""
PSD export nodes.

PSDAssemble              — raster PSD (VERIFIED, default)
PSDAssembleSmart         — proxy to coeyes when present, else raster
PSDAssembleSmartTemplate — template-extraction smart-object writer
PSDTemplateExtract       — pull SoLd template from Photoshop-saved PSD
PSDSaveComposite         — write flat PNG preview
PSDLayerInfo             — inspect any PSD via psd-tools
"""
from __future__ import annotations

import base64
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


def _tensor_to_pil(t: torch.Tensor) -> Image.Image:
    if t.dim() == 4:
        t = t[0]
    arr = (t.clamp(0, 1).cpu().numpy() * 255).astype("uint8")
    return Image.fromarray(arr, "RGBA" if arr.shape[-1] == 4 else "RGB").convert("RGBA")


def _out_dir() -> Path:
    return Path(folder_paths.get_output_directory()) if folder_paths else Path("outputs")


def _coeyes_available() -> bool:
    try:
        import importlib
        importlib.import_module("ComfyUI_PSD_Layers")
        return True
    except Exception:
        return False


class PSDAssemble:
    """Raster writer — verified, always works. Default export path."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE",),
                "layer_names": (
                    "STRING",
                    {
                        "multiline": True,
                        "default": "masts_rigging\nship_hull\nsea_resin\nbottle_glass\ntable\nbackground",
                    },
                ),
                "filename_prefix": ("STRING", {"default": "psd/bottle"}),
                "compression": (["rle", "raw"], {"default": "rle"}),
            }
        }

    RETURN_TYPES = ("STRING", "IMAGE")
    RETURN_NAMES = ("psd_path", "preview")
    FUNCTION = "assemble"
    CATEGORY = "PSD"

    def assemble(self, images, layer_names, filename_prefix, compression):
        d = _out_dir()
        d.mkdir(parents=True, exist_ok=True)
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
    """Proxy to coeyes Save Seedream Layers PSD when installed; else raster."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "base_image": ("IMAGE",),
                "base_mask": ("MASK",),
                "layers": ("IMAGE",),
                "masks": ("MASK",),
                "layer_names": (
                    "STRING",
                    {
                        "multiline": True,
                        "default": "masts_rigging\nship_hull\nsea_resin\nbottle_glass\ntable",
                    },
                ),
                "filename_prefix": ("STRING", {"default": "psd/bottle_smart"}),
            }
        }

    RETURN_TYPES = ("STRING", "IMAGE")
    RETURN_NAMES = ("psd_path", "preview")
    FUNCTION = "assemble"
    CATEGORY = "PSD"

    def assemble(self, base_image, base_mask, layers, masks, layer_names, filename_prefix):
        d = _out_dir()
        d.mkdir(parents=True, exist_ok=True)
        names = [n.strip() for n in layer_names.splitlines() if n.strip()]

        if _coeyes_available():
            try:
                from ComfyUI_PSD_Layers.nodes import SeedreamLayersPSD

                node = SeedreamLayersPSD()
                return node.save_psd(
                    base_image=base_image,
                    base_mask=base_mask,
                    layers=layers,
                    masks=masks,
                    bboxes=None,
                    filename_prefix=filename_prefix,
                )
            except Exception as e:
                print(f"[PSDAssembleSmart] coeyes failed: {e}; falling back to raster")

        all_imgs = torch.cat([base_image, layers], dim=0)
        all_names = ["background"] + names
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
    """Extract SoLd template from a Photoshop-saved reference PSD (one-time per version)."""

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"reference_psd": ("STRING", {"default": "input/template.psd"})}}

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("template_token",)
    FUNCTION = "extract"
    CATEGORY = "PSD"

    def extract(self, reference_psd):
        from .template_extract import extract_template

        p = Path(reference_psd)
        if not p.exists():
            return (f"ERROR: {reference_psd} not found",)
        t = extract_template(p)
        token = {
            "sold": base64.b64encode(t["sold_template"]).decode("ascii"),
            "lnk2": base64.b64encode(t["lnk2_template"]).decode("ascii"),
            "sold_uuid_off": t["sold_uuid_off"],
            "lnk2_uuid_off": t["lnk2_uuid_off"],
            "lnk2_size_off": t["lnk2_size_off"],
        }
        return (_json.dumps(token),)


class PSDAssembleSmartTemplate:
    """Smart-object PSD using exact SoLd bytes from a Photoshop-saved template."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE",),
                "layer_names": (
                    "STRING",
                    {
                        "multiline": True,
                        "default": "masts_rigging\nship_hull\nsea_resin\nbottle_glass\ntable\nbackground",
                    },
                ),
                "template_token": ("STRING", {"multiline": True, "default": ""}),
                "filename_prefix": ("STRING", {"default": "psd/bottle_tmpl"}),
                "compression": (["rle", "raw"], {"default": "rle"}),
            }
        }

    RETURN_TYPES = ("STRING", "IMAGE")
    RETURN_NAMES = ("psd_path", "preview")
    FUNCTION = "assemble"
    CATEGORY = "PSD"

    def assemble(self, images, layer_names, template_token, filename_prefix, compression):
        from .template_extract import build_layer_blocks_from_template
        from .smart_object_writer import _inject

        if not template_token.strip():
            raise ValueError("template_token is empty — run PSDTemplateExtract first")

        token = _json.loads(template_token)
        template = {
            "sold_template": base64.b64decode(token["sold"]),
            "lnk2_template": base64.b64decode(token["lnk2"]),
            "sold_uuid_off": token["sold_uuid_off"],
            "lnk2_uuid_off": token["lnk2_uuid_off"],
            "lnk2_size_off": token["lnk2_size_off"],
        }

        d = _out_dir()
        d.mkdir(parents=True, exist_ok=True)
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
            im.convert("RGBA").save(buf, format="PNG", compress_level=6)
            blocks.append(build_layer_blocks_from_template(template, uid, buf.getvalue()))

        p = d / f"{filename_prefix}_00001_.psd"
        tmp = d / f".{filename_prefix.replace('/', '_')}.tmp.psd"
        write_layered_psd(file_layers, file_names, tmp, compression)
        _inject(tmp, p, blocks)
        tmp.unlink(missing_ok=True)

        base = Image.new("RGBA", pil[0].size, (0, 0, 0, 0))
        for im in reversed(pil):
            base = Image.alpha_composite(base, im)
        prev = torch.from_numpy((np.array(base).astype("float32") / 255.0)[None, ...])
        return (str(p), prev)


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
        d = _out_dir()
        d.mkdir(parents=True, exist_ok=True)
        p = d / f"{filename_prefix}_00001_.png"
        _tensor_to_pil(image).save(p)
        return (str(p),)


class PSDLayerInfo:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"psd_path": ("STRING", {"default": ""})}}

    RETURN_TYPES = ("STRING", "INT")
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
    "PSDAssembleSmart": PSDAssembleSmart,
    "PSDAssembleSmartTemplate": PSDAssembleSmartTemplate,
    "PSDTemplateExtract": PSDTemplateExtract,
    "PSDSaveComposite": PSDSaveComposite,
    "PSDLayerInfo": PSDLayerInfo,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "PSDAssemble": "PSD Assemble (raster)",
    "PSDAssembleSmart": "PSD Assemble Smart (coeyes proxy)",
    "PSDAssembleSmartTemplate": "PSD Assemble Smart (template)",
    "PSDTemplateExtract": "PSD Template Extract",
    "PSDSaveComposite": "PSD Save Composite PNG",
    "PSDLayerInfo": "PSD Layer Info",
}
