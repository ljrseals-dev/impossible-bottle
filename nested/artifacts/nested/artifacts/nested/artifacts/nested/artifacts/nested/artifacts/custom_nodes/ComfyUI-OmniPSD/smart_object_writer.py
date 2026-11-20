"""
Smart Object PSD writer.

Each layer carries:
  - 8BIM/SoLd  : placed layer data (transform, ID)
  - 8BIM/lnk2  : linked layer with embedded PNG bytes

Built on top of the verified raster writer by constructing full
layer records with SoLd/lnk2 in the extra-data section from the start.
"""
from __future__ import annotations

import io
import struct
import uuid as uuidlib
from collections import OrderedDict
from pathlib import Path
from typing import Any, Sequence

import numpy as np
from PIL import Image

from .psd_writer import (
    _packbits_encode,
    _flatten,
    write_layered_psd,
)


def _u32(v: int) -> bytes:
    return struct.pack(">I", v)


def _u16(v: int) -> bytes:
    return struct.pack(">H", v)


def _i32(v: int) -> bytes:
    return struct.pack(">i", v)


def _f64(v: float) -> bytes:
    return struct.pack(">d", v)


def _write_unicode_string(s: str) -> bytes:
    if not s:
        return _u32(0)
    encoded = s.encode("utf-16-be")
    # Char count includes the null terminator in some PSD variants;
    # Adobe uses count of UTF-16 code units without forcing null.
    return _u32(len(encoded) // 2) + encoded


def _write_class_id(name: str) -> bytes:
    if not name:
        return _u32(0)
    raw = name.encode("ascii", errors="replace")
    if len(raw) == 4:
        # 4-char keys are written as length 0 + 4-byte key
        return _u32(0) + raw
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
        return unit.encode("ascii")[:4].ljust(4, b" ") + _f64(float(val))
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
        # Key: 4-char keys as length 0 + key, longer as length + name
        if len(key) == 4:
            out.extend(_u32(0) + key.encode("ascii"))
        else:
            kb = key.encode("ascii")
            out.extend(_u32(len(kb)) + kb)
            pad = (4 - len(kb) % 4) % 4
            out.extend(b"\x00" * pad)
        out.extend(type_str.encode("ascii"))
        out.extend(_write_value(type_str, value))
    return bytes(out)


def _build_sold_block(uuid_hex: str, transform: Sequence[float] | None = None) -> bytes:
    if transform is None:
        transform = [1.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0]
    transform = list(transform)
    while len(transform) < 8:
        transform.append(0.0)

    desc: OrderedDict = OrderedDict()
    desc["Idnt"] = ("TEXT", uuid_hex)
    desc["PgNm"] = ("long", 1)
    desc["totalPages"] = ("long", 1)
    desc["Crop"] = ("bool", False)
    desc["frameStep"] = ("Objc", OrderedDict([
        ("numerator", ("long", 0)),
        ("denominator", ("long", 1)),
    ]))
    desc["duration"] = ("Objc", OrderedDict([
        ("numerator", ("long", 0)),
        ("denominator", ("long", 1)),
    ]))
    desc["frameCount"] = ("long", 1)
    desc["Annt"] = ("enum", ("Annt", "Anno"))
    desc["Type"] = ("enum", ("rasterConvertType", "rasterizeContent"))
    desc["Trnf"] = ("VlLs", [("doub", v) for v in transform])
    desc["nonAffineTransform"] = ("VlLs", [("doub", v) for v in transform])
    desc["Sz  "] = ("Objc", OrderedDict([
        ("Wdth", ("UntF", ("#Pxl", 0.0))),
        ("Hght", ("UntF", ("#Pxl", 0.0))),
    ]))
    desc["Rslt"] = ("UntF", ("#Rsl", 72.0))

    # SoLd: 8BIM SoLd + length + soLD + version(4) + descVersion(16) + descriptor
    # See psd-tools Tag.SMART_OBJECT_LAYER_DATA1 / PlacedLayerData
    desc_bytes = _write_descriptor(desc)
    body = b"soLD" + _u32(4) + _u32(16) + desc_bytes

    out = bytearray()
    out.extend(b"8BIM")
    out.extend(b"SoLd")
    # Length must be even
    if len(body) % 2:
        body = body + b"\x00"
    out.extend(_u32(len(body)))
    out.extend(body)
    return bytes(out)


def _guess_filetype(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    return {
        ".png": "png ", ".jpg": "JPEG", ".jpeg": "JPEG",
        ".tif": "TIFF", ".tiff": "TIFF", ".psd": "8BPS",
    }.get(ext, "png ")


def _build_lnk2_block(uuid_hex: str, filename: str, embedded_bytes: bytes) -> bytes:
    filetype = _guess_filetype(filename)
    uuid_bytes = uuid_hex.encode("ascii")[:16].ljust(16, b"0")

    # LinkedFile data (version 7)
    link = bytearray()
    link.extend(_u32(7))  # version
    link.extend(uuid_bytes)
    link.extend(_write_unicode_string(filename))
    link.extend(filetype.encode("ascii")[:4].ljust(4, b" "))
    link.extend(b"8BIM")  # creator
    link.extend(struct.pack(">Q", len(embedded_bytes)))  # 8-byte size
    link.extend(b"\x00" * 8)  # file open descriptor (empty)
    link.extend(uuid_bytes)
    link.extend(_write_pascal_string(filename))
    link.extend(_write_unicode_string(filename))
    link.extend(_u32(0))  # child documents count / end marker

    # Full block = header + link metadata + embedded bytes
    payload = bytes(link) + embedded_bytes
    out = bytearray()
    out.extend(b"8BIM")
    out.extend(b"lnk2")
    out.extend(_u32(len(payload)))
    out.extend(payload)
    if len(payload) % 2:
        out.extend(b"\x00")
    return bytes(out)


def _encode_layer_png(im: Image.Image) -> bytes:
    buf = io.BytesIO()
    im.convert("RGBA").save(buf, format="PNG", optimize=False, compress_level=6)
    return buf.getvalue()


def _encode_channel_rle(plane: np.ndarray) -> bytes:
    h = plane.shape[0]
    plane = plane.astype(np.uint8)
    row_lengths = []
    packed = []
    for y in range(h):
        enc = _packbits_encode(plane[y].tobytes())
        row_lengths.append(len(enc))
        packed.append(enc)
    out = bytearray()
    out.extend(struct.pack(">H", 1))
    for L in row_lengths:
        out.extend(struct.pack(">H", L))
    for row in packed:
        out.extend(row)
    return bytes(out)


def write_smart_object_psd(
    layers: Sequence[Image.Image],
    names: Sequence[str],
    output_path: str | Path,
    compression: str = "rle",
) -> Path:
    """
    Write a layered PSD where each layer record includes SoLd + lnk2 blocks.
    Pixel data remains as normal channel image data (Photoshop still needs it
    for the layer preview); the smart-object blocks provide the embedded source.
    """
    if len(layers) != len(names):
        raise ValueError("layers and names must match")
    if not layers:
        raise ValueError("at least one layer required")

    layers = [im.convert("RGBA") for im in layers]
    width, height = layers[0].size
    for im in layers:
        if im.size != (width, height):
            raise ValueError("all layers must share canvas size")

    # File order is bottom-to-top
    file_layers = list(reversed(layers))
    file_names = list(reversed(names))

    out = bytearray()
    # Header
    out.extend(b"8BPS")
    out.extend(struct.pack(">H", 1))
    out.extend(b"\x00" * 6)
    out.extend(struct.pack(">H", 4))
    out.extend(struct.pack(">I", height))
    out.extend(struct.pack(">I", width))
    out.extend(struct.pack(">H", 8))
    out.extend(struct.pack(">H", 3))
    out.extend(struct.pack(">I", 0))  # color mode data
    out.extend(struct.pack(">I", 0))  # image resources

    # Build layer info body with smart-object extras
    li = bytearray()
    li.extend(struct.pack(">h", len(file_layers)))
    channel_blobs_all = []

    for im, name in zip(file_layers, file_names):
        arr = np.asarray(im)
        planes = [
            (0, arr[..., 0]),
            (1, arr[..., 1]),
            (2, arr[..., 2]),
            (-1, arr[..., 3]),
        ]
        encoded = []
        for cid, plane in planes:
            blob = _encode_channel_rle(plane) if compression == "rle" else (
                struct.pack(">H", 0) + plane.astype(np.uint8).tobytes()
            )
            encoded.append((cid, blob))
        channel_blobs_all.append(encoded)

        # Layer record
        li.extend(struct.pack(">i", 0))
        li.extend(struct.pack(">i", 0))
        li.extend(struct.pack(">i", height))
        li.extend(struct.pack(">i", width))
        li.extend(struct.pack(">H", 4))
        for cid, blob in encoded:
            li.extend(struct.pack(">h", cid))
            li.extend(struct.pack(">I", len(blob)))

        li.extend(b"8BIM")
        li.extend(b"norm")
        li.extend(struct.pack(">BBBB", 255, 0, 0, 0))

        # Extra data: mask(0) + blending(0) + name + SoLd + lnk2
        uid = uuidlib.uuid4().hex
        fname = f"{name}.png"
        png_bytes = _encode_layer_png(im)
        sold = _build_sold_block(uid)
        lnk2 = _build_lnk2_block(uid, fname, png_bytes)

        extra = bytearray()
        extra.extend(struct.pack(">I", 0))  # mask
        extra.extend(struct.pack(">I", 0))  # blending ranges
        name_bytes = name.encode("macroman", errors="replace")[:255]
        extra.append(len(name_bytes))
        extra.extend(name_bytes)
        pad = (4 - (len(name_bytes) + 1) % 4) % 4
        extra.extend(b"\x00" * pad)
        extra.extend(sold)
        extra.extend(lnk2)

        li.extend(struct.pack(">I", len(extra)))
        li.extend(extra)

    for encoded in channel_blobs_all:
        for _cid, blob in encoded:
            li.extend(blob)
    if len(li) % 2:
        li.extend(b"\x00")

    # Layer and mask section
    layer_and_mask = bytearray()
    layer_and_mask.extend(struct.pack(">I", len(li)))
    layer_and_mask.extend(li)
    layer_and_mask.extend(struct.pack(">I", 0))  # global mask

    out.extend(struct.pack(">I", len(layer_and_mask)))
    out.extend(layer_and_mask)

    # Composite
    composite = _flatten(file_layers)
    # Reuse composite encoder from raster writer path
    arr = np.asarray(composite)
    planes = [arr[..., 0], arr[..., 1], arr[..., 2], arr[..., 3]]
    if compression == "raw":
        out.extend(struct.pack(">H", 0))
        for p in planes:
            out.extend(p.astype(np.uint8).tobytes())
    else:
        out.extend(struct.pack(">H", 1))
        all_lengths = []
        all_data = []
        for plane in planes:
            plane = plane.astype(np.uint8)
            lengths, data = [], []
            for y in range(plane.shape[0]):
                enc = _packbits_encode(plane[y].tobytes())
                lengths.append(len(enc))
                data.append(enc)
            all_lengths.append(lengths)
            all_data.append(data)
        for lengths in all_lengths:
            for L in lengths:
                out.extend(struct.pack(">H", L))
        for data in all_data:
            for row in data:
                out.extend(row)

    Path(output_path).write_bytes(bytes(out))
    return Path(output_path)
