"""Minimal layered PSD writer with RGBA support and RLE compression."""
from __future__ import annotations

import struct
from pathlib import Path
from typing import Sequence

import numpy as np
from PIL import Image


def _packbits_encode(data: bytes) -> bytes:
    out = bytearray()
    i = 0
    n = len(data)
    while i < n:
        run_byte = data[i]
        run_len = 1
        while i + run_len < n and data[i + run_len] == run_byte and run_len < 128:
            run_len += 1
        if run_len >= 3:
            out.append(257 - run_len)
            out.append(run_byte)
            i += run_len
        else:
            lit_start = i
            lit_len = 1
            while i + lit_len < n and lit_len < 128:
                if (i + lit_len + 2 < n
                        and data[i + lit_len] == data[i + lit_len + 1]
                        == data[i + lit_len + 2]):
                    break
                lit_len += 1
            out.append(lit_len - 1)
            out.extend(data[lit_start:lit_start + lit_len])
            i += lit_len
    return bytes(out)


def write_layered_psd(
    layers: Sequence[Image.Image],
    names: Sequence[str],
    output_path: str | Path,
    compression: str = "rle",
) -> Path:
    if len(layers) != len(names):
        raise ValueError("layers and names must have the same length")
    if not layers:
        raise ValueError("at least one layer required")

    layers = [im.convert("RGBA") for im in layers]
    width, height = layers[0].size
    for im in layers:
        if im.size != (width, height):
            raise ValueError("all layers must share the same canvas size")

    out = bytearray()
    out.extend(b"8BPS")
    out.extend(struct.pack(">H", 1))
    out.extend(b"\x00" * 6)
    out.extend(struct.pack(">H", 4))
    out.extend(struct.pack(">I", height))
    out.extend(struct.pack(">I", width))
    out.extend(struct.pack(">H", 8))
    out.extend(struct.pack(">H", 3))
    out.extend(struct.pack(">I", 0))
    out.extend(struct.pack(">I", 0))

    layer_section = _build_layer_section(layers, names, width, height, compression)
    out.extend(struct.pack(">I", len(layer_section)))
    out.extend(layer_section)

    composite = _flatten(layers)
    out.extend(_encode_image_data(composite, compression))

    Path(output_path).write_bytes(bytes(out))
    return Path(output_path)


def _flatten(layers: Sequence[Image.Image]) -> Image.Image:
    base = Image.new("RGBA", layers[0].size, (0, 0, 0, 0))
    for im in reversed(layers):
        base = Image.alpha_composite(base, im)
    return base


def _build_layer_section(layers, names, width, height, compression) -> bytes:
    layer_info = bytearray()
    layer_info.extend(struct.pack(">h", len(layers)))
    channel_data_blobs = []

    for im, name in zip(layers, names):
        record = bytearray()
        record.extend(struct.pack(">iiii", 0, 0, height, width))
        record.extend(struct.pack(">H", 4))
        arr = np.array(im)
        chan_ids = [0, 1, 2, -1]
        chan_blobs = []
        for cid in chan_ids:
            plane = arr[..., 3] if cid == -1 else arr[..., cid]
            blob = _encode_channel_plane(plane, compression)
            chan_blobs.append(blob)
            record.extend(struct.pack(">h", cid))
            record.extend(struct.pack(">I", len(blob) + 2))
        channel_data_blobs.append(chan_blobs)

        record.extend(b"8BIM")
        record.extend(b"norm")
        record.extend(struct.pack(">BBBB", 255, 0, 0, 0))

        extra = bytearray()
        extra.extend(struct.pack(">I", 0))
        extra.extend(struct.pack(">I", 0))
        name_bytes = name.encode("utf-8")
        extra.extend(struct.pack(">B", len(name_bytes)))
        extra.extend(name_bytes)
        pad = (4 - (len(name_bytes) + 1) % 4) % 4
        extra.extend(b"\x00" * pad)
        record.extend(struct.pack(">I", len(extra)))
        record.extend(extra)
        layer_info.extend(record)

    for chan_blobs in channel_data_blobs:
        for blob in chan_blobs:
            layer_info.extend(blob)
    if len(layer_info) % 2:
        layer_info.extend(b"\x00")
    return bytes(layer_info) + struct.pack(">I", 0)


def _encode_channel_plane(plane: np.ndarray, compression: str) -> bytes:
    h, w = plane.shape
    if compression == "raw":
        return struct.pack(">H", 0) + plane.tobytes()
    out = bytearray()
    out.extend(struct.pack(">H", 1))
    for row in range(h):
        encoded = _packbits_encode(plane[row].tobytes())
        out.extend(struct.pack(">H", len(encoded)))
        out.extend(encoded)
    return bytes(out)


def _encode_image_data(im: Image.Image, compression: str) -> bytes:
    arr = np.array(im)
    planes = [arr[..., 0], arr[..., 1], arr[..., 2], arr[..., 3]]
    out = bytearray()
    if compression == "raw":
        out.extend(struct.pack(">H", 0))
        for plane in planes:
            out.extend(plane.tobytes())
    else:
        out.extend(struct.pack(">H", 1))
        for plane in planes:
            for row in plane:
                encoded = _packbits_encode(row.tobytes())
                out.extend(struct.pack(">H", len(encoded)))
                out.extend(encoded)
    return bytes(out)
