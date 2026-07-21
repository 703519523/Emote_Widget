"""Convert supported wrapped PSB files to validated raw PSB bytes."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Union
import os
from .psb_reader import PsbBadFormatError, PsbReader
from .psb_shell import PsbShellError, unwrap_psb
from .psb_crypto import PsbCryptoError, decrypt_psb
StrPath = Union[str, "os.PathLike[str]"]
class PsbNormalizerError(ValueError):
    """Raised when a PSB cannot be safely normalized."""
@dataclass(frozen=True)
class NormalizeResult:
    """Normalized bytes and machine-readable validation metadata."""
    data: bytes
    shell: str
    summary: Dict[str, Any]
class PsbNormalizer:
    """Unwrap, parse, checksum-validate and return canonical raw PSB bytes."""
    def __init__(self, path: StrPath, *, require_win_spec: bool = True, crypt_key: Optional[int] = None):
        self.path = Path(path)
        self.require_win_spec = require_win_spec
        self.crypt_key = crypt_key
    def normalize_with_summary(self) -> NormalizeResult:
        """Return normalized data together with structural validation results."""
        try:
            unwrapped = unwrap_psb(self.path.read_bytes())
            decrypted = decrypt_psb(unwrapped.data, self.crypt_key)
            parsed = PsbReader(decrypted.data).parse()
        except (OSError, PsbShellError, PsbCryptoError, PsbBadFormatError) as exc:
            raise PsbNormalizerError(f"cannot normalize {self.path}: {exc}") from exc
        if parsed["checksum_valid"] is False:
            raise PsbNormalizerError(f"{self.path}: PSB header checksum mismatch")
        spec = parsed.get("spec")
        if self.require_win_spec and spec not in (None, "win"):
            raise PsbNormalizerError(f"{self.path}: spec={spec!r}; refusing unsafe spec conversion")
        header = parsed["header"]
        root = parsed["root"]
        summary: Dict[str, Any] = {
            "source": str(self.path),
            "shell": unwrapped.shell,
            "source_size": self.path.stat().st_size,
            "unwrapped_size": len(unwrapped.data),
            "pure_size": len(decrypted.data),
            "version": parsed["version"],
            "header_encrypt": header["header_encrypt"],
            "source_header_encrypted": decrypted.header_was_encrypted,
            "source_body_encrypted": decrypted.body_was_encrypted,
            "crypt_key": decrypted.key,
            "crypt_key_source": decrypted.key_source,
            "checksum_valid": parsed["checksum_valid"],
            "type": parsed["type"],
            "spec": spec,
            "name_count": len(parsed["names"]),
            "string_count": len(parsed["strings"]),
            "resource_count": len(parsed["resources"]),
            "extra_resource_count": len(parsed["extra_resources"]),
            "resources": parsed["resources"],
            "extra_resources": parsed["extra_resources"],
            "root_keys": list(root.keys()) if isinstance(root, dict) else []
        }
        return NormalizeResult(decrypted.data, unwrapped.shell, summary)
    def normalize(self) -> bytes:
        """Return only normalized raw PSB bytes."""
        return self.normalize_with_summary().data
    def write(self, output: Optional[StrPath] = None) -> Path:
        """Write normalized bytes and return the output path."""
        result = self.normalize_with_summary()
        target = Path(output) if output is not None else self.path.with_suffix(".pure.psb")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(result.data)
        return target
PsbQuickNormalizer = PsbNormalizer
