"""DXT/BC texture decompression.

Based on FreeMote/DxtUtil.cs (MonoGame) and FreeMote/DxtCodec.cs.
Implements DXT1, DXT3, DXT5 (BC1, BC2, BC3) decompression to RGBA8.
"""

from __future__ import annotations
import struct


class DxtDecoderError(ValueError):
    """DXT decoding failed."""
    pass


def _validate_input(data: bytes, width: int, height: int, block_size: int, name: str) -> None:
    if width <= 0 or height <= 0:
        raise DxtDecoderError(f"{name} dimensions must be positive: {width}x{height}")
    expected = ((width + 3) // 4) * ((height + 3) // 4) * block_size
    if len(data) != expected:
        raise DxtDecoderError(f"{name} data size mismatch: {len(data)} != {expected}")


def _rgb565_to_rgb888(color: int) -> tuple[int, int, int]:
    """Convert RGB565 to RGB888 using the MonoGame formula.

    This matches FreeMote/DxtUtil.cs ConvertRgb565ToRgb888.
    """
    temp = (color >> 11) * 255 + 16
    r = (temp // 32 + temp) // 32

    temp = ((color & 0x07E0) >> 5) * 255 + 32
    g = (temp // 64 + temp) // 64

    temp = (color & 0x001F) * 255 + 16
    b = (temp // 32 + temp) // 32

    return (r & 0xFF, g & 0xFF, b & 0xFF)


def decompress_dxt1(data: bytes, width: int, height: int) -> bytes:
    """Decompress DXT1/BC1 to RGBA8.

    Args:
        data: DXT1 compressed data (width*height//2 bytes)
        width: Image width in pixels (must be multiple of 4)
        height: Image height in pixels (must be multiple of 4)

    Returns:
        RGBA8 pixel data (width*height*4 bytes)
    """
    _validate_input(data, width, height, 8, "DXT1")

    output = bytearray(width * height * 4)
    offset = 0

    block_count_x = (width + 3) // 4
    block_count_y = (height + 3) // 4

    for by in range(block_count_y):
        for bx in range(block_count_x):
            if offset + 8 > len(data):
                raise DxtDecoderError(f"DXT1 block truncated at offset {offset}")

            c0, c1, lookup = struct.unpack_from('<HHI', data, offset)
            offset += 8

            r0, g0, b0 = _rgb565_to_rgb888(c0)
            r1, g1, b1 = _rgb565_to_rgb888(c1)

            for py in range(4):
                for px in range(4):
                    index = (lookup >> (2 * (4 * py + px))) & 0x03

                    if c0 > c1:
                        if index == 0:
                            r, g, b, a = r0, g0, b0, 255
                        elif index == 1:
                            r, g, b, a = r1, g1, b1, 255
                        elif index == 2:
                            r, g, b, a = (2*r0 + r1)//3, (2*g0 + g1)//3, (2*b0 + b1)//3, 255
                        else:  # index == 3
                            r, g, b, a = (r0 + 2*r1)//3, (g0 + 2*g1)//3, (b0 + 2*b1)//3, 255
                    else:
                        if index == 0:
                            r, g, b, a = r0, g0, b0, 255
                        elif index == 1:
                            r, g, b, a = r1, g1, b1, 255
                        elif index == 2:
                            r, g, b, a = (r0 + r1)//2, (g0 + g1)//2, (b0 + b1)//2, 255
                        else:  # index == 3
                            r, g, b, a = 0, 0, 0, 0

                    img_x = (bx << 2) + px
                    img_y = (by << 2) + py
                    if img_x < width and img_y < height:
                        out_offset = ((img_y * width) + img_x) << 2
                        output[out_offset] = r
                        output[out_offset + 1] = g
                        output[out_offset + 2] = b
                        output[out_offset + 3] = a

    return bytes(output)


def decompress_dxt3(data: bytes, width: int, height: int) -> bytes:
    """Decompress DXT3/BC2 to RGBA8.

    Args:
        data: DXT3 compressed data (width*height bytes)
        width: Image width in pixels (must be multiple of 4)
        height: Image height in pixels (must be multiple of 4)

    Returns:
        RGBA8 pixel data (width*height*4 bytes)
    """
    _validate_input(data, width, height, 16, "DXT3")

    output = bytearray(width * height * 4)
    offset = 0

    block_count_x = (width + 3) // 4
    block_count_y = (height + 3) // 4

    for by in range(block_count_y):
        for bx in range(block_count_x):
            if offset + 16 > len(data):
                raise DxtDecoderError(f"DXT3 block truncated at offset {offset}")

            alpha_bytes = data[offset:offset+8]
            c0, c1, lookup = struct.unpack_from('<HHI', data, offset + 8)
            offset += 16

            r0, g0, b0 = _rgb565_to_rgb888(c0)
            r1, g1, b1 = _rgb565_to_rgb888(c1)

            alpha_index = 0
            for py in range(4):
                for px in range(4):
                    index = (lookup >> (2 * (4 * py + px))) & 0x03

                    # DXT3 alpha: 4-bit per pixel, expand to 8-bit
                    alpha_byte = alpha_bytes[alpha_index >> 1]
                    if alpha_index & 1:
                        a_val = (alpha_byte & 0xF0) >> 4
                    else:
                        a_val = alpha_byte & 0x0F
                    a = (a_val << 4) | a_val  # Replicate to 8-bit
                    alpha_index += 1

                    if index == 0:
                        r, g, b = r0, g0, b0
                    elif index == 1:
                        r, g, b = r1, g1, b1
                    elif index == 2:
                        r, g, b = (2*r0 + r1)//3, (2*g0 + g1)//3, (2*b0 + b1)//3
                    else:  # index == 3
                        r, g, b = (r0 + 2*r1)//3, (g0 + 2*g1)//3, (b0 + 2*b1)//3

                    img_x = (bx << 2) + px
                    img_y = (by << 2) + py
                    if img_x < width and img_y < height:
                        out_offset = ((img_y * width) + img_x) << 2
                        output[out_offset] = r
                        output[out_offset + 1] = g
                        output[out_offset + 2] = b
                        output[out_offset + 3] = a

    return bytes(output)


def decompress_dxt5(data: bytes, width: int, height: int) -> bytes:
    """Decompress DXT5/BC3 to RGBA8.

    Args:
        data: DXT5 compressed data (width*height bytes)
        width: Image width in pixels (must be multiple of 4)
        height: Image height in pixels (must be multiple of 4)

    Returns:
        RGBA8 pixel data (width*height*4 bytes)

    Format per 16-byte block:
        - Bytes 0-1: alpha0, alpha1 endpoints
        - Bytes 2-7: 48-bit alpha lookup table (3 bits per pixel)
        - Bytes 8-9: c0 RGB565
        - Bytes 10-11: c1 RGB565
        - Bytes 12-15: 32-bit color lookup table (2 bits per pixel)

    This matches FreeMote/DxtUtil.cs DecompressDxt5Block.
    """
    _validate_input(data, width, height, 16, "DXT5")

    output = bytearray(width * height * 4)
    offset = 0

    block_count_x = (width + 3) // 4
    block_count_y = (height + 3) // 4

    for by in range(block_count_y):
        for bx in range(block_count_x):
            if offset + 16 > len(data):
                raise DxtDecoderError(f"DXT5 block truncated at offset {offset}")

            alpha0 = data[offset]
            alpha1 = data[offset + 1]

            # Read 48-bit alpha mask as 6 bytes, little-endian
            alpha_mask = (
                data[offset + 2] |
                (data[offset + 3] << 8) |
                (data[offset + 4] << 16) |
                (data[offset + 5] << 24) |
                (data[offset + 6] << 32) |
                (data[offset + 7] << 40)
            )

            c0, c1, lookup = struct.unpack_from('<HHI', data, offset + 8)
            offset += 16

            r0, g0, b0 = _rgb565_to_rgb888(c0)
            r1, g1, b1 = _rgb565_to_rgb888(c1)

            for py in range(4):
                for px in range(4):
                    color_index = (lookup >> (2 * (4 * py + px))) & 0x03
                    alpha_index = (alpha_mask >> (3 * (4 * py + px))) & 0x07

                    # DXT5 alpha interpolation
                    if alpha_index == 0:
                        a = alpha0
                    elif alpha_index == 1:
                        a = alpha1
                    elif alpha0 > alpha1:
                        a = ((8 - alpha_index) * alpha0 + (alpha_index - 1) * alpha1) // 7
                    elif alpha_index == 6:
                        a = 0
                    elif alpha_index == 7:
                        a = 0xFF
                    else:
                        a = ((6 - alpha_index) * alpha0 + (alpha_index - 1) * alpha1) // 5

                    # DXT1-style color interpolation (always 4-color mode for DXT5)
                    if color_index == 0:
                        r, g, b = r0, g0, b0
                    elif color_index == 1:
                        r, g, b = r1, g1, b1
                    elif color_index == 2:
                        r, g, b = (2*r0 + r1)//3, (2*g0 + g1)//3, (2*b0 + b1)//3
                    else:  # color_index == 3
                        r, g, b = (r0 + 2*r1)//3, (g0 + 2*g1)//3, (b0 + 2*b1)//3

                    img_x = (bx << 2) + px
                    img_y = (by << 2) + py
                    if img_x < width and img_y < height:
                        out_offset = ((img_y * width) + img_x) << 2
                        output[out_offset] = r
                        output[out_offset + 1] = g
                        output[out_offset + 2] = b
                        output[out_offset + 3] = a

    return bytes(output)
