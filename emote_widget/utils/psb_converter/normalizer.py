"""Core PSB shell normalization; encryption is supplied by optional middleware."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Union
import os
from .psb_reader import PsbBadFormatError, PsbReader
StrPath = Union[str, os.PathLike[str]]
class PsbNormalizerError(ValueError):
    pass
@dataclass(frozen=True)
class NormalizeResult:
    data: bytes
    shell: str
    summary: Dict[str, Any]
class PsbNormalizer:
    def __init__(self, path: StrPath, *, require_win_spec: bool = True):
        self.path = Path(path)
        self.require_win_spec = require_win_spec
    def normalize_data(self, data: bytes, *, shell: str = "raw", source_size: Optional[int] = None, crypto_summary: Optional[Dict[str, Any]] = None) -> NormalizeResult:
        try:
            parsed = PsbReader(data).parse()
        except PsbBadFormatError as exc:
            raise PsbNormalizerError(f"cannot normalize {self.path}: {exc}") from exc
        if parsed["checksum_valid"] is False:
            raise PsbNormalizerError(f"{self.path}: PSB header checksum mismatch")
        spec = parsed.get("spec")
        if self.require_win_spec and spec not in (None, "win"):
            raise PsbNormalizerError(f"{self.path}: spec={spec!r}; refusing unsafe spec conversion")
        root = parsed["root"]
        summary = {"source": str(self.path), "shell": shell, "source_size": source_size if source_size is not None else len(data), "pure_size": len(data), "version": parsed["version"], "header_encrypt": parsed["header"]["header_encrypt"], "checksum_valid": parsed["checksum_valid"], "type": parsed["type"], "spec": spec, "name_count": len(parsed["names"]), "string_count": len(parsed["strings"]), "resource_count": len(parsed["resources"]), "extra_resource_count": len(parsed["extra_resources"]), "resources": parsed["resources"], "extra_resources": parsed["extra_resources"], "root_keys": list(root.keys()) if isinstance(root, dict) else []}
        if crypto_summary:
            summary.update(crypto_summary)
        return NormalizeResult(data, shell, summary)
    def normalize_with_summary(self) -> NormalizeResult:
        try:
            data = self.path.read_bytes()
            if not data.startswith(b"PSB\0"):
                raise PsbNormalizerError("core normalizer accepts only raw/pure PSB input")
            return self.normalize_data(data, shell="raw", source_size=self.path.stat().st_size)
        except (OSError, PsbNormalizerError) as exc:
            raise PsbNormalizerError(f"cannot normalize {self.path}: {exc}") from exc
    def normalize(self) -> bytes:
        return self.normalize_with_summary().data
    def write(self, output: Optional[StrPath] = None) -> Path:
        result = self.normalize_with_summary()
        target = Path(output) if output is not None else self.path.with_suffix(".pure.psb")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(result.data)
        return target
PsbQuickNormalizer = PsbNormalizer
