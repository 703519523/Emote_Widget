import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from emote_widget.utils.psb_converter import PsbReader
from emote_widget.core.middleware import MiddlewareManager
from emote_widget.core.middleware import Middleware


class ModelNormalizerTests(unittest.TestCase):
    def test_core_loader_rejects_wrapped_input_without_extension(self):
        from emote_widget.utils.model_normalizer import normalize_model_path

        source = Path("models/dx_e-moteアズキ私服a.psb")
        self.assertTrue(source.exists())
        from emote_widget.core.middleware import MiddlewareManager
        MiddlewareManager.clear_all()
        with self.assertRaises(ValueError):
            normalize_model_path(source, cache_root=".emote_cache/no_plugin")

    def test_wrapped_model_is_written_to_cache_and_returns_cache_path(self):
        from emote_widget.utils.model_normalizer import normalize_model_path

        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "character.psb"
            source.write_bytes(b"wrapped input")
            normalized = b"PSB\0validated payload"

            MiddlewareManager.clear_all()
            class TestExtensionMiddleware(Middleware):
                def process(self, data, next):
                    data["normalized_data"] = normalized
                    data["shell"] = "test-extension"
                    return next(data)

            MiddlewareManager.get_chain("psb.normalize").use(TestExtensionMiddleware())

            with patch("emote_widget.utils.model_normalizer.PsbNormalizer") as normalizer_cls:
                normalize_result = normalizer_cls.return_value.normalize_data.return_value
                normalize_result.data = normalized
                result = normalize_model_path(source, cache_root=Path(directory) / "cache")

            self.assertNotEqual(result, source)
            self.assertEqual(result.read_bytes(), normalized)
            normalizer_cls.assert_called_once_with(source)

    def test_pure_model_keeps_legacy_loader_compatibility(self):
        from emote_widget.utils.model_normalizer import normalize_model_path

        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "character.psb"
            source.write_bytes(b"PSB\0already pure")

            with patch("emote_widget.utils.model_normalizer.PsbNormalizer") as normalizer_cls:
                result = normalize_model_path(source, cache_root=Path(directory) / "cache")

            self.assertEqual(result, source)
            normalizer_cls.assert_not_called()

    def test_real_lz4_win_rgba8_model_is_adapted_for_ems_driver(self):
        source = Path("models/dx_e-moteアズキ私服a.psb")
        self.assertTrue(source.exists(), "real wrapped regression fixture is missing")

        from emote_widget.utils.psb_converter import PsbReader, unwrap_psb
        from plugins.psb_decryption.psb_crypto import decrypt_psb
        from plugins.psb_decryption.ems_adapter import adapt_win_psb_to_ems

        raw = decrypt_psb(unwrap_psb(source.read_bytes()).data).data
        before = PsbReader(raw).parse()
        converted = adapt_win_psb_to_ems(raw)
        after = PsbReader(converted).parse()

        self.assertEqual(before["spec"], "win")
        self.assertEqual(after["spec"], "ems")
        self.assertTrue(after["checksum_valid"])
        self.assertEqual(len(converted), len(raw))

        header = before["header"]
        first_resource = before["resources"][0]
        start = header["offset_chunk_data"] + first_resource["offset"]
        self.assertEqual(converted[start], raw[start + 2])
        self.assertEqual(converted[start + 1], raw[start + 1])
        self.assertEqual(converted[start + 2], raw[start])
        self.assertEqual(converted[start + 3], raw[start + 3])


if __name__ == "__main__":
    unittest.main()