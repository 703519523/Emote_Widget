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
PSZ_MAGIC = b"PSZ\0"


def detect_shell(data: bytes) -> str:
    if data.startswith(b"PSB\0"):
        return "raw"
    if data.startswith(PSZ_MAGIC):
        return "psz"
    if data.startswith(LZ4_FRAME_MAGIC):
        return "lz4"
    if data[:3].lower() == b"mdf":
        return "mdf"
    return "unknown"


def unwrap_psb(data: bytes) -> UnwrappedPsb:
    shell = detect_shell(data)
    if shell == "raw":
        pure = data
    elif shell == "psz":
        if len(data) < 16:
            raise PsbShellError("truncated PSZ shell")
        # PSZ header: "PSZ\0" (4) + zipped_len (4) + ori_len (4) + reserved (4)
        import struct
        zipped_len, ori_len, _ = struct.unpack("<III", data[4:16])
        # C# PszShell reads the two zlib header bytes for metadata and then
        # rewinds them through the underlying stream. ``zipped_len`` is the
        # complete RFC 1950 stream, including its own trailing Adler32.
        if len(data) < 16 + zipped_len:
            raise PsbShellError(f"PSZ data truncated: expected {16 + zipped_len}, got {len(data)}")
        if len(data) != 16 + zipped_len:
            raise PsbShellError(f"PSZ size mismatch: header describes {16 + zipped_len}, got {len(data)}")
        zlib_stream = data[16 : 16 + zipped_len]
        try:
            decompressor = zlib.decompressobj()
            pure = decompressor.decompress(zlib_stream) + decompressor.flush()
        except zlib.error as exc:
            raise PsbShellError(f"invalid PSZ zlib stream: {exc}") from exc
        if not decompressor.eof or decompressor.unused_data or decompressor.unconsumed_tail:
            raise PsbShellError("PSZ zlib stream is incomplete or contains trailing data")
        if len(pure) != ori_len:
            raise PsbShellError(f"PSZ decompressed size mismatch: expected {ori_len}, got {len(pure)}")
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
