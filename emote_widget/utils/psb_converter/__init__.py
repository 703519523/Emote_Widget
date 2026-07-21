"""Standalone PSB shell converter and structural validator."""

from .normalizer import NormalizeResult, PsbNormalizer, PsbNormalizerError
from .psb_reader import PsbBadFormatError, PsbReader
from .psb_shell import PsbShellError, UnwrappedPsb, detect_shell, unwrap_psb
from .psb_crypto import DecryptedPsb, PsbCryptoError, PsbStreamContext, decrypt_psb, recover_header_key
from .ems_adapter import adapt_win_psb_to_ems

__all__ = [
    "NormalizeResult",
    "PsbBadFormatError",
    "PsbNormalizer",
    "PsbNormalizerError",
    "PsbReader",
    "PsbShellError",
    "UnwrappedPsb",
    "DecryptedPsb",
    "PsbCryptoError",
    "PsbStreamContext",
    "adapt_win_psb_to_ems",
    "decrypt_psb",
    "detect_shell",
    "recover_header_key",
    "unwrap_psb",
]
