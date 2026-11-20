"""Template-based smart-object extraction from a Photoshop-saved reference PSD."""
from __future__ import annotations

import struct
from pathlib import Path


def extract_template(reference_psd: Path) -> dict:
    raw = reference_psd.read_bytes()
    sold_pos = raw.find(b"8BIMSoLd")
    lnk2_pos = raw.find(b"8BIMlnk2")
    if sold_pos < 0 or lnk2_pos < 0:
        raise ValueError("no smart object found in reference PSD")

    sold_len = struct.unpack_from(">I", raw, sold_pos + 8)[0]
    sold = raw[sold_pos:sold_pos + 12 + sold_len]
    lnk2_len = struct.unpack_from(">I", raw, lnk2_pos + 8)[0]
    lnk2 = raw[lnk2_pos:lnk2_pos + 12 + lnk2_len]

    sold_body = sold[12:]
    uuid_off = -1
    for i in range(0, len(sold_body) - 16):
        chunk = sold_body[i:i + 16]
        if all(48 <= b <= 57 or 97 <= b <= 102 for b in chunk):
            uuid_off = 12 + i
            break
    if uuid_off < 0:
        raise ValueError("could not locate UUID in SoLd descriptor")

    lnk2_uuid_off = 12 + 4
    body = lnk2[12:]
    creator = body.find(b"8BIM")
    if creator < 0:
        raise ValueError("could not locate creator signature in lnk2")
    lnk2_size_off = 12 + creator + 4

    return {
        "sold_template": sold,
        "lnk2_template": lnk2,
        "sold_uuid_off": uuid_off,
        "lnk2_uuid_off": lnk2_uuid_off,
        "lnk2_size_off": lnk2_size_off,
        "reference_path": str(reference_psd),
    }


def build_layer_blocks_from_template(template: dict, uuid_hex: str, embedded_bytes: bytes) -> bytes:
    sold = bytearray(template["sold_template"])
    lnk2 = bytearray(template["lnk2_template"])
    ub = uuid_hex.encode("ascii")[:16].ljust(16, b"0")
    sold[template["sold_uuid_off"]:template["sold_uuid_off"] + 16] = ub
    lnk2[template["lnk2_uuid_off"]:template["lnk2_uuid_off"] + 16] = ub
    struct.pack_into(">Q", lnk2, template["lnk2_size_off"], len(embedded_bytes))
    return bytes(sold) + bytes(lnk2) + embedded_bytes
