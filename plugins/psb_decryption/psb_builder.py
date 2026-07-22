"""PSB Builder - Serialize PSB objects to binary format.

This module provides a modular, extensible PSB builder that can reconstruct
PSB files from parsed data. Designed for:
- In-memory operations (no disk I/O)
- Component-wise implementation and testing
- Future expansion to full compiler

Architecture:
- Each section (Names/Entries/Strings/Resources) is independently buildable
- Clear interfaces for testing and comparison with C# output
- Supports incremental implementation
"""

from __future__ import annotations

from io import BytesIO
from typing import Any, Dict, List, Optional, Tuple
import struct
import zlib


class PsbBuilderError(ValueError):
    """Raised when PSB building fails."""
    pass


class PsbBuilder:
    """Build PSB binary from parsed data.
    
    This is a simplified builder focused on resource reconstruction.
    For full PSB compilation from JSON, see future PsbCompiler.
    """
    
    def __init__(self, version: int = 4):
        """Initialize builder.
        
        Args:
            version: PSB version (2, 3, or 4)
        """
        self.version = version
        self.encoding = 'utf-8'
        
        # Data structures (will be populated)
        self.names: List[str] = []
        self.strings: List[str] = []
        self.resources: List[bytes] = []
        self.extra_resources: List[bytes] = []
        self.root: Optional[Dict[str, Any]] = None
        
    def rebuild_with_new_resources(
        self,
        original_psb: bytes,
        new_resources: List[bytes],
        new_spec: Optional[str] = None
    ) -> bytes:
        """Rebuild PSB with new resources (e.g., decompressed textures).
        
        This is the simplified path for KrKr→EMS conversion:
        1. Parse original PSB structure
        2. Replace resource data
        3. Rebuild Resources section
        4. Update offsets and checksum
        
        Args:
            original_psb: Original PSB bytes
            new_resources: New resource data (e.g., decompressed)
            new_spec: New spec string (e.g., "ems"), optional
            
        Returns:
            Rebuilt PSB bytes
        """
        from plugins.psb_decryption.psb_reader import PsbReader
        
        # Parse original
        reader = PsbReader(original_psb)
        parsed = reader.parse()
        
        # Validate resource count
        if len(new_resources) != len(parsed['resources']):
            raise PsbBuilderError(
                f"Resource count mismatch: expected {len(parsed['resources'])}, "
                f"got {len(new_resources)}"
            )
        
        # Build new PSB
        return self._rebuild_from_parsed(
            parsed=parsed,
            original_bytes=original_psb,
            new_resources=new_resources,
            new_spec=new_spec
        )
    
    def _rebuild_from_parsed(
        self,
        parsed: Dict[str, Any],
        original_bytes: bytes,
        new_resources: List[bytes],
        new_spec: Optional[str]
    ) -> bytes:
        """Rebuild PSB from parsed data with new resources.
        
        Strategy: Keep Names/Entries/Strings unchanged, rebuild Resources.
        """
        header = parsed['header']
        
        # Extract unchanged sections from original
        names_section = self._extract_section(
            original_bytes,
            header['offset_names'],
            header['offset_entries']
        )
        
        entries_section = self._extract_section(
            original_bytes,
            header['offset_entries'],
            header['offset_strings']
        )
        
        strings_offsets_section = self._extract_section(
            original_bytes,
            header['offset_strings'],
            header['offset_strings_data']
        )
        
        strings_data_section = self._extract_section(
            original_bytes,
            header['offset_strings_data'],
            header['offset_chunk_offsets']
        )
        
        # Handle spec string change if requested
        if new_spec:
            strings_data_section = self._replace_spec_string(
                strings_data_section,
                parsed['spec'],
                new_spec
            )
        
        # Build new Resources section
        resources_section = self._build_resources_section(
            new_resources,
            parsed['extra_resources'],
            self.version
        )
        
        # Assemble PSB
        output = BytesIO()
        
        # Reserve space for header
        header_length = self._get_header_length(self.version)
        output.write(b'\x00' * header_length)
        
        # Write Names
        offset_names = output.tell()
        output.write(names_section)
        
        # Write Entries
        offset_entries = output.tell()
        output.write(entries_section)
        
        # Write Strings
        offset_strings = output.tell()
        output.write(strings_offsets_section)
        
        offset_strings_data = output.tell()
        output.write(strings_data_section)
        
        # Write Resources
        resource_offsets = self._write_resources_section(
            output,
            resources_section,
            self.version
        )
        
        # Build and write header
        new_header = self._build_header(
            version=self.version,
            offset_names=offset_names,
            offset_entries=offset_entries,
            offset_strings=offset_strings,
            offset_strings_data=offset_strings_data,
            resource_offsets=resource_offsets
        )
        
        # Write header at beginning
        result = bytearray(output.getvalue())
        result[:len(new_header)] = new_header
        
        # Calculate and write checksum (v3/v4)
        if self.version >= 3:
            checksum = self._calculate_checksum(
                header_length=header_length,
                offset_names=offset_names,
                offset_strings=offset_strings,
                offset_strings_data=offset_strings_data,
                offset_chunk_offsets=resource_offsets['offset_chunk_offsets'],
                offset_chunk_lengths=resource_offsets['offset_chunk_lengths'],
                offset_chunk_data=resource_offsets['offset_chunk_data'],
                offset_entries=offset_entries,
                offset_extra_chunk_offsets=resource_offsets.get('offset_extra_chunk_offsets', 0),
                offset_extra_chunk_lengths=resource_offsets.get('offset_extra_chunk_lengths', 0),
                offset_extra_chunk_data=resource_offsets.get('offset_extra_chunk_data', 0)
            )
            # Checksum位置：v3=40, v4=40
            checksum_offset = 40
            result[checksum_offset:checksum_offset + 4] = struct.pack('<I', checksum)
        
        return bytes(result)
    
    def _extract_section(
        self,
        data: bytes,
        start: int,
        end: int
    ) -> bytes:
        """Extract a section from original PSB."""
        return data[start:end]
    
    def _replace_spec_string(
        self,
        strings_data: bytes,
        old_spec: str,
        new_spec: str
    ) -> bytes:
        """Replace spec string in strings data section."""
        old_bytes = (old_spec + '\0').encode('utf-8')
        new_bytes = (new_spec + '\0').encode('utf-8')
        
        # Simple replacement (assumes single occurrence)
        result = bytearray(strings_data)
        pos = result.find(old_bytes)
        
        if pos < 0:
            raise PsbBuilderError(f"Spec string '{old_spec}' not found")
        
        # Handle length mismatch
        if len(new_bytes) != len(old_bytes):
            # For now, use padding hack (e.g., "krkr\0" → "ems\0" keeps extra byte)
            if len(new_bytes) < len(old_bytes):
                result[pos:pos + len(new_bytes)] = new_bytes
                # Keep remaining bytes as padding
            else:
                raise PsbBuilderError(
                    f"New spec '{new_spec}' is longer than old spec '{old_spec}'"
                )
        else:
            result[pos:pos + len(new_bytes)] = new_bytes
        
        return bytes(result)
    
    def _build_resources_section(
        self,
        resources: List[bytes],
        extra_resources: List[bytes],
        version: int
    ) -> Dict[str, Any]:
        """Build resources section data.
        
        Returns:
            dict with 'offsets', 'lengths', 'data' for both regular and extra
        """
        # Build regular resources
        regular_data = BytesIO()
        regular_offsets = []
        regular_lengths = []
        
        for res in resources:
            regular_offsets.append(regular_data.tell())
            regular_lengths.append(len(res))
            regular_data.write(res)
        
        # Build extra resources (v4 only)
        extra_data = BytesIO()
        extra_offsets = []
        extra_lengths = []
        
        if version >= 4 and extra_resources:
            for res in extra_resources:
                extra_offsets.append(extra_data.tell())
                extra_lengths.append(len(res))
                extra_data.write(res)
        
        return {
            'regular': {
                'offsets': regular_offsets,
                'lengths': regular_lengths,
                'data': regular_data.getvalue()
            },
            'extra': {
                'offsets': extra_offsets,
                'lengths': extra_lengths,
                'data': extra_data.getvalue()
            }
        }
    
    def _write_resources_section(
        self,
        output: BytesIO,
        resources_section: Dict[str, Any],
        version: int
    ) -> Dict[str, int]:
        """Write resources section and return offsets.
        
        Returns:
            dict with all resource-related offsets
        """
        offsets = {}
        
        # Write extra resources first (v4) - always write even if empty
        if version >= 4:
            extra = resources_section['extra']
            
            offsets['offset_extra_chunk_offsets'] = output.tell()
            self._write_uint_array(output, extra['offsets'])
            
            offsets['offset_extra_chunk_lengths'] = output.tell()
            self._write_uint_array(output, extra['lengths'])
            
            # Align if needed (only if we have data)
            if extra['data']:
                self._align_data(output, 16)
                offsets['offset_extra_chunk_data'] = output.tell()
                output.write(extra['data'])
            else:
                offsets['offset_extra_chunk_data'] = output.tell()
        
        # Write regular resources
        regular = resources_section['regular']
        
        offsets['offset_chunk_offsets'] = output.tell()
        self._write_uint_array(output, regular['offsets'])
        
        offsets['offset_chunk_lengths'] = output.tell()
        self._write_uint_array(output, regular['lengths'])
        
        # Align if needed
        self._align_data(output, 16)
        
        offsets['offset_chunk_data'] = output.tell()
        output.write(regular['data'])
        
        return offsets
    
    def _write_uint_array(self, output: BytesIO, values: List[int]) -> None:
        """Write PSB uint array (variable-width encoding)."""
        from plugins.psb_decryption.psb_types import write_psb_array
        output.write(write_psb_array(values))
    
    def _align_data(self, output: BytesIO, alignment: int = 16) -> int:
        """Align stream position to specified boundary."""
        pos = output.tell()
        remainder = pos % alignment
        if remainder:
            padding = alignment - remainder
            output.write(b'\x00' * padding)
            return padding
        return 0
    
    def _get_header_length(self, version: int) -> int:
        """Get header length for PSB version."""
        if version == 2:
            return 40
        elif version == 3:
            return 44
        elif version == 4:
            return 56
        else:
            raise PsbBuilderError(f"Unsupported PSB version: {version}")
    
    def _build_header(
        self,
        version: int,
        offset_names: int,
        offset_entries: int,
        offset_strings: int,
        offset_strings_data: int,
        resource_offsets: Dict[str, int]
    ) -> bytes:
        """Build PSB header."""
        header = BytesIO()
        
        # Magic
        header.write(b'PSB\0')
        
        # Version
        header.write(struct.pack('<H', version))
        
        # Header encrypt flag
        header.write(struct.pack('<H', 0))
        
        # Header length (offset 8)
        header_len = self._get_header_length(version)
        header.write(struct.pack('<I', header_len))
        
        # Offsets
        header.write(struct.pack('<I', offset_names))
        header.write(struct.pack('<I', offset_strings))
        header.write(struct.pack('<I', offset_strings_data))
        header.write(struct.pack('<I', resource_offsets['offset_chunk_offsets']))
        header.write(struct.pack('<I', resource_offsets['offset_chunk_lengths']))
        header.write(struct.pack('<I', resource_offsets['offset_chunk_data']))
        header.write(struct.pack('<I', offset_entries))
        
        if version >= 3:
            # Adler32 checksum (placeholder, will calculate later)
            header.write(struct.pack('<I', 0))
        
        if version >= 4:
            # Extra resource offsets
            header.write(struct.pack('<I', resource_offsets.get('offset_extra_chunk_offsets', 0)))
            header.write(struct.pack('<I', resource_offsets.get('offset_extra_chunk_lengths', 0)))
            header.write(struct.pack('<I', resource_offsets.get('offset_extra_chunk_data', 0)))
        
        return header.getvalue()
    
    def _calculate_checksum(
        self,
        header_length: int,
        offset_names: int,
        offset_strings: int,
        offset_strings_data: int,
        offset_chunk_offsets: int,
        offset_chunk_lengths: int,
        offset_chunk_data: int,
        offset_entries: int,
        offset_extra_chunk_offsets: int = 0,
        offset_extra_chunk_lengths: int = 0,
        offset_extra_chunk_data: int = 0
    ) -> int:
        """Calculate Adler32 checksum for PSB v3/v4.
        
        Checksum is calculated over the header offset fields (little-endian uint32).
        v3: 8 fields (HeaderLength through OffsetEntries)
        v4: 11 fields (adds 3 extra resource offsets)
        """
        import zlib
        
        # Build checksum buffer (all offset fields as little-endian uint32)
        check_buffer = bytearray()
        check_buffer.extend(struct.pack('<I', header_length))
        check_buffer.extend(struct.pack('<I', offset_names))
        check_buffer.extend(struct.pack('<I', offset_strings))
        check_buffer.extend(struct.pack('<I', offset_strings_data))
        check_buffer.extend(struct.pack('<I', offset_chunk_offsets))
        check_buffer.extend(struct.pack('<I', offset_chunk_lengths))
        check_buffer.extend(struct.pack('<I', offset_chunk_data))
        check_buffer.extend(struct.pack('<I', offset_entries))
        
        if self.version >= 4:
            check_buffer.extend(struct.pack('<I', offset_extra_chunk_offsets))
            check_buffer.extend(struct.pack('<I', offset_extra_chunk_lengths))
            check_buffer.extend(struct.pack('<I', offset_extra_chunk_data))
        
        return zlib.adler32(check_buffer) & 0xFFFFFFFF
