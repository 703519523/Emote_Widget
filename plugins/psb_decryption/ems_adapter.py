"""Adapt Win/KrKr PSB to EMS (Emote Web runtime) format.

Converts PSB files from various platform specs to the EMS (Emscripten-based
JavaScript runtime) format, which requires:
- spec="ems"
- Uncompressed RGBA8 textures with RGB byte order
- Resource offsets and lengths updated after decompression
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Iterator

from .psb_reader import PsbBadFormatError, PsbReader, PsbResourceRef
from .rle_compress import decompress as rle_decompress, RleCompressError
from .dxt_decoder import decompress_dxt5, DxtDecoderError


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
    """Convert an unwrapped Win/RGBA8 PSB for the bundled EMS renderer.

    This deliberately supports only uncompressed RGBA8 textures whose resource
    lengths exactly match ``width * height * 4``. Unsupported texture layouts
    fail explicitly instead of producing a structurally valid but unloadable PSB.
    """
    reader = PsbReader(data)
    parsed = reader.parse()

    if parsed["spec"] == "ems":
        return data

    if parsed["spec"] not in ("win", "krkr"):
        raise PsbBadFormatError(f"cannot adapt spec={parsed['spec']!r} to EMS (only win/krkr supported)")

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

        # Validate format - now support DXT5 in addition to RGBA8
        if tex_type is not None and tex_type not in ("RGBA8", "DXT5"):
            raise PsbBadFormatError(
                f"unsupported texture type {tex_type!r}; only RGBA8 and DXT5 are supported"
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

        # Mark for conversion if RL-compressed, RGBA8, or DXT5
        if compress == "RL" or tex_type in ("RGBA8", "DXT5"):
            if res_index not in resources_to_convert:
                resources_to_convert[res_index] = texture

    if parsed["spec"] == "krkr":
        from .psb_compiler import PsbCompiler
        root = parsed['root']
        _convert_krkr_tree_to_ems(root, data, header, resources)
        prepared_root = _prepare_root_for_compiler(root, [], [])
        return PsbCompiler(version=header['version']).compile(
            prepared_root, merge_strings=True, merge_resources=False
        )

    # Win already uses the common atlas schema. Recompile it while switching
    # the platform marker and preserving both resource index spaces.
    if parsed["spec"] == "win":
        from .psb_compiler import PsbCompiler
        root = parsed["root"]
        root["spec"] = "ems"
        regular = _extract_resource_bytes(data, header, parsed["resources"], False)
        extra = _extract_resource_bytes(data, header, parsed["extra_resources"], True)

        # Process resources that need conversion
        for resource_index, texture_info in resources_to_convert.items():
            tex_type = texture_info.get("type")
            width = texture_info.get("width")
            height = texture_info.get("height")

            if tex_type == "DXT5":
                # DXT5 decompression to RGBA8
                if not width or not height:
                    raise PsbBadFormatError(f"DXT5 texture #{resource_index} missing width/height")
                try:
                    rgba_data = decompress_dxt5(regular[resource_index], width, height)
                    regular[resource_index] = rgba_data
                except DxtDecoderError as e:
                    raise PsbBadFormatError(f"DXT5 decode failed for resource #{resource_index}: {e}") from e
            elif tex_type == "RGBA8":
                # Win RGBA8 is little-endian ARGB as consumed by System.Drawing
                # (memory bytes BGRA). EMS expects byte-order RGBA. This is the same
                # R/B conversion performed by C# ConvertToImage +
                # GetPixelBytesFromImage when switching the platform.
                regular[resource_index] = _bgr_to_rgb(regular[resource_index])

        # Update texture metadata in the tree to remove DXT5 markers
        _update_texture_metadata_for_ems(root)

        prepared_root = _prepare_root_for_compiler(root, regular, extra)
        return PsbCompiler(version=header["version"]).compile(prepared_root)

    # If no conversion needed, just return original
    return data


@dataclass
class _AtlasItem:
    path: str
    width: int
    height: int
    pixels: bytes
    icon: dict[str, Any]


@dataclass
class _Rect:
    x: int
    y: int
    width: int
    height: int
    split: int  # 0 = horizontal, 1 = vertical


def _extract_resource_bytes(
    data: bytes, header: dict[str, Any], infos: list[dict[str, Any]], extra: bool
) -> list[bytes]:
    base_key = "offset_extra_chunk_data" if extra else "offset_chunk_data"
    base = int(header[base_key])
    result: list[bytes] = []
    for info in sorted(infos, key=lambda value: value["index"]):
        start = base + int(info["offset"])
        result.append(data[start:start + int(info["length"])])
    return result


def _layout_atlas(
    items: list[_AtlasItem], size: int, padding: int
) -> tuple[list[tuple[_AtlasItem, _Rect]], list[_AtlasItem]]:
    """Port TexturePacker.LayoutAtlas with MaxOneAxis and FIFO free-list."""
    remaining = list(items)
    free: list[_Rect] = [_Rect(0, 0, size, size, 0)]
    placed: list[tuple[_AtlasItem, _Rect]] = []
    while free and remaining:
        node = free.pop(0)
        best: _AtlasItem | None = None
        best_ratio = 0.0
        for item in remaining:
            if item.width <= node.width and item.height <= node.height:
                ratio = max(item.width / node.width, item.height / node.height)
                if ratio > best_ratio:
                    best_ratio = ratio
                    best = item
        if best is None:
            continue

        if node.split == 0:  # HorizontalSplit
            right = _Rect(
                node.x + best.width + padding, node.y,
                node.width - best.width - padding, best.height, 1,
            )
            bottom = _Rect(
                node.x, node.y + best.height + padding,
                node.width, node.height - best.height - padding, 0,
            )
        else:  # VerticalSplit
            right = _Rect(
                node.x + best.width + padding, node.y,
                node.width - best.width - padding, node.height, 1,
            )
            bottom = _Rect(
                node.x, node.y + best.height + padding,
                best.width, node.height - best.height - padding, 0,
            )
        if right.width > 0 and right.height > 0:
            free.append(right)
        if bottom.width > 0 and bottom.height > 0:
            free.append(bottom)
        bounds = _Rect(node.x, node.y, best.width, best.height, node.split)
        placed.append((best, bounds))
        remaining.remove(best)
    return placed, remaining


def _pack_atlases(items: list[_AtlasItem], initial_size: int = 2048, padding: int = 5):
    remaining = list(items)
    atlases: list[tuple[int, list[tuple[_AtlasItem, _Rect]]]] = []
    while remaining:
        placed, leftovers = _layout_atlas(remaining, initial_size, padding)
        if not leftovers:
            size = initial_size
            while True:
                smaller = size // 2
                test_placed, test_leftovers = _layout_atlas(remaining, smaller, padding)
                if test_leftovers:
                    break
                size = smaller
                placed = test_placed
            placed, leftovers = _layout_atlas(remaining, size, padding)
            atlases.append((size, placed))
        else:
            atlases.append((initial_size, placed))
        remaining = leftovers
    return atlases


def _copy_icon_to_atlas(
    atlas: bytearray, atlas_size: int, item: _AtlasItem, rect: _Rect
) -> None:
    row_bytes = item.width * 4
    for y in range(item.height):
        src = y * row_bytes
        dst = ((rect.y + y) * atlas_size + rect.x) * 4
        atlas[dst:dst + row_bytes] = item.pixels[src:src + row_bytes]

    # Atlas.ApplyEdgeProcessFast(Expand1Px): copy the four edge strips.
    if rect.y > 0:
        src = (rect.y * atlas_size + rect.x) * 4
        dst = ((rect.y - 1) * atlas_size + rect.x) * 4
        atlas[dst:dst + row_bytes] = atlas[src:src + row_bytes]
    if rect.y + item.height < atlas_size:
        src = ((rect.y + item.height - 1) * atlas_size + rect.x) * 4
        dst = ((rect.y + item.height) * atlas_size + rect.x) * 4
        atlas[dst:dst + row_bytes] = atlas[src:src + row_bytes]
    if rect.x > 0:
        for y in range(item.height):
            src = ((rect.y + y) * atlas_size + rect.x) * 4
            dst = src - 4
            atlas[dst:dst + 4] = atlas[src:src + 4]
    if rect.x + item.width < atlas_size:
        for y in range(item.height):
            src = ((rect.y + y) * atlas_size + rect.x + item.width - 1) * 4
            dst = src + 4
            atlas[dst:dst + 4] = atlas[src:src + 4]


def _convert_krkr_tree_to_ems(
    root: dict[str, Any], data: bytes, header: dict[str, Any],
    resources: dict[int, dict[str, Any]],
) -> None:
    source = root.get("source")
    if not isinstance(source, dict):
        raise PsbBadFormatError("KrKr PSB source is not a dictionary")

    items: list[_AtlasItem] = []
    for group_name, group in source.items():
        if not isinstance(group, dict) or not isinstance(group.get("icon"), dict):
            continue
        for icon_name, icon in group["icon"].items():
            if not isinstance(icon, dict) or not isinstance(icon.get("pixel"), PsbResourceRef):
                continue
            ref: PsbResourceRef = icon["pixel"]
            info = resources[ref.index]
            start = int(header["offset_chunk_data"]) + int(info["offset"])
            compressed = data[start:start + int(info["length"])]
            width, height = int(icon["width"]), int(icon["height"])
            pixels = rle_decompress(
                compressed, align=4, actual_size=width * height * 4
            )
            if len(pixels) != width * height * 4:
                raise PsbBadFormatError(
                    f"bad decompressed size for {group_name}@{icon_name}: {len(pixels)}"
                )
            # KrKr stores BeRGBA8. C# RL.DecompressToImage first swaps R/B
            # into the System.Drawing BGRA representation, and
            # GetPixelBytesFromImage(BeRGBA8) swaps them back into the EMS
            # atlas convention. The net observable conversion here is the
            # R/B swap before copying raw pixels into the atlas.
            pixels = bytearray(pixels)
            for offset in range(0, len(pixels), 4):
                pixels[offset], pixels[offset + 2] = (
                    pixels[offset + 2], pixels[offset]
                )
            items.append(_AtlasItem(
                f"{group_name}@{icon_name}", width, height, bytes(pixels), icon
            ))

    area = sum(item.width * item.height for item in items)
    max_side = max(max(item.width, item.height) for item in items)
    atlas_size = 4096 if max_side >= 2048 or area > 2048 * 2048 else 2048
    packed = _pack_atlases(items, atlas_size, 5)
    icon_map: dict[str, tuple[str, str]] = {}
    new_source: dict[str, Any] = {}

    for atlas_index, (size, placements) in enumerate(packed):
        atlas = bytearray(size * size * 4)
        icons: dict[str, Any] = {}
        for item, rect in placements:
            _copy_icon_to_atlas(atlas, size, item, rect)
            icon = item.icon
            # .NET Dictionary.Remove keeps entry slots on a LIFO free-list.
            # Krkr2CommonConverter removes compress then pixel; the following
            # new left/top keys therefore occupy pixel's and compress's old
            # positions respectively. Rebuild the ordered Python mapping to
            # preserve that observable enumeration order for OptimizeMode.
            original_items = list(icon.items())
            removed_slots = [
                index for index, (key, _) in enumerate(original_items)
                if key in ("compress", "pixel")
            ]
            icon.pop("compress", None)
            icon.pop("pixel", None)
            icon["attr"] = 0
            icon["left"] = rect.x
            icon["top"] = rect.y
            if len(removed_slots) == 2:
                replacement = {
                    removed_slots[1]: ("left", rect.x),
                    removed_slots[0]: ("top", rect.y),
                }
                reordered = []
                for index, pair in enumerate(original_items):
                    if index in replacement:
                        reordered.append(replacement[index])
                    elif pair[0] not in ("compress", "pixel", "left", "top"):
                        reordered.append((pair[0], icon[pair[0]]))
                icon.clear()
                icon.update(reordered)
            if icon.get("resolution") != 1 and "resolution" in icon:
                icon["resolution_hint"] = float(icon["resolution"])
                icon.pop("resolution", None)
            meaningful = re.sub(r"^tex#.+?@", "", item.path)
            icon_name = meaningful if meaningful and meaningful not in icons else str(len(icons))
            icons[icon_name] = icon
            icon_map[item.path] = (f"tex#{atlas_index:03d}", icon_name)

        resource = {
            "_type": "resource", "index": atlas_index,
            "is_extra": False, "data": bytes(atlas),
        }
        new_source[f"tex#{atlas_index:03d}"] = {
            "icon": icons,
            "metadata": None,
            "texture": {
                "height": size, "pixel": resource,
                "truncated_height": size, "truncated_width": size,
                "type": "RGBA8", "width": size,
            },
            "type": 0,
        }

    root["source"] = new_source
    _rewrite_motion_references(root.get("object"), icon_map)
    _add_common_fields(root)
    _translate_timeline(root)
    _fix_timeline_content_values(root)
    root["spec"] = "ems"


def _rewrite_motion_references(value: Any, icon_map: dict[str, tuple[str, str]], name=None):
    if isinstance(value, dict):
        if name == "content" and "mask" in value:
            src = value.get("src")
            if isinstance(src, str):
                if src.startswith("blank"):
                    value["icon"] = src.rsplit("/", 1)[-1]
                    value["src"] = "blank"
                elif src.startswith("src/"):
                    parts = src.split("/")
                    key = f"{parts[1]}@{parts[-1]}"
                    if key in icon_map:
                        value["src"], value["icon"] = icon_map[key]
                    else:
                        value.pop("src", None)
                elif src.startswith("motion/"):
                    parts = src.split("/")
                    value["src"] = parts[1]
                    value["icon"] = parts[-1]
                elif src == "layout" or src.startswith("shape/"):
                    value.pop("src", None)
            if not value.get("ox", 0) and not value.get("oy", 0):
                value.pop("ox", None)
                value.pop("oy", None)
                value["mask"] = int(value["mask"]) & 0x7FFFFFFE
        for key, child in list(value.items()):
            _rewrite_motion_references(child, icon_map, key)
    elif isinstance(value, list):
        for child in value:
            _rewrite_motion_references(child, icon_map, name)


def _add_common_fields(root: dict[str, Any]) -> None:
    root.setdefault("easing", [])
    objects = root.get("object")
    if not isinstance(objects, dict):
        return
    for character in objects.values():
        motions = character.get("motion") if isinstance(character, dict) else None
        if not isinstance(motions, dict):
            continue
        for motion in motions.values():
            if not isinstance(motion, dict):
                continue
            motion.setdefault("bounds", {"top": 0, "left": 0, "right": 0, "bottom": 0})
            if "layerIndexMap" not in motion and isinstance(motion.get("layer"), list):
                labels: list[str] = []
                def visit(layers):
                    for layer in layers:
                        if isinstance(layer, dict) and "children" in layer:
                            if isinstance(layer.get("label"), str):
                                labels.append(layer["label"])
                            if isinstance(layer.get("children"), list):
                                visit(layer["children"])
                visit(motion["layer"])
                index_map: dict[str, int] = {}
                for label in labels:
                    if label not in index_map:
                        index_map[label] = len(index_map)
                motion["layerIndexMap"] = index_map


def _translate_timeline(root: dict[str, Any]) -> None:
    metadata = root.get("metadata")
    timelines = metadata.get("timelineControl") if isinstance(metadata, dict) else None
    if not isinstance(timelines, list):
        return
    flattened: list[Any] = []
    def visit(items, path):
        for item in items:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "folder" and isinstance(item.get("children"), list):
                visit(item["children"], f"{path}/{item.get('label', '')}")
            elif isinstance(item.get("variableList"), list):
                item["path_hint"] = f"{path}/{item.get('label', '')}"
                flattened.append(item)
    visit(timelines, "")
    metadata["timelineControl"] = flattened


def _fix_timeline_content_values(value: Any) -> None:
    if isinstance(value, dict):
        if "value" in value and isinstance(value["value"], str):
            try:
                value["value"] = int(value["value"])
            except ValueError:
                pass
        for child in value.values():
            _fix_timeline_content_values(child)
    elif isinstance(value, list):
        for child in value:
            _fix_timeline_content_values(child)


def _bgr_to_rgb(data: bytearray | bytes) -> bytes:
    """Convert BGRA memory bytes to RGBA and return immutable bytes."""
    data = bytearray(data)
    for i in range(0, len(data), 4):
        data[i], data[i + 2] = data[i + 2], data[i]
    return bytes(data)


def _update_texture_metadata_for_ems(obj: Any) -> None:
    """递归遍历对象树，修改所有纹理元数据为 EMS 格式。

    删除 'compress' 字段，确保 'type' 设置为 'RGBA8'。
    """
    if isinstance(obj, dict):
        # 检查是否是纹理描述符
        if 'pixel' in obj and isinstance(obj.get('pixel'), PsbResourceRef):
            # 删除压缩标记
            if 'compress' in obj:
                del obj['compress']
            # 确保类型为 RGBA8
            obj['type'] = 'RGBA8'

        # 递归处理所有值
        for value in obj.values():
            _update_texture_metadata_for_ems(value)
    elif isinstance(obj, list):
        # 递归处理列表项
        for item in obj:
            _update_texture_metadata_for_ems(item)


def _prepare_root_for_compiler(
    root: dict, new_resources: list[bytes], new_extra_resources: list[bytes]
) -> dict:
    """准备根对象以供编译器使用。

    将 PsbResourceRef 转换为编译器可以理解的资源标记格式。
    """
    def convert_resource_refs(obj: Any) -> Any:
        """递归转换资源引用"""
        if isinstance(obj, PsbResourceRef):
            resource_data = new_extra_resources if obj.is_extra else new_resources
            # 转换为编译器格式
            return {
                '_type': 'resource',
                'index': obj.index,
                'is_extra': obj.is_extra,
                'data': resource_data[obj.index]
                if obj.index < len(resource_data) else b''
            }
        elif isinstance(obj, dict):
            return {k: convert_resource_refs(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [convert_resource_refs(item) for item in obj]
        else:
            return obj

    return convert_resource_refs(root)
