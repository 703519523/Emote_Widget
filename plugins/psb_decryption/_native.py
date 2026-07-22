"""Optional repository-local PyO3 acceleration."""

from __future__ import annotations

from typing import Callable

EXPECTED_API_VERSION = 1

_native_error: BaseException | None = None
_unpack_psp: Callable[[bytes], bytes] | None = None
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
except (ImportError, OSError) as exc:
    _native_error = exc


def unpack_psp(data: bytes) -> bytes | None:
    """Return zero-copy native output, or ``None`` when the extension is absent."""
    if _unpack_psp is None:
        return None
    return _unpack_psp(data)


def available(capability: str | None = None) -> bool:
    if capability is None:
        return _unpack_psp is not None
    return capability in _capabilities


def capabilities() -> frozenset[str]:
    return _capabilities


def load_error() -> BaseException | None:
    return _native_error
