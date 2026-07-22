"""PSB type encoding/decoding utilities.

Implements variable-width integer encoding and PSB array serialization.
"""

from __future__ import annotations
from typing import List, Optional


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
    count_size = get_size(count)
    
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
    result.extend(zip_number_bytes(count, count_size))
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
