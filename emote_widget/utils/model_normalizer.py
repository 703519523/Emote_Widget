"""Normalize wrapped FreeMote PSB files before exposing them to the WebEngine."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Union

from .psb_converter import PsbNormalizer, adapt_win_psb_to_ems, detect_shell


StrPath = Union[str, os.PathLike[str]]


def normalize_model_path(path: StrPath, *, cache_root: StrPath = ".emote_cache/normalized_models") -> Path:
    """Validate a PSB and cache an unwrapped copy when necessary.

    Raw ``PSB\0`` files keep the legacy loader path because existing Emote models
    may legitimately use ``spec=ems``. Wrapped files are strictly normalized;
    supported Win/RGBA8 payloads are adapted for the bundled EMS driver before
    being written to cache. The original resource is never modified.
    """
    source = Path(path).resolve()
    if detect_shell(source.read_bytes()) == "raw":
        return source

    result = PsbNormalizer(source).normalize_with_summary()
    normalized_data = result.data
    if result.summary.get("spec") == "win":
        normalized_data = adapt_win_psb_to_ems(normalized_data)

    source_digest = hashlib.sha256(source.read_bytes()).hexdigest()[:16]
    cache_dir = Path(cache_root).resolve()
    cache_dir.mkdir(parents=True, exist_ok=True)
    target = cache_dir / f"{source.stem}.{source_digest}.pure.psb"

    if not target.exists() or target.read_bytes() != normalized_data:
        temporary = target.with_suffix(target.suffix + ".tmp")
        temporary.write_bytes(normalized_data)
        os.replace(temporary, target)

    return target
