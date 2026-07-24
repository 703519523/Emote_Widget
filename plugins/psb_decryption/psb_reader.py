"""Read unwrapped PSB v2-v4 files.

The implementation follows ``PsbHeader.cs``, ``PsbValues.cs`` and
``FreeMote.Psb/Psb.cs``. Shell handling is intentionally kept in
``psb_shell.py`` so shell detection cannot be confused with encryption.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from enum import IntEnum
import hashlib
import struct
import zlib
from typing import Any, Dict, List, Optional, Tuple

from .psb_types import PsbDouble


class PsbBadFormatError(ValueError):
    """The input is not a structurally valid supported PSB."""


class PsbObjType(IntEnum):
    NONE = 0x00
    NULL = 0x01
    FALSE = 0x02
    TRUE = 0x03
    NUMBER_N0 = 0x04
    NUMBER_N1 = 0x05
    NUMBER_N8 = 0x0C
    ARRAY_N1 = 0x0D
    ARRAY_N8 = 0x14
    STRING_N1 = 0x15
    STRING_N4 = 0x18
    RESOURCE_N1 = 0x19
    RESOURCE_N4 = 0x1C
    FLOAT0 = 0x1D
    FLOAT = 0x1E
    DOUBLE = 0x1F
    LIST = 0x20
    OBJECTS = 0x21
    EXTRA_CHUNK_N1 = 0x22
    EXTRA_CHUNK_N4 = 0x25


@dataclass(frozen=True)
class PsbHeader:
    version: int
    header_encrypt: int
    header_length: int
    offset_names: int
    offset_strings: int
    offset_strings_data: int
    offset_chunk_offsets: int
    offset_chunk_lengths: int
    offset_chunk_data: int
    offset_entries: int
    checksum: int = 0
    offset_extra_chunk_offsets: int = 0
    offset_extra_chunk_lengths: int = 0
    offset_extra_chunk_data: int = 0

    @property
    def expected_length(self) -> int:
        return 40 if self.version < 3 else (56 if self.version > 3 else 44)


@dataclass(frozen=True)
class PsbResourceRef:
    index: int
    is_extra: bool = False


@dataclass(frozen=True)
class PsbResourceInfo:
    index: int
    offset: int
    length: int
    sha256: str
    is_extra: bool = False


class PsbReader:
    """Parse one *unwrapped* and unencrypted PSB byte sequence."""

    def __init__(self, data: bytes, *, load_resource_data: bool = False):
        self._bytes = data
        self.data = memoryview(data)
        self.load_resource_data = load_resource_data
        self.header: Optional[PsbHeader] = None
        self.charset: List[int] = []
        self.names_data: List[int] = []
        self.name_indexes: List[int] = []
        self.names: List[str] = []
        self.string_offsets: List[int] = []
        self._string_cache: Dict[int, str] = {}
        self.chunk_offsets: List[int] = []
        self.chunk_lengths: List[int] = []
        self.extra_chunk_offsets: List[int] = []
        self.extra_chunk_lengths: List[int] = []

    @staticmethod
    def is_psb(data: bytes) -> bool:
        return data[:4] == b"PSB\0"

    def parse(self) -> Dict[str, Any]:
        self.header = self._read_header()
        self._validate_header_offsets()
        self._load_tables()
        root, _ = self._unpack(self.header.offset_entries)
        return {
            "version": self.header.version,
            "header": asdict(self.header),
            "checksum_valid": self.validate_header_checksum(),
            "names": self.names,
            "strings": [self._read_string(i) for i in range(len(self.string_offsets))],
            "root": root,
            "resources": self._resource_infos(False),
            "extra_resources": self._resource_infos(True),
            "spec": self._infer_spec(root),
            "type": self._infer_type(root),
        }

    def _read_header(self) -> PsbHeader:
        if len(self.data) < 40 or bytes(self.data[:4]) != b"PSB\0":
            raise PsbBadFormatError("expected an unwrapped PSB\\0 stream")
        version, encrypted = struct.unpack_from("<HH", self.data, 4)
        if version not in (1, 2, 3, 4):
            raise PsbBadFormatError(f"unsupported PSB version {version}")
        size = 40 if version <= 2 else (44 if version == 3 else 56)
        if len(self.data) < size:
            raise PsbBadFormatError(f"truncated PSB v{version} header")
        values = struct.unpack_from("<8I", self.data, 8)
        checksum = struct.unpack_from("<I", self.data, 40)[0] if version >= 3 else 0
        extra = struct.unpack_from("<3I", self.data, 44) if version >= 4 else (0, 0, 0)
        return PsbHeader(version, encrypted, *values, checksum, *extra)

    def _validate_header_offsets(self) -> None:
        assert self.header is not None
        if self.header.header_encrypt != 0:
            raise PsbBadFormatError(
                "encrypted PSB headers require explicit decryption before parsing"
            )
        offsets = [
            self.header.offset_names,
            self.header.offset_strings,
            self.header.offset_strings_data,
            self.header.offset_chunk_offsets,
            self.header.offset_chunk_lengths,
            self.header.offset_chunk_data,
            self.header.offset_entries,
        ]
        if any(offset < self.header.expected_length or offset > len(self.data) for offset in offsets):
            raise PsbBadFormatError(f"header contains out-of-range offsets: {offsets}")
        if self.header.version == 1:
            # In v1 HeaderLength is the position of the NameIndexes array,
            # unlike v2+ where it is the fixed header size. C# repairs the
            # historical malformed value when it points past EOF; values
            # before the fixed header are never safe to interpret.
            if 0 < self.header.header_length < self.header.expected_length:
                raise PsbBadFormatError(
                    f"invalid PSBv1 name-index offset {self.header.header_length}"
                )
        elif self.header.header_length not in (0, self.header.expected_length):
            raise PsbBadFormatError(
                f"invalid PSB header length {self.header.header_length}"
            )
        if not (
            self.header.offset_entries
            <= self.header.offset_strings
            <= self.header.offset_strings_data
            <= self.header.offset_chunk_offsets
            <= self.header.offset_chunk_lengths
            <= self.header.offset_chunk_data
        ):
            raise PsbBadFormatError("PSB header offsets are not monotonic")

    def validate_header_checksum(self) -> Optional[bool]:
        assert self.header is not None
        if self.header.version < 3:
            return None
        checksum = zlib.adler32(self.data[8:40])
        if self.header.version >= 4:
            checksum = zlib.adler32(self.data[44:56], checksum)
        return (checksum & 0xFFFFFFFF) == self.header.checksum

    def _load_tables(self) -> None:
        assert self.header is not None
        if self.header.version == 1:
            # PSBv1 stores the name-index array at HeaderLength and the
            # zero-terminated UTF-8 name data at OffsetNames.  Unlike v2+ it
            # has no charset/name-trie arrays.
            name_index_pos = self.header.header_length
            if name_index_pos >= len(self.data):
                # Match Psb.cs LoadFromStream's v1 recovery for files whose
                # legacy HeaderLength field was left unusable.
                name_index_pos = self.header.expected_length
                self.header = replace(self.header, header_length=name_index_pos)
            self.name_indexes, _ = self._read_array(name_index_pos)
            self.names = []
            for index in self.name_indexes:
                start = self.header.offset_names + index
                if start >= len(self.data):
                    raise PsbBadFormatError(f"name index {index} is out of range")
                end = self._bytes.find(b"\0", start)
                if end < 0:
                    raise PsbBadFormatError("unterminated PSBv1 name")
                self.names.append(self._bytes[start:end].decode("utf-8"))
        else:
            pos = self.header.offset_names
            self.charset, pos = self._read_array(pos)
            self.names_data, pos = self._read_array(pos)
            self.name_indexes, _ = self._read_array(pos)
            self.names = self._decode_names()
        self.string_offsets, _ = self._read_array(self.header.offset_strings)
        self.chunk_offsets, _ = self._read_array(self.header.offset_chunk_offsets)
        self.chunk_lengths, _ = self._read_array(self.header.offset_chunk_lengths)
        if self.header.version >= 4:
            self.extra_chunk_offsets, _ = self._read_array(
                self.header.offset_extra_chunk_offsets
            )
            self.extra_chunk_lengths, _ = self._read_array(
                self.header.offset_extra_chunk_lengths
            )

    def _read_array(self, pos: int) -> Tuple[List[int], int]:
        type_byte = self._byte(pos)
        if not PsbObjType.ARRAY_N1 <= type_byte <= PsbObjType.ARRAY_N8:
            raise PsbBadFormatError(f"expected PSB array at 0x{pos:X}, got 0x{type_byte:02X}")
        count_width = type_byte - PsbObjType.ARRAY_N1 + 1
        pos += 1
        count = self._uint(pos, count_width)
        pos += count_width
        entry_tag = self._byte(pos)
        pos += 1
        entry_width = entry_tag - PsbObjType.NUMBER_N8
        if not 0 <= entry_width <= 8:
            raise PsbBadFormatError(f"invalid array entry width tag 0x{entry_tag:02X}")
        end = pos + count * entry_width
        if end > len(self.data):
            raise PsbBadFormatError("truncated PSB array")
        values = [self._uint(pos + i * entry_width, entry_width) for i in range(count)]
        return values, end

    def _decode_names(self) -> List[str]:
        result: List[str] = []
        for start in self.name_indexes:
            if start >= len(self.names_data):
                raise PsbBadFormatError(f"name index {start} is out of range")
            encoded = bytearray()
            char_node = self.names_data[start]
            while char_node != 0:
                if char_node >= len(self.names_data):
                    raise PsbBadFormatError("name trie node is out of range")
                code = self.names_data[char_node]
                if code >= len(self.charset):
                    raise PsbBadFormatError("name trie charset index is out of range")
                delta = self.charset[code]
                encoded.append((char_node - delta) & 0xFF)
                char_node = code
            encoded.reverse()
            result.append(encoded.decode("utf-8"))
        return result

    def _read_string(self, index: int) -> str:
        if index in self._string_cache:
            return self._string_cache[index]
        assert self.header is not None
        if index >= len(self.string_offsets):
            raise PsbBadFormatError(f"string index {index} is out of range")
        pos = self.header.offset_strings_data + self.string_offsets[index]
        end = self._bytes.find(b"\0", pos)
        if end < 0:
            raise PsbBadFormatError(f"unterminated string #{index}")
        value = self._bytes[pos:end].decode("utf-8")
        self._string_cache[index] = value
        return value

    def _unpack(self, pos: int, depth: int = 0) -> Tuple[Any, int]:
        if depth > 256:
            raise PsbBadFormatError("PSB object nesting exceeds 256 levels")
        type_byte = self._byte(pos)
        payload = pos + 1
        if type_byte in (PsbObjType.NONE, PsbObjType.NULL):
            return None, payload
        if type_byte == PsbObjType.FALSE:
            return False, payload
        if type_byte == PsbObjType.TRUE:
            return True, payload
        if PsbObjType.NUMBER_N0 <= type_byte <= PsbObjType.NUMBER_N8:
            width = type_byte - PsbObjType.NUMBER_N0
            return self._int(payload, width), payload + width
        if PsbObjType.ARRAY_N1 <= type_byte <= PsbObjType.ARRAY_N8:
            return self._read_array(pos)
        if PsbObjType.STRING_N1 <= type_byte <= PsbObjType.STRING_N4:
            width = type_byte - PsbObjType.STRING_N1 + 1
            return self._read_string(self._uint(payload, width)), payload + width
        if PsbObjType.RESOURCE_N1 <= type_byte <= PsbObjType.RESOURCE_N4:
            width = type_byte - PsbObjType.RESOURCE_N1 + 1
            return PsbResourceRef(self._uint(payload, width), False), payload + width
        if type_byte == PsbObjType.FLOAT0:
            return 0.0, payload
        if type_byte == PsbObjType.FLOAT:
            return struct.unpack_from("<f", self.data, payload)[0], payload + 4
        if type_byte == PsbObjType.DOUBLE:
            return PsbDouble(struct.unpack_from("<d", self.data, payload)[0]), payload + 8
        if type_byte == PsbObjType.LIST:
            return self._read_list(payload, depth + 1)
        if type_byte == PsbObjType.OBJECTS:
            if self.header is not None and self.header.version == 1:
                return self._read_objects_v1(payload, depth + 1)
            return self._read_objects(payload, depth + 1)
        if PsbObjType.EXTRA_CHUNK_N1 <= type_byte <= PsbObjType.EXTRA_CHUNK_N4:
            width = type_byte - PsbObjType.EXTRA_CHUNK_N1 + 1
            return PsbResourceRef(self._uint(payload, width), True), payload + width
        raise PsbBadFormatError(f"unknown PSB object type 0x{type_byte:02X} at 0x{pos:X}")

    def _read_list(self, pos: int, depth: int = 0) -> Tuple[List[Any], int]:
        offsets, base = self._read_array(pos)
        values: List[Any] = []
        end = base
        for offset in offsets:
            value, item_end = self._unpack(base + offset, depth)
            values.append(value)
            end = max(end, item_end)
        return values, end

    def _read_objects(self, pos: int, depth: int = 0) -> Tuple[Dict[str, Any], int]:
        name_indexes, pos = self._read_array(pos)
        offsets, base = self._read_array(pos)
        if len(name_indexes) != len(offsets):
            raise PsbBadFormatError("dictionary name and value counts differ")
        result: Dict[str, Any] = {}
        end = base
        for name_index, offset in zip(name_indexes, offsets):
            if name_index >= len(self.names):
                raise PsbBadFormatError(f"dictionary name index {name_index} is out of range")
            value, item_end = self._unpack(base + offset, depth)
            result[self.names[name_index]] = value
            end = max(end, item_end)
        return result, end

    def _read_objects_v1(self, pos: int, depth: int = 0) -> Tuple[Dict[str, Any], int]:
        """Read C# ``LoadObjectsV1`` records.

        v1 has one offset array. Each record starts with a compact unsigned
        name index followed immediately by the packed value.
        """
        offsets, base = self._read_array(pos)
        result: Dict[str, Any] = {}
        end = base
        for offset in offsets:
            record = base + offset
            tag = self._byte(record)
            # C# SaveObjectsV1 writes KeyNameN1..KeyNameN4 (0x11..0x14),
            # followed by the packed value. They are not NumberN tags.
            if not 0x11 <= tag <= 0x14:
                raise PsbBadFormatError(
                    f"invalid PSBv1 name index tag 0x{tag:02X} at 0x{record:X}"
                )
            width = tag - 0x11 + 1
            name_index = self._uint(record + 1, width)
            if name_index >= len(self.names):
                raise PsbBadFormatError(
                    f"dictionary name index {name_index} is out of range"
                )
            value, item_end = self._unpack(record + 1 + width, depth)
            result[self.names[name_index]] = value
            end = max(end, item_end)
        return result, end

    def _resource_infos(self, extra: bool) -> List[Dict[str, Any]]:
        assert self.header is not None
        offsets = self.extra_chunk_offsets if extra else self.chunk_offsets
        lengths = self.extra_chunk_lengths if extra else self.chunk_lengths
        base = self.header.offset_extra_chunk_data if extra else self.header.offset_chunk_data
        if len(offsets) != len(lengths):
            raise PsbBadFormatError("resource offset and length counts differ")
        result = []
        for index, (offset, length) in enumerate(zip(offsets, lengths)):
            start, end = base + offset, base + offset + length
            if end > len(self.data):
                raise PsbBadFormatError(f"resource #{index} exceeds file size")
            chunk = self.data[start:end]
            info: Dict[str, Any] = asdict(PsbResourceInfo(
                index, offset, length, hashlib.sha256(chunk).hexdigest(), extra
            ))
            if self.load_resource_data:
                info["data"] = bytes(chunk)
            result.append(info)
        return result

    @staticmethod
    def _infer_spec(root: Any) -> Optional[str]:
        if not isinstance(root, dict):
            return None
        root_dict: Dict[str, Any] = root
        root_value = root_dict.get("spec")
        if isinstance(root_value, str):
            return root_value
        metadata = root_dict.get("metadata")
        if isinstance(metadata, dict):
            value = metadata.get("spec") or metadata.get("platform")
            if isinstance(value, str):
                return value
        return None

    @staticmethod
    def _infer_type(root: Any) -> Optional[str]:
        if not isinstance(root, dict):
            return None
        root_dict: Dict[str, Any] = root
        root_value = root_dict.get("id") or root_dict.get("type")
        if isinstance(root_value, str):
            return root_value
        metadata = root_dict.get("metadata")
        if isinstance(metadata, dict) and isinstance(metadata.get("type"), str):
            return metadata["type"]
        return None

    def _byte(self, pos: int) -> int:
        if not 0 <= pos < len(self.data):
            raise PsbBadFormatError(f"offset 0x{pos:X} is out of range")
        return self.data[pos]

    def _uint(self, pos: int, width: int) -> int:
        if width == 0:
            return 0
        end = pos + width
        if pos < 0 or end > len(self.data):
            raise PsbBadFormatError("truncated compact integer")
        return int.from_bytes(self.data[pos:end], "little", signed=False)

    def _int(self, pos: int, width: int) -> int:
        """Read a signed PSB NumberN payload (arrays/indexes stay unsigned)."""
        if width == 0:
            return 0
        end = pos + width
        if pos < 0 or end > len(self.data):
            raise PsbBadFormatError("truncated compact integer")
        return int.from_bytes(self.data[pos:end], "little", signed=True)
