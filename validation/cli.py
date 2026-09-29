from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .validator import ArtifactValidator


def _print_report(report, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
        return

    state = "PASS" if report.ok else "FAIL"
    print(f"{state}: {report.artifact_count} artifact(s), {len(report.issues)} issue(s)")
    for issue in report.issues:
        source = f" [{issue.artifact}]" if issue.artifact else ""
        print(f"- {issue.severity} {issue.code}{source} {issue.path}: {issue.message}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate Shadow Army build artifacts")
    parser.add_argument(
        "path",
        type=Path,
        help="Artifact JSON file or a directory containing one JSON artifact per stage",
    )
    parser.add_argument(
        "--schema",
        type=Path,
        default=Path("schemas/pipeline.schema.json"),
        help="Pipeline JSON Schema path",
    )
    parser.add_argument("--json", action="store_true", help="Emit the report as JSON")
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="Allow a directory to omit pipeline stages; cross-reference checks use available stages",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        validator = ArtifactValidator.from_schema_file(args.schema)
        if args.path.is_dir():
            report = validator.validate_directory(args.path, require_complete=not args.allow_partial)
        else:
            report = validator.validate_file(args.path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    _print_report(report, as_json=args.json)
    return 0 if report.ok else 1
