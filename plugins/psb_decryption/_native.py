"""可选的仓库内 PyO3 加速；保持插件现有 PSP native ABI。"""

from __future__ import annotations

from typing import Callable

EXPECTED_API_VERSION = 1

_native_error: BaseException | None = None
_unpack_psp: Callable[[bytes], bytes] | None = None
_pack_psb_object: Callable[..., bytes] | None = None
_build_string_table: Callable[..., tuple[list[int], bytes]] | None = None
_capabilities: frozenset[str] = frozenset()

try:
    from . import _freemote_native as _extension

    version = _extension.api_version()
    if version != EXPECTED_API_VERSION:
        raise ImportError(
            f"native API mismatch: expected {EXPECTED_API_VERSION}, got {version}"
        )
    _capabilities = frozenset(_extension.capabilities())
    if "psp_lzss_unpack" in _capabilities:
        _unpack_psp = _extension.unpack_psp
    # 新版 native 扩展可选提供编译器加速；旧版仅提供 PSP 解包时保持兼容。
    if "psb_object_pack" in _capabilities:
        _pack_psb_object = getattr(_extension, "pack_psb_object", None)
    if "string_table_build" in _capabilities:
        _build_string_table = getattr(_extension, "build_string_table", None)
except (ImportError, OSError) as exc:
    _native_error = exc


def unpack_psp(data: bytes) -> bytes | None:
    """调用 native PSP 解包；扩展不可用时返回 None。"""
    if _unpack_psp is None:
        return None
    return _unpack_psp(data)


def available(capability: str | None = None) -> bool:
    if capability is None:
        return _unpack_psp is not None
    return capability in _capabilities


def pack_psb_object(
    obj: object,
    version: int,
    optimize: bool,
    names: dict[str, int],
    strings: dict[str, int],
) -> bytes | None:
    """可选的 PSB 对象打包加速；旧 native 扩展返回 None。"""
    if _pack_psb_object is None:
        return None
    return _pack_psb_object(obj, version, optimize, names, strings)


def build_string_table(
    values: list[str], optimize: bool
) -> tuple[list[int], bytes] | None:
    """可选的字符串表加速；旧 native 扩展返回 None。"""
    if _build_string_table is None:
        return None
    offsets, data = _build_string_table(values, optimize)
    return list(offsets), data


def capabilities() -> frozenset[str]:
    return _capabilities


def load_error() -> BaseException | None:
    return _native_error
