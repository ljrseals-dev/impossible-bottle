"""
Smart-object PSD writer — full implementation.

Extends psd_writer.py to emit embedded smart objects by splicing SoLd + lnk2
blocks into each layer record. Prefer coeyes or template path for Photoshop.
"""
from __future__ import annotations

import io
import struct
import uuid as uuidlib
from collections import OrderedDict
from pathlib import Path
from typing import Any, Sequence

from PIL import Image


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
        et, ev = value
        return _write_class_id(et) + _write_class_id(ev)
    if type_str == "VlLs":
        items = value or []
        out = bytearray(_u32(len(items)))
        for item in items:
            if (isinstance(item, tuple) and len(item) == 2
                    and isinstance(item[0], str) and len(item[0]) == 4):
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


def _build_sold_block(uuid_hex, width, height, transform=None) -> bytes:
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
    db = _write_descriptor(desc)
    return b"8BIM" + b"SoLd" + _u32(len(db)) + db


def _guess_filetype(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    return {".png": "png ", ".jpg": "JPEG", ".jpeg": "JPEG", ".tif": "TIFF",
            ".tiff": "TIFF", ".psd": "8BPS", ".psb": "8BPS",
            ".gif": "GIFf", ".bmp": "BMP "}.get(ext, "png ")


def _build_lnk2_block(uuid_hex, filename, embedded_bytes, filetype=None) -> bytes:
    if filetype is None:
        filetype = _guess_filetype(filename)
    ub = uuid_hex.encode("ascii")[:16].ljust(16, b"0")
    link = bytearray()
    link.extend(_u32(7))
    link.extend(ub)
    link.extend(_write_unicode_string(filename))
    link.extend(filetype.encode("ascii"))
    link.extend(b"8BIM")
    link.extend(struct.pack(">Q", len(embedded_bytes)))
    link.extend(b"\x00" * 8)
    link.extend(ub)
    link.extend(_write_pascal_string(filename))
    link.extend(_write_unicode_string(filename))
    link.extend(_u32(0))
    return b"8BIM" + b"lnk2" + _u32(len(link)) + bytes(link) + embedded_bytes


def _encode_layer_png(im: Image.Image) -> bytes:
    buf = io.BytesIO()
    im.convert("RGBA").save(buf, format="PNG", optimize=False, compress_level=6)
    return buf.getvalue()


def build_smart_object_layer_info(uuid_hex, filename, embedded_bytes,
                                  canvas_width, canvas_height, transform=None) -> bytes:
    return (_build_sold_block(uuid_hex, canvas_width, canvas_height, transform)
            + _build_lnk2_block(uuid_hex, filename, embedded_bytes))


def write_smart_object_psd(layers, names, output_path, source_format="png", compression="rle") -> Path:
    try:
        from .psd_writer import write_layered_psd
    except ImportError:
        from psd_writer import write_layered_psd

    if len(layers) != len(names):
        raise ValueError("layers and names must match")
    if not layers:
        raise ValueError("at least one layer required")
    layers = [im.convert("RGBA") for im in layers]
    width, height = layers[0].size
    for im in layers:
        if im.size != (width, height):
            raise ValueError("all layers must share canvas size")

    file_layers = list(reversed(layers))
    file_names = list(reversed(names))
    blocks = []
    for im, name in zip(file_layers, file_names):
        uid = uuidlib.uuid4().hex
        payload = _encode_layer_png(im)
        blocks.append(build_smart_object_layer_info(
            uuid_hex=uid, filename=f"{name}.{source_format}",
            embedded_bytes=payload, canvas_width=width, canvas_height=height))

    raster_tmp = Path(output_path).with_suffix(".raster.tmp.psd")
    write_layered_psd(file_layers, file_names, raster_tmp, compression)
    inject_smart_object_records(raster_tmp, Path(output_path), blocks)
    raster_tmp.unlink(missing_ok=True)
    return Path(output_path)


def inject_smart_object_records(src: Path, dst: Path, info_blocks: list[bytes]) -> None:
    """Splice SoLd/lnk2 into each layer extra-data section."""
    raw = bytearray(src.read_bytes())
    if raw[:4] != b"8BPS":
        raise ValueError("source is not a PSD")
    pos = 26
    cm_len = struct.unpack_from(">I", raw, pos)[0]
    pos += 4 + cm_len
    ir_len = struct.unpack_from(">I", raw, pos)[0]
    pos += 4 + ir_len

    lm_len_pos = pos
    lm_len = struct.unpack_from(">I", raw, pos)[0]
    pos += 4

    # Nested layer-info length (from our writer)
    li_len_pos = pos
    li_len = struct.unpack_from(">I", raw, pos)[0]
    pos += 4

    layer_count = struct.unpack_from(">h", raw, pos)[0]
    pos += 2

    extra_len_positions = []
    extra_len_values = []
    for _ in range(abs(layer_count)):
        pos += 16
        chan_count = struct.unpack_from(">H", raw, pos)[0]
        pos += 2 + chan_count * 6 + 12  # blend 8BIM+norm+flags = 12
        extra_len_positions.append(pos)
        ev = struct.unpack_from(">I", raw, pos)[0]
        extra_len_values.append(ev)
        pos += 4 + ev

    if len(info_blocks) != len(extra_len_positions):
        raise ValueError(f"block count {len(info_blocks)} != layer count {len(extra_len_positions)}")

    total_added = 0
    for i in reversed(range(len(extra_len_positions))):
        block = info_blocks[i]
        ep = extra_len_positions[i]
        ev = extra_len_values[i]
        extra_end = ep + 4 + ev
        raw[extra_end:extra_end] = block
        struct.pack_into(">I", raw, ep, ev + len(block))
        total_added += len(block)

    struct.pack_into(">I", raw, lm_len_pos, lm_len + total_added)
    struct.pack_into(">I", raw, li_len_pos, li_len + total_added)
    dst.write_bytes(bytes(raw))


# Alias for older call sites
_inject = inject_smart_object_records
