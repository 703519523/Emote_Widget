"""PSB 静态校验与保守的模型健康诊断。"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Iterator, cast

from .psb_converter import PsbBadFormatError, PsbReader
from .psb_converter.psb_reader import PsbResourceRef


@dataclass(frozen=True)
class ModelHealthIssue:
    code: str
    severity: str
    message: str
    path: str = ""
    details: dict[str, Any] = field(default_factory=lambda: cast(dict[str, Any], {}))


@dataclass(frozen=True)
class ModelHealthReport:
    accepted: bool
    issues: tuple[ModelHealthIssue, ...]
    summary: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "issues": [asdict(issue) for issue in self.issues],
            "summary": self.summary,
        }


class ModelValidationError(ValueError):
    def __init__(self, code: str, message: str, report: ModelHealthReport | None = None):
        super().__init__(message)
        self.code = code
        self.report = report


def _walk(value: Any, path: str = "root") -> Iterator[tuple[str, Any]]:
    yield path, value
    if isinstance(value, dict):
        mapping = cast(dict[str, Any], value)
        for key, child in mapping.items():
            yield from _walk(child, f"{path}.{key}")
    elif isinstance(value, list):
        items = cast(list[Any], value)
        for index, child in enumerate(items):
            yield from _walk(child, f"{path}[{index}]")


def _as_mapping(value: Any) -> dict[str, Any]:
    """将解析器输出安全收窄为字符串键字典。"""
    if isinstance(value, dict):
        return cast(dict[str, Any], value)
    return {}


def inspect_model_bytes(data: bytes) -> ModelHealthReport:
    """解析裸 PSB，并报告硬错误与保守的健康警告。"""
    try:
        parsed = PsbReader(data).parse()
    except (PsbBadFormatError, UnicodeError, ValueError, OverflowError) as exc:
        report = ModelHealthReport(False, (
            ModelHealthIssue("PSB_PARSE_FAILED", "error", str(exc)),
        ), {})
        raise ModelValidationError("PSB_PARSE_FAILED", str(exc), report) from exc

    # 从此处开始将解析结果视为字符串键字典，避免 PsbReader 的 Any 类型污染诊断代码。
    parsed_map = _as_mapping(parsed)
    issues: list[ModelHealthIssue] = []
    if parsed_map.get("checksum_valid") is False:
        issues.append(ModelHealthIssue(
            "CHECKSUM_MISMATCH", "error", "PSB header checksum mismatch"
        ))

    root = parsed_map.get("root")
    root_mapping = _as_mapping(root)
    if not root_mapping:
        issues.append(ModelHealthIssue(
            "INVALID_ROOT", "error", "PSB root is not an object"
        ))

    # PsbReader 返回的是结构化字典，但其底层类型是 Any；这里集中收窄，
    # 避免把未知类型扩散到后续的资源校验逻辑。
    resources_raw = parsed_map.get("resources", [])
    extra_resources_raw = parsed_map.get("extra_resources", [])
    resources = {
        item["index"]: item
        for item in cast(list[dict[str, Any]], resources_raw)
    }
    extra_resources = {
        item["index"]: item
        for item in cast(list[dict[str, Any]], extra_resources_raw)
    }
    header = _as_mapping(parsed_map.get("header", {}))
    texture_count = 0
    checked_texture_count = 0
    has_motion = False
    has_variables = False

    for path, value in _walk(root_mapping):
        if isinstance(value, dict):
            node = cast(dict[str, Any], value)
            if isinstance(node.get("motion"), dict) and node["motion"]:
                has_motion = True
            if isinstance(node.get("timelineControl"), list) and node["timelineControl"]:
                has_motion = True
            if any(key in node for key in ("variable", "variableList", "parameter")):
                has_variables = True

            pixel = node.get("pixel")
            if not isinstance(pixel, PsbResourceRef) or "width" not in node or "height" not in node:
                continue
            texture_count += 1
            try:
                width, height = int(node["width"]), int(node["height"])
            except (TypeError, ValueError, OverflowError):
                issues.append(ModelHealthIssue(
                    "INVALID_TEXTURE_DIMENSIONS", "error", "Texture dimensions are invalid", path
                ))
                continue
            if width <= 0 or height <= 0 or width > 16384 or height > 16384:
                issues.append(ModelHealthIssue(
                    "INVALID_TEXTURE_DIMENSIONS", "error",
                    f"Unsafe texture dimensions: {width}x{height}", path
                ))
                continue

            table = extra_resources if pixel.is_extra else resources
            info = table.get(pixel.index)
            if info is None:
                issues.append(ModelHealthIssue(
                    "TEXTURE_RESOURCE_MISSING", "error",
                    f"Texture resource #{pixel.index} is missing", path
                ))
                continue
            length = int(info["length"])
            if length <= 0:
                issues.append(ModelHealthIssue(
                    "TEXTURE_RESOURCE_EMPTY", "error",
                    f"Texture resource #{pixel.index} is empty", path
                ))
                continue

            texture_type = cast(str | None, node.get("type"))
            compression = cast(str | None, node.get("compress"))
            if texture_type == "RGBA8" and compression in (None, ""):
                expected = width * height * 4
                if length != expected:
                    issues.append(ModelHealthIssue(
                        "TEXTURE_SIZE_MISMATCH", "error",
                        f"RGBA8 texture length {length} does not match {width}x{height}x4 ({expected})",
                        path,
                    ))
                    continue
                base_key = "offset_extra_chunk_data" if pixel.is_extra else "offset_chunk_data"
                start = int(header[base_key]) + int(info["offset"])
                raw = memoryview(data)[start:start + length]
                alpha = raw[3::4]
                checked_texture_count += 1
                # A full alpha scan is zero-copy and avoids false positives from sparse atlases.
                nonzero = sum(1 for item in alpha if item != 0)
                if nonzero == 0:
                    issues.append(ModelHealthIssue(
                        "TEXTURE_FULLY_TRANSPARENT", "warning",
                        "Texture is fully transparent", path,
                        {"width": width, "height": height, "nonzero_alpha_pixels": 0},
                    ))
                elif nonzero < 64:
                    issues.append(ModelHealthIssue(
                        "TEXTURE_NEAR_EMPTY", "warning",
                        f"Texture has only {nonzero} non-transparent pixels", path,
                        {"width": width, "height": height, "nonzero_alpha_pixels": nonzero},
                    ))

    if not has_motion:
        issues.append(ModelHealthIssue(
            "NO_TIMELINE_DATA", "warning", "No recognizable motion/timeline data was found"
        ))
    if not has_variables:
        issues.append(ModelHealthIssue(
            "NO_VARIABLE_DATA", "warning", "No recognizable variable/parameter data was found"
        ))
    if texture_count == 0:
        issues.append(ModelHealthIssue(
            "NO_TEXTURE_DATA", "warning", "No recognizable texture descriptor was found"
        ))

    accepted = not any(issue.severity == "error" for issue in issues)
    report = ModelHealthReport(accepted, tuple(issues), {
        "version": parsed_map.get("version"),
        "spec": parsed_map.get("spec"),
        "type": parsed_map.get("type"),
        "resource_count": len(resources),
        "extra_resource_count": len(extra_resources),
        "texture_count": texture_count,
        "checked_texture_count": checked_texture_count,
    })
    if not accepted:
        first = next(issue for issue in issues if issue.severity == "error")
        raise ModelValidationError(first.code, first.message, report)
    return report
