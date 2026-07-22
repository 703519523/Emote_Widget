"""Self-contained PSB conversion plugin package."""

from .psb_crypto import (
    DecryptedPsb,
    PsbCryptoError,
    PsbStreamContext,
    decrypt_psb,
    recover_header_key,
)

__version__ = "0.1.0"
