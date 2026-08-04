"""Command-line entry points for the Python PSB layer."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .psb_normalizer import PsbNormalizer


def main() -> int:
    parser = argparse.ArgumentParser(prog="freemote-python")
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--summary", type=Path)
    args = parser.parse_args()

    result = PsbNormalizer(args.input).normalize_with_summary()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(result.data)
    summary = json.dumps(result.summary, ensure_ascii=False, indent=2)
    if args.summary:
        args.summary.parent.mkdir(parents=True, exist_ok=True)
        args.summary.write_text(summary + "\n", encoding="utf-8")
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
