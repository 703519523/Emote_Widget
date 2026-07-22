"""RLE (Run-Length Encoding) compression/decompression for PSB resources.

Ported from FreeMote C# implementation (FreeMote/RleCompress.cs).
Original author: number201724
"""

from io import BytesIO
from typing import Optional


class RleCompressError(ValueError):
    """Raised when RLE decompression fails."""
    pass


LZSS_LOOK_SHIFT = 7
LZSS_LOOK_AHEAD = 1 << LZSS_LOOK_SHIFT  # 128


def decompress(data: bytes, align: int = 4, actual_size: Optional[int] = None) -> bytes:
    """Decompress RLE-encoded data.

    Args:
        data: Compressed input bytes
        align: Byte alignment (default 4 for RGBA)
        actual_size: Expected output size (optional, for pre-allocation)

    Returns:
        Decompressed bytes

    Raises:
        RleCompressError: If decompression fails
    """
    input_stream = BytesIO(data)
    output = BytesIO() if actual_size is None else BytesIO(bytearray(actual_size))

    total_bytes = 0
    input_len = len(data)

    while input_stream.tell() < input_len:
        current_byte = input_stream.read(1)
        if not current_byte:
            break

        current = current_byte[0]
        total_bytes += 1

        if (current & LZSS_LOOK_AHEAD) != 0:  # Redundant pattern (bit 7 set)
            count = (current ^ LZSS_LOOK_AHEAD) + 3
            buffer = input_stream.read(align)
            if len(buffer) != align:
                raise RleCompressError(
                    f"Unexpected EOF: expected {align} bytes for redundant pattern, got {len(buffer)}"
                )

            for _ in range(count):
                output.write(buffer)

            total_bytes += align
        else:  # Non-redundant data (bit 7 clear)
            count = (current + 1) * align
            buffer = input_stream.read(count)
            if len(buffer) != count:
                raise RleCompressError(
                    f"Unexpected EOF: expected {count} bytes for non-redundant data, got {len(buffer)}"
                )

            output.write(buffer)
            total_bytes += count

    return output.getvalue()


def compress(data: bytes, align: int = 4) -> bytes:
    """Compress data using RLE.

    Args:
        data: Input bytes to compress
        align: Byte alignment (default 4 for RGBA)

    Returns:
        Compressed bytes
    """
    input_stream = BytesIO(data)
    output = BytesIO()
    input_len = len(data)

    while input_stream.tell() < input_len:
        pos = input_stream.tell()

        # Check for redundant pattern
        redundant_count, pattern = _count_redundant(input_stream, align)

        if redundant_count >= 3:
            # Encode as redundant
            cmd_byte = (redundant_count - 3) | LZSS_LOOK_AHEAD
            output.write(bytes([cmd_byte]))
            output.write(pattern)
            input_stream.seek(pos + align * redundant_count)
        else:
            # Encode as non-redundant
            input_stream.seek(pos)
            non_redundant_count = _count_non_redundant(input_stream, align)
            input_stream.seek(pos)

            buffer = input_stream.read(non_redundant_count * align)
            cmd_byte = non_redundant_count - 1
            output.write(bytes([cmd_byte]))
            output.write(buffer)

    return output.getvalue()


def _count_redundant(stream: BytesIO, align: int) -> tuple[int, bytes]:
    """Count consecutive redundant patterns.

    Returns:
        (count, pattern): Number of repetitions and the repeated pattern
    """
    pos = stream.tell()
    if pos >= len(stream.getvalue()):
        return 0, b''

    pattern = stream.read(align)
    if len(pattern) != align:
        stream.seek(pos)
        return 0, b''

    count = 1

    for _ in range(1, LZSS_LOOK_AHEAD + 2):
        if stream.tell() >= len(stream.getvalue()):
            break

        next_pattern = stream.read(align)
        if len(next_pattern) != align or next_pattern != pattern:
            break

        count += 1

    stream.seek(pos)
    return (count, pattern) if count >= 3 else (0, b'')


def _count_non_redundant(stream: BytesIO, align: int) -> int:
    """Count consecutive non-redundant patterns.

    Returns:
        count: Number of non-redundant patterns
    """
    pos = stream.tell()
    count = 1

    # Skip first pattern
    stream.read(align)

    for _ in range(1, LZSS_LOOK_AHEAD):
        if stream.tell() >= len(stream.getvalue()):
            break

        # Check if next position starts redundant pattern
        redundant_count, _ = _count_redundant(stream, align)
        if redundant_count > 0:
            break

        # Skip this pattern
        stream.read(align)
        count += 1

    stream.seek(pos)
    return count
