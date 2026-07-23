"""Self-contained PSB conversion plugin package."""

from .psb_crypto import (
    DecryptedPsb,
    PsbCryptoError,
    PsbStreamContext,
    decrypt_psb,
    recover_header_key,
)
from .main import PsbDecryptionPlugin

__version__ = "0.1.0"

__all__ = [
    "DecryptedPsb",
    "PsbCryptoError",
    "PsbDecryptionPlugin",
    "PsbStreamContext",
    "decrypt_psb",
    "recover_header_key",
]
