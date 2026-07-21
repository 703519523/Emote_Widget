"""Adapt a narrowly supported Win PSB for the bundled EMS Web driver."""

from __future__ import annotations

from typing import Any, Iterator

from .psb_reader import PsbBadFormatError, PsbReader, PsbResourceRef


def _iter_texture_descriptors(value: Any) -> Iterator[dict[str, Any]]:
    if isinstance(value, dict):
        texture = value.get("texture")
        if isinstance(texture, dict) and isinstance(texture.get("pixel"), PsbResourceRef):
            yield texture
        for child in value.values():
            yield from _iter_texture_descriptors(child)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_texture_descriptors(child)


def adapt_win_psb_to_ems(data: bytes) -> bytes:
    """Convert an unwrapped Win/RGBA8 PSB for the bundled EMS renderer.

    This deliberately supports only uncompressed RGBA8 textures whose resource
    lengths exactly match ``width * height * 4``. Unsupported texture layouts
    fail explicitly instead of producing a structurally valid but unloadable PSB.
    """
    reader = PsbReader(data)
    parsed = reader.parse()
    if parsed["spec"] == "ems":
        return data
    if parsed["spec"] != "win":
        raise PsbBadFormatError(f"cannot adapt spec={parsed['spec']!r} to EMS")

    header = parsed["header"]
    resources = {resource["index"]: resource for resource in parsed["resources"]}
    textures = list(_iter_texture_descriptors(parsed["root"].get("source")))
    if not textures:
        raise PsbBadFormatError("Win PSB contains no recognizable texture descriptors")

    converted = bytearray(data)
    converted_resources: set[int] = set()
    for texture in textures:
        if texture.get("type") != "RGBA8":
            raise PsbBadFormatError(
                f"unsupported Win texture type {texture.get('type')!r}; only RGBA8 is safe"
            )
        resource_ref = texture["pixel"]
        resource = resources.get(resource_ref.index)
        if resource is None or resource_ref.is_extra:
            raise PsbBadFormatError(f"missing regular texture resource #{resource_ref.index}")
        expected = int(texture["width"]) * int(texture["height"]) * 4
        if resource["length"] != expected:
            raise PsbBadFormatError(
                f"texture resource #{resource['index']} has {resource['length']} bytes; expected {expected}"
            )
        if resource["index"] in converted_resources:
            continue
        start = header["offset_chunk_data"] + resource["offset"]
        end = start + resource["length"]
        pixels = converted[start:end]
        red = pixels[0::4]
        pixels[0::4] = pixels[2::4]
        pixels[2::4] = red
        converted[start:end] = pixels
        converted_resources.add(resource["index"])

    string_start = header["offset_strings_data"]
    replacements = 0
    for offset in reader.string_offsets:
        pos = string_start + offset
        if bytes(converted[pos:pos + 4]) == b"win\0":
            converted[pos:pos + 4] = b"ems\0"
            replacements += 1
    if replacements != 1:
        raise PsbBadFormatError(f"expected one Win spec string, found {replacements}")

    result = bytes(converted)
    verified = PsbReader(result).parse()
    if verified["spec"] != "ems" or verified["checksum_valid"] is False:
        raise PsbBadFormatError("EMS adaptation failed post-conversion validation")
    return result