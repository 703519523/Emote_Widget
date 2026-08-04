"""Normalize wrapped FreeMote PSB files before exposing them to the WebEngine."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Union

from emote_widget.core.middleware import MiddlewareManager
from .psb_converter import PsbNormalizer
from .model_health import ModelHealthReport, inspect_model_bytes


StrPath = Union[str, os.PathLike[str]]
_HEALTH_REPORTS: dict[Path, ModelHealthReport] = {}


def get_model_health_report(path: StrPath) -> ModelHealthReport | None:
    return _HEALTH_REPORTS.get(Path(path).resolve())


def _normalize_model_path_default(context: dict) -> dict:
    """Run the built-in model normalizer for a middleware context."""
    source = Path(context["source_path"]).resolve()
    cache_root = context["cache_root"]

    if context.get("normalized_data") is not None:
        result = PsbNormalizer(source, require_win_spec=False).normalize_data(
            context["normalized_data"],
            shell=context.get("shell", "raw"),
            source_size=source.stat().st_size,
            crypto_summary=context.get("crypto_summary"),
        )
        normalized_data = result.data
        context["summary"] = result.summary
    elif source.read_bytes().startswith(b"PSB\0"):
        report = inspect_model_bytes(source.read_bytes())
        _HEALTH_REPORTS[source] = report
        context["health_report"] = report
        context["normalized_path"] = source
        return context
    else:
        raise ValueError(
            f"{source}: wrapped PSB input requires an extension plugin; "
            "the core loader accepts only raw/pure PSB files"
        )
    source_digest = hashlib.sha256(source.read_bytes()).hexdigest()[:16]
    cache_dir = Path(cache_root).resolve()
    cache_dir.mkdir(parents=True, exist_ok=True)
    target = cache_dir / f"{source.stem}.{source_digest}.pure.psb"

    if not target.exists() or target.read_bytes() != normalized_data:
        temporary = target.with_suffix(target.suffix + ".tmp")
        temporary.write_bytes(normalized_data)
        os.replace(temporary, target)

    report = inspect_model_bytes(normalized_data)
    _HEALTH_REPORTS[source] = report
    _HEALTH_REPORTS[target] = report
    context["health_report"] = report

    context["normalized_path"] = target
    return context


def normalize_model_path(path: StrPath, *, cache_root: StrPath = ".emote_cache/normalized_models") -> Path:
    """Validate a PSB and cache an unwrapped copy when necessary.

    Raw ``PSB\0`` files keep the legacy loader path because existing Emote models
    may legitimately use ``spec=ems``. Wrapped files are strictly normalized;
    supported Win/RGBA8 payloads are adapted for the bundled EMS driver before
    being written to cache. The original resource is never modified.
    """
    context = {
        "source_path": Path(path).resolve(),
        "cache_root": Path(cache_root),
        "normalized_path": None,
        "summary": None,
        "normalized_data": None,
        "shell": None,
        "crypto_summary": None,
        "health_report": None,
    }
    chain = MiddlewareManager.get_chain("psb.normalize")
    result = chain.execute(context, terminal=_normalize_model_path_default)
    normalized_path = result.get("normalized_path")
    if not isinstance(normalized_path, Path):
        raise ValueError("psb.normalize middleware did not provide normalized_path")
    return normalized_path
