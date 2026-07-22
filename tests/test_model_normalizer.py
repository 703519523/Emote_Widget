import hashlib
import inspect
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from emote_widget.utils.psb_converter import PsbReader
from emote_widget.core.middleware import MiddlewareManager
from emote_widget.core.middleware import Middleware


class ModelNormalizerTests(unittest.TestCase):
    WRAPPED_WIN_FIXTURE = Path("test_models/dx_e-moteアズキ私服a.psb")
    PSP_SHA256 = "72e4b8e539e75d32bb2c4a4faa4cce71ecdf25edacf6929559365b23a368b941"
    PSP_PAYLOAD_SHA256 = "2f48682545795cac2cc135e95fd13b5004ba9a6f8ed8d391f12f43f1ca8d96d7"

    def tearDown(self):
        MiddlewareManager.clear_all()

    def _require_wrapped_win_fixture(self):
        if not self.WRAPPED_WIN_FIXTURE.exists():
            self.skipTest("local wrapped Win PSB fixture is not available")
        return self.WRAPPED_WIN_FIXTURE

    def _require_named_fixture(self, name_fragment):
        root = Path("test_models")
        fixture = next(
            (path for path in root.glob("*") if name_fragment in path.name),
            None,
        )
        if fixture is None:
            self.skipTest(f"local {name_fragment} fixture is not available")
        return fixture

    def test_extension_normalizes_real_wrapped_model_to_ems(self):
        from emote_widget.utils.model_normalizer import normalize_model_path
        from plugins.psb_decryption.main import PsbDecryptionMiddleware

        source = self._require_wrapped_win_fixture()
        MiddlewareManager.get_chain("psb.normalize").use(PsbDecryptionMiddleware())

        with tempfile.TemporaryDirectory() as directory:
            target = normalize_model_path(source, cache_root=directory)
            self.assertEqual(PsbReader(target.read_bytes()).parse()["spec"], "ems")

    def test_core_loader_rejects_wrapped_input_without_extension(self):
        from emote_widget.utils.model_normalizer import normalize_model_path

        source = self._require_wrapped_win_fixture()
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

    def test_psb_plugin_detects_and_unwraps_psp_lzss_literals(self):
        from plugins.psb_decryption.psb_shell import detect_shell, unwrap_psb

        payload = b"PSB\0test"
        shell = struct.pack("<I", len(payload)) + b"\xff" + payload

        self.assertEqual(detect_shell(shell), "psp")
        unwrapped = unwrap_psb(shell)
        self.assertEqual(unwrapped.shell, "psp")
        self.assertEqual(unwrapped.data, payload)

    def test_psb_plugin_native_facade_is_optional_and_exposes_psp_capability(self):
        from plugins.psb_decryption import _native

        self.assertIsInstance(_native.capabilities(), frozenset)
        if _native.available("psp_lzss_unpack"):
            self.assertIsNone(_native.load_error())

    def test_psb_plugin_native_psp_unpack_matches_python_fallback(self):
        from plugins.psb_decryption import _native
        from plugins.psb_decryption.psb_shell import _unpack_psp_python

        payload = b"PSB\0test"
        shell = struct.pack("<I", len(payload)) + b"\xff" + payload
        native = _native.unpack_psp(shell)
        if native is None:
            self.skipTest("native extension unavailable")
        self.assertEqual(native, _unpack_psp_python(shell, len(payload)))

    def test_psb_plugin_psp_lzss_rejects_truncated_stream(self):
        from plugins.psb_decryption.psb_shell import PsbShellError, unwrap_psb

        shell = struct.pack("<I", 8) + b"\xffPSB"

        with self.assertRaisesRegex(PsbShellError, "truncated PSP LZSS stream"):
            unwrap_psb(shell)

    def test_real_psp_lzss_shell_matches_fixed_oracle(self):
        from plugins.psb_decryption.psb_shell import detect_shell, unwrap_psb

        source = self._require_named_fixture("PSP(shell)")
        wrapped = source.read_bytes()
        self.assertEqual(len(wrapped), 5_860_942)
        self.assertEqual(hashlib.sha256(wrapped).hexdigest(), self.PSP_SHA256)
        self.assertEqual(detect_shell(wrapped), "psp")

        payload = unwrap_psb(wrapped).data
        self.assertEqual(len(payload), 27_705_408)
        self.assertEqual(hashlib.sha256(payload).hexdigest(), self.PSP_PAYLOAD_SHA256)

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
        source = self._require_wrapped_win_fixture()

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

    def test_win_bgra_conversion_returns_immutable_ems_rgba_bytes(self):
        from plugins.psb_decryption.ems_adapter import _bgr_to_rgb

        source = bytearray(b"\x10\x20\x30\x40\xaa\xbb\xcc\xdd")

        converted = _bgr_to_rgb(source)

        self.assertIsInstance(converted, bytes)
        self.assertEqual(converted, b"\x30\x20\x10\x40\xcc\xbb\xaa\xdd")
        self.assertEqual(source, bytearray(b"\x10\x20\x30\x40\xaa\xbb\xcc\xdd"))

    def test_flatten_array_win_texture_converts_bgra_and_preserves_extra_resources(self):
        from plugins.psb_decryption.ems_adapter import adapt_win_psb_to_ems
        from plugins.psb_decryption.psb_crypto import decrypt_psb
        from plugins.psb_decryption.psb_reader import PsbReader
        from plugins.psb_decryption.psb_shell import unwrap_psb

        source = self._require_named_fixture("FlattenArray")
        raw = decrypt_psb(unwrap_psb(source.read_bytes()).data).data
        before = PsbReader(raw, load_resource_data=True).parse()
        converted = adapt_win_psb_to_ems(raw)
        after = PsbReader(converted, load_resource_data=True).parse()

        self.assertEqual(before["spec"], "win")
        self.assertEqual(after["spec"], "ems")
        self.assertEqual(len(before["extra_resources"]), 136)
        self.assertEqual(
            [item["data"] for item in after["extra_resources"]],
            [item["data"] for item in before["extra_resources"]],
        )

        source_atlas = before["resources"][0]["data"]
        converted_atlas = after["resources"][0]["data"]
        self.assertEqual(len(source_atlas), 2048 * 2048 * 4)
        self.assertEqual(len(converted_atlas), len(source_atlas))
        self.assertEqual(converted_atlas[0::4], source_atlas[2::4])
        self.assertEqual(converted_atlas[1::4], source_atlas[1::4])
        self.assertEqual(converted_atlas[2::4], source_atlas[0::4])
        self.assertEqual(converted_atlas[3::4], source_atlas[3::4])

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