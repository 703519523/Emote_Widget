import inspect
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from emote_widget.utils.psb_converter import PsbReader
from emote_widget.core.middleware import MiddlewareManager
from emote_widget.core.middleware import Middleware


class ModelNormalizerTests(unittest.TestCase):
    def tearDown(self):
        MiddlewareManager.clear_all()

    def test_extension_normalizes_real_wrapped_model_to_ems(self):
        from emote_widget.utils.model_normalizer import normalize_model_path
        from plugins.psb_decryption.main import PsbDecryptionMiddleware

        source = Path("models/dx_e-moteアズキ私服a.psb")
        MiddlewareManager.get_chain("psb.normalize").use(PsbDecryptionMiddleware())

        with tempfile.TemporaryDirectory() as directory:
            target = normalize_model_path(source, cache_root=directory)
            self.assertEqual(PsbReader(target.read_bytes()).parse()["spec"], "ems")

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
            normalizer_cls.assert_called_once_with(source, require_win_spec=False)

    def test_pure_model_keeps_legacy_loader_compatibility(self):
        from emote_widget.utils.model_normalizer import normalize_model_path

        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "character.psb"
            source.write_bytes(b"PSB\0already pure")

            with patch("emote_widget.utils.model_normalizer.PsbNormalizer") as normalizer_cls:
                result = normalize_model_path(source, cache_root=Path(directory) / "cache")

            self.assertEqual(result, source)
            normalizer_cls.assert_not_called()

    def test_core_normalizer_rejects_wrapped_input(self):
        from emote_widget.utils.psb_converter import PsbNormalizer, PsbNormalizerError

        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "wrapped.psb"
            source.write_bytes(b"PSZ\0not handled by core")

            with self.assertRaises(PsbNormalizerError):
                PsbNormalizer(source).normalize_with_summary()

    def test_model_resource_normalization_error_is_not_reported_as_missing_path(self):
        from emote_widget.utils.paths import ResourceNormalizationError

        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "broken.psb"
            source.write_bytes(b"PSB\0broken")

            with patch(
                "emote_widget.utils.paths.normalize_model_path",
                side_effect=ValueError("cannot adapt spec='krkr' to EMS"),
            ):
                from emote_widget.utils.paths import resolve_resource_url

                with self.assertRaises(ResourceNormalizationError) as raised:
                    resolve_resource_url(str(source), "models")

            self.assertIn("cannot adapt spec='krkr' to EMS", str(raised.exception))

    def test_real_lz4_win_rgba8_model_is_adapted_for_ems_driver(self):
        source = Path("models/dx_e-moteアズキ私服a.psb")
        self.assertTrue(source.exists(), "real wrapped regression fixture is missing")

        from emote_widget.utils.psb_converter import PsbReader
        from plugins.psb_decryption.psb_shell import unwrap_psb
        from plugins.psb_decryption.psb_crypto import decrypt_psb
        from plugins.psb_decryption.ems_adapter import adapt_win_psb_to_ems

        raw = decrypt_psb(unwrap_psb(source.read_bytes()).data).data
        before = PsbReader(raw).parse()
        converted = adapt_win_psb_to_ems(raw)
        after = PsbReader(converted).parse()

        self.assertEqual(before["spec"], "win")
        self.assertEqual(after["spec"], "ems")
        self.assertTrue(after["checksum_valid"])

        before_resource = before["resources"][0]
        before_start = before["header"]["offset_chunk_data"] + before_resource["offset"]
        after_resource = after["resources"][0]
        after_start = after["header"]["offset_chunk_data"] + after_resource["offset"]
        self.assertEqual(converted[after_start], raw[before_start + 2])
        self.assertEqual(converted[after_start + 1], raw[before_start + 1])
        self.assertEqual(converted[after_start + 2], raw[before_start])
        self.assertEqual(converted[after_start + 3], raw[before_start + 3])

    def test_psb_plugin_contains_freemote_rl_codec(self):
        from plugins.psb_decryption.rle_compress import compress, decompress

        pixels = (b"\x10\x20\x30\xff" * 8) + bytes(range(32))
        encoded = compress(pixels, align=4)

        self.assertNotEqual(encoded, pixels)
        self.assertEqual(decompress(encoded, align=4, actual_size=len(pixels)), pixels)

    def test_psb_plugin_compiler_builds_parseable_v4_with_extra_resources(self):
        from plugins.psb_decryption.psb_compiler import PsbCompiler
        from plugins.psb_decryption.psb_reader import PsbReader

        root = {
            "spec": "ems",
            "label": "compiler-roundtrip",
            "regular": {
                "_type": "resource", "index": 0,
                "is_extra": False, "data": b"regular-resource",
            },
            "extra": {
                "_type": "resource", "index": 0,
                "is_extra": True, "data": b"extra-resource",
            },
        }

        compiled = PsbCompiler(version=4).compile(root)
        parsed = PsbReader(compiled, load_resource_data=True).parse()

        self.assertEqual(parsed["spec"], "ems")
        self.assertTrue(parsed["checksum_valid"])
        self.assertEqual(parsed["resources"][0]["data"], b"regular-resource")
        self.assertEqual(parsed["extra_resources"][0]["data"], b"extra-resource")

    def test_psb_plugin_uses_full_krkr_atlas_conversion(self):
        from plugins.psb_decryption import ems_adapter

        source = inspect.getsource(ems_adapter)
        self.assertIn("def _pack_atlases", source)
        self.assertIn("def _convert_krkr_tree_to_ems", source)
        self.assertIn("PsbCompiler", source)


if __name__ == "__main__":
    unittest.main()