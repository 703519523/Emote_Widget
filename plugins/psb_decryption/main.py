from __future__ import annotations

from emote_widget.core.middleware import Middleware
from emote_widget.core.plugin_interface import IEmotePlugin
from emote_widget.utils.psb_converter import detect_shell, unwrap_psb
from .psb_crypto import PsbCryptoError, decrypt_psb
from .ems_adapter import adapt_win_psb_to_ems


class PsbDecryptionMiddleware(Middleware):
    """Provide decrypted PSB bytes to the core normalizer."""

    def process(self, data, next):
        source = data["source_path"]
        raw = source.read_bytes()
        shell = detect_shell(raw)
        unwrapped = raw if shell == "raw" else unwrap_psb(raw).data

        try:
            decrypted = decrypt_psb(unwrapped)
        except PsbCryptoError:
            # Plain PSB files continue through the built-in normalizer.
            return next(data)

        normalized_data = decrypted.data
        # Platform conversion is also an optional extension responsibility.
        normalized_data = adapt_win_psb_to_ems(normalized_data)
        data["normalized_data"] = normalized_data
        data["shell"] = shell
        data["crypto_summary"] = {
            "source_header_encrypted": decrypted.header_was_encrypted,
            "source_body_encrypted": decrypted.body_was_encrypted,
            "crypt_key": decrypted.key,
            "crypt_key_source": decrypted.key_source,
        }
        return next(data)


class PsbDecryptionPlugin(IEmotePlugin):
    def get_name(self) -> str:
        return "psb_decryption"

    def get_description(self) -> str:
        return "Optional PSB XorShift128 decryption middleware"

    def initialize(self) -> None:
        self.middleware.get_chain("psb.normalize").use(PsbDecryptionMiddleware())
        self.logger.info("PSB decryption middleware enabled")

    def cleanup(self) -> None:
        self.middleware.clear_chain("psb.normalize")