"""Detect and unwrap common PSB shells without interpreting PSB content."""

from __future__ import annotations

from dataclasses import dataclass
import zlib


class PsbShellError(ValueError):
    pass


@dataclass(frozen=True)
class UnwrappedPsb:
    data: bytes
    shell: str


LZ4_FRAME_MAGIC = b"\x04\x22\x4D\x18"


def detect_shell(data: bytes) -> str:
    if data.startswith(b"PSB\0"):
        return "raw"
    if data.startswith(LZ4_FRAME_MAGIC):
        return "lz4"
    if data[:3].lower() == b"mdf":
        return "mdf"
    return "unknown"


def unwrap_psb(data: bytes) -> UnwrappedPsb:
    shell = detect_shell(data)
    if shell == "raw":
        pure = data
    elif shell == "lz4":
        try:
            import lz4.frame
        except ImportError as exc:
            raise PsbShellError("LZ4 shell requires: pip install lz4") from exc
        try:
            pure = lz4.frame.decompress(data)
        except RuntimeError as exc:
            raise PsbShellError(f"invalid LZ4 frame: {exc}") from exc
    elif shell == "mdf":
        if len(data) < 10:
            raise PsbShellError("truncated MDF shell")
        try:
            pure = zlib.decompress(data[8:])
        except zlib.error:
            try:
                pure = zlib.decompress(data[10:], -zlib.MAX_WBITS)
            except zlib.error as exc:
                raise PsbShellError(f"invalid MDF zlib stream: {exc}") from exc
    else:
        raise PsbShellError(f"unsupported PSB shell signature: {data[:8].hex(' ')}")
    if not pure.startswith(b"PSB\0"):
        raise PsbShellError(f"{shell} payload is not PSB\\0")
    return UnwrappedPsb(pure, shell)
