"""PSB stream-cipher support compatible with FreeMote's C# implementation.

The cipher is the byte-oriented XorShift128 stream implemented by
``FreeMote/PsbStreamContext.cs``.  PSB v3/v4 files commonly encrypt only the
header bytes starting at offset 8; PSB v2 files commonly encrypt the table
area between the fixed header and the chunk-offset table.
"""

from __future__ import annotations

from dataclasses import dataclass
import struct
import zlib
from typing import Optional


KEY1 = 123456789
KEY2 = 362436069
KEY3 = 521288629
UINT32_MASK = 0xFFFFFFFF


class PsbCryptoError(ValueError):
    """Raised when encrypted PSB data cannot be decrypted safely."""


class PsbStreamContext:
    """Exact Python port of ``FreeMote.PsbStreamContext.Encode``."""

    def __init__(self, key: int):
        self.key1 = KEY1
        self.key2 = KEY2
        self.key3 = KEY3
        self.key4 = key & UINT32_MASK
        self.current_key = 0
        self.round = 0
        self.byte_count = 0

    def encode(self, data: bytes) -> bytes:
        output = bytearray(data)
        for index in range(len(output)):
            if self.current_key == 0:
                a = (self.key1 ^ (self.key1 << 11)) & UINT32_MASK
                b = self.key4
                c = (a ^ b ^ ((a ^ (b >> 11)) >> 8)) & UINT32_MASK
                self.key1, self.key2, self.key3, self.key4 = (
                    self.key2,
                    self.key3,
                    b,
                    c,
                )
                self.current_key = c
                self.round += 1
            output[index] ^= self.current_key & 0xFF
            self.current_key >>= 8
            self.byte_count += 1
        return bytes(output)

    def _next_word(self) -> None:
        """Advance the XorShift state when the current word is exhausted."""
        a = (self.key1 ^ (self.key1 << 11)) & UINT32_MASK
        b = self.key4
        c = (a ^ b ^ ((a ^ (b >> 11)) >> 8)) & UINT32_MASK
        self.key1, self.key2, self.key3, self.key4 = self.key2, self.key3, b, c
        self.current_key = c
        self.round += 1

    def fast_forward(self, byte_length: int) -> None:
        """Match C# ``PsbStreamContext.FastForward`` exactly.

        This is a state-navigation helper, not the same operation as
        consuming bytes through :meth:`encode`: the C# implementation shifts
        one bit per skipped byte and therefore intentionally advances by one
        bit rather than one cipher byte.
        """
        if byte_length < 0:
            raise ValueError("byte_length must be non-negative")
        for _ in range(byte_length):
            if self.current_key == 0:
                self._next_word()
            self.current_key >>= 1
            self.byte_count += 1

    def next_round(self) -> int:
        """Match C# ``PsbStreamContext.NextRound`` and return the new word."""
        while self.current_key != 0:
            self.current_key >>= 1
            self.byte_count += 1
        self._next_word()
        return self.current_key


@dataclass(frozen=True)
class DecryptedPsb:
    data: bytes
    key: Optional[int]
    key_source: str
    header_was_encrypted: bool
    body_was_encrypted: bool


def expected_header_length(version: int) -> int:
    if version == 2:
        return 40
    if version == 3:
        return 44
    if version == 4:
        return 56
    raise PsbCryptoError(f"unsupported PSB version {version}")


def recover_header_key(data: bytes) -> int:
    """Recover Key4 from the encrypted first header word of PSB v3/v4.

    The first encrypted uint is HeaderLength, whose canonical value is fixed
    by the PSB version.  For the first XorShift word::

        c = a ^ b ^ (a >> 8) ^ (b >> 19)

    Therefore ``b ^ (b >> 19)`` is known and can be inverted exactly.  The
    recovered key is accepted only if all offsets and the v3/v4 Adler32
    checksum validate after decryption.
    """

    if len(data) < 12 or data[:4] != b"PSB\0":
        raise PsbCryptoError("expected an unwrapped PSB stream")
    version, header_encrypt = struct.unpack_from("<HH", data, 4)
    if version not in (3, 4) or header_encrypt == 0:
        raise PsbCryptoError("automatic key recovery requires an encrypted PSB v3/v4 header")
    known_plaintext = expected_header_length(version)
    encrypted_word = struct.unpack_from("<I", data, 8)[0]
    first_stream_word = encrypted_word ^ known_plaintext
    a = (KEY1 ^ (KEY1 << 11)) & UINT32_MASK
    transformed_key = first_stream_word ^ a ^ (a >> 8)
    return (transformed_key ^ (transformed_key >> 19)) & UINT32_MASK


def _header_checksum(data: bytes, version: int) -> int:
    checksum = zlib.adler32(data[8:40])
    if version >= 4:
        checksum = zlib.adler32(data[44:56], checksum)
    return checksum & UINT32_MASK


def _validate_decrypted_header(data: bytes, version: int) -> None:
    size = expected_header_length(version)
    if len(data) < size:
        raise PsbCryptoError(f"truncated PSB v{version} header")
    values = struct.unpack_from("<8I", data, 8)
    header_length, names, strings, strings_data, chunk_offsets, chunk_lengths, chunk_data, entries = values
    required = (header_length, names, strings, strings_data, chunk_offsets, chunk_lengths, chunk_data, entries)
    if header_length != size or names != size:
        raise PsbCryptoError(
            f"decrypted header has invalid fixed offsets: header={header_length}, names={names}, expected={size}"
        )
    if any(offset < size or offset > len(data) for offset in required):
        raise PsbCryptoError(f"decrypted header contains out-of-range offsets: {required}")
    if not (entries <= strings <= strings_data <= chunk_offsets <= chunk_lengths <= chunk_data):
        raise PsbCryptoError(f"decrypted header offsets are inconsistent: {required}")
    if version >= 3:
        stored = struct.unpack_from("<I", data, 40)[0]
        calculated = _header_checksum(data, version)
        if stored != calculated:
            raise PsbCryptoError(
                f"decrypted header checksum mismatch: stored=0x{stored:08X}, calculated=0x{calculated:08X}"
            )


def _body_is_encrypted(data: bytes, version: int, offset_names: int) -> bool:
    # Mirrors PsbFile.TestBodyEncrypted.  C# uses GetHeaderLength() for v2-v4.
    position = expected_header_length(version) if version in (2, 3, 4) else offset_names
    if position >= len(data):
        return True
    array_type = data[position]
    array_n0 = 0x0C
    if array_n0 < array_type <= array_n0 + 4:
        entry_pos = position + 1 + (array_type - array_n0)
        if entry_pos < len(data) and array_n0 < data[entry_pos] <= array_n0 + 4:
            return False
    return True


def decrypt_psb(data: bytes, key: Optional[int] = None, *, recover_key: bool = True) -> DecryptedPsb:
    """Return canonical unencrypted PSB bytes.

    This follows ``PsbFile.Encode(..., Decrypt, Auto)``: header and body are
    detected independently; when both are encrypted the same stream context
    continues from the header into the body.  Only the names-to-chunk-offsets
    table area is body-encrypted in the C# implementation.
    """

    if len(data) < 16 or data[:4] != b"PSB\0":
        raise PsbCryptoError("expected an unwrapped PSB stream")
    version, header_encrypt = struct.unpack_from("<HH", data, 4)
    size = expected_header_length(version)
    header_was_encrypted = header_encrypt != 0
    key_source = "none"

    if not header_was_encrypted:
        # Validate before trusting offsets used by body decryption.
        _validate_decrypted_header(data, version)
        canonical = bytearray(data)
        context = PsbStreamContext(key) if key is not None else None
        if key is not None:
            key_source = "explicit"
    else:
        if key is None:
            if not recover_key:
                raise PsbCryptoError("encrypted PSB header requires a key")
            key = recover_header_key(data)
            key_source = "recovered"
        else:
            key_source = "explicit"
        context = PsbStreamContext(key)
        canonical = bytearray(data)
        canonical[8:size] = context.encode(data[8:size])
        canonical[6:8] = b"\0\0"
        _validate_decrypted_header(bytes(canonical), version)

    offset_names = struct.unpack_from("<I", canonical, 12)[0]
    offset_chunk_offsets = struct.unpack_from("<I", canonical, 24)[0]
    body_was_encrypted = _body_is_encrypted(bytes(canonical), version, offset_names)
    if body_was_encrypted:
        if key is None:
            raise PsbCryptoError("encrypted PSB body requires an explicit key")
        if context is None:
            context = PsbStreamContext(key)
        canonical[size:offset_chunk_offsets] = context.encode(data[size:offset_chunk_offsets])
        if _body_is_encrypted(bytes(canonical), version, offset_names):
            raise PsbCryptoError("body remained structurally encrypted after decryption")

    # C# rewrites the marker to zero and recalculates checksum on decryption.
    canonical[6:8] = b"\0\0"
    if version >= 3:
        struct.pack_into("<I", canonical, 40, _header_checksum(bytes(canonical), version))
    _validate_decrypted_header(bytes(canonical), version)
    return DecryptedPsb(bytes(canonical), key, key_source, header_was_encrypted, body_was_encrypted)
