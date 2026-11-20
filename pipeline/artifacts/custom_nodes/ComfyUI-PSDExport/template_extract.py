"""Extract SoLd/lnk2 template from a Photoshop-saved reference PSD."""
from __future__ import annotations

import base64
import struct
from pathlib import Path


def _scan_for_uuid(body: bytes) -> int:
    """Find 16 ASCII hex bytes, or 32 UTF-16BE hex digits (TEXT field)."""
    for i in range(0, len(body) - 16):
        chunk = body[i:i + 16]
        if all(48 <= b <= 57 or 97 <= b <= 102 for b in chunk):
            return i
    # UTF-16BE: each hex char is 0x00 followed by the ASCII digit
    for i in range(0, len(body) - 32):
        chunk = body[i:i + 32]
        if all(
            (j % 2 == 0 and chunk[j] == 0)
            or (j % 2 == 1 and (48 <= chunk[j] <= 57 or 97 <= chunk[j] <= 102))
            for j in range(32)
        ):
            return i
    return -1


def extract_template(reference_psd: Path) -> dict:
    ref = Path(reference_psd)
    if not ref.exists():
        raise FileNotFoundError(f"reference PSD not found: {ref}")
    raw = ref.read_bytes()
    if raw[:4] != b"8BPS":
        raise ValueError("reference is not a PSD")
    sold_pos = raw.find(b"8BIMSoLd")
    lnk2_pos = raw.find(b"8BIMlnk2")
    if sold_pos < 0 or lnk2_pos < 0:
        raise ValueError("no smart object blocks found in reference")
    sold_len = struct.unpack_from(">I", raw, sold_pos + 8)[0]
    sold = raw[sold_pos:sold_pos + 12 + sold_len]
    lnk2_len = struct.unpack_from(">I", raw, lnk2_pos + 8)[0]
    lnk2 = raw[lnk2_pos:lnk2_pos + 12 + lnk2_len]
    uuid_off = _scan_for_uuid(sold[12:])
    if uuid_off < 0:
        raise ValueError("could not locate UUID in SoLd descriptor")
    body = lnk2[12:]
    creator = body.find(b"8BIM")
    if creator < 0:
        raise ValueError("could not locate creator signature in lnk2")
    return {
        "sold_template": sold,
        "lnk2_template": lnk2,
        "sold_uuid_off": 12 + uuid_off,
        "lnk2_uuid_off": 12 + 4,
        "lnk2_size_off": 12 + creator + 4,
        "reference_path": str(ref),
    }


def build_layer_blocks_from_template(template: dict, uuid_hex: str, embedded_bytes: bytes) -> bytes:
    sold = bytearray(template["sold_template"])
    lnk2 = bytearray(template["lnk2_template"])
    hex16 = uuid_hex.lower()[:32].ljust(32, "0")[:32]
    # SoLd UUID may be ASCII (16) or UTF-16BE (32)
    so = template["sold_uuid_off"]
    remaining = len(sold) - so
    if remaining >= 32 and sold[so] == 0:
        ub_sold = hex16.encode("utf-16-be")
        sold[so:so + 32] = ub_sold
    else:
        ub_sold = hex16[:16].encode("ascii")
        sold[so:so + 16] = ub_sold
    # lnk2 UUID is always 16 ASCII in our writer
    lo = template["lnk2_uuid_off"]
    lnk2[lo:lo + 16] = hex16[:16].encode("ascii")
    struct.pack_into(">Q", lnk2, template["lnk2_size_off"], len(embedded_bytes))
    return bytes(sold) + bytes(lnk2) + embedded_bytes


def template_to_token(template: dict) -> dict:
    return {
        "sold": base64.b64encode(template["sold_template"]).decode("ascii"),
        "lnk2": base64.b64encode(template["lnk2_template"]).decode("ascii"),
        "sold_uuid_off": template["sold_uuid_off"],
        "lnk2_uuid_off": template["lnk2_uuid_off"],
        "lnk2_size_off": template["lnk2_size_off"],
    }


def token_to_template(token: dict) -> dict:
    return {
        "sold_template": base64.b64decode(token["sold"]),
        "lnk2_template": base64.b64decode(token["lnk2"]),
        "sold_uuid_off": int(token["sold_uuid_off"]),
        "lnk2_uuid_off": int(token["lnk2_uuid_off"]),
        "lnk2_size_off": int(token["lnk2_size_off"]),
    }
