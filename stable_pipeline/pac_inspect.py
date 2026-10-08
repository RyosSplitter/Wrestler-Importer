"""Read-only inspector for the PAC layout observed in our HCTP/PSP samples."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys


class FormatError(ValueError):
    """A supported structure is malformed or outside the input buffer."""


def _check_ranges(ranges: list[tuple[int, int]], limit: int, minimum: int) -> None:
    previous_end = minimum
    for start, end in sorted(ranges):
        if start < previous_end or end < start or end > limit:
            raise FormatError("Overlapping, truncated, or out-of-bounds entries")
        previous_end = end


def _text(raw: bytes) -> str:
    # Names are metadata only, never output paths.
    return raw.split(b"\0", 1)[0].decode("ascii", errors="replace")


def parse_textures(data: bytes) -> list[dict]:
    """Parse the observed named-texture table, without decoding image pixels."""
    if len(data) < 16:
        raise FormatError("Truncated texture table header")
    count, marker, reserved, table_offset = struct.unpack_from("<4I", data)
    if marker != 0x100 or reserved != 0 or table_offset != 16:
        raise FormatError("Unsupported texture table header")
    table_end = 16 + count * 32
    if count == 0 or table_end > len(data):
        raise FormatError("Invalid texture count")
    textures = []
    for i in range(count):
        row = data[16 + i * 32:48 + i * 32]
        size, offset = struct.unpack_from("<II", row, 20)
        if size == 0:
            raise FormatError("Empty texture entry")
        textures.append({
            "index": i, "name": _text(row[:16]), "extension": _text(row[16:20]),
            "offset": offset, "size": size,
        })
    _check_ranges([(t["offset"], t["offset"] + t["size"]) for t in textures],
                  len(data), table_end)
    for t in textures:
        image = data[t["offset"]:t["offset"] + t["size"]]
        t["signature"] = _text(image[:12])
        t["sha256"] = hashlib.sha256(image).hexdigest()
    return textures


def inspect_pac(data: bytes) -> dict:
    """Validate a PAC table: u16 section id, u24 offset, u24 size, all LE.

    Offsets are relative to the end of the table. This layout is confirmed
    only for the supplied samples; this does not validate game compatibility.
    """
    if len(data) < 8 or data[:4] != b"PAC ":
        raise FormatError("Missing PAC header")
    count = struct.unpack_from("<I", data, 4)[0]
    payload_start = 8 + count * 8
    if count == 0 or payload_start > len(data):
        raise FormatError("Invalid PAC section count")
    sections = []
    for i in range(count):
        row = data[8 + i * 8:16 + i * 8]
        section_id = int.from_bytes(row[:2], "little")
        relative_offset = int.from_bytes(row[2:5], "little")
        size = int.from_bytes(row[5:8], "little")
        if size == 0:
            raise FormatError("Empty PAC section")
        sections.append({"index": i, "id": section_id,
                         "offset": payload_start + relative_offset, "size": size})
    _check_ranges([(s["offset"], s["offset"] + s["size"]) for s in sections],
                  len(data), payload_start)
    warnings = []
    for s in sections:
        payload = data[s["offset"]:s["offset"] + s["size"]]
        s["sha256"] = hashlib.sha256(payload).hexdigest()
        s["signature"] = _text(payload[:4])
        if payload.startswith(b"YOBJ"):
            s["kind"] = "model_section"
            # Keep the whole section. The YOBJ size field alone does not
            # account for the extra data following the model in these samples.
        elif payload.startswith(b"RTX3"):
            s["kind"] = "standalone_rtx3"
        elif len(payload) >= 16 and payload[4:16] == struct.pack("<3I", 0x100, 0, 16):
            s["kind"] = "texture_table"
            s["textures"] = parse_textures(payload)
        else:
            s["kind"] = "unknown"
            warnings.append(f"Section index {s['index']} has an unsupported payload")
    end = max(s["offset"] + s["size"] for s in sections)
    return {"size": len(data), "sha256": hashlib.sha256(data).hexdigest(),
            "payload_start": payload_start, "section_count": count,
            "trailing_bytes": len(data) - end, "sections": sections,
            "warnings": warnings, "scope": "Container inspection; conversion is not implemented"}


def extract_pac(data: bytes, destination: Path) -> dict:
    """Extract exact section/image slices to a new directory; never overwrite."""
    report = inspect_pac(data)
    destination.mkdir(parents=True, exist_ok=False)
    for s in report["sections"]:
        payload = data[s["offset"]:s["offset"] + s["size"]]
        stem = f"section_{s['index']:02d}_id_{s['id']:04d}"
        section_file = stem + ".bin"
        (destination / section_file).write_bytes(payload)
        s["file"] = section_file
        for t in s.get("textures", []):
            extension = {"gim": "gim", "txc": "txc"}.get(t["extension"], "bin")
            image_file = f"{stem}_texture_{t['index']:02d}.{extension}"
            (destination / image_file).write_bytes(payload[t["offset"]:t["offset"] + t["size"]])
            t["file"] = image_file
    (destination / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pac", type=Path)
    parser.add_argument("--extract", type=Path, help="Extract into a NEW output directory")
    args = parser.parse_args()
    try:
        data = args.pac.read_bytes()
        report = extract_pac(data, args.extract) if args.extract else inspect_pac(data)
    except (OSError, FormatError) as exc:
        print(f"Inspection failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
