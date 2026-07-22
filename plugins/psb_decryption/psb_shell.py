"""Detect and unwrap common PSB shells without interpreting PSB content."""

from __future__ import annotations

from dataclasses import dataclass
import struct
import zlib

from ._native import unpack_psp as _native_unpack_psp


class PsbShellError(ValueError):
    pass


@dataclass(frozen=True)
class UnwrappedPsb:
    data: bytes
    shell: str


LZ4_FRAME_MAGIC = b"\x04\x22\x4D\x18"
PSZ_MAGIC = b"PSZ\0"
PSP_EMBEDDED_MAGIC_OFFSET = 5


def _unpack_psp_python(data: bytes, unpacked_size: int) -> bytes:
    frame = bytearray(0x1000)
    frame_position = 1
    source_position = 4
    output = bytearray()
    try:
        while len(output) < unpacked_size:
            control = data[source_position]
            source_position += 1
            bit = 1
            while len(output) < unpacked_size and bit != 0x100:
                if control & bit:
                    value = data[source_position]
                    source_position += 1
                    frame[frame_position & 0xFFF] = value
                    frame_position += 1
                    output.append(value)
                else:
                    high = data[source_position]
                    low = data[source_position + 1]
                    source_position += 2
                    offset = (high << 4) | (low >> 4)
                    for _ in range(2 + (low & 0xF)):
                        if len(output) == unpacked_size:
                            break
                        value = frame[offset & 0xFFF]
                        offset += 1
                        frame[frame_position & 0xFFF] = value
                        frame_position += 1
                        output.append(value)
                bit <<= 1
    except IndexError as exc:
        raise PsbShellError(
            f"truncated PSP LZSS stream at input offset {source_position}"
        ) from exc
    return bytes(output)


def _unpack_psp(data: bytes) -> bytes:
    if len(data) < 5:
        raise PsbShellError("truncated PSP shell")
    unpacked_size = struct.unpack_from("<I", data)[0]
    if unpacked_size < 4:
        raise PsbShellError(f"invalid PSP decompressed size: {unpacked_size}")
    try:
        pure = _native_unpack_psp(data)
    except ValueError as exc:
        raise PsbShellError(str(exc)) from exc
    if pure is None:
        pure = _unpack_psp_python(data, unpacked_size)
    if len(pure) != unpacked_size:
        raise PsbShellError(
            f"PSP decompressed size mismatch: expected {unpacked_size}, got {len(pure)}"
        )
    if not pure.startswith(b"PSB\0"):
        raise PsbShellError("psp payload is not PSB\\0")
    return pure


def detect_shell(data: bytes) -> str:
    if data.startswith(b"PSB\0"):
        return "raw"
    if data.startswith(PSZ_MAGIC):
        return "psz"
    if data.startswith(LZ4_FRAME_MAGIC):
        return "lz4"
    # FreeMote PspShell identifies this LZSS container by the decompressed
    # PSB signature appearing at offset 5 (size + first control byte).
    if len(data) >= 8 and data[PSP_EMBEDDED_MAGIC_OFFSET:8] == b"PSB":
        return "psp"
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
    elif shell == "psp":
        pure = _unpack_psp(data)
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
