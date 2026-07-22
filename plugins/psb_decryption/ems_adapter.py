"""Adapt Win/KrKr PSB to EMS (Emote Web runtime) format.

Converts PSB files from various platform specs to the EMS (Emscripten-based
JavaScript runtime) format, which requires:
- spec="ems" 
- Uncompressed RGBA8 textures with RGB byte order
- Resource offsets and lengths updated after decompression
"""

from __future__ import annotations

from typing import Any, Iterator

from .psb_reader import PsbBadFormatError, PsbReader, PsbResourceRef
from .rle_compress import decompress as rle_decompress, RleCompressError


def _iter_texture_descriptors(value: Any) -> Iterator[dict[str, Any]]:
    """Recursively find all texture descriptors in PSB tree."""
    if isinstance(value, dict):
        # Win/EMS style: texture wrapper
        texture = value.get("texture")
        if isinstance(texture, dict) and isinstance(texture.get("pixel"), PsbResourceRef):
            yield texture
        
        # KrKr style: direct texture without wrapper, identified by 'pixel' + 'width' + 'height'
        if (isinstance(value.get("pixel"), PsbResourceRef) and 
            "width" in value and "height" in value):
            yield value
        
        for child in value.values():
            yield from _iter_texture_descriptors(child)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_texture_descriptors(child)


def adapt_win_psb_to_ems(data: bytes) -> bytes:
    """Convert an unwrapped Win/KrKr PSB for the bundled EMS renderer.

    This deliberately supports only uncompressed RGBA8 textures whose resource
    lengths exactly match ``width * height * 4``. Unsupported texture layouts
    fail explicitly instead of producing a structurally valid but unloadable PSB.
    """
    reader = PsbReader(data)
    parsed = reader.parse()
    
    if parsed["spec"] == "ems":
        return data
    
    if parsed["spec"] not in ("win", "krkr"):
        raise PsbBadFormatError(f"cannot adapt spec={parsed['spec']!r} to EMS")

    header = parsed["header"]
    resources = {resource["index"]: resource for resource in parsed["resources"]}
    textures = list(_iter_texture_descriptors(parsed["root"].get("source")))
    
    if not textures:
        raise PsbBadFormatError("PSB contains no recognizable texture descriptors")

    # Mark resources that need conversion
    resources_to_convert: dict[int, dict] = {}  # res_index -> texture_info
    
    for texture in textures:
        # Get texture format
        tex_type = texture.get("type")
        compress = texture.get("compress")
        
        # Validate format
        if tex_type is not None and tex_type != "RGBA8":
            raise PsbBadFormatError(
                f"unsupported texture type {tex_type!r}; only RGBA8 is safe"
            )
        
        if compress is not None and compress != "RL":
            raise PsbBadFormatError(
                f"unsupported compression {compress!r}; only RL is supported"
            )
        
        resource_ref = texture["pixel"]
        resource = resources.get(resource_ref.index)
        
        if resource is None or resource_ref.is_extra:
            raise PsbBadFormatError(f"missing regular texture resource #{resource_ref.index}")
        
        res_index = resource["index"]
        
        # Mark for conversion if RL-compressed or RGBA8
        if compress == "RL" or tex_type == "RGBA8":
            if res_index not in resources_to_convert:
                resources_to_convert[res_index] = texture

    # Build new resources list if we need to convert anything
    if resources_to_convert:
        from .psb_builder import PsbBuilder
        
        # Build list of new resources in order (using decompressed data where available)
        # Note: After decompression, offsets in 'converted' are invalid,
        # but we stored the new lengths in resource metadata
        new_resources = []
        for resource in sorted(resources.values(), key=lambda r: r['index']):
            res_index = resource['index']
            if res_index in resources_to_convert:
                # Extract from original data (before in-place modifications)
                # and re-decompress
                orig_start = header['offset_chunk_data'] + resource['offset']
                orig_end = orig_start + parsed['resources'][res_index]['length']
                
                # Get texture info and extract data
                compressed = data[orig_start:orig_end]
                tex_info = resources_to_convert[res_index]
                if tex_info.get('compress') == 'RL':
                    # Decompress RL
                    width = int(tex_info['width'])
                    height = int(tex_info['height'])
                    expected_size = width * height * 4
                    try:
                        decompressed = rle_decompress(compressed, align=4, actual_size=expected_size)
                    except RleCompressError as exc:
                        raise PsbBadFormatError(
                            f"RL decompression failed for resource #{res_index}: {exc}"
                        ) from exc
                    _bgr_to_rgb_inplace(decompressed)
                    new_resources.append(bytes(decompressed))
                else:
                    # RGBA8, just BGR→RGB swap
                    pixels = bytearray(compressed)
                    _bgr_to_rgb_inplace(pixels)
                    new_resources.append(bytes(pixels))
            else:
                # Use original data unchanged
                orig_start = header['offset_chunk_data'] + resource['offset']
                orig_end = orig_start + resource['length']
                new_resources.append(data[orig_start:orig_end])
        
        # Rebuild PSB with new resources
        builder = PsbBuilder(version=header['version'])
        result = builder.rebuild_with_new_resources(
            original_psb=data,
            new_resources=new_resources,
            new_spec='ems'
        )
        
        return result
    
    # If no conversion needed, just return original
    return data


def _bgr_to_rgb_inplace(data: bytearray | bytes) -> None:
    """Swap B and R channels in BGRA data (inplace for bytearray)."""
    if isinstance(data, bytes):
        data = bytearray(data)
    
    for i in range(0, len(data), 4):
        data[i], data[i + 2] = data[i + 2], data[i]
