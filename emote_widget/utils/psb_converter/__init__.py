"""Standalone PSB shell converter and structural validator."""

from .normalizer import NormalizeResult, PsbNormalizer, PsbNormalizerError
from .psb_reader import PsbBadFormatError, PsbReader
from .psb_shell import PsbShellError, UnwrappedPsb, detect_shell, unwrap_psb
from .ems_adapter import adapt_win_psb_to_ems

__all__ = [
    "NormalizeResult",
    "PsbBadFormatError",
    "PsbNormalizer",
    "PsbNormalizerError",
    "PsbReader",
    "PsbShellError",
    "UnwrappedPsb",
    "adapt_win_psb_to_ems",
    "detect_shell",
    "unwrap_psb",
]
