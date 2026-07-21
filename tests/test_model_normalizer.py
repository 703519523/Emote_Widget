import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from emote_widget.utils.psb_converter import PsbReader, adapt_win_psb_to_ems


class ModelNormalizerTests(unittest.TestCase):
    def test_wrapped_model_is_written_to_cache_and_returns_cache_path(self):
        from emote_widget.utils.model_normalizer import normalize_model_path

        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "character.psb"
            source.write_bytes(b"wrapped input")
            normalized = b"PSB\0validated payload"

            with patch("emote_widget.utils.model_normalizer.PsbNormalizer") as normalizer_cls:
                normalize_result = normalizer_cls.return_value.normalize_with_summary.return_value
                normalize_result.data = normalized
                normalize_result.shell = "mdf"
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

        from emote_widget.utils.psb_converter import PsbNormalizer

        raw = PsbNormalizer(source).normalize_with_summary().data
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