"""
Minimal layered PSD writer with RGBA support and RLE compression.
PSD File Format Spec (Adobe) compliant enough for psd-tools + Photoshop.
"""
from __future__ import annotations

import struct
from pathlib import Path
from typing import Sequence

import numpy as np
from PIL import Image


def _packbits_encode(data: bytes) -> bytes:
    """Encode one scanline with PackBits."""
    out = bytearray()
    i = 0
    n = len(data)
    while i < n:
        run_byte = data[i]
        run_len = 1
        while i + run_len < n and data[i + run_len] == run_byte and run_len < 128:
            run_len += 1
        if run_len >= 3:
            out.append((256 - (run_len - 1)) & 0xFF)  # negative count
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

    # File header
    out.extend(b"8BPS")
    out.extend(struct.pack(">H", 1))          # version
    out.extend(b"\x00" * 6)                    # reserved
    out.extend(struct.pack(">H", 4))          # channels
    out.extend(struct.pack(">I", height))
    out.extend(struct.pack(">I", width))
    out.extend(struct.pack(">H", 8))          # depth
    out.extend(struct.pack(">H", 3))          # RGB

    # Color mode data (empty)
    out.extend(struct.pack(">I", 0))

    # Image resources (empty)
    out.extend(struct.pack(">I", 0))

    # Layer and mask information
    layer_and_mask = _build_layer_and_mask(layers, names, width, height, compression)
    out.extend(struct.pack(">I", len(layer_and_mask)))
    out.extend(layer_and_mask)

    # Composite image data
    composite = _flatten(layers)
    out.extend(_encode_composite(composite, compression))

    Path(output_path).write_bytes(bytes(out))
    return Path(output_path)


def _flatten(layers: Sequence[Image.Image]) -> Image.Image:
    base = Image.new("RGBA", layers[0].size, (0, 0, 0, 0))
    for im in reversed(layers):
        base = Image.alpha_composite(base, im)
    return base


def _build_layer_and_mask(layers, names, width, height, compression) -> bytes:
    layer_info_body = _build_layer_info_body(layers, names, width, height, compression)
    # Layer info length must be even
    if len(layer_info_body) % 2:
        layer_info_body += b"\x00"

    section = bytearray()
    section.extend(struct.pack(">I", len(layer_info_body)))
    section.extend(layer_info_body)
    # Global layer mask info (empty)
    section.extend(struct.pack(">I", 0))
    return bytes(section)


def _build_layer_info_body(layers, names, width, height, compression) -> bytes:
    body = bytearray()
    # Layer count (positive = first alpha is transparency)
    body.extend(struct.pack(">h", len(layers)))

    channel_blobs_per_layer = []

    for im, name in zip(layers, names):
        arr = np.asarray(im)
        # Channel order for RGB mode with transparency: R, G, B, A
        # Channel IDs: 0=R, 1=G, 2=B, -1=transparency
        planes = [
            (0, arr[..., 0]),
            (1, arr[..., 1]),
            (2, arr[..., 2]),
            (-1, arr[..., 3]),
        ]
        encoded_channels = []
        for cid, plane in planes:
            blob = _encode_channel_rle(plane) if compression == "rle" else _encode_channel_raw(plane)
            encoded_channels.append((cid, blob))
        channel_blobs_per_layer.append(encoded_channels)

        # Layer record
        body.extend(struct.pack(">i", 0))       # top
        body.extend(struct.pack(">i", 0))       # left
        body.extend(struct.pack(">i", height))  # bottom
        body.extend(struct.pack(">i", width))   # right
        body.extend(struct.pack(">H", 4))       # channel count

        for cid, blob in encoded_channels:
            body.extend(struct.pack(">h", cid))
            # Length includes the 2-byte compression field at the start of blob
            body.extend(struct.pack(">I", len(blob)))

        body.extend(b"8BIM")
        body.extend(b"norm")                    # blend mode
        body.extend(struct.pack(">B", 255))     # opacity
        body.extend(struct.pack(">B", 0))       # clipping
        body.extend(struct.pack(">B", 0))       # flags
        body.extend(struct.pack(">B", 0))       # filler

        # Extra data
        extra = bytearray()
        extra.extend(struct.pack(">I", 0))      # layer mask data length
        extra.extend(struct.pack(">I", 0))      # blending ranges length
        # Pascal string name, padded to multiple of 4
        name_bytes = name.encode("macroman", errors="replace")[:255]
        extra.append(len(name_bytes))
        extra.extend(name_bytes)
        pad = (4 - (len(name_bytes) + 1) % 4) % 4
        extra.extend(b"\x00" * pad)

        body.extend(struct.pack(">I", len(extra)))
        body.extend(extra)

    # Channel image data (same order as records)
    for encoded_channels in channel_blobs_per_layer:
        for _cid, blob in encoded_channels:
            body.extend(blob)

    return bytes(body)


def _encode_channel_raw(plane: np.ndarray) -> bytes:
    return struct.pack(">H", 0) + plane.astype(np.uint8).tobytes()


def _encode_channel_rle(plane: np.ndarray) -> bytes:
    """RLE channel data: compression(2) + row_lengths(2*h) + packed rows."""
    h, w = plane.shape
    plane = plane.astype(np.uint8)
    row_lengths = []
    packed_rows = []
    for y in range(h):
        encoded = _packbits_encode(plane[y].tobytes())
        row_lengths.append(len(encoded))
        packed_rows.append(encoded)

    out = bytearray()
    out.extend(struct.pack(">H", 1))  # RLE
    for length in row_lengths:
        out.extend(struct.pack(">H", length))
    for row in packed_rows:
        out.extend(row)
    return bytes(out)


def _encode_composite(im: Image.Image, compression: str) -> bytes:
    arr = np.asarray(im.convert("RGBA"))
    planes = [arr[..., 0], arr[..., 1], arr[..., 2], arr[..., 3]]
    out = bytearray()
    if compression == "raw":
        out.extend(struct.pack(">H", 0))
        for plane in planes:
            out.extend(plane.astype(np.uint8).tobytes())
    else:
        out.extend(struct.pack(">H", 1))
        # For composite: all channel row-length tables first, then data
        # Spec: for each channel, row lengths then data — interleaved per channel
        all_lengths = []
        all_data = []
        for plane in planes:
            plane = plane.astype(np.uint8)
            lengths = []
            data = []
            for y in range(plane.shape[0]):
                encoded = _packbits_encode(plane[y].tobytes())
                lengths.append(len(encoded))
                data.append(encoded)
            all_lengths.append(lengths)
            all_data.append(data)
        for lengths in all_lengths:
            for L in lengths:
                out.extend(struct.pack(">H", L))
        for data in all_data:
            for row in data:
                out.extend(row)
    return bytes(out)
