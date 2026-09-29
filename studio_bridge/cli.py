from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .dry_run import StudioBridgeDryRun


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Dry-run a Shadow Army Studio build manifest")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--manifest-schema", type=Path, default=Path("schemas/build-manifest.schema.json"))
    parser.add_argument("--allowlist", type=Path, default=Path("registry/bridge_allowlist.json"))
    parser.add_argument("--asset-registry", type=Path, default=Path("registry/asset_registry.json"))
    parser.add_argument("--json", action="store_true", help="Emit JSON report")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        runner = StudioBridgeDryRun.from_files(args.manifest_schema, args.allowlist, args.asset_registry)
        report = runner.run_file(args.manifest)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(f"{report.status}: {report.operation_count} operation(s), {len(report.issues)} issue(s), {len(report.warnings)} warning(s)")
        for action, count in sorted(report.counts.items()):
            print(f"- {action}: {count}")
        for issue in report.issues:
            print(f"- ERROR {issue.code} {issue.path}: {issue.message}")
        for warning in report.warnings:
            print(f"- WARNING {warning.code} {warning.path}: {warning.message}")
        print(f"Release ready: {'yes' if report.release_ready else 'no'}")
    return 0 if report.ok else 1
