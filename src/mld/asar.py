"""Minimal, dependency-free reader/writer for Electron's asar format.

Only packed entries are supported. The layout is the one Electron uses:

    4 bytes   uint32  4
    4 bytes   uint32  header size (bytes from offset 8 to the data area)
    4 bytes   uint32  pickled payload size
    4 bytes   uint32  JSON length
    N bytes   JSON header
    padding   to an 8-byte boundary
    file data, concatenated in header order

Each file entry carries ``offset`` (relative to the data area), ``size`` and an
``integrity`` block (SHA-256, 4 MiB blocks).
"""

from __future__ import annotations

import hashlib
import json
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

BLOCK = 4 * 1024 * 1024


@dataclass
class Asar:
    tree: dict
    entries: List[Tuple[str, dict]]
    contents: Dict[str, bytes]

    def get(self, path: str) -> bytes:
        return self.contents["/" + path.lstrip("/")]


def load(path: str | Path) -> Asar:
    raw = Path(path).read_bytes()
    if len(raw) < 16 or struct.unpack("<I", raw[0:4])[0] != 4:
        raise ValueError("not an asar archive")
    header_size, payload_size, json_len = struct.unpack("<III", raw[4:16])
    if 16 + json_len > len(raw):
        raise ValueError("truncated asar header")
    tree = json.loads(raw[16:16 + json_len])
    data_start = 8 + header_size

    entries: List[Tuple[str, dict]] = []
    def walk(node, prefix=""):
        for name, value in node.items():
            full = prefix + "/" + name
            if "files" in value:
                walk(value["files"], full)
            else:
                entries.append((full, value))
    walk(tree.get("files", {}))

    contents = {}
    for full, meta in entries:
        if meta.get("unpacked"):
            raise ValueError("unpacked asar entries are not supported: " + full)
        off = data_start + int(meta["offset"])
        contents[full] = raw[off:off + int(meta["size"])]
    return Asar(tree, entries, contents)


def _integrity(data: bytes) -> dict:
    blocks = [hashlib.sha256(data[i:i + BLOCK]).hexdigest()
              for i in range(0, len(data), BLOCK)] or [hashlib.sha256(b"").hexdigest()]
    return {
        "algorithm": "SHA256",
        "hash": hashlib.sha256(data).hexdigest(),
        "blockSize": BLOCK,
        "blocks": blocks,
    }


def build(asar: Asar) -> bytes:
    """Serialize ``asar`` back to bytes, recomputing offsets and hashes."""
    pos = 0
    def set_meta(node, prefix=""):
        nonlocal pos
        for name, value in node.items():
            full = prefix + "/" + name
            if "files" in value:
                set_meta(value["files"], full)
            else:
                data = asar.contents[full]
                value["size"] = len(data)
                value["offset"] = str(pos)
                value["integrity"] = _integrity(data)
                pos += len(data)
    set_meta(asar.tree["files"])

    header = json.dumps(asar.tree, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    payload = 4 + len(header)
    inner = 4 + payload
    pad = (8 - inner % 8) % 8
    header_size = inner + pad
    out = bytearray(struct.pack("<IIII", 4, header_size, payload + pad, len(header)))
    out += header + b"\x00" * pad
    for full, _ in asar.entries:
        out += asar.contents[full]
    return bytes(out)


def verify_bytes(raw: bytes) -> None:
    """Sanity-check a serialized archive (offsets, hashes, contiguity)."""
    header_size, _, json_len = struct.unpack("<III", raw[4:16])
    tree = json.loads(raw[16:16 + json_len])
    data_start = 8 + header_size
    pos = 0
    def walk(node, prefix=""):
        nonlocal pos
        for name, value in node.items():
            full = prefix + "/" + name
            if "files" in value:
                walk(value["files"], full)
            else:
                if int(value["offset"]) != pos:
                    raise ValueError("non-contiguous offset at " + full)
                data = raw[data_start + pos:data_start + pos + int(value["size"])]
                if hashlib.sha256(data).hexdigest() != value["integrity"]["hash"]:
                    raise ValueError("hash mismatch at " + full)
                pos += int(value["size"])
    walk(tree["files"])
    if data_start + pos != len(raw):
        raise ValueError("trailing bytes in asar")