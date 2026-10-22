#!/usr/bin/env python3
"""Regenerate the output field of trainv2-last.json conservatively.

The source file is a draft corpus.  This utility intentionally starts from
each record's input, applies typography cleanup and a small set of
fact-neutral edits, then validates the pair before writing the result.  The
first three Alpaca fields are treated as immutable.
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from build_dataset import SYSTEM_PROMPT, INSTRUCTION, known_terms, validate_pair


def _paired_quotes(text: str, mark: str, left: str, right: str) -> str:
    """Convert balanced ASCII quote marks while leaving apostrophes alone."""
    if text.count(mark) == 0 or text.count(mark) % 2:
        return text
    out: list[str] = []
    n = 0
    for char in text:
        if char == mark:
            out.append(left if n % 2 == 0 else right)
            n += 1
        else:
            out.append(char)
    return "".join(out)


def normalize_typography(text: str) -> str:
    """Apply presentation-only cleanup; never substitute Chinese words."""
    text = text.translate(str.maketrans({",": "，", ";": "；", ":": "：", "?": "？", "!": "！"}))
    text = _paired_quotes(text, '"', "“", "”")
    # Single quotes in these chapters are paired labels inside dialogue.  Do
    # not convert an unpaired apostrophe, which could be part of a Latin id.
    text = _paired_quotes(text, "'", "‘", "’")
    return text


def candidate_output(source: str) -> str:
    # All lexical/structural edits belong in the reviewed override table.
    # Keeping the automatic candidate limited to typography prevents a broad
    # synonym rule from silently changing tone, aspect, or spatial wording.
    return normalize_typography(source).strip()


def load_overrides(path: Path | None) -> dict[int, str]:
    if path is None or not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"override file must be an object: {path}")
    result: dict[int, str] = {}
    for key, value in payload.items():
        index = int(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"invalid override at {key}")
        result[index] = value.strip()
    return result


def rewrite_file(source_path: Path, override_path: Path | None, dry_run: bool = False) -> dict[str, Any]:
    original = json.loads(source_path.read_text(encoding="utf-8"))
    if not isinstance(original, list):
        raise ValueError("dataset root must be an array")
    overrides = load_overrides(override_path)
    terms = known_terms(source_path.parents[2] / "books")
    rewritten: list[dict[str, str]] = []
    counts = {"total": len(original), "changed": 0, "typography_or_safe": 0, "overrides": 0, "fallback": 0}
    failures: list[dict[str, Any]] = []

    for index, record in enumerate(original):
        if not isinstance(record, dict):
            raise ValueError(f"record {index} is not an object")
        if list(record) != ["system", "instruction", "input", "output"]:
            raise ValueError(f"record {index} has unexpected fields/order")
        if record["system"] != SYSTEM_PROMPT or record["instruction"] != INSTRUCTION:
            raise ValueError(f"record {index} has changed prompt constants")
        source = record["input"]
        if not isinstance(source, str):
            raise ValueError(f"record {index} input is not a string")
        output = overrides.get(index, candidate_output(source))
        if index in overrides:
            counts["overrides"] += 1
        validation = validate_pair(source, output, terms)
        if not validation["ok"]:
            failures.append({"index": index, "problems": validation["problems"]})
            output = normalize_typography(source)
            # Typography-only fallback must itself pass the fact checks.
            fallback_validation = validate_pair(source, output, terms)
            if not fallback_validation["ok"]:
                output = source
                counts["fallback"] += 1
        if output != source:
            counts["changed"] += 1
            if index not in overrides:
                counts["typography_or_safe"] += 1
        rewritten.append(
            {
                "system": record["system"],
                "instruction": record["instruction"],
                "input": source,
                "output": output,
            }
        )

    if failures:
        # Overrides that fail validation are never written.  The failure list
        # is useful for fixing the review overlay on the next run.
        print(json.dumps({"validation_failures": failures}, ensure_ascii=False, indent=2))
    if not dry_run:
        encoded = json.dumps(rewritten, ensure_ascii=False, indent=2) + "\n"
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=str(source_path.parent),
            prefix=f".{source_path.name}.", suffix=".tmp", delete=False
        ) as handle:
            handle.write(encoded)
            temp_name = handle.name
        os.replace(temp_name, source_path)
    return counts | {"validation_failures": len(failures)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=Path("datasets/ai_style_editing/trainv2-last.json"))
    parser.add_argument("--overrides", type=Path, default=Path("scripts/trainv2_last_overrides.json"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    override_path = args.overrides if args.overrides.exists() else None
    stats = rewrite_file(args.dataset, override_path, args.dry_run)
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
