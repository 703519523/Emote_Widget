"""PSB type encoding/decoding utilities.

Implements variable-width integer encoding and PSB array serialization.
"""

from __future__ import annotations
from typing import List, Optional


class PsbType:
    """PSB Object Type Constants (based on PsbObjType enum in C#)"""
    NONE = 0x00
    NULL = 0x01
    FALSE = 0x02
    TRUE = 0x03

    # Numbers
    NUMBER_N0 = 0x04
    NUMBER_N1 = 0x05
    NUMBER_N2 = 0x06
    NUMBER_N3 = 0x07
    NUMBER_N4 = 0x08
    NUMBER_N5 = 0x09
    NUMBER_N6 = 0x0A
    NUMBER_N7 = 0x0B
    NUMBER_N8 = 0x0C

    # Arrays
    ARRAY_N1 = 0x0D
    ARRAY_N2 = 0x0E
    ARRAY_N3 = 0x0F
    ARRAY_N4 = 0x10
    ARRAY_N5 = 0x11
    ARRAY_N6 = 0x12
    ARRAY_N7 = 0x13
    ARRAY_N8 = 0x14

    # Strings (index into string table)
    STRING_N1 = 0x15
    STRING_N2 = 0x16
    STRING_N3 = 0x17
    STRING_N4 = 0x18

    # Resources (index into resource table)
    RESOURCE_N1 = 0x19
    RESOURCE_N2 = 0x1A
    RESOURCE_N3 = 0x1B
    RESOURCE_N4 = 0x1C

    # Floating point
    FLOAT_0 = 0x1D
    FLOAT = 0x1E
    DOUBLE = 0x1F

    # Collections
    LIST = 0x20
    OBJECTS = 0x21

    # Extra resources (PSB v4+)
    EXTRA_CHUNK_N1 = 0x22
    EXTRA_CHUNK_N2 = 0x23
    EXTRA_CHUNK_N3 = 0x24
    EXTRA_CHUNK_N4 = 0x25


class PsbDouble(float):
    """Float value whose original PSB representation was an 8-byte Double."""


def get_size(value: int) -> int:
    """Get minimum bytes needed to represent an unsigned integer.

    Args:
        value: Unsigned integer value

    Returns:
        Number of bytes needed (1-8)
    """
    if value == 0:
        return 1

    n = 0
    while value != 0:
        value >>= 8
        n += 1

    return n


def zip_number_bytes(value: int, size: int = 0) -> bytes:
    """Compress integer to minimum bytes (little-endian).

    Args:
        value: Integer to compress
        size: Fixed size (0 = auto-detect minimum)

    Returns:
        Bytes in little-endian order
    """
    if size <= 0:
        size = get_size(value)

    # Convert to bytes (little-endian, unsigned)
    return value.to_bytes(size, byteorder='little', signed=False)


def write_psb_array(values: List[int]) -> bytes:
    """Encode a list of unsigned integers as PSB array.

    PSB array format:
    - 1 byte: Type (0x0D-0x14 for ArrayN1-ArrayN8)
    - N bytes: Count (variable-width)
    - 1 byte: EntryLength + 0x0C
    - Count * EntryLength bytes: Values

    Args:
        values: List of unsigned integers

    Returns:
        Encoded PSB array bytes
    """
    if not values:
        # Empty array
        return b'\x0D\x00\x0C'  # ArrayN1, count=0, entrylen=0

    count = len(values)
    # PsbArray.Value.Count is a C# signed int. Its compact width must retain
    # the sign bit (e.g. count 149 is ArrayN2 with bytes 95 00, not ArrayN1
    # 95). Array entries themselves are uint and continue to use get_size().
    count_size = 1
    while count > (1 << (count_size * 8 - 1)) - 1:
        count_size += 1

    # Determine entry length (max size among all values)
    max_val = max(values)
    entry_length = get_size(max_val)
    if entry_length > 8:
        entry_length = 8

    # Determine array type based on count size
    array_type = 0x0C + count_size  # ArrayN1=0x0D, ArrayN2=0x0E, etc.

    # Build array
    result = bytearray()
    result.append(array_type)
    result.extend(count.to_bytes(count_size, byteorder='little', signed=True))
    result.append(entry_length + 0x0C)  # EntryLength + NumberN8 offset

    for val in values:
        result.extend(zip_number_bytes(val, entry_length))

    return bytes(result)


def calculate_adler32(data: bytes, start: int = 0, end: Optional[int] = None) -> int:
    """Calculate Adler-32 checksum for PSB v3/v4.

    Args:
        data: Data to checksum
        start: Start offset
        end: End offset (None = end of data)

    Returns:
        Adler-32 checksum as uint32
    """
    import zlib

    if end is None:
        end = len(data)

    return zlib.adler32(data[start:end]) & 0xFFFFFFFF
