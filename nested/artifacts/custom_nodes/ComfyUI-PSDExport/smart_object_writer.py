from __future__ import annotations

"""REFERENCE IMPLEMENTATION ONLY — not wired into default path.
Use coeyes or PSDAssembleSmartTemplate instead.
"""
"""
REFERENCE IMPLEMENTATION ONLY — not wired into default path.
Use coeyes/ComfyUI-PSD-Layers or PSDAssembleSmartTemplate instead.
"""
"""Smart Object PSD writer — SoLd + lnk2 blocks for embedded smart objects."""

import io
import struct
import uuid as uuidlib
from collections import OrderedDict
from pathlib import Path
from typing import Any, Sequence

import numpy as np
from PIL import Image

try:
    from .psd_writer import write_layered_psd
except ImportError:
    from psd_writer import write_layered_psd


def _u32(v: int) -> bytes:
    return struct.pack(">I", v)


def _i32(v: int) -> bytes:
    return struct.pack(">i", v)


def _f64(v: float) -> bytes:
    return struct.pack(">d", v)


def _write_unicode_string(s: str) -> bytes:
    if not s:
        return _u32(0)
    encoded = s.encode("utf-16-be")
    return _u32(len(encoded) // 2) + encoded


def _write_class_id(name: str) -> bytes:
    if not name:
        return _u32(0)
    raw = name.encode("ascii", errors="replace")
    out = _u32(len(raw)) + raw
    pad = (4 - len(raw) % 4) % 4
    return out + b"\x00" * pad


def _write_pascal_string(s: str) -> bytes:
    raw = s.encode("ascii", errors="replace")[:255]
    out = bytes([len(raw)]) + raw
    if len(out) % 2:
        out += b"\x00"
    return out


def _write_value(type_str: str, value: Any) -> bytes:
    if type_str == "TEXT":
        return _write_unicode_string(str(value))
    if type_str == "long":
        return _i32(int(value))
    if type_str == "bool":
        return b"\x01" if value else b"\x00"
    if type_str == "doub":
        return _f64(float(value))
    if type_str == "UntF":
        unit, val = value
        return unit.encode("ascii") + _f64(float(val))
    if type_str == "enum":
        enum_type, enum_val = value
        return _write_class_id(enum_type) + _write_class_id(enum_val)
    if type_str == "VlLs":
        items = value or []
        out = bytearray(_u32(len(items)))
        for item in items:
            if isinstance(item, tuple) and len(item) == 2 and isinstance(item[0], str) and len(item[0]) == 4:
                t, v = item
                out.extend(t.encode("ascii"))
                out.extend(_write_value(t, v))
            else:
                out.extend(b"doub")
                out.extend(_f64(float(item)))
        return bytes(out)
    if type_str == "Objc":
        return _write_descriptor(value)
    raise ValueError(f"unsupported descriptor type: {type_str}")


def _write_descriptor(desc: OrderedDict) -> bytes:
    out = bytearray()
    out.extend(_write_unicode_string(""))
    out.extend(_write_class_id("null"))
    out.extend(_u32(len(desc)))
    for key, (type_str, value) in desc.items():
        out.extend(_write_unicode_string(key))
        out.extend(type_str.encode("ascii"))
        out.extend(_write_value(type_str, value))
    return bytes(out)


def _build_sold_block(uuid_hex: str, width: int, height: int,
                      transform: Sequence[float] | None = None) -> bytes:
    if transform is None:
        transform = [1.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0]
    transform = list(transform)
    while len(transform) < 8:
        transform.append(0.0)
    desc: OrderedDict = OrderedDict()
    desc["ID  "] = ("TEXT", uuid_hex)
    desc["PgNm"] = ("long", 1)
    desc["Total"] = ("long", 1)
    desc["Placed"] = ("TEXT", uuid_hex)
    desc["Artboard"] = ("TEXT", "")
    desc["Crop"] = ("VlLs", [])
    desc["FrameX"] = ("VlLs", [("doub", 0.0)] * 4)
    desc["FrameY"] = ("VlLs", [("doub", 0.0)] * 4)
    desc["Resolution"] = ("UntF", ("#Pxl", 72.0))
    desc["Comp"] = ("long", 0)
    desc["Transform"] = ("VlLs", [("doub", v) for v in transform])
    desc["NonAffineTransform"] = ("VlLs", [("doub", v) for v in transform])
    desc_bytes = _write_descriptor(desc)
    out = bytearray()
    out.extend(b"8BIM")
    out.extend(b"SoLd")
    out.extend(_u32(len(desc_bytes)))
    out.extend(desc_bytes)
    return bytes(out)


def _guess_filetype(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    return {".png": "png ", ".jpg": "JPEG", ".jpeg": "JPEG", ".tif": "TIFF",
            ".tiff": "TIFF", ".psd": "8BPS", ".psb": "8BPS"}.get(ext, "png ")


def _build_lnk2_block(uuid_hex: str, filename: str, embedded_bytes: bytes,
                      filetype: str | None = None) -> bytes:
    if filetype is None:
        filetype = _guess_filetype(filename)
    uuid_bytes = uuid_hex.encode("ascii")[:16].ljust(16, b"0")
    link = bytearray()
    link.extend(_u32(7))
    link.extend(uuid_bytes)
    link.extend(_write_unicode_string(filename))
    link.extend(filetype.encode("ascii"))
    link.extend(b"8BIM")
    link.extend(struct.pack(">Q", len(embedded_bytes)))
    link.extend(b"\x00" * 8)
    link.extend(uuid_bytes)
    link.extend(_write_pascal_string(filename))
    link.extend(_write_unicode_string(filename))
    link.extend(_u32(0))
    out = bytearray()
    out.extend(b"8BIM")
    out.extend(b"lnk2")
    out.extend(_u32(len(link)))
    out.extend(link)
    out.extend(embedded_bytes)
    return bytes(out)


def build_smart_object_layer_info(uuid_hex, filename, embedded_bytes,
                                  canvas_width, canvas_height, transform=None) -> bytes:
    sold = _build_sold_block(uuid_hex, canvas_width, canvas_height, transform)
    lnk2 = _build_lnk2_block(uuid_hex, filename, embedded_bytes)
    return sold + lnk2


def _encode_layer_png(im: Image.Image) -> bytes:
    buf = io.BytesIO()
    im.convert("RGBA").save(buf, format="PNG", optimize=False, compress_level=6)
    return buf.getvalue()


def write_smart_object_psd(
    layers: Sequence[Image.Image],
    names: Sequence[str],
    output_path: str | Path,
    source_format: str = "png",
    compression: str = "rle",
) -> Path:
    if len(layers) != len(names):
        raise ValueError("layers and names must match")
    if not layers:
        raise ValueError("at least one layer required")
    layers = [im.convert("RGBA") for im in layers]
    width, height = layers[0].size
    for im in layers:
        if im.size != (width, height):
            raise ValueError("all layers must share canvas size")

    file_order_layers = list(reversed(layers))
    file_order_names = list(reversed(names))

    info_blocks: list[bytes] = []
    for im, name in zip(file_order_layers, file_order_names):
        uid = uuidlib.uuid4().hex
        fname = f"{name}.{source_format}"
        payload = _encode_layer_png(im)
        block = build_smart_object_layer_info(
            uuid_hex=uid, filename=fname, embedded_bytes=payload,
            canvas_width=width, canvas_height=height,
        )
        info_blocks.append(block)

    raster_path = Path(output_path).with_suffix(".raster.tmp.psd")
    write_layered_psd(file_order_layers, file_order_names, raster_path, compression)
    _inject_smart_object_records(raster_path, Path(output_path), info_blocks)
    raster_path.unlink(missing_ok=True)
    return Path(output_path)


def _inject_smart_object_records(src: Path, dst: Path, info_blocks: list[bytes]) -> None:
    """
    Layout from our write_layered_psd:
      header(26) | color_mode(4+n) | image_resources(4+n)
      | layer_and_mask_len(4)
        | layer_info_len(4)
          | layer_count(2)
          | layer_records...
          | channel_image_data...
        | global_mask_len(4) [=0]
      | composite_image_data
    Channel length field in each record stores len(blob) where blob already
    includes the 2-byte compression marker.
    """
    import struct
    raw = bytearray(src.read_bytes())
    assert raw[0:4] == b"8BPS", "not a PSD"
    pos = 26
    cm_len = struct.unpack_from(">I", raw, pos)[0]
    pos += 4 + cm_len
    ir_len = struct.unpack_from(">I", raw, pos)[0]
    pos += 4 + ir_len

    lm_len_pos = pos
    lm_len = struct.unpack_from(">I", raw, pos)[0]
    pos += 4

    li_len_pos = pos
    li_len = struct.unpack_from(">I", raw, pos)[0]
    pos += 4

    layer_count = struct.unpack_from(">h", raw, pos)[0]
    pos += 2
    n = abs(layer_count)

    extra_len_positions: list[int] = []
    extra_len_values: list[int] = []

    for _ in range(n):
        # bbox: 4 * i32
        pos += 16
        chan_count = struct.unpack_from(">H", raw, pos)[0]
        pos += 2
        # per channel: id(2) + length(4)
        for _c in range(chan_count):
            pos += 2  # channel id
            pos += 4  # channel data length
        # blend signature(4) + key(4) + opacity/clip/flags/filler(4)
        pos += 12
        # extra data length
        extra_len_positions.append(pos)
        extra_len = struct.unpack_from(">I", raw, pos)[0]
        extra_len_values.append(extra_len)
        pos += 4 + extra_len

    if len(info_blocks) != n:
        raise ValueError(f"info_blocks ({len(info_blocks)}) != layer count ({n})")

    for i in reversed(range(n)):
        block = info_blocks[i]
        el_pos = extra_len_positions[i]
        el_val = extra_len_values[i]
        extra_end = el_pos + 4 + el_val
        raw[extra_end:extra_end] = block
        struct.pack_into(">I", raw, el_pos, el_val + len(block))

    total_added = sum(len(b) for b in info_blocks)
    struct.pack_into(">I", raw, lm_len_pos, lm_len + total_added)
    struct.pack_into(">I", raw, li_len_pos, li_len + total_added)
    dst.write_bytes(bytes(raw))